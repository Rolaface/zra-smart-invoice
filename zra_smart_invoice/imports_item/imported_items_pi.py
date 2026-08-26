import frappe
from frappe.utils import flt
from typing import List, Dict, Any, Optional

def create_purchase_invoices_for_imports(items: List[Dict[str, Any]], declaration_no: str, declaration_date: str) -> List[str]:

    if not items:
        return []

    grouped_supplier_items = _filter_and_group_approved_items(items)
    
    if not grouped_supplier_items:
        return []

    formatted_declaration_date = _parse_declaration_date(declaration_date)
    default_system_currency = frappe.defaults.get_global_default("default_currency")
    created_purchase_invoices = []

    for supplier_name, supplier_items in grouped_supplier_items.items():
        invoice_name = _create_supplier_purchase_invoice(
            supplier=supplier_name,
            supplier_items=supplier_items,
            declaration_no=declaration_no,
            declaration_date_formatted=formatted_declaration_date,
            default_currency=default_system_currency
        )
        created_purchase_invoices.append(invoice_name)

    return created_purchase_invoices


def _filter_and_group_approved_items(items: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:

    grouped_items = {}
    validation_errors = []

    for item_data in items:
        item_status_code = str(item_data.get("imptItemSttsCd"))
        if item_status_code != "3":
            continue
        
        erp_item_code = item_data.get("mapped_erp_item")
        erp_supplier = item_data.get("mapped_erp_supplier")
        original_item_name = item_data.get("itemNm", "Unknown Item")

        if not erp_item_code:
            validation_errors.append(f"Missing Item Code for approved item: '{original_item_name}'")
        elif not erp_supplier:
            validation_errors.append(f"Missing Supplier for approved mapped ERP item: '{erp_item_code}'")
        else:
            if erp_supplier not in grouped_items:
                grouped_items[erp_supplier] = []
            grouped_items[erp_supplier].append(item_data)
            
    if validation_errors:
        frappe.throw("<br>".join(validation_errors), title="Missing ERP Mappings")
        
    return grouped_items


def _parse_declaration_date(raw_date_str: str) -> Optional[str]:

    if raw_date_str and len(raw_date_str) == 8:
        return f"{raw_date_str[:4]}-{raw_date_str[4:6]}-{raw_date_str[6:]}"
    return None


def _create_supplier_purchase_invoice(
    supplier: str, 
    supplier_items: List[Dict[str, Any]], 
    declaration_no: str, 
    declaration_date_formatted: Optional[str], 
    default_currency: str
) -> str:

    if not frappe.db.exists("Supplier", supplier):
        frappe.throw(f"Mapped ERP Supplier '{supplier}' does not exist in the system.")

    supplier_payment_terms = frappe.db.get_value("Supplier", supplier, "payment_terms")

    first_item = supplier_items[0]
    invoice_currency = first_item.get("invcFcurCd")
    exchange_rate = flt(first_item.get("invcFcurExcrt", 1.0))

    purchase_invoice = frappe.new_doc("Purchase Invoice")
    purchase_invoice.supplier = supplier
    purchase_invoice.update_stock = 0
    
    if supplier_payment_terms:
        purchase_invoice.payment_terms_template = supplier_payment_terms

    remarks_text = f"Generated automatically from ZRA Import Declaration.\nDeclaration No: {declaration_no}"
    if declaration_date_formatted:
        remarks_text += f"\nDeclaration Date: {declaration_date_formatted}"
    
    purchase_invoice.remarks = remarks_text
    
    company = frappe.defaults.get_user_default("Company")
    if company and frappe.db.exists("Company", company):
        company_doc = frappe.get_doc("Company", company)

        extended_details = (
            company_doc.custom_extended_details[0]
            if company_doc.custom_extended_details
            else None
        )

        company_default_payment_mode = (
            extended_details.default_payment_mode
            if extended_details
            else None
        )

        if company_default_payment_mode:
            purchase_invoice.append("custom_invoice_metadata", {
                "payment_mode": company_default_payment_mode
            })

    if invoice_currency:
        purchase_invoice.currency = invoice_currency
        if invoice_currency != default_currency:
            purchase_invoice.conversion_rate = exchange_rate

    for item_data in supplier_items:
        quantity = flt(item_data.get("qty", 0))
        total_foreign_amount = flt(item_data.get("invcFcurAmt", 0))
        target_warehouse = item_data.get("target_warehouse")
        
        unit_rate = (total_foreign_amount / quantity) if quantity > 0 else 0.0

        item_row = {
            "item_code": item_data.get("mapped_erp_item"),
            "qty": quantity,
            "rate": unit_rate,
        }

        if target_warehouse:
            item_row["warehouse"] = target_warehouse

        purchase_invoice.append("items", item_row)

    purchase_invoice.set_missing_values()

    purchase_invoice.insert(ignore_permissions=True)
    frappe.logger().info(f"Draft Purchase Invoice '{purchase_invoice.name}' created for Supplier '{supplier}'.")
    
    return purchase_invoice.name