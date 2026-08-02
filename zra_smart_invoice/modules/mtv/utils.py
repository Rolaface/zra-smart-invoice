import frappe

def get_item_tax_template(code):
    return frappe.get_value(
        "Item Tax Template",
        {"title": ["like", f"{code} |%"]},
        ["name", "title"],
        as_dict=True
    )