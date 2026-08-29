import frappe
from zra_smart_invoice.config.constant import ITEM_TYPE_CODE_MAP

def get_item_type_code(item_group: str) -> str:
   
    return ITEM_TYPE_CODE_MAP.get(item_group, "2")


def get_tax_template(doc):

    tax_templates = []

    for tax in doc.taxes:
        if tax.item_tax_template:
            tax_template = frappe.get_doc("Item Tax Template", tax.item_tax_template)
            tax_templates.append(tax_template)

    return tax_templates

def tax_template_title(tax_templates, category):

    for tax_template in tax_templates:
        tax_template_title = tax_template.title.split("|")[0].strip()
        tax_template_category = tax_template.title.split("|")[-1].strip()

        if tax_template_category == category:
            return tax_template_title

    return None