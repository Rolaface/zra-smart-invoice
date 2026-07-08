from zra_smart_invoice.config.constant import PAYMENT_TYPE_CODE_MAP
import frappe
import requests
from zra_smart_invoice.config import is_zra_enabled, get_zra_config
from zra_smart_invoice.client import make_vsdc_request
import json


# ═══════════════════════════════════════════════════════════════════
#  PHASE 1 — Testing with pure defaults (no custom fields required)
#
#  [STANDARD]  = ERPNext built-in field
#  [DEFAULT]   = hardcoded safe default
#  TODO        = will be replaced by custom field in Phase 2
# ═══════════════════════════════════════════════════════════════════


# ───────────────────────────────────────────────────────────────────
# HELPER — safely set a field on doc (skip if column not yet created)
# ───────────────────────────────────────────────────────────────────

ITEM_TYPE_CODE_MAP = {
    "Raw Material":     "1",
    "Finished Product": "2",
    "Service":          "3",
}

ITEM_TYPE_CODE_DEFAULT = "2"

def get_item_type_code(item_group: str) -> str:
   
    return ITEM_TYPE_CODE_MAP.get(item_group, ITEM_TYPE_CODE_DEFAULT)

def _safe_set(doc, field, value):
    """
    Set a field only if the DB column exists.
    Prevents crashes when custom fields are not yet created in ERPNext.
    """
    try:
        if frappe.db.has_column(doc.doctype, field):
            doc.set(field, value)
    except Exception:
        pass

def _zra_user_id(max_len=20):
    user = frappe.session.user or "Administrator"
    if "@" in user:
        user = user.split("@")[0]
    return user[:max_len]
# ───────────────────────────────────────────────────────────────────
# HELPER — Item payload
# ───────────────────────────────────────────────────────────────────

def _build_item_payload(doc):
    
    if len(doc.taxes) > 1:
        frappe.throw(f"Multiple tax templates not supported for Item {doc.name}, ZRA requires only one tax template per item.")

    tax_template = frappe.get_doc("Item Tax Template", doc.taxes[0].item_tax_template) if doc.taxes else None
    if tax_template and len(tax_template.taxes) > 1:
        frappe.throw(f"Multiple taxes in tax template not supported for Item {doc.name}, ZRA requires only one tax per item.")

    tax_template_title = tax_template.title.split("|")[0] if tax_template else None
    if not tax_template_title:
        frappe.throw("Please select a valid Tax Template for the item.")
    if doc.country_of_origin:
        orgn_nat_cd = frappe.get_value("Country", doc.country_of_origin, "code").upper()
    else:
        orgn_nat_cd = frappe.get_value("Country", frappe.defaults.get_user_default("country"), "code").upper()
    return {
        # ── Identity ──────────────────────────────────────────────
        "itemCd":        doc.item_code,           # [STANDARD]
        "itemNm":        doc.item_name,           # [STANDARD]
        "itemStdNm":     doc.item_name,           # [STANDARD]

        # ── Classification ────────────────────────────────────────
        "itemClsCd":     doc.custom_item_metadata[0].hsn_code,
        "itemTyCd":      get_item_type_code(doc.item_group),
        "vatCatCd":      tax_template_title.strip() if tax_template_title else None,
        "iplCatCd":      None,                    # [DEFAULT] TODO: custom_zra_ipl_cat_cd
        "tlCatCd":       None,                    # [DEFAULT]
        "exciseTxCatCd": None,                    # [DEFAULT]

        # ── Units ─────────────────────────────────────────────────
        "pkgUnitCd":     frappe.get_value("Packaging Unit Of Measure", doc.custom_item_metadata[0].packaging_uom, "code"),
        "qtyUnitCd":     frappe.get_value("UOM", doc.stock_uom, "common_code"),

        # ── Pricing ───────────────────────────────────────────────
        "dftPrc":        doc.standard_rate or 0,  # [STANDARD]

        # ── Origin & flags ────────────────────────────────────────
        "orgnNatCd":     orgn_nat_cd,
        "btchNo":        None,
        "bcd":           None,
        "addInfo":       None,
        "sftyQty":       0,
        "isrcAplcbYn":   "Y" if doc.custom_item_metadata[0].insurance else "N",
        "svcChargeYn":   "Y" if doc.custom_item_metadata[0].service_charge else "N",
        "rentalYn":      "N",
        "useYn":         "Y",

        # ── Audit ─────────────────────────────────────────────────
        # "regrId":        frappe.session.user,     # [STANDARD]
        # "regrNm":        frappe.session.user,
        # "modrId":        frappe.session.user,
        # "modrNm":        frappe.session.user,
        "regrId": _zra_user_id(),
        "regrNm": _zra_user_id(),
        "modrId": _zra_user_id(),
        "modrNm": _zra_user_id(),
    }


def _get_rcpt_type_cd(doc):
    if doc.is_return:
        return "R"
    if hasattr(doc, "is_debit_note") and doc.is_debit_note:
        return "D"
    return "S"


def _get_vat_cat_cd(doc):
    """Tax category detect karo"""
    if doc.tax_category == "Export":
        return "C1"
    if doc.tax_category == "Exempt":
        return "D"
    return "A"  # Default — Standard VAT


def _is_export(doc):
    return doc.tax_category == "Export"

# def _build_invoice_payload(doc):

#     items = []

#     for item in doc.items:
#         tax_type = "A"  # VAT 16%

#         qty = round(float(item.qty or 0), 4)

#         prc_raw = float(item.rate or 0)
#         prc = round(prc_raw, 2)

#         tot_amt = round(prc * qty, 2)

#         # VAT-inclusive logic (correct)
#         vat_taxable = round(tot_amt / 1.16, 2)
#         vat_amt     = round(tot_amt - vat_taxable, 2)

#         items.append({
#             "itemSeq": item.idx,
#             "itemCd": item.item_code,
#             "itemNm": item.item_name,
#             "itemClsCd": "43322555",
#             "bcd": "",

