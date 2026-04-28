import frappe
import requests
from zra_smart_invoice.config import is_zra_enabled, get_zra_config
from zra_smart_invoice.client import make_vsdc_request


# ─────────────────────────────────────────────
# Device
# ─────────────────────────────────────────────

@frappe.whitelist()
def initialize_device():
    """Initialize VSDC — call once per device"""
    config = get_zra_config()
    if not config:
        frappe.throw("ZRA is not configured for this site.")

    payload = {
        "tpin": config["tpin"],
        "bhfId": config["bhf_id"],
        "dvcSrlNo": config["dvc_srl_no"]
    }

    url = f"{config['vsdc_url']}/initializer/selectInitInfo"
    response = requests.post(
        url,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=30
    )
    result = response.json()
    frappe.msgprint(
        f"ZRA Response: {result.get('resultMsg')} (Code: {result.get('resultCd')})"
    )
    return result


# ─────────────────────────────────────────────
# Items
# ─────────────────────────────────────────────

@frappe.whitelist()
def register_item(item_code):
    """Register a single item with ZRA VSDC"""
    if not is_zra_enabled():
        frappe.throw("ZRA is not configured for this site.")

    item = frappe.get_doc("Item", item_code)

    payload = {
        "itemCd": item.item_code,
        "itemClsCd": item.get("custom_zra_item_class_code") or "5020230000",
        "itemTyCd": item.get("custom_zra_item_type_code") or "1",
        "itemNm": item.item_name,
        "itemStdNm": item.item_name,
        "orgnNatCd": "ZM",
        "pkgUnitCd": "NT",
        "qtyUnitCd": "U",
        "taxTyCd": item.get("custom_zra_tax_type") or "B",
        "btchNo": "",
        "bcd": "",
        "useYn": "Y",
        "dftPrc": item.standard_rate or 0,
        "addInfo": "",
        "sftyQty": 0,
        "isrcAplcbYn": "N",
        "regrId": frappe.session.user,
        "regrNm": frappe.session.user,
        "modrId": frappe.session.user,
        "modrNm": frappe.session.user
    }

    result = make_vsdc_request("items/saveItem", payload)
    return result  # ← just return, let caller handle DB/doc update


@frappe.whitelist()
def register_all_items():
    """Register all unregistered items with ZRA"""
    if not is_zra_enabled():
        frappe.throw("ZRA is not configured for this site.")

    items = frappe.get_all(
        "Item",
        filters={"custom_zra_registered": 0, "disabled": 0},
        fields=["name", "item_name"]
    )

    if not items:
        frappe.msgprint("✅ All items already registered with ZRA!")
        return

    success, failed, failed_items = 0, 0, []

    for item in items:
        try:
            result = register_item(item.name)
            if result.get("resultCd") == "000":
                frappe.db.set_value("Item", item.name, {
                    "custom_zra_registered": 1,
                    "custom_zra_item_cd": item.name
                })
                frappe.db.commit()
                success += 1
            else:
                failed += 1
                failed_items.append(item.item_name)
        except Exception as e:
            failed += 1
            failed_items.append(item.item_name)
            frappe.log_error(str(e), f"ZRA Item Reg Failed: {item.name}")

    msg = f"✅ Registered: {success} items"
    if failed:
        msg += f"<br>❌ Failed: {failed}: {', '.join(failed_items)}"
    frappe.msgprint(msg)


# ─────────────────────────────────────────────
# Sales Invoice
# ─────────────────────────────────────────────

