import frappe

def validate_zra_taxes(tax_templates):
    print(tax_templates)
    tax_categories = set()

    for tax_template in tax_templates:
        if not tax_template:
            continue

        if tax_template in tax_categories:
            frappe.throw(
                f"Only one '{tax_template}' tax is allowed on an item. "
                f"Please remove the duplicate tax."
            )

        tax_categories.add(tax_template)
            