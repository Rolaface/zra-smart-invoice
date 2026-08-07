from zra_smart_invoice.modules.mtv.utils import get_item_tax_template
from zra_smart_invoice.api import get_item_type_name
from zra_smart_invoice.client import make_vsdc_request
import frappe
from frappe import _
from custom_api.utils.response import send_old_response, send_response_list

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

@frappe.whitelist(allow_guest = True, methods=["POST"])
def save_purchase_sales():
    try:
        data = frappe.request.get_json()
        payload = data
        return send_response_list(
                    status="success",
                    message="Purchase Invoices saved successfully",
                    data=None,
                    status_code=200,
                    http_status=200
                )
        # result = make_vsdc_request("trnsPurchase/saveTrnsPurchaseSales", payload)
        # if result.get("resultCd") and result.get("resultCd") == "000":
        #     return result

        # else:
        #     frappe.throw(_("Failed to save purchase sales to ZRA"))  
          
    except Exception as e:
        raise e