@frappe.whitelist()
def submit_sales_invoice(invoice_name):
    """Submit Sales Invoice to ZRA VSDC"""
    if not is_zra_enabled():
        return {"skipped": True, "reason": "ZRA not configured"}

    invoice = frappe.get_doc("Sales Invoice", invoice_name)

    items = []
    for item in invoice.items:
        tax_type = frappe.db.get_value("Item", item.item_code, "custom_zra_tax_type") or "A"
        vat_taxable = item.amount if tax_type == "A" else 0.0
        vat_amt = round(item.amount * 0.16, 4) if tax_type == "A" else 0.0

        items.append({
            "itemSeq": item.idx,
            "itemCd": item.item_code,
            "itemClsCd": frappe.db.get_value("Item", item.item_code, "custom_zra_item_class_code") or "43322555",
            "itemNm": item.item_name,
            "bcd": "",
            "pkgUnitCd": frappe.db.get_value("Item", item.item_code, "custom_zra_pkg_unit_code") or "BX",
            "pkg": 1,
            "qtyUnitCd": frappe.db.get_value("Item", item.item_code, "custom_zra_qty_unit_code") or "EA",
            "qty": item.qty,
            "prc": item.rate,
            "splyAmt": item.amount,
            "dcRt": 0.0,
            "dcAmt": 0.0,
            "isrccCd": "",
            "isrccNm": "",
            "isrcAmt": 0.0,
            "vatCatCd": tax_type,
            "exciseTxCatCd": None,
            "tlCatCd": None,
            "iplCatCd": None,
            "vatTaxblAmt": vat_taxable,
            "vatAmt": vat_amt,
            "exciseTaxblAmt": 0.0,
            "tlTaxblAmt": 0.0,
            "iplTaxblAmt": 0.0,
            "iplAmt": 0.0,
            "tlAmt": 0.0,
            "exciseTxAmt": 0.0,
            "totAmt": item.amount
        })

    now_dt = frappe.utils.now_datetime()
    tax_amt_a = invoice.total_taxes_and_charges or 0.0

    payload = {
        "orgInvcNo": 0,
        "cisInvcNo": invoice.name,
        "custTpin": invoice.get("custom_customer_tpin") or "",
        "custNm": invoice.customer_name,
        "salesTyCd": "N",
        "rcptTyCd": "S",
        "pmtTyCd": invoice.get("custom_zra_payment_type") or "01",
        "salesSttsCd": "02",
        "cfmDt": now_dt.strftime("%Y%m%d%H%M%S"),
        "salesDt": invoice.posting_date.strftime("%Y%m%d"),
        "stockRlsDt": None,
        "cnclReqDt": None,
        "cnclDt": None,
        "rfdDt": None,
        "rfdRsnCd": None,
        "totItemCnt": len(items),
        "taxblAmtA": invoice.net_total,
        "taxblAmtB": 0.0, "taxblAmtC1": 0.0, "taxblAmtC2": 0.0,
        "taxblAmtC3": 0.0, "taxblAmtD": 0.0, "taxblAmtRvat": 0.0,
        "taxblAmtE": 0.0, "taxblAmtF": 0.0, "taxblAmtIpl1": 0.0,
        "taxblAmtIpl2": 0.0, "taxblAmtTl": 0.0, "taxblAmtEcm": 0.0,
        "taxblAmtExeeg": 0.0, "taxblAmtTot": 0.0,
        "taxRtA": 16, "taxRtB": 16, "taxRtC1": 0, "taxRtC2": 0,
        "taxRtC3": 0, "taxRtD": 0, "taxRtRvat": 16, "taxRtE": 0,
        "taxRtF": 10, "taxRtIpl1": 5, "taxRtIpl2": 0,
        "taxRtTl": 1.5, "taxRtEcm": 5, "taxRtExeeg": 3, "taxRtTot": 0,
        "taxAmtA": tax_amt_a,
        "taxAmtB": 0.0, "taxAmtC1": 0.0, "taxAmtC2": 0.0,
        "taxAmtC3": 0.0, "taxAmtD": 0.0, "taxAmtRvat": 0.0,
        "taxAmtE": 0.0, "taxAmtF": 0.0, "taxAmtIpl1": 0.0,
        "taxAmtIpl2": 0.0, "taxAmtTl": 0.0, "taxAmtEcm": 0.0,
        "taxAmtExeeg": 0.0, "taxAmtTot": 0.0,
        "totTaxblAmt": invoice.net_total,
        "totTaxAmt": tax_amt_a,
        "totAmt": invoice.grand_total,
        "cashDcRt": 0.0,
        "cashDcAmt": 0.0,
        "prchrAcptcYn": "N",
        "remark": "",
        "regrId": frappe.session.user,
        "regrNm": frappe.session.user,
        "modrId": frappe.session.user,
        "modrNm": frappe.session.user,
        "saleCtyCd": "1",
        "lpoNumber": None,
        "currencyTyCd": "ZMW",
        "exchangeRt": 1,
        "destnCountryCd": "",
        "dbtRsnCd": "",
        "invcAdjustReason": "",
        "itemList": items
    }

    return make_vsdc_request("trnsSales/saveSales", payload)  # ← just return



