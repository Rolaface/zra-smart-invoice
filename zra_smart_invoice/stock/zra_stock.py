import json

import frappe
from frappe.utils import flt, getdate
import time

from zra_smart_invoice.config import is_zra_enabled, get_zra_config
from zra_smart_invoice.client import make_vsdc_request
from zra_smart_invoice.config.constant import _ALL_TAX_FIELDS, SALES_INVOICE_CATEGORY_FIELD_MAP
from zra_smart_invoice.modules.item.utils import get_map_taxes
from zra_smart_invoice.modules.sales_invoice.utils import cascade_forward

def on_stock_transaction_submit(doc, method):

    if not is_zra_enabled():
        return
    if doc.flags.ignore_zra_sync:
        print("🚀 ~ on_stock_transaction_submit ~ ignore_zra_sync:", doc.flags.ignore_zra_sync)
        return

    try:
        payloads_to_send = []

        if doc.doctype == "Stock Reconciliation":
            pos_payload = _build_stock_items_payload(doc, "06", recon_filter="positive")
            neg_payload = _build_stock_items_payload(doc, "16", recon_filter="negative")
            
            if pos_payload.get("itemList"):
                payloads_to_send.append(pos_payload)
            if neg_payload.get("itemList"):
                payloads_to_send.append(neg_payload)
        else:
            zra_sar_type = _get_zra_sar_type(doc)
            if not zra_sar_type:
                return
            
            se_payload = _build_stock_items_payload(doc, zra_sar_type)
            if se_payload.get("itemList"):
                payloads_to_send.append(se_payload)

        if not payloads_to_send:
            return 
            
        for payload in payloads_to_send:
            print(f"🚀 ~ on_stock_transaction_submit ~ stock_items_payload (Type {payload.get('sarTyCd')}):")
            print(json.dumps(payload, indent=4))
            
            stock_items_result = make_vsdc_request("stock/saveStockItems", payload)

            if stock_items_result.get("resultCd") != "000":
                frappe.throw(
                    f"ZRA Stock Items Error ({stock_items_result.get('resultCd')}): "
                    f"{stock_items_result.get('resultMsg')} — Sync Failed."
                )
            print(f"🚀 ~ ZRA Stock Items Response: {stock_items_result}")

        stock_master_payload = _build_stock_master_payload(doc)
        print("🚀 ~ on_stock_transaction_submit ~ stock_master_payload:")
        print(json.dumps(stock_master_payload, indent=4))

        stock_master_result = make_vsdc_request("stockMaster/saveStockMaster", stock_master_payload)

        if stock_master_result.get("resultCd") != "000":
            frappe.throw(
                f"ZRA Stock Master Error ({stock_master_result.get('resultCd')}): "
                f"{stock_master_result.get('resultMsg')} — Sync Failed."
            )

        print(f"🚀 ~ ZRA Stock Master Response: {stock_master_result}")
        print(f"✅ ZRA Stock Sync Successful | {doc.doctype}: {doc.name}")

        frappe.logger().info(f"✅ ZRA Stock Sync Successful | {doc.doctype}: {doc.name}")
        frappe.msgprint(
            f"✅ ZRA Stock Sync Successful for {doc.name}",
            title="ZRA Smart Invoice",
            indicator="green",
            alert=True
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"ZRA Stock Sync Failed: {doc.name}")
        frappe.throw(f"ZRA connection failed: {str(e)}")


def _get_zra_sar_type(doc):
    if doc.doctype == "Stock Entry":
        mapping = {
            "Material Receipt": "01",
            "Material Issue": "15",      
            "Material Transfer": "13",   
            "Write Off": "06",           
        }
        return mapping.get(doc.stock_entry_type)

    return None