#             "pkgUnitCd": "BX",
#             "pkg": 1,
#             "qtyUnitCd": "EA",

#             "qty": qty,
#             "prc": prc,

#             "splyAmt": tot_amt,
#             "dcRt": 0.0,
#             "dcAmt": 0.0,
#             "totAmt": tot_amt,

#             "vatCatCd": tax_type,
#             "vatTaxblAmt": vat_taxable,
#             "vatAmt": vat_amt,

#             "exciseTxCatCd": None,
#             "tlCatCd": None,
#             "iplCatCd": None,

#             "exciseTaxblAmt": 0.0,
#             "tlTaxblAmt": 0.0,
#             "iplTaxblAmt": 0.0,
#             "iplAmt": 0.0,
#             "tlAmt": 0.0,
#             "exciseTxAmt": 0.0,

#             "isrccCd": "",
#             "isrccNm": "",
#             "isrcAmt": 0.0,
#         })

#     net_total   = round(sum(i["vatTaxblAmt"] for i in items), 2)
#     tax_amt     = round(sum(i["vatAmt"] for i in items), 2)
#     grand_total = round(sum(i["totAmt"] for i in items), 2)

#     # ZRA strict validation
#     if round(net_total + tax_amt, 2) != grand_total:
#         raise ValueError(
#             f"ZRA Mismatch → taxable({net_total}) + tax({tax_amt}) != total({grand_total})"
#         )

#     now_dt = frappe.utils.now_datetime()

#     payload = {
#         "orgInvcNo": 0,
#         "cisInvcNo": doc.name,
#         "custTpin": "2000000011",
#         "custNm": doc.customer_name,

#         "salesTyCd": "N",
#         "rcptTyCd": "S",
#         "pmtTyCd": "01",
#         "salesSttsCd": "02",

#         "cfmDt": now_dt.strftime("%Y%m%d%H%M%S"),
#         "salesDt": frappe.utils.getdate(doc.posting_date).strftime("%Y%m%d"),

#         "totItemCnt": len(items),

#         # ✅ Taxable + Tax
#         "taxblAmtA": net_total,
#         "taxAmtA": tax_amt,

#         "totTaxblAmt": net_total,
#         "totTaxAmt": tax_amt,
#         "totAmt": grand_total,

#         # ✅ REQUIRED TAX RATE BLOCK (THIS WAS MISSING ❗)
#         "taxRtA": 16,
#         "taxRtB": 16,
#         "taxRtC1": 0,
#         "taxRtC2": 0,
#         "taxRtC3": 0,
#         "taxRtD": 0,
#         "taxRtRvat": 16,
#         "taxRtE": 0,
#         "taxRtF": 10,
#         "taxRtIpl1": 5,
#         "taxRtIpl2": 0,
#         "taxRtTl": 1.5,
#         "taxRtEcm": 5,
#         "taxRtExeeg": 3,
#         "taxRtTot": 0,

#         "currencyTyCd": "ZMW",
#         "exchangeRt": 1,

#         "regrId": _zra_user_id(),
#         "regrNm": _zra_user_id(),
#         "modrId": _zra_user_id(),
#         "modrNm": _zra_user_id(),

#         "itemList": items,
#     }

#     return payload

