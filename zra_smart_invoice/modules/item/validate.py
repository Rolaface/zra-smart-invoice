import frappe

def validate_zra_taxes(tax_templates):
    vat_taxes = 0
    insurance_premium_levy = 0
    tourism_levy = 0
    excise = 0
    for tax_template in tax_templates:
        tax_template_category = tax_template.title.split("|")[-1].strip() if tax_template else "VAT"
        
        if tax_template_category == "VAT":
            if vat_taxes > 0:
                frappe.throw("Only one Vat Category Tax is allowed on item")
            else:
                vat_taxes +=1

        elif tax_template_category == "Insurance Premium Levy":
            if insurance_premium_levy > 0:
                frappe.throw("Only one Insurance Premium Levy Category Tax is allowed on item")
            else:
                insurance_premium_levy +=1

        elif tourism_levy == "Tourism levy":
            if tourism_levy > 0:
                frappe.throw("Only one Tourism levy Category Tax is allowed on item")
            else:
                tourism_levy +=1

        elif excise == "Excise":
            if excise > 0:
                frappe.throw("Only one Excise Category Tax is allowed on item")
            else:
                excise += 1
            