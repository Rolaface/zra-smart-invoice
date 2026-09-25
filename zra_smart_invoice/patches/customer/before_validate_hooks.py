import frappe
import re

def before_validate(doc, method):
    if len(doc.tax_id)>10:
        frappe.throw("TPIN should not be more than 10 characters.")