def _build_stock_items_payload(doc, zra_sar_type, recon_filter=None):
    item_list = []
    total_taxable = 0.0
    total_tax = 0.0
    total_amt = 0.0

    for idx, item in enumerate(doc.items, start=1):
        if doc.doctype == "Stock Reconciliation":
            current_qty = flt(item.current_qty)
            new_qty = flt(item.qty)
            qty_change = new_qty - current_qty

            if qty_change == 0:
                continue

            if recon_filter == "positive" and qty_change < 0:
                continue
            if recon_filter == "negative" and qty_change > 0:
                continue

            qty = abs(qty_change)
            rate = flt(item.valuation_rate)
        else:
            qty = flt(item.transfer_qty) if hasattr(item, "transfer_qty") else flt(item.qty)
            rate = flt(item.basic_rate) or flt(item.valuation_rate)

        qty = abs(round(qty, 2))
        rate = abs(round(rate, 2))

        item_doc = frappe.get_cached_doc("Item", item.item_code)

        item_class_code = (
            frappe.db.get_value(
                "Custom Item Details", {"parent": item.item_code}, "hsn_code"
            )
            or "43322555"
        )
        pkg_unit_name = frappe.db.get_value(
            "Custom Item Details", {"parent": item.item_code}, "packaging_uom"
        )
        qty_unit_name = item.get("stock_uom") or item_doc.stock_uom

        pkg_unit_cd = _resolve_pkg_unit_code(pkg_unit_name)
        qty_unit_cd = _resolve_qty_unit_code(qty_unit_name)

        mapped_tax = {}
        item_tax_template_name = item.get("item_tax_template") or (
            item_doc.taxes[0].item_tax_template if item_doc.taxes else None
        )

        if item_tax_template_name:
            tax_template = frappe.get_cached_doc("Item Tax Template", item_tax_template_name)
            mapped_tax = get_map_taxes(tax_template)

        prc, unit_breakdown = cascade_forward(rate, mapped_tax)
        sply_amt = abs(round(prc * qty, 2))

        tax_fields = dict(_ALL_TAX_FIELDS)
        for category, amounts in unit_breakdown.items():
            cfg = SALES_INVOICE_CATEGORY_FIELD_MAP.get(category)
            if cfg:
                code = mapped_tax[category]["tax_code"]
                tax_fields[cfg["cat_field"]] = code
                tax_fields[cfg["taxbl_field"]] = abs(round(amounts["base"] * qty, 4))
                tax_fields[cfg["amt_field"]] = abs(round(amounts["tax"] * qty, 4))

        vatCatCd = tax_fields.get("vatCatCd") or None
        iplCatCd = tax_fields.get("iplCatCd") or None
        tlCatCd = tax_fields.get("tlCatCd") or None
        exciseTxCatCd = tax_fields.get("exciseTxCatCd") or None

        vatAmt = tax_fields.get("vatAmt", 0.0)
        iplAmt = tax_fields.get("iplAmt", 0.0)
        tlAmt = tax_fields.get("tlAmt", 0.0)
        exciseTxAmt = tax_fields.get("exciseTxAmt", 0.0)

        taxblAmt = tax_fields.get("vatTaxblAmt", 0.0)
        taxAmt = round(vatAmt + iplAmt + tlAmt + exciseTxAmt, 2)

        total_taxable += taxblAmt
        total_tax += taxAmt
        total_amt += sply_amt

        item_list.append({
            "itemSeq": idx,
            "itemCd": item.item_code,
            "itemClsCd": item_class_code,
            "itemNm": item.item_name or item.item_code,
            "pkgUnitCd": pkg_unit_cd,
            "pkg": 0.0,
            "qtyUnitCd": qty_unit_cd,
            "qty": qty,
            "prc": rate,
            "splyAmt": sply_amt,
            "totDcAmt": 0.0,
            "taxblAmt": taxblAmt,
            "vatCatCd": vatCatCd,
            "iplCatCd": iplCatCd,
            "tlCatCd": tlCatCd,
            "exciseTxCatCd": exciseTxCatCd,
            "vatAmt": vatAmt,
            "iplAmt": iplAmt,
            "tlAmt": tlAmt,
            "exciseTxAmt": exciseTxAmt,
            "taxAmt": taxAmt,
            "totAmt": sply_amt,
            "bcd": "",
        })

    posting_date = getdate(doc.posting_date).strftime("%Y%m%d")
    config = get_zra_config() or {}

    return {
        "tpin": config.get("tpin"),
        "bhfId": config.get("bhf_id"),
        "sarNo": int(time.time()),
        "orgSarNo": 0,
        "regTyCd": "M",
        "sarTyCd": zra_sar_type,
        "ocrnDt": posting_date,
        "totItemCnt": len(item_list),
        "totTaxblAmt": round(total_taxable, 4),
        "totTaxAmt": round(total_tax, 4),
        "totAmt": round(total_amt, 2),
        "remark": (doc.get("remarks", "") or doc.get("purpose", ""))[:400] or f"Stock movement type {zra_sar_type}",
        "regrId": doc.owner or "Admin",
        "regrNm": doc.owner or "Admin",
        "modrNm": doc.modified_by or "Admin",
        "modrId": doc.modified_by or "Admin",
        "itemList": item_list,
    }

def _build_stock_master_payload(doc):

    stock_item_list = []
    processed_items = set()
    sl_updated = frappe.db.exists(
        "Stock Ledger Entry", 
        {"voucher_no": doc.name, "voucher_type": doc.doctype}
    )

    for item in doc.items:
        if item.item_code in processed_items:
            continue
            
        processed_items.add(item.item_code)

        bin_qtys = frappe.db.get_all(
            "Bin", 
            filters={"item_code": item.item_code}, 
            pluck="actual_qty"
        )
        current_rsd_qty = sum(flt(qty) for qty in bin_qtys) if bin_qtys else 0.0

        if sl_updated:
            final_rsd_qty = current_rsd_qty
        else:
            net_change = 0.0
            
            for row in doc.items:
                if row.item_code != item.item_code:
                    continue
                
                if doc.doctype == "Stock Reconciliation":
                    old_qty = flt(row.current_qty)
                    new_qty = flt(row.qty)
                    net_change += (new_qty - old_qty)
                    
                elif doc.doctype == "Stock Entry":
                    row_qty = flt(row.transfer_qty) if hasattr(row, "transfer_qty") else flt(row.qty)
                    
                    if row.get("s_warehouse"):
                        net_change -= row_qty
                    if row.get("t_warehouse"):
                        net_change += row_qty

            final_rsd_qty = current_rsd_qty + net_change

        stock_item_list.append({
            "itemCd": item.item_code,
            "rsdQty": round(final_rsd_qty, 2)
        })

    return {
        "regrId": doc.owner or "Admin",
        "regrNm": doc.owner or "Admin",
        "modrNm": doc.modified_by or "Admin",
        "modrId": doc.modified_by or "Admin",
        "stockItemList": stock_item_list
    }

def _resolve_qty_unit_code(uom_name):
    """
    Resolves the ERPNext UOM name to the ZRA Quantity Unit Code.
    Fetches the 'common_code' from tabUOM.
    """
    if not uom_name:
        return None
    
    zra_code = frappe.db.get_value("UOM", uom_name, "common_code")
    
    return zra_code if zra_code else None


def _resolve_pkg_unit_code(pkg_uom_name):
    """
    Resolves the ERPNext Packaging UOM to the ZRA Packaging Unit Code.
    Fetches the 'code' from tabPackaging Unit Of Measure.
    """
    if not pkg_uom_name:
        return None
        
    zra_code = frappe.db.get_value("Packaging Unit Of Measure", pkg_uom_name, "code")
    
    return zra_code if zra_code else None