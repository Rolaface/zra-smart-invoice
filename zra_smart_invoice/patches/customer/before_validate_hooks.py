import frappe
import re

def before_validate(doc, method):
    tax_category = doc.tax_category
    tax_category =  re.sub(r"[^A-Za-z0-9]", "", tax_category).lower()
    if not doc.tax_id and tax_category == "nonexport":
        frappe.throw("TPIN is required for Customer.")