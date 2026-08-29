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
                frappe.throw("Multiple VAT taxes are not allowed on the same item. Please keep only one VAT tax.")
            else:
                vat_taxes +=1

        elif tax_template_category == "Insurance Premium Levy":
            if insurance_premium_levy > 0:
                frappe.throw(
                            "Multiple Insurance Premium Levy taxes are not allowed on the same item. "
                            "Please keep only one Insurance Premium Levy tax."
                        )            
            else:
                insurance_premium_levy +=1

        elif tourism_levy == "Tourism levy":
            if tourism_levy > 0:
                frappe.throw(
                            "Multiple Tourism Levy taxes are not allowed on the same item. "
                            "Please keep only one Tourism Levy tax."
                        )
            else:
                tourism_levy +=1

        elif excise == "Excise":
            if excise > 0:
                frappe.throw(
                            "Multiple Excise taxes are not allowed on the same item. "
                            "Please keep only one Excise tax."
                        )
            else:
                excise += 1
            