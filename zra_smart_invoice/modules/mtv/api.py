from zra_smart_invoice.modules.mtv.utils import get_item_tax_template
from zra_smart_invoice.api import get_item_type_name
from zra_smart_invoice.client import make_vsdc_request
import frappe

@frappe.whitelist(allow_guest = True, methods=["GET"])
def get_rrp_items(mfg_tpin):
    try:
        payload = {"tpin":mfg_tpin,  "lastReqDt":"20231215000000"}
        result = make_vsdc_request("items/selectRrpItems", payload)

        for item in result.get("data").get("itemList"):
            if item.get("itemTyCd"):
                item["itemTyCd"] = get_item_type_name(item.get("itemTyCd"))
            if item.get("orgnNatCd"):
                item["orgnNatCd"] = frappe.get_value("Country", {"code": item.get("orgnNatCd")}, "country_name")
            if item.get("qtyUnitCd"):
                item["qtyUnitCd"] = frappe.get_value("UOM", {"common_code": item.get("qtyUnitCd")}, "uom_name")
            if item.get("pkgUnitCd"):
                item["pkgUnitCd"] = frappe.get_value("Packaging Unit Of Measure", {"code": item.get("pkgUnitCd")}, "name")

            tax_template = get_item_tax_template("B")
            item["tax"] = tax_template if tax_template else None
            
        return result   
    except Exception as e:
        raise e

