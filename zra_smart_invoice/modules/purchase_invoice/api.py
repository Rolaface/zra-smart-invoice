from zra_smart_invoice.modules.mtv.utils import get_item_tax_template
from zra_smart_invoice.api import get_item_type_name
from zra_smart_invoice.client import make_vsdc_request
import frappe
from frappe import _

@frappe.whitelist(allow_guest = True, methods=["GET"])
def get_purchase_sales():
    try:
        payload = {"lastReqDt":"20231215000000"}

        result = make_vsdc_request("trnsPurchase/selectTrnsPurchaseSales", payload)
        if result.get("resultCd") and result.get("resultCd") == "000":
            return result

        else:
            frappe.throw(_("No purchase sales Found from ZRA"))  
          
    except Exception as e:
        raise e