def on_item_save(doc, method):
    """
    before_insert hook:
    1. Send to ZRA first using doc object directly
    2. ZRA 000 → ERPNext saves ✅
    3. ZRA fails → frappe.throw() → ERPNext does NOT save ❌
    """
    if not is_zra_enabled():
        return

    try:

        def get_field(field, default):
            val = doc.get(field)
            return val if val else default
        # ── Build payload from doc directly (not from DB) ──
        payload = {
            "itemCd": doc.item_name.replace(" ", ""),
            "itemClsCd": get_field("custom_zra_item_class_code", "43322555"),
            "itemTyCd": str(get_field("custom_zra_item_type_code", "2")),
            "itemNm": doc.item_name,
            "itemStdNm": doc.item_name,
            "orgnNatCd": "ZM",
            "pkgUnitCd": get_field("custom_zra_pkg_unit_code", "BX"),
            "qtyUnitCd": get_field("custom_zra_qty_unit_code", "EA"),
            "vatCatCd": get_field("custom_zra_tax_type", "B"),
            "iplCatCd": get_field("custom_zra_ipl_cat_cd", "IPL1"),  # ← ADD
            "tlCatCd": None,                                          # ← ADD
            "exciseTxCatCd": None,                                    # ← ADD
            "btchNo": None,
            "bcd": None,
            "dftPrc": doc.standard_rate or 0,
            "addInfo": None,
            "sftyQty": 0,
            "isrcAplcbYn": "N",
            "svcChargeYn": get_field("custom_zra_svc_charge", "N"),  # ← ADD
            "rentalYn": "N",                                          # ← ADD
            "useYn": "Y",
            "regrId": frappe.session.user,
            "regrNm": frappe.session.user,
            "modrId": frappe.session.user,
            "modrNm": frappe.session.user
        }

        frappe.log_error(str(payload), "ZRA DEBUG PAYLOAD")  # ← log full payload for debugging

        result = make_vsdc_request("items/saveItem", payload)
        print(f"ZRA RESULT: {result}", flush=True)
        if result.get("resultCd") == "000":
            # ✅ ZRA saved — set on doc, ERPNext will save with these values
            doc.custom_zra_registered = 1
            doc.custom_zra_item_cd = doc.item_code
            frappe.logger().info(f"✅ ZRA saved item: {doc.item_code}")
        else:
            # ❌ Block ERPNext from saving
            frappe.throw(
                f"ZRA Error ({result.get('resultCd')}): {result.get('resultMsg')} — Item NOT saved."
            )

    except frappe.ValidationError:
        raise

    except Exception as e:
        frappe.log_error(str(e), f"ZRA Item Sync Failed: {doc.item_code}")
        frappe.throw(f"ZRA connection failed: {str(e)} — Item NOT saved.")



# def on_sales_invoice_save(doc, method):
#     """
#     before_insert hook:
#     1. Send to ZRA first using doc object directly
#     2. ZRA 000 → set fields on doc → ERPNext creates ✅
#     3. ZRA fails → frappe.throw() → ERPNext does NOT create ❌
#     """
#     if not is_zra_enabled():
#         return

#     try:
#         items = []
#         for item in doc.items:
#             tax_type = frappe.db.get_value("Item", item.item_code, "custom_zra_tax_type") or "A"
#             vat_taxable = item.amount if tax_type == "A" else 0.0
#             vat_amt = round(item.amount * 0.16, 4) if tax_type == "A" else 0.0

