import json
from typing import Any, Dict, List, Optional, Tuple

import frappe
import requests

from custom_api.config import zra_exception
from zra_smart_invoice.utils import _zra_user_id, _safe_set
from zra_smart_invoice.client import make_vsdc_request
from zra_smart_invoice.config import get_zra_config, is_zra_enabled
from zra_smart_invoice.config.constant import PAYMENT_TYPE_CODE_MAP

def _get_reason_details(doc: Any) -> Tuple[Optional[str], Optional[str]]:
    if not hasattr(doc, "custom_details") or not doc.custom_details:
        return None, None

    raw_reason = getattr(doc.custom_details[0], "reason", None)
    if not raw_reason:
        return None, None

    try:
        details = json.loads(raw_reason) if isinstance(raw_reason, str) else raw_reason

        code = details.get("code")
        reason = details.get("reason")

        return (
            str(code) if code is not None else None,
            str(reason) if reason is not None else None,
        )
    except (json.JSONDecodeError, TypeError, AttributeError):
        return None, None


def _resolve_original_zra_invoice(doc: Any) -> Tuple[int, Optional[str]]:    
    reference_doc_name = getattr(doc, "return_against", None) or getattr(doc, "original_invoice", None)
    
    if not reference_doc_name:
        frappe.throw(
            "Debit Note must reference an original invoice. "
            "Please ensure 'Return Against' or 'Original Invoice' field is populated."
        )

    orig_inv = frappe.get_doc("Sales Invoice", reference_doc_name)
    zra_response_raw = None

    if hasattr(orig_inv, "custom_details") and orig_inv.custom_details:
        zra_response_raw = getattr(orig_inv.custom_details[0], "zra_response", None)

    if not zra_response_raw:
        frappe.throw(
            f"Original Invoice ({reference_doc_name}) has no recorded ZRA response. "
            "Ensure the original invoice is submitted and synced with ZRA first."
        )

    try:
        zra_resp = json.loads(zra_response_raw) if isinstance(zra_response_raw, str) else zra_response_raw
        
        org_rcpt_no = zra_resp.get("rcptNo") or (zra_resp.get("data", {}).get("rcptNo") if isinstance(zra_resp.get("data"), dict) else None)
        org_sdc_id = zra_resp.get("sdcId") or (zra_resp.get("data", {}).get("sdcId") if isinstance(zra_resp.get("data"), dict) else None)

        if not org_rcpt_no:
            frappe.throw(
                f"Original Invoice ({reference_doc_name}) ZRA response is missing a valid 'rcptNo'. "
                f"Data found: {zra_response_raw}"
            )

        return int(org_rcpt_no), org_sdc_id

    except (json.JSONDecodeError, ValueError, TypeError) as err:
        frappe.throw(
            f"Failed to parse ZRA response from Original Invoice ({reference_doc_name}): {str(err)}"
        )


def _build_debit_note_item(item: Any, default_vat_cat: str) -> Dict[str, Any]:
    qty = abs(round(float(item.qty or 0), 4))
    item_doc = frappe.get_doc("Item", item.item_code)
    
    tax_rate = frappe.get_value(
        "Item Tax Template Detail",
        {"parent": item.item_tax_template, "parenttype": "Item Tax Template"},
        "tax_rate"
    )
    if tax_rate is None:
        frappe.throw(f"Tax rate missing for Item {item.item_code} (Template: {item.item_tax_template})")

    vat_cat_cd = item.item_tax_template.split("|")[0].strip() if item.item_tax_template else None

    net_amt = abs(round(float(item.net_amount or 0), 2))
    vat_amt = abs(round(net_amt * (float(tax_rate) / 100.0), 4))
    tot_amt = abs(round(net_amt + vat_amt, 2))
    prc = abs(round(tot_amt / qty, 2)) if qty > 0 else 0.0

    metadata = item_doc.custom_item_metadata[0] if getattr(item_doc, "custom_item_metadata", None) else None
    
    hsn_code = getattr(metadata, "hsn_code", "43322555") if metadata else "43322555"
    packing_unit = getattr(metadata, "packing_unit", 1) if metadata else 1
    
    pkg_uom_code = "BX"
    if metadata and getattr(metadata, "packaging_uom", None):
        pkg_uom_code = frappe.get_value("Packaging Unit Of Measure", metadata.packaging_uom, "code") or "BX"

    qty_uom_code = frappe.get_value("UOM", item_doc.stock_uom, "common_code") or "EA"

    return {
        "itemSeq": item.idx,
        "itemCd": item.item_code,
        "itemClsCd": hsn_code,
        "itemNm": item.item_name,
        "bcd": "",
        "pkgUnitCd": pkg_uom_code,
        "pkg": packing_unit,
        "qtyUnitCd": qty_uom_code,
        "qty": qty,
        "prc": prc,
        "splyAmt": tot_amt,
        "dcRt": float(item.discount_percentage or 0),
        "dcAmt": abs(float(item.discount_amount or 0)),
        "isrccCd": "",
        "isrccNm": "",
        "isrcAmt": 0.0,
        "vatCatCd": vat_cat_cd or default_vat_cat,
        "exciseTxCatCd": "",
        "vatTaxblAmt": net_amt,
        "exciseTaxblAmt": 0.0,
        "tlTaxblAmt": 0.0,
        "iplTaxblAmt": 0.0,
        "iplAmt": 0.0,
        "tlAmt": 0.0,
        "vatAmt": vat_amt,
        "exciseTxAmt": 0.0,
        "totAmt": tot_amt
    }