def _build_invoice_payload(doc):
    """
        Frappe invoice, the tax is configured as tax-exclusive (added on top),
        but ZRA expects tax-inclusive
    """

    # ✅ Auto Detect
    is_export = (doc.tax_category == "Export")
    is_return = doc.is_return
    is_debit  = getattr(doc, "is_debit_note", False)

    vat_cat   = "C1" if is_export else ("D" if doc.tax_category == "Exempt" else "A")
    rcpt_type = "R"  if is_return else ("D" if is_debit else "S")

    items = []

    for item in doc.items:
        qty     = abs(round(float(item.qty or 0), 4))
        item_doc = frappe.get_doc("Item", item.item_code)
        tax_rate = frappe.get_value("Item Tax Template Detail", {"parent": item.item_tax_template, "parenttype": "Item Tax Template"}, "tax_rate")
        vat_cat_cd = item.item_tax_template.split("|")[0] if item.item_tax_template else None
        net_amt   = abs(round(float(item.net_amount or 0), 2))
        vat_amt   = abs(round(net_amt * tax_rate / 100, 4))
        tot_amt   = abs(round(net_amt + vat_amt, 2))
        prc     = abs(round(tot_amt / qty, 2))
        items.append({
            "itemSeq": item.idx,
            "itemCd": item.item_code,
            "itemClsCd": item_doc.custom_item_metadata[0].hsn_code,
            "itemNm": item.item_name,
            "bcd": "",
            "pkgUnitCd": frappe.get_value("Packaging Unit Of Measure", item_doc.custom_item_metadata[0].packaging_uom, "code"),
            "pkg": item_doc.custom_item_metadata[0].packing_unit,
            "qtyUnitCd": frappe.get_value("UOM", item_doc.stock_uom, "common_code"),
            "qty": qty,
            "prc": prc,
            "splyAmt": tot_amt,
            "dcRt": item.discount_percentage,
            "dcAmt": item.discount_amount,
            "isrccCd": "",
            "isrccNm": "",
            "isrcAmt": 0.0,
            "vatCatCd": vat_cat_cd.strip(),
            "exciseTxCatCd": None,
            "vatTaxblAmt": net_amt,
            "exciseTaxblAmt": 0.0,
            "tlTaxblAmt": 0.0,
            "iplTaxblAmt": 0.0,
            "iplAmt": 0.0,
            "tlAmt": 0.0,
            "vatAmt": vat_amt,
            "exciseTxAmt": 0.0,
            "totAmt": tot_amt
        })

    net_total   = round(sum(i["vatTaxblAmt"] for i in items), 2)
    tax_amt     = round(sum(i["vatAmt"]      for i in items), 2)
    grand_total = round(sum(i["totAmt"]      for i in items), 2)

    # ZRA strict validation
    if round(net_total + tax_amt, 2) != grand_total:
        raise ValueError(
            f"ZRA Mismatch → taxable({net_total}) + tax({tax_amt}) != total({grand_total})"
        )

    now_dt = frappe.utils.now_datetime()
    if not doc.custom_details or not doc.custom_details[0].payment_mode:
        frappe.throw("Please select a payment mode for the Sales Invoice.")
    customer_country = frappe.get_value("Address", f"{doc.customer}-Shipping", "country")
    customer_country_code = frappe.get_value("Country", customer_country, "code").upper() if customer_country else ""
    reason = None
    if doc.is_return == 1:
        try:
            remarks_data = json.loads(doc.remarks)
            reason = remarks_data.get("code", "03")
        except Exception:
            reason = "03"
    if doc.is_return == 1:
        sales_invoice_doc = frappe.get_doc("Sales Invoice", doc.return_against)
        zra_response = json.loads(sales_invoice_doc.custom_details[0].zra_response) if sales_invoice_doc.custom_details and sales_invoice_doc.custom_details[0].zra_response else {}
    payload = {
        # ✅ Auto detect
        "tpin":          get_zra_config()["tpin"],
        "bhfId":         get_zra_config()["bhf_id"],
        "orgInvcNo":     zra_response.get("rcptNo") if doc.is_return == 1 and zra_response else 0,
        "cisInvcNo":      doc.name,
        "orgSdcId":       zra_response.get("sdcId") if doc.is_return == 1 and zra_response else None,
        "custTpin":       frappe.get_value("Customer", doc.customer, "tax_id") or "",
        "custNm":         doc.customer_name,

        "salesTyCd":      "N",
        "rcptTyCd":       rcpt_type,          # ✅ Auto S/R/D
        "pmtTyCd":         PAYMENT_TYPE_CODE_MAP.get(
                                                        doc.custom_details[0].payment_mode
                                                    ) if doc.custom_details else None,
        "salesSttsCd":    "02",

        "cfmDt":          now_dt.strftime("%Y%m%d%H%M%S"),
        "salesDt":        frappe.utils.getdate(doc.posting_date).strftime("%Y%m%d"),
        "stockRlsDt":     None,
        "cnclReqDt":      None,
        "cnclDt":         None,
        "rfdDt":          None,
        "rfdRsnCd":       reason,

        "totItemCnt":     len(items),

        "dbtRsnCd":       "03" if is_debit else "",   # ✅ Auto
        "invcAdjustReason": "",
        "cashDcRt":       0,
        "cashDcAmt":      0,


        # ✅ Auto — Export C1, Normal A
        "taxblAmtA":      net_total,
        "taxblAmtB":      0,
        "taxblAmtC1":     doc.net_total if is_export else 0,
        "taxblAmtC2":     0, "taxblAmtC3":    0,
        "taxblAmtD":      0, "taxblAmtRvat":  0,
        "taxblAmtE":      0, "taxblAmtF":     0,
        "taxblAmtIpl1":   0, "taxblAmtIpl2":  0,
        "taxblAmtTl":     0, "taxblAmtEcm":   0,
        "taxblAmtExeeg":  0, "taxblAmtTot":   0,

        "taxRtA": 16, "taxRtB": 16, "taxRtC1": 0, "taxRtC2": 0,
        "taxRtC3": 0, "taxRtD": 0, "taxRtRvat": 16, "taxRtE": 0,
        "taxRtF": 10, "taxRtIpl1": 5, "taxRtIpl2": 0,
        "taxRtTl": 1.5, "taxRtEcm": 5, "taxRtExeeg": 3, "taxRtTot": 0,

        # ✅ Auto — Export 0 tax, Normal tax_amt
        "taxAmtA":        tax_amt,
        "taxAmtB":        0, "taxAmtC1":     0, "taxAmtC2":    0,
        "taxAmtC3":       0, "taxAmtD":      0, "taxAmtRvat":  0,
        "taxAmtE":        0, "taxAmtF":      0, "taxAmtIpl1":  0,
        "taxAmtIpl2":     0, "taxAmtTl":     0, "taxAmtEcm":   0,
        "taxAmtExeeg":    0, "taxAmtTot":    0,

        "totTaxblAmt":    abs(net_total),
        "totTaxAmt":      tax_amt,
        "totAmt":         grand_total,

        "prchrAcptcYn":   "N",
        "remark":         "",

        "currencyTyCd":   "ZMW",
        "exchangeRt":     1,

        "destnCountryCd":  customer_country_code if is_export else "",
        "lpoNumber":       None,          # ✅ Auto

        "saleCtyCd":      "1",

        "regrId": _zra_user_id(),
        "regrNm": _zra_user_id(),
        "modrId": _zra_user_id(),
        "modrNm": _zra_user_id(),

        "itemList": items,
    }

    return payload

# ═══════════════════════════════════════════════════════════════════
# Device
# ═══════════════════════════════════════════════════════════════════

@frappe.whitelist()
def initialize_device():
    """Initialize VSDC — call once per device"""
    config = get_zra_config()
    if not config:
        frappe.throw("ZRA is not configured for this site.")

    payload = {
        "tpin":     config["tpin"],
        "bhfId":    config["bhf_id"],
        "dvcSrlNo": config["dvc_srl_no"],
    }
    url      = f"{config['vsdc_url']}/initializer/selectInitInfo"
    response = requests.post(url, json=payload,
                             headers={"Content-Type": "application/json"}, timeout=30)
    result   = response.json()
    frappe.msgprint(
        f"ZRA Response: {result.get('resultMsg')} (Code: {result.get('resultCd')})"
    )
    return result


# ═══════════════════════════════════════════════════════════════════
# Items — manual endpoints
# ═══════════════════════════════════════════════════════════════════