#             items.append({
#                 "itemSeq": item.idx,
#                 "itemCd": item.item_code,
#                 "itemClsCd": frappe.db.get_value("Item", item.item_code, "custom_zra_item_class_code") or "43322555",
#                 "itemNm": item.item_name,
#                 "bcd": "",
#                 "pkgUnitCd": frappe.db.get_value("Item", item.item_code, "custom_zra_pkg_unit_code") or "BX",
#                 "pkg": 1,
#                 "qtyUnitCd": frappe.db.get_value("Item", item.item_code, "custom_zra_qty_unit_code") or "EA",
#                 "qty": item.qty,
#                 "prc": item.rate,
#                 "splyAmt": item.amount,
#                 "dcRt": 0.0,
#                 "dcAmt": 0.0,
#                 "isrccCd": "",
#                 "isrccNm": "",
#                 "isrcAmt": 0.0,
#                 "vatCatCd": tax_type,
#                 "exciseTxCatCd": None,
#                 "tlCatCd": None,
#                 "iplCatCd": None,
#                 "vatTaxblAmt": vat_taxable,
#                 "vatAmt": vat_amt,
#                 "exciseTaxblAmt": 0.0,
#                 "tlTaxblAmt": 0.0,
#                 "iplTaxblAmt": 0.0,
#                 "iplAmt": 0.0,
#                 "tlAmt": 0.0,
#                 "exciseTxAmt": 0.0,
#                 "totAmt": item.amount
#             })

#         now_dt = frappe.utils.now_datetime()
#         tax_amt_a = doc.total_taxes_and_charges or 0.0

#         payload = {
#             "orgInvcNo": 0,
#             "cisInvcNo": doc.name or frappe.generate_hash(length=10),
#             "custTpin": doc.get("custom_customer_tpin") or "",
#             "custNm": doc.customer_name,
#             "salesTyCd": "N",
#             "rcptTyCd": "S",
#             "pmtTyCd": doc.get("custom_zra_payment_type") or "01",
#             "salesSttsCd": "02",
#             "cfmDt": now_dt.strftime("%Y%m%d%H%M%S"),
#             "salesDt": doc.posting_date.strftime("%Y%m%d"),
#             "stockRlsDt": None,
#             "cnclReqDt": None,
#             "cnclDt": None,
#             "rfdDt": None,
#             "rfdRsnCd": None,
#             "totItemCnt": len(items),
#             "taxblAmtA": doc.net_total,
#             "taxblAmtB": 0.0, "taxblAmtC1": 0.0, "taxblAmtC2": 0.0,
#             "taxblAmtC3": 0.0, "taxblAmtD": 0.0, "taxblAmtRvat": 0.0,
#             "taxblAmtE": 0.0, "taxblAmtF": 0.0, "taxblAmtIpl1": 0.0,
#             "taxblAmtIpl2": 0.0, "taxblAmtTl": 0.0, "taxblAmtEcm": 0.0,
#             "taxblAmtExeeg": 0.0, "taxblAmtTot": 0.0,
#             "taxRtA": 16, "taxRtB": 16, "taxRtC1": 0, "taxRtC2": 0,
#             "taxRtC3": 0, "taxRtD": 0, "taxRtRvat": 16, "taxRtE": 0,
#             "taxRtF": 10, "taxRtIpl1": 5, "taxRtIpl2": 0,
#             "taxRtTl": 1.5, "taxRtEcm": 5, "taxRtExeeg": 3, "taxRtTot": 0,
#             "taxAmtA": tax_amt_a,
#             "taxAmtB": 0.0, "taxAmtC1": 0.0, "taxAmtC2": 0.0,
#             "taxAmtC3": 0.0, "taxAmtD": 0.0, "taxAmtRvat": 0.0,
#             "taxAmtE": 0.0, "taxAmtF": 0.0, "taxAmtIpl1": 0.0,
#             "taxAmtIpl2": 0.0, "taxAmtTl": 0.0, "taxAmtEcm": 0.0,
#             "taxAmtExeeg": 0.0, "taxAmtTot": 0.0,
#             "totTaxblAmt": doc.net_total,
#             "totTaxAmt": tax_amt_a,
#             "totAmt": doc.grand_total,
#             "cashDcRt": 0.0,
#             "cashDcAmt": 0.0,
#             "prchrAcptcYn": "N",
#             "remark": "",
#             "regrId": frappe.session.user,
#             "regrNm": frappe.session.user,
#             "modrId": frappe.session.user,
#             "modrNm": frappe.session.user,
#             "saleCtyCd": "1",
#             "lpoNumber": None,
#             "currencyTyCd": "ZMW",
#             "exchangeRt": 1,
#             "destnCountryCd": "",
#             "dbtRsnCd": "",
#             "invcAdjustReason": "",
#             "itemList": items
#         }

