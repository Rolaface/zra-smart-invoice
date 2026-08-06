from zra_smart_invoice.modules.mtv.utils import get_item_tax_template
from zra_smart_invoice.api import get_item_type_name
from zra_smart_invoice.client import make_vsdc_request
import frappe

@frappe.whitelist(allow_guest = True, methods=["GET"])
def get_principals():
    try:
        payload = {"lastReqDt":"20231215000000"}
        result = make_vsdc_request("trnsSales/selectPrincipals", payload)
        return result   
    except Exception as e:
        raise e

