from apps.zra_smart_invoice.zra_smart_invoice.api import _zra_user_id
from apps.zra_smart_invoice.zra_smart_invoice.modules.mtv.utils import get_item_tax_template
import frappe

def build_purchase_sales_items(items):

    po_items = []

    for item in items:
        item_code = item.get("mapped_erp_item")

        if not item_code:
            frappe.throw("item_code is required")

        item_doc = frappe.get_doc("Item", item_code)

        item_tax_template = get_item_tax_template(item.get("vatCatCd"))
        tax_rate = frappe.get_value("Item Tax Template Detail", {"parent": item_tax_template.get("name"), "parenttype": "Item Tax Template"}, "tax_rate")
        price = item.get("prc")/(1+(tax_rate/100))

        item_dict = {
            "item_code": item_code,
            "item_name": item_doc.name,
            "qty": float(item.get("qty", 1)),
            "price_list_rate": price,
            "warehouse": item.get("mapped_erp_warehouse"),
            "item_tax_template": item_tax_template.get("name")
        }

        po_items.append(item_dict)

    return po_items

def create_purchase_sales_response(payload):
    now_dt = frappe.utils.now_datetime()

    if payload.get("transaction_progress") == "Rejected":
        payload["pchsSttsCd"] = "04"
    else:
        payload["pchsSttsCd"] = "02"

    payload["pchsTyCd"] = "N"
    payload["cfmDt"] = now_dt.strftime("%Y%m%d%H%M%S")
    payload["pchsDt"] = now_dt.strftime("%Y%m%d")
    payload["regTyCd"] = "A"
    payload["rcptTyCd"] = "P"
    payload["cisInvcNo"] = payload["spplrInvcNo"]
    payload["regrId"] = _zra_user_id()
    payload["regrNm"] = _zra_user_id()
    payload["modrId"] = _zra_user_id()
    payload["modrNm"] = _zra_user_id()
    payload.pop("transaction_progress")
    for item in payload.get("itemList"):
        item["taxAmt"] = item.get("vatAmt")
    return payload