import json

import frappe
from frappe.utils import flt, getdate
import time

from zra_smart_invoice.config import is_zra_enabled
from zra_smart_invoice.client import make_vsdc_request

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
    total_taxable = 0
    total_tax = 0
    total_amt = 0

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

        item_doc = frappe.get_cached_doc("Item", item.item_code)
        
        item_class_code = frappe.db.get_value("Custom Item Details", {"parent": item.item_code}, "hsn_code") or ""
        pkg_unit_name = frappe.db.get_value("Custom Item Details", {"parent": item.item_code}, "packaging_uom")
        qty_unit_name = item.get("stock_uom") or item_doc.stock_uom

        pkg_unit_cd = _resolve_pkg_unit_code(pkg_unit_name)
        qty_unit_cd = _resolve_qty_unit_code(qty_unit_name)

        vat_cat_cd = "A"  
        vat_cat_percentage = 16.0  
        
        if item_doc.taxes:
            tax_template_name = item_doc.taxes[0].item_tax_template
            if tax_template_name:
                tax_template_doc = frappe.get_cached_doc("Item Tax Template", tax_template_name)
                
                if tax_template_doc.title:
                    vat_cat_cd = tax_template_doc.title.split("|")[0].strip()
                
                if tax_template_doc.taxes:
                    vat_cat_percentage = flt(tax_template_doc.taxes[0].tax_rate)

        sply_amt = qty * rate
        
        if vat_cat_percentage > 0:
            taxable_amt = sply_amt / (1 + (vat_cat_percentage / 100.0))
        else:
            taxable_amt = sply_amt
            
        tax_amt = sply_amt - taxable_amt 

        total_taxable += taxable_amt
        total_tax += tax_amt
        total_amt += sply_amt

        item_list.append({
            "itemSeq": idx,
            "itemCd": item.item_code,
            "itemClsCd": item_class_code,
            "itemNm": item.item_name or item.item_code,
            "pkgUnitCd": pkg_unit_cd,
            "qtyUnitCd": qty_unit_cd,
            "qty": round(qty, 2),
            "prc": round(rate, 2),
            "splyAmt": round(sply_amt, 2),
            "totDcAmt": 0.0,
            "pkg": 0.0,
            "taxblAmt": round(taxable_amt, 2),
            "vatCatCd": vat_cat_cd,
            "taxAmt": round(tax_amt, 2),
            "totAmt": round(sply_amt, 2)
        })

    posting_date = getdate(doc.posting_date).strftime("%Y%m%d")

    return {
        "sarNo": int(time.time()),
        "orgSarNo": 0,
        "regTyCd": "M",              
        "sarTyCd": zra_sar_type,     
        "ocrnDt": posting_date,
        "totItemCnt": len(item_list),
        "totTaxblAmt": round(total_taxable, 2),
        "totTaxAmt": round(total_tax, 2),
        "totAmt": round(total_amt, 2),
        "remark": (doc.get("remarks", "") or doc.get("purpose", ""))[:400],
        "regrId": doc.owner or "Admin",
        "regrNm": doc.owner or "Admin",
        "modrNm": doc.modified_by or "Admin",
        "modrId": doc.modified_by or "Admin",
        "itemList": item_list
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