@frappe.whitelist()
def register_item(item_code):
    """Manually register a single Item with ZRA"""
    if not is_zra_enabled():
        frappe.throw("ZRA is not configured for this site.")
    doc = frappe.get_doc("Item", item_code)
    return make_vsdc_request("items/saveItem", _build_item_payload(doc))


@frappe.whitelist()
def register_all_items():
    """Manually register all active Items with ZRA (Phase 1 — no custom field filter)"""
    if not is_zra_enabled():
        frappe.throw("ZRA is not configured for this site.")

    # TODO Phase 2: add filter {"custom_zra_registered": 0} once field is created
    items = frappe.get_all("Item", filters={"disabled": 0}, fields=["name", "item_name"])

    if not items:
        frappe.msgprint("No active items found.")
        return

    success, failed, failed_items = 0, 0, []
    for item in items:
        try:
            result = register_item(item.name)
            if result.get("resultCd") == "000":
                success += 1
                # TODO Phase 2: frappe.db.set_value("Item", item.name, "custom_zra_registered", 1)
            else:
                failed += 1
                failed_items.append(f"{item.item_name} [{result.get('resultCd')}]")
        except Exception as e:
            failed += 1
            failed_items.append(item.item_name)
            frappe.log_error(str(e), f"ZRA Bulk Reg Failed: {item.name}")

    msg = f"✅ ZRA Synced: {success} items"
    if failed:
        msg += f"<br>❌ Failed: {failed} — {', '.join(failed_items)}"
    frappe.msgprint(msg)


# ═══════════════════════════════════════════════════════════════════
# Sales Invoice — manual endpoint
# ═══════════════════════════════════════════════════════════════════

@frappe.whitelist()
def submit_sales_invoice(invoice_name):
    """Manually re-submit a Sales Invoice to ZRA"""
    if not is_zra_enabled():
        return {"skipped": True, "reason": "ZRA not configured"}
    doc = frappe.get_doc("Sales Invoice", invoice_name)
    return make_vsdc_request("trnsSales/saveSales", _build_invoice_payload(doc))



# def on_item_save(doc, method):
#     """
#     Hook: after_insert + on_update on Item

#     Flow:
#     1. after_insert → ZRA ko bhejo
#     2. ZRA 000  → ERPNext item rehta hai ✅
#        ZRA fail → ERPNext item DELETE (rollback) → frappe.throw() ❌
#     """
#     if not is_zra_enabled():
#         return

#     try:
#         payload = _build_item_payload(doc)
#         frappe.log_error(str(payload), f"ZRA Item Payload | {doc.item_code}")

#         result = make_vsdc_request("items/saveItem", payload)
#         frappe.log_error(str(result), f"ZRA Item Result | {doc.item_code}")

#         if result.get("resultCd") == "000":
#             _safe_set(doc, "custom_zra_registered", 1)
#             _safe_set(doc, "custom_zra_item_cd", doc.item_code)
#             frappe.logger().info(f"✅ ZRA Item synced: {doc.item_code}")

#         else:
#             # ── ZRA fail → rollback only on fresh insert ──
#             if method == "after_insert":
#                 frappe.delete_doc(
#                     "Item", doc.name,
#                     force=True,
#                     ignore_permissions=True
#                 )
#                 frappe.db.commit()
#             frappe.throw(
#                 f"ZRA Error ({result.get('resultCd')}): {result.get('resultMsg')}"
#                 " — Item NOT saved."
#             )

#     except frappe.ValidationError:
#         raise
#     except Exception as e:
#         # ── Connection fail → bhi rollback on fresh insert ──
#         if method == "after_insert":
#             try:
#                 frappe.delete_doc(
#                     "Item", doc.name,
#                     force=True,
#                     ignore_permissions=True
#                 )
#                 frappe.db.commit()
#             except Exception as del_err:
#                 frappe.log_error(str(del_err), f"ZRA Rollback Failed: {doc.item_code}")

#         frappe.log_error(str(e), f"ZRA Item Sync Failed: {doc.item_code}")
#         frappe.throw(f"ZRA connection failed: {str(e)} — Item NOT saved.")


def on_item_save(doc, method):
    """
    Hook: after_insert + on_update on Item

    Flow:
    1. after_insert → saveItem endpoint
    2. on_update    → updateItem endpoint
    3. ZRA 000  → ERPNext item rehta hai ✅
       ZRA fail → ERPNext item DELETE (rollback on insert) → frappe.throw() ❌
    """
    if not is_zra_enabled():
        return

    try:
        payload = _build_item_payload(doc)

        # ✅ Method ke hisaab se alag endpoint
        if method == "after_insert":
            endpoint = "items/saveItem"
        else:
            endpoint = "items/updateItem"

        result = make_vsdc_request(endpoint, payload)

        if result.get("resultCd") == "000":
            _safe_set(doc, "custom_zra_registered", 1)
            _safe_set(doc, "custom_zra_item_cd", doc.item_code)
            print(f"✅ ZRA Item synced via {endpoint}: {doc.item_code}")

        else:
            # ── ZRA fail → rollback only on fresh insert ──
            if method == "after_insert":
                frappe.delete_doc(
                    "Item", doc.name,
                    force=True,
                    ignore_permissions=True
                )
                frappe.db.commit()
            frappe.throw(
                f"ZRA Error ({result.get('resultCd')}): {result.get('resultMsg')}"
                " — Item NOT saved."
            )

    except frappe.ValidationError:
        raise
    except Exception as e:
        # ── Connection fail → rollback on fresh insert ──
        if method == "after_insert":
            try:
                frappe.delete_doc(
                    "Item", doc.name,
                    force=True,
                    ignore_permissions=True
                )
                frappe.db.commit()
            except Exception as del_err:
                frappe.log_error(
                    title=f"ZRA Rollback Failed: {doc.item_code}",
                    message=str(del_err)
                )

        frappe.log_error(
            title=f"ZRA Item Sync Failed: {doc.item_code}",
            message=frappe.get_traceback()
        )
        frappe.throw(f"ZRA connection failed: {str(e)} — Item NOT saved.")


