from zra_smart_invoice.modules.purchase_invoice.utils import build_purchase_sales_items, create_purchase_sales_response
from custom_api.api.selling.sales_invoice.utils import validate_receivable_account_for_currency
from custom_api.utils.response import send_old_response
from erpnext.accounts.party import get_due_date_from_template
import frappe
from frappe.utils import getdate

def make_pi_from_purcahse_sale(payload):
    try:
        frappe.log_error(f"Supplier Tpin = {payload.get("spplrTpin")}")
        supplier_doc = frappe.get_doc("Supplier", {"tax_id": payload.get("spplrTpin")})
        company = frappe.defaults.get_user_default("Company")
        currency = supplier_doc.default_currency
        account = validate_receivable_account_for_currency(currency, "Payable", "Liability")
        company_doc = frappe.get_doc("Company", company)

        extended_details = ( company_doc.custom_extended_details[0]
                             if company_doc.custom_extended_details
                             else None
                            )
        company_default_payment_mode = ( extended_details.default_payment_mode
                                         if extended_details
                                         else None
                                        )

        supplier_payment_terms = frappe.db.get_value("Supplier", supplier_doc.name, "payment_terms")
        due_date = format(get_due_date_from_template(supplier_payment_terms, format(getdate(frappe.utils.now_datetime())), format(getdate(frappe.utils.now_datetime()))))
        pi_doc = frappe.get_doc({
                        "doctype": "Purchase Invoice",
                        "posting_date": getdate(frappe.utils.now_datetime()),
                        "due_date": due_date,
                        "company": company,
                        "supplier": supplier_doc.name,
                        "update_stock": True,
                        "currency": currency,
                        "credit_to": account,
                        "tax_category":supplier_doc.tax_category,
                        "bill_no": payload.get("spplrInvcNo"),
                        "bill_date": format(getdate(frappe.utils.now_datetime())),
                        "payment_terms_template": supplier_payment_terms,
                        "items": build_purchase_sales_items(payload.get("itemList")),
                        "custom_invoice_metadata": [
                                                    {   
                                                        "payment_mode": company_default_payment_mode if company_default_payment_mode else None,
                                                        "purchase_sales_response": create_purchase_sales_response(payload)
                                                    }
                                                   ],
                    })
        pi_doc.run_method("set_missing_values")
        pi_doc.run_method("calculate_taxes_and_totals")

        pi_doc.insert(ignore_permissions=True)
        pi_doc.submit()

    except frappe.DoesNotExistError:
        return send_old_response(
                                status="fail",
                                message=f"Supplier with TPIN {payload.get("spplrTpin")} not found",
                                status_code=404,
                                http_status=404
                            )