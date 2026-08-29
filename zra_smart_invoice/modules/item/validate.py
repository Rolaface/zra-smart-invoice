import frappe

def validate_zra_taxes(tax_templates):
    tax_categories = set()

    for tax_template in tax_templates:
        tax_template_category = tax_template.title.split("|")[-1].strip() if tax_template else "VAT"
        
        if tax_template_category in tax_categories:
            frappe.throw(
                f"Only one '{tax_template_category}' tax is allowed on an item. "
                f"Please remove the duplicate tax."
            )

        tax_categories.add(tax_template_category)
            