def on_sales_invoice_submit(doc, method):

    if not is_zra_enabled():
        return

    try:
        payload = _build_invoice_payload(doc)
        print(payload)
        # ✅ SAFETY CHECK
        if not payload:
            frappe.throw("ZRA Payload generation failed")

        frappe.log_error(str(payload), f"ZRA Invoice Payload | {doc.name}")
        print(doc.custom_details[0].barcode_data)
        result = make_vsdc_request("trnsSales/saveSales", payload)

        # ✅ SAFETY CHECK
        if not result or not isinstance(result, dict):
            frappe.throw(f"Invalid ZRA response: {result}")

        frappe.log_error(str(result), f"ZRA Invoice Result | {doc.name}")

        if result.get("resultCd") == "000":
            zra_data = result.get("data") or {}

            _safe_set(doc, "custom_zra_submitted", 1)
            _safe_set(doc, "custom_zra_result_code", result.get("resultCd"))
            _safe_set(doc, "custom_zra_result_msg", result.get("resultMsg"))
            _safe_set(doc, "custom_zra_rcpt_no", zra_data.get("rcptNo"))
            print(zra_data)
            frappe.logger().info(
                f"✅ ZRA Invoice submitted | RcptNo: {zra_data.get('rcptNo')} | {doc.name}"
            )
            doc.custom_details[0].barcode_data = zra_data.get("qrCodeUrl", "")
            doc.custom_details[0].zra_response = zra_data
        else:
            frappe.throw(
                f"ZRA Error ({result.get('resultCd')}): {result.get('resultMsg')}"
            )

    except Exception as e:
        frappe.log_error(str(e), f"ZRA Invoice Submit Failed: {doc.name}")
        frappe.throw(f"ZRA connection failed: {str(e)}")


def on_sales_invoice_cancel(doc, method):
    """
    Hook: on_cancel on Sales Invoice
    Does NOT block ERPNext cancel — only warns if ZRA fails.
    """
    if not is_zra_enabled():
        return
    try:
        now_str = frappe.utils.now_datetime().strftime("%Y%m%d%H%M%S")
        payload = {
            "orgInvcNo": doc.name,
            "cnclReqDt": now_str,
            "cnclDt":    now_str,
            "rfdRsnCd":  "01",
            "remark":    "Invoice Cancelled",
        }
        result = make_vsdc_request("trnsSales/saveCreditNote", payload)
        if result.get("resultCd") == "000":
            frappe.msgprint("✅ ZRA cancellation submitted successfully.")
        else:
            frappe.msgprint(
                f"⚠️ ZRA cancellation warning: {result.get('resultMsg')}",
                indicator="orange",
            )
    except Exception as e:
        frappe.log_error(str(e), f"ZRA Cancel Failed: {doc.name}")
        frappe.msgprint(
            f"⚠️ ZRA cancel failed (ERPNext cancel still processed): {str(e)}",
            indicator="orange",
        )


# ═══════════════════════════════════════════════════════════════════
# DEBUG — Remove after testing
# ═══════════════════════════════════════════════════════════════════

@frappe.whitelist()
def debug_invoice_payload(invoice_name):
    """
    Returns the exact payload that would be sent to ZRA — WITHOUT sending it.
    Use this to inspect amounts and find what ZRA is rejecting.

    Call from browser console:
      frappe.call('zra_smart_invoice.api.debug_invoice_payload',
                  {invoice_name: 'ACC-SINV-2025-00001'}).then(r => console.log(r.message))

    Or via URL:
      /api/method/zra_smart_invoice.api.debug_invoice_payload?invoice_name=ACC-SINV-2025-00001
    """
    doc     = frappe.get_doc("Sales Invoice", invoice_name)
    payload = _build_invoice_payload(doc)

    # Show a readable per-item breakdown
    lines = ["<b>Per-item breakdown:</b><br>"]
    for item in payload["itemList"]:
        lines.append(
            f"<b>{item['itemNm']}</b>: "
            f"qty={item['qty']} × prc={item['prc']} = "
            f"splyAmt={item['splyAmt']} | "
            f"vatAmt={item['vatAmt']} | "
            f"totAmt={item['totAmt']}<br>"
        )

    lines.append("<br><b>Invoice totals:</b><br>")
    lines.append(f"taxblAmtA  = {payload['taxblAmtA']}<br>")
    lines.append(f"taxAmtA    = {payload['taxAmtA']}<br>")
    lines.append(f"totTaxblAmt= {payload['totTaxblAmt']}<br>")
    lines.append(f"totTaxAmt  = {payload['totTaxAmt']}<br>")
    lines.append(f"totAmt     = {payload['totAmt']}<br>")

    # Verify ZRA cross-checks locally
    lines.append("<br><b>ZRA cross-check (local verification):</b><br>")
    sum_sply = round(sum(i["splyAmt"] for i in payload["itemList"]), 2)
    sum_vat  = round(sum(i["vatAmt"]  for i in payload["itemList"]), 2)
    sum_tot  = round(sum(i["totAmt"]  for i in payload["itemList"]), 2)

    lines.append(f"sum(splyAmt)={sum_sply} == taxblAmtA={payload['taxblAmtA']} → {'✅' if sum_sply == payload['taxblAmtA'] else '❌'}<br>")
    lines.append(f"sum(vatAmt) ={sum_vat}  == taxAmtA  ={payload['taxAmtA']}   → {'✅' if sum_vat  == payload['taxAmtA']   else '❌'}<br>")
    lines.append(f"sum(totAmt) ={sum_tot}  == totAmt   ={payload['totAmt']}    → {'✅' if sum_tot  == payload['totAmt']    else '❌'}<br>")
    lines.append(f"taxblAmtA+taxAmtA={round(payload['taxblAmtA']+payload['taxAmtA'],2)} == totAmt={payload['totAmt']} → {'✅' if round(payload['taxblAmtA']+payload['taxAmtA'],2) == payload['totAmt'] else '❌'}<br>")

    frappe.msgprint("".join(lines), title="ZRA Payload Debug", wide=True)
    return payload


