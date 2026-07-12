import frappe

def on_organization_update(doc, method):
    custom_extended_details = doc.custom_extended_details
    if not custom_extended_details:
        frappe.throw("Custom Extended Details are required for Company.")
    if custom_extended_details:
        extended_details = doc.custom_extended_details[0]
        if not extended_details.sdc_id:
            frappe.throw("SDC ID is required for Company.")