from zra_smart_invoice.modules.purchase_invoice.service import make_pi_from_purcahse_sale
from zra_smart_invoice.modules.purchase_invoice.utils import create_purchase_sales_response
from zra_smart_invoice.client import make_vsdc_request
import frappe
from frappe import _
from custom_api.utils.response import send_old_response

@frappe.whitelist(allow_guest = False, methods=["GET"])
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

@frappe.whitelist(allow_guest = False, methods=["POST"])
def save_purchase_sales():
    try:
        payload = frappe.request.get_json()

        if payload.get("transaction_progress") == "Rejected":
            new_payload = create_purchase_sales_response(payload)
            result = make_vsdc_request("trnsPurchase/savePurchase", new_payload)

            if result.get("resultCd") and result.get("resultCd") == "000":
                return send_old_response(
                            status="success",
                            message="Purchase Invoices saved successfully",
                            data=None,
                            status_code=200,
                            http_status=200
                        )
            else:
                frappe.throw(_("Failed to save purchase sales to ZRA"))

        else:
            response = make_pi_from_purcahse_sale(payload)

    except Exception as e:
        raise e