# ───────────────────────────────────────────────────────────────────
# HELPER — Purchase Invoice payload
# ───────────────────────────────────────────────────────────────────

def _build_purchase_payload(doc):
    items = []

    for item in doc.items:
        qty         = round(float(item.qty  or 0), 4)
        prc         = round(float(item.rate or 0), 2)
        tot_amt     = round(prc * qty,             2)   # VAT inclusive
        vat_taxable = round(tot_amt / 1.16,        2)   # ex-VAT
        vat_amt     = round(tot_amt - vat_taxable, 2)   # VAT amount

        items.append({
            "itemSeq":         item.idx,
            "itemCd":          item.item_code,
            "itemNm":          item.item_name,
            "itemClsCd":       "43322555",        # TODO: custom_zra_item_class_code
            "bcd":             None,

            "spplrItemClsCd":  None,
            "spplrItemCd":     None,
            "spplrItemNm":     None,

            "pkgUnitCd":       "BX",              # TODO: custom_zra_pkg_unit_code
            "pkg":             1,
            "qtyUnitCd":       "EA",              # TODO: custom_zra_qty_unit_code

            "qty":             qty,
            "prc":             prc,               # VAT inclusive
            "splyAmt":         tot_amt,
            "dcRt":            0.0,
            "dcAmt":           0.0,

            "vatCatCd":        "A",
            "taxblAmt":        vat_taxable,       # ex-VAT
            "taxAmt":          vat_amt,           # VAT amount

            "iplCatCd":        None,
            "tlCatCd":         None,
            "exciseCatCd":     None,
            "iplTaxblAmt":     0.0,
            "tlTaxblAmt":      0.0,
            "exciseTaxblAmt":  0.0,
            "iplAmt":          0.0,
            "tlAmt":           0.0,
            "exciseTxAmt":     0.0,

            "totAmt":          tot_amt,
        })

    net_total   = round(sum(i["taxblAmt"] for i in items), 2)
    tax_amt     = round(sum(i["taxAmt"]   for i in items), 2)
    grand_total = round(sum(i["totAmt"]   for i in items), 2)
    now_dt      = frappe.utils.now_datetime()

    return {
        "cisInvcNo":    doc.name,
        "orgInvcNo":    0,

        # Supplier info
        "spplrTpin":    "2000000011",             # TODO: custom_supplier_tpin
        "spplrBhfId":   "000",                    # TODO: custom_supplier_bhf_id
        "spplrNm":      doc.supplier_name,
        "spplrInvcNo":  doc.bill_no or "",        # Supplier ka invoice number

        "regTyCd":      "M",
        "pchsTyCd":     "N",
        "rcptTyCd":     "P",
        "pmtTyCd":      "01",                     # TODO: custom_zra_payment_type
        "pchsSttsCd":   "02",

        "cfmDt":        now_dt.strftime("%Y%m%d%H%M%S"),
        "pchsDt":       frappe.utils.getdate(doc.posting_date).strftime("%Y%m%d"),
        "cnclReqDt":    "",
        "cnclDt":       "",

        "totItemCnt":   len(items),
        "totTaxblAmt":  net_total,
        "totTaxAmt":    tax_amt,
        "totAmt":       grand_total,

        "remark":       "",
        "regrId":       _zra_user_id(),
        "regrNm":       _zra_user_id(),
        "modrId":       _zra_user_id(),
        "modrNm":       _zra_user_id(),

        "itemList":     items,
    }


# ───────────────────────────────────────────────────────────────────
# HELPER — Stock Items payload (after Purchase approved)
# ───────────────────────────────────────────────────────────────────

def _build_stock_items_payload(doc):
    """
    Stock Entry se ZRA saveStockItems payload banao.
    ERPNext Stock Entry items se stock movement ZRA ko bhejo.
    """
    items = []

    for item in doc.items:
        qty = round(float(item.qty or 0), 4)
        prc = round(float(item.basic_rate or item.valuation_rate or 0), 2)

        items.append({
            "itemSeq":    item.idx,
            "itemCd":     item.item_code,
            "itemNm":     item.item_name,
            "itemClsCd":  "43322555",             # TODO: custom_zra_item_class_code
            "bcd":        None,
            "pkgUnitCd":  "BX",
            "pkg":        1,
            "qtyUnitCd":  "EA",
            "qty":        qty,
            "prc":        prc,
            "splyAmt":    round(prc * qty, 2),
            "totAmt":     round(prc * qty, 2),
            "vatCatCd":   "A",
            "taxblAmt":   round((prc * qty) / 1.16, 2),
            "taxAmt":     round((prc * qty) - ((prc * qty) / 1.16), 2),
            "dcRt":       0.0,
            "dcAmt":      0.0,
        })

    now_dt = frappe.utils.now_datetime()

    return {
        "cisInvcNo":  doc.name,
        "stockTyCd":  "P",                        # P = Purchase
        "pchsDt":     frappe.utils.getdate(doc.posting_date).strftime("%Y%m%d"),
        "totItemCnt": len(items),
        "totAmt":     round(sum(i["totAmt"] for i in items), 2),
        "regrId":     _zra_user_id(),
        "regrNm":     _zra_user_id(),
        "modrId":     _zra_user_id(),
        "modrNm":     _zra_user_id(),
        "itemList":   items,
    }