def _build_sales_debit_note_payload(doc: Any) -> Dict[str, Any]:
    is_export = (doc.tax_category == "Export")
    default_vat_cat = "C1" if is_export else ("D" if doc.tax_category == "Exempt" else "A")

    items = [_build_debit_note_item(item, default_vat_cat) for item in doc.items]
    
    net_total = round(sum(i["vatTaxblAmt"] for i in items), 2)
    tax_amt = round(sum(i["vatAmt"] for i in items), 2)
    grand_total = round(sum(i["totAmt"] for i in items), 2)

    org_rcpt_no, org_sdc_id = _resolve_original_zra_invoice(doc)
    reason_code, reason_desc = _get_reason_details(doc)
    zra_cfg = get_zra_config()
    user_id = _zra_user_id()
    now_dt = frappe.utils.now_datetime()

    dest_country = ""
    if is_export and doc.customer:
        shipping_addr = frappe.get_value("Address", f"{doc.customer}-Shipping", "country")
        if shipping_addr:
            dest_country = (frappe.get_value("Country", shipping_addr, "code") or "").upper()

    pmt_mode = None
    if getattr(doc, "custom_details", None) and doc.custom_details:
        pmt_mode = PAYMENT_TYPE_CODE_MAP.get(doc.custom_details[0].payment_mode)

    return {
        "tpin": zra_cfg["tpin"],
        "bhfId": zra_cfg["bhf_id"],
        "orgInvcNo": org_rcpt_no,
        "cisInvcNo": doc.name,
        "orgSdcId": org_sdc_id,
        "custTpin": frappe.get_value("Customer", doc.customer, "tax_id") or "",
        "custNm": doc.customer_name,
        "salesTyCd": "N",
        "rcptTyCd": "D",
        "pmtTyCd": pmt_mode,
        "salesSttsCd": "02",
        "cfmDt": now_dt.strftime("%Y%m%d%H%M%S"),
        "salesDt": frappe.utils.getdate(doc.posting_date).strftime("%Y%m%d"),
        "totItemCnt": len(items),
        "dbtRsnCd": reason_code,
        "invcAdjustReason": reason_desc,

        "cashDcRt": 0,
        "cashDcAmt": 0,
        "taxblAmtA": net_total,
        "taxblAmtB": 0,
        "taxblAmtC1": doc.net_total if is_export else 0,
        "taxblAmtC2": 0, "taxblAmtC3": 0,
        "taxblAmtD": 0, "taxblAmtRvat": 0,
        "taxblAmtE": 0, "taxblAmtF": 0,
        "taxblAmtIpl1": 0, "taxblAmtIpl2": 0,
        "taxblAmtTl": 0, "taxblAmtEcm": 0,
        "taxblAmtExeeg": 0, "taxblAmtTot": 0,

        "taxRtA": 16, "taxRtB": 16, "taxRtC1": 0, "taxRtC2": 0,
        "taxRtC3": 0, "taxRtD": 0, "taxRtRvat": 16, "taxRtE": 0,
        "taxRtF": 10, "taxRtIpl1": 5, "taxRtIpl2": 0,
        "taxRtTl": 1.5, "taxRtEcm": 5, "taxRtExeeg": 3, "taxRtTot": 0,

        "taxAmtA": tax_amt,
        "taxAmtB": 0, "taxAmtC1": 0, "taxAmtC2": 0,
        "taxAmtC3": 0, "taxAmtD": 0, "taxAmtRvat": 0,
        "taxAmtE": 0, "taxAmtF": 0, "taxAmtIpl1": 0,
        "taxAmtIpl2": 0, "taxAmtTl": 0, "taxAmtEcm": 0,
        "taxAmtExeeg": 0, "taxAmtTot": 0,

        "totTaxblAmt": abs(net_total),
        "totTaxAmt": tax_amt,
        "totAmt": grand_total,
        "remark": reason_desc,
        "currencyTyCd": "ZMW",
        "exchangeRt": 1,
        "destnCountryCd": dest_country,
        "saleCtyCd": "1",
        "regrId": user_id,
        "regrNm": user_id,
        "modrId": user_id,
        "modrNm": user_id,
        "itemList": items,
    }

        # is_debit = getattr(doc, "is_debit_note", False)
        
        # if is_debit:
        #     payload = _build_sales_debit_note_payload(doc)
        # else:
        #     payload = _build_invoice_payload(doc)