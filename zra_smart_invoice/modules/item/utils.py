import frappe
from zra_smart_invoice.config.constant import ITEM_TYPE_CODE_MAP

def get_item_type_code(item_group: str) -> str:
   
    return ITEM_TYPE_CODE_MAP.get(item_group, "2")


def get_tax_template(doc):

    taxes = doc.taxes
    if not taxes:
        frappe.throw("Please select a valid Tax Template for the item.")

    if len(taxes) > 1:
        frappe.throw("Only one Tax Template is allowed on an item.")

    tax = taxes[0]
    tax_template = frappe.get_doc("Item Tax Template", tax.item_tax_template)
    return get_map_taxes(tax_template) 

def get_map_taxes(tax_template):
    title = tax_template.title
    codes_part = title.split("|")[0].strip()
    categories_part = title.split("|")[-1].strip()

    codes = [c.strip() for c in codes_part.split(",") if c.strip()]
    categories = [c.strip() for c in categories_part.split(",") if c.strip()]

    rows = tax_template.taxes or []
    if len(codes) != len(categories) or len(codes) != len(rows):
        frappe.log_error(
            title=f"Tax Template parse mismatch: {tax_template.name}",
            message=(
                f"codes={codes}, categories={categories}, "
                f"tax_rows={[d.tax_rate for d in rows]}"
            ),
        )

    tax_templates = {}
    for code, category, detail in zip(codes, categories, rows):
        tax_templates[category] = {
            "tax_code": code,
            "rate": detail.tax_rate,
        }

    return tax_templates

def tax_template_title(tax_templates, category):

    for tax_category, tax_template in tax_templates.items():

        if tax_category == category:
            return tax_template["tax_code"]

    return None