#         frappe.log_error(str(payload), "ZRA SI DEBUG PAYLOAD")

#         result = make_vsdc_request("trnsSales/saveSales", payload)

#         frappe.log_error(str(result), "ZRA SI DEBUG RESULT")

#         if result.get("resultCd") == "000":
#             # ✅ ZRA saved — set on doc before ERPNext creates
#             zra_data = result.get("data") or {}
#             doc.custom_zra_submitted = 1
#             doc.custom_zra_result_code = result.get("resultCd")
#             doc.custom_zra_result_msg = result.get("resultMsg")
#             doc.custom_zra_rcpt_no = zra_data.get("rcptNo")
#             doc.custom_zra_intrl_data = zra_data.get("intrlData")
#             doc.custom_zra_rcpt_sign = zra_data.get("rcptSign")
#             doc.custom_zra_sdc_id = zra_data.get("sdcId")
#             doc.custom_zra_mrc_no = zra_data.get("mrcNo")
#             frappe.logger().info(f"✅ ZRA Invoice saved | RcptNo: {zra_data.get('rcptNo')}")
#         else:
#             frappe.throw(
#                 f"ZRA Error ({result.get('resultCd')}): {result.get('resultMsg')} — Invoice NOT created."
#             )

#     except frappe.ValidationError:
#         raise

#     except Exception as e:
#         frappe.log_error(str(e), f"ZRA Invoice Save Failed: {doc.name}")
#         frappe.throw(f"ZRA connection failed: {str(e)} — Invoice NOT created.")