def _build_stock_master_payload(doc):
    """
    Stock Entry se ZRA saveStockMaster payload banao.
    Current stock quantities ZRA ko bhejo.
    """
    items = []

    for item in doc.items:
        # ERPNext se current stock quantity lo
        current_stock = frappe.db.get_value(
            "Bin",
            {"item_code": item.item_code, "warehouse": item.t_warehouse or item.s_warehouse},
            "actual_qty"
        ) or 0

        items.append({
            "itemCd":     item.item_code,
            "itemNm":     item.item_name,
            "itemClsCd":  "43322555",
            "pkgUnitCd":  "BX",
            "qtyUnitCd":  "EA",
            "qty":        round(float(current_stock), 4),
            "prc":        round(float(item.basic_rate or 0), 2),
            "splyAmt":    round(float(current_stock) * float(item.basic_rate or 0), 2),
        })

    now_dt = frappe.utils.now_datetime()

    return {
        "cisInvcNo":  doc.name,
        "stockTyCd":  "P",
        "pchsDt":     frappe.utils.getdate(doc.posting_date).strftime("%Y%m%d"),
        "totItemCnt": len(items),
        "regrId":     _zra_user_id(),
        "regrNm":     _zra_user_id(),
        "modrId":     _zra_user_id(),
        "modrNm":     _zra_user_id(),
        "itemList":   items,
    }


# ═══════════════════════════════════════════════════════════════════
# Purchase Invoice Hooks
# ═══════════════════════════════════════════════════════════════════

def on_purchase_invoice_submit(doc, method):
    """
    Hook: before_submit on Purchase Invoice
    ZRA 000  → ERPNext submits ✅
    ZRA fail → frappe.throw() → ERPNext does NOT submit ❌
    """
    if not is_zra_enabled():
        return
    try:
        payload = _build_purchase_payload(doc)
        result  = make_vsdc_request("trnsPurchase/savePurchase", payload)

        # Log har baar
        # 
        # _log_zra_transaction("Purchase Invoice", doc.name, "submit", payload, result)

        if result.get("resultCd") == "000":
            _safe_set(doc, "custom_zra_submitted",   1)
            _safe_set(doc, "custom_zra_result_code", result.get("resultCd"))
            _safe_set(doc, "custom_zra_result_msg",  result.get("resultMsg"))
            frappe.logger().info(f"✅ ZRA Purchase submitted | {doc.name}")
        else:
            frappe.throw(
                f"ZRA Error ({result.get('resultCd')}): {result.get('resultMsg')}"
                " — Purchase NOT submitted."
            )
    except frappe.ValidationError:
        raise
    except Exception as e:
        frappe.log_error(str(e), f"ZRA Purchase Submit Failed: {doc.name}")
        frappe.throw(f"ZRA connection failed: {str(e)} — Purchase NOT submitted.")


def on_purchase_invoice_cancel(doc, method):
    """
    Hook: on_cancel on Purchase Invoice
    Does NOT block ERPNext cancel — only warns if ZRA fails.
    """
    if not is_zra_enabled():
        return
    try:
        now_str = frappe.utils.now_datetime().strftime("%Y%m%d%H%M%S")
        payload = {
            "cisInvcNo":  doc.name,
            "cnclReqDt":  now_str,
            "cnclDt":     now_str,
            "rfdRsnCd":   "01",
            "remark":     "Purchase Invoice Cancelled",
        }
        result = make_vsdc_request("trnsPurchase/savePurchase", payload)
        # _log_zra_transaction("Purchase Invoice", doc.name, "cancel", payload, result)

        if result.get("resultCd") == "000":
            frappe.msgprint("✅ ZRA purchase cancellation submitted.")
        else:
            frappe.msgprint(
                f"⚠️ ZRA cancellation warning: {result.get('resultMsg')}",
                indicator="orange",
            )
    except Exception as e:
        frappe.log_error(str(e), f"ZRA Purchase Cancel Failed: {doc.name}")
        frappe.msgprint(
            f"⚠️ ZRA cancel failed (ERPNext cancel still processed): {str(e)}",
            indicator="orange",
        )


# ═══════════════════════════════════════════════════════════════════
# Stock Entry Hook
# ═══════════════════════════════════════════════════════════════════

def on_stock_entry_submit(doc, method):
    """
    Hook: before_submit on Stock Entry
    Only fires for Purchase Receipt type entries.
    1. saveStockItems  → purchased items ZRA mein add karo
    2. saveStockMaster → current stock quantities update karo
    """
    if not is_zra_enabled():
        return

    # Sirf Purchase Receipt type ke liye chalao
    if doc.stock_entry_type not in ("Material Receipt", "Purchase Receipt"):
        return

    try:
        # ── Step 1: saveStockItems ──────────────────────────────
        stock_items_payload = _build_stock_items_payload(doc)
        stock_items_result  = make_vsdc_request("stock/saveStockItems", stock_items_payload)
        # _log_zra_transaction("Stock Entry", doc.name, "stock_items", stock_items_payload, stock_items_result)

        if stock_items_result.get("resultCd") != "000":
            frappe.throw(
                f"ZRA Stock Items Error ({stock_items_result.get('resultCd')}): "
                f"{stock_items_result.get('resultMsg')} — Stock Entry NOT submitted."
            )

        # ── Step 2: saveStockMaster ─────────────────────────────
        stock_master_payload = _build_stock_master_payload(doc)
        stock_master_result  = make_vsdc_request("stockMaster/saveStockMaster", stock_master_payload)
        # _log_zra_transaction("Stock Entry", doc.name, "stock_master", stock_master_payload, stock_master_result)

        if stock_master_result.get("resultCd") != "000":
            frappe.throw(
                f"ZRA Stock Master Error ({stock_master_result.get('resultCd')}): "
                f"{stock_master_result.get('resultMsg')} — Stock Entry NOT submitted."
            )

        frappe.logger().info(f"✅ ZRA Stock updated | {doc.name}")

    except frappe.ValidationError:
        raise
    except Exception as e:
        frappe.log_error(str(e), f"ZRA Stock Entry Failed: {doc.name}")
        frappe.throw(f"ZRA connection failed: {str(e)} — Stock Entry NOT submitted.")



