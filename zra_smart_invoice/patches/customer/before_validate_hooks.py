import frappe
import re

def before_validate(doc, method):
    if doc.tax_id and len(doc.tax_id)>10:
        frappe.throw("TPIN should not be more than 10 characters.")