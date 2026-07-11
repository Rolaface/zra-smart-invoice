import frappe

def before_validate(doc, method):
    
    if not doc.tax_id:
        frappe.throw("TPIN is required for Customer.")