def on_stock_entry_submit(doc, method):
    try:
        # Step 1 — saveStockItems
        stock_payload = _build_stock_items_payload(doc)
        result1 = make_vsdc_request("stock/saveStockItems", stock_payload)

        if result1.get("resultCd") != "000":
            frappe.throw(f"ZRA Stock Items Failed: {result1.get('resultMsg')}")

        # Step 2 — saveStockMaster (saveStockItems ke baad call karo)
        master_payload = _build_stock_master_payload(doc)
        result2 = make_vsdc_request("stockMaster/saveStockMaster", master_payload)

        if result2.get("resultCd") != "000":
            frappe.throw(f"ZRA Stock Master Failed: {result2.get('resultMsg')}")

        frappe.log_error(
            title=f"ZRA Stock Success | {doc.name}",
            message=f"saveStockItems: {result1} | saveStockMaster: {result2}"
        )

    except Exception as e:
        frappe.log_error(
            title=f"ZRA Stock Submit Error | {doc.name}",
            message=frappe.get_traceback()
        )
        frappe.throw(f"ZRA Stock sync failed: {str(e)}")


def _build_stock_items_payload(doc):
    company = frappe.defaults.get_user_default("Company")
    
    item_list = []
    total_taxable = 0
    total_tax = 0
    total_amt = 0

    for idx, item in enumerate(doc.items, start=1):
        # Item details fetch karo
        item_doc = frappe.get_doc("Item", item.item_code)
        pkg_unit = "BX"  # Default package unit
        uom = "U"       # Default quantity units
        
        
        item_class_code = frappe.db.get_value(
            "Custom Item Details",
            {"parent": item.item_code},
            "hsn_code"
        ) or ""

        # pkg_unit = frappe.db.get_value(
        #     "Custom Item Details",
        #     {"parent": item.item_code},
        #     "packing_unit"
        # ) or "BA"

        # ZRA Valid Code Mappings
        UOM_MAP = {
            "Nos": "U",
            "Acre": "U",        # Default U
            "Kg": "KG",
            "Ltr": "LT",
            "Meter": "MT",
            "Box": "BX",
            "Bag": "BA",
            "Each": "EA",
        }

        PKG_UNIT_MAP = {
            "Box": "BX",
            "Bag": "BA",
            "Bottle": "BT",
            "Each": "EA",
            "": "BX",           # Default BX
        }

        qty = item.qty or 0
        rate = item.basic_rate or item.valuation_rate or 0
        sply_amt = qty * rate
        taxable_amt = round(sply_amt / 1.16, 4)  # VAT 16% assume
        tax_amt = round(sply_amt - taxable_amt, 4)

        total_taxable += taxable_amt
        total_tax += tax_amt
        total_amt += sply_amt

        exp_date = ""
        if item.batch_no:
            exp = frappe.db.get_value("Batch", item.batch_no, "expiry_date")
            exp_date = str(exp).replace("-", "") if exp else ""

        item_list.append({
            "itemSeq": idx,
            "itemCd": item.item_code,
            "itemClsCd": item_class_code,
            "itemNm": item.item_name,
            "pkgUnitCd": PKG_UNIT_MAP.get(pkg_unit, "BX"),
            "qtyUnitCd": UOM_MAP.get(uom, "U"),
            "qty": qty,
            "prc": rate,
            "splyAmt": round(sply_amt, 2),
            "taxblAmt": round(taxable_amt, 4),
            "vatCatCd": "A",
            "taxAmt": round(tax_amt, 4),
            "totAmt": round(sply_amt, 2),
            "totDcAmt": 0,
            "iplCatCd": "IPL1",    # ✅ Valid ZRA code
            "tlCatCd": "TL",      # ✅ Valid ZRA code
            "exciseTxCatCd": "EXEEG",
            "iplAmt": 0,
            "tlAmt": 0,
            "exciseTxAmt": 0,
            "itemExprDt": exp_date,
            "pkg": item.qty or 0,
            "bcd": ""
        })

    return {
        "sarNo": _get_next_sar_no(),
        "orgSarNo": 0,
        "regTyCd": "M",
        "sarTyCd": _get_sar_type(doc.stock_entry_type),
        "ocrnDt": str(doc.posting_date).replace("-", ""),
        "totItemCnt": len(item_list),
        "totTaxblAmt": round(total_taxable, 4),
        "totTaxAmt": round(total_tax, 4),
        "totAmt": round(total_amt, 4),
        "remark": doc.remarks or "",
        "regrId": doc.owner or "Admin",
        "regrNm": doc.owner or "Admin",
        "modrNm": doc.modified_by or "Admin",
        "modrId": doc.modified_by or "Admin",
        "itemList": item_list
    }


def _build_stock_master_payload(doc):
    stock_item_list = []

    for item in doc.items:
        # Warehouse se current stock dekho
        rsd_qty = frappe.db.get_value(
            "Bin",
            {"item_code": item.item_code, "warehouse": item.t_warehouse or item.s_warehouse},
            "actual_qty"
        ) or 0

        stock_item_list.append({
            "itemCd": item.item_code,
            "rsdQty": rsd_qty
        })

    return {
        "regrId": doc.owner or "Admin",
        "regrNm": doc.owner or "Admin",
        "modrNm": doc.modified_by or "Admin",
        "modrId": doc.modified_by or "Admin",
        "stockItemList": stock_item_list
    }


def _get_next_sar_no():
    # Unique SAR No — timestamp based
    import time
    return int(time.time())


def _get_sar_type(stock_entry_type):
    # Stock Entry Type → ZRA SAR Type Code
    mapping = {
        "Material Receipt": "01",    # Purchase
        "Material Issue": "02",      # Sales
        "Material Transfer": "13",   # Transfer
        "Write Off": "06",           # Loss
    }
    return mapping.get(stock_entry_type, "02")