def on_sales_invoice_save(doc, method):
    if not is_zra_enabled():
        return

    try:
        items = []
        for item in doc.items:
            items.append({
                "itemSeq": item.idx,
                "itemCd": item.item_code,
                "itemClsCd": "43322555",           # ← default ZRA class
                "itemNm": item.item_name,
                "bcd": "",
                "pkgUnitCd": "BX",
                "pkg": 1,
                "qtyUnitCd": "EA",
                "qty": item.qty,
                "prc": item.rate,
                "splyAmt": item.amount,
                "dcRt": 0.0,
                "dcAmt": 0.0,
                "isrccCd": "",
                "isrccNm": "",
                "isrcAmt": 0.0,
                "vatCatCd": "A",                   # ← default VAT category
                "exciseTxCatCd": None,
                "tlCatCd": None,
                "iplCatCd": None,
                "vatTaxblAmt": item.amount,
                "vatAmt": round(item.amount * 0.16, 4),
                "exciseTaxblAmt": 0.0,
                "tlTaxblAmt": 0.0,
                "iplTaxblAmt": 0.0,
                "iplAmt": 0.0,
                "tlAmt": 0.0,
                "exciseTxAmt": 0.0,
                "totAmt": item.amount
            })

        now_dt = frappe.utils.now_datetime()
        tax_amt = doc.total_taxes_and_charges or 0.0

        net_total = doc.net_total or 0.0
        grand_total = doc.grand_total or 0.0
        tax_amt = doc.total_taxes_and_charges or 0.0

        payload = {
            "orgInvcNo": 0,
            "cisInvcNo": doc.name or frappe.generate_hash(length=10),
            "custTpin": "",
            "custNm": doc.customer_name,
            "salesTyCd": "N",
            "rcptTyCd": "S",
            "pmtTyCd": "01",                       # ← Cash payment
            "salesSttsCd": "02",
            "cfmDt": now_dt.strftime("%Y%m%d%H%M%S"),
            "salesDt": doc.posting_date.strftime("%Y%m%d"),
            "stockRlsDt": None,
            "cnclReqDt": None,
            "cnclDt": None,
            "rfdDt": None,
            "rfdRsnCd": None,
            "totItemCnt": len(items),
            "taxblAmtA": net_total,
            "taxblAmtB": 0.0, "taxblAmtC1": 0.0, "taxblAmtC2": 0.0,
            "taxblAmtC3": 0.0, "taxblAmtD": 0.0, "taxblAmtRvat": 0.0,
            "taxblAmtE": 0.0, "taxblAmtF": 0.0, "taxblAmtIpl1": 0.0,
            "taxblAmtIpl2": 0.0, "taxblAmtTl": 0.0, "taxblAmtEcm": 0.0,
            "taxblAmtExeeg": 0.0, "taxblAmtTot": 0.0,
            "taxRtA": 16, "taxRtB": 16, "taxRtC1": 0, "taxRtC2": 0,
            "taxRtC3": 0, "taxRtD": 0, "taxRtRvat": 16, "taxRtE": 0,
            "taxRtF": 10, "taxRtIpl1": 5, "taxRtIpl2": 0,
            "taxRtTl": 1.5, "taxRtEcm": 5, "taxRtExeeg": 3, "taxRtTot": 0,
            "taxAmtA": tax_amt,
            "taxAmtB": 0.0, "taxAmtC1": 0.0, "taxAmtC2": 0.0,
            "taxAmtC3": 0.0, "taxAmtD": 0.0, "taxAmtRvat": 0.0,
            "taxAmtE": 0.0, "taxAmtF": 0.0, "taxAmtIpl1": 0.0,
            "taxAmtIpl2": 0.0, "taxAmtTl": 0.0, "taxAmtEcm": 0.0,
            "taxAmtExeeg": 0.0, "taxAmtTot": 0.0,
            "totTaxblAmt": net_total,
            "totTaxAmt": tax_amt,
            "totAmt": grand_total,
            "cashDcRt": 0.0,
            "cashDcAmt": 0.0,
            "prchrAcptcYn": "N",
            "remark": "",
            "regrId": frappe.session.user,
            "regrNm": frappe.session.user,
            "modrId": frappe.session.user,
            "modrNm": frappe.session.user,
            "saleCtyCd": "1",
            "lpoNumber": None,
            "currencyTyCd": "ZMW",
            "exchangeRt": 1,
            "destnCountryCd": "",
            "dbtRsnCd": "",
            "invcAdjustReason": "",
            "itemList": items
        }

        frappe.log_error(str(payload), "ZRA SI DEBUG PAYLOAD")
        result = make_vsdc_request("trnsSales/saveSales", payload)
        frappe.log_error(str(result), "ZRA SI DEBUG RESULT")

        if result.get("resultCd") == "000":
            zra_data = result.get("data") or {}
            doc.custom_zra_submitted = 1
            doc.custom_zra_result_code = result.get("resultCd")
            doc.custom_zra_result_msg = result.get("resultMsg")
            doc.custom_zra_rcpt_no = zra_data.get("rcptNo")
            doc.custom_zra_intrl_data = zra_data.get("intrlData")
            doc.custom_zra_rcpt_sign = zra_data.get("rcptSign")
            doc.custom_zra_sdc_id = zra_data.get("sdcId")
            doc.custom_zra_mrc_no = zra_data.get("mrcNo")
        else:
            frappe.throw(
                f"ZRA Error ({result.get('resultCd')}): {result.get('resultMsg')} — Invoice NOT created."
            )

    except frappe.ValidationError:
        raise

    except Exception as e:
        frappe.log_error(str(e), f"ZRA Invoice Save Failed: {doc.name}")
        frappe.throw(f"ZRA connection failed: {str(e)} — Invoice NOT created.")


def on_sales_invoice_cancel(doc, method):
    """Auto-triggered on Sales Invoice cancel"""
    if not is_zra_enabled():
        return
    try:
        payload = {
            "orgInvcNo": doc.name,
            "cnclReqDt": frappe.utils.now_datetime().strftime("%Y%m%d%H%M%S"),
            "cnclDt": frappe.utils.now_datetime().strftime("%Y%m%d%H%M%S"),
            "rfdRsnCd": "01",
            "remark": "Invoice Cancelled"
        }
        result = make_vsdc_request("trnsSales/saveCreditNote", payload)
        if result.get("resultCd") == "000":
            frappe.msgprint("✅ ZRA cancellation submitted!")
        else:
            frappe.msgprint(
                f"⚠️ ZRA cancellation failed: {result.get('resultMsg')}",
                indicator="orange"
            )
    except Exception as e:
        frappe.log_error(str(e), f"ZRA Cancel Failed: {doc.name}")