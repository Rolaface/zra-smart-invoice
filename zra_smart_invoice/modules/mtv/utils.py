import frappe
from frappe.utils import flt

def get_item_tax_template(code):
    return frappe.get_value(
        "Item Tax Template",
        {"title": ["like", f"{code} |%"]},
        ["name", "title"],
        as_dict=True
    )

def create_mtv_item_payload(item, item_doc, qty, rrp_rate, vat_cat_cd, tax_rate):

    tax_base_amount = abs(round(((rrp_rate/1.16 )* flt(item.qty)), 4))
    if rrp_rate < item.net_amount:
        tax_base_amount = abs(round(((item.net_amount/1.16 )* flt(item.qty)), 4))

    prc = item.net_rate
    vat_amt   = abs(round(tax_base_amount * tax_rate / 100, 4))

    payload =  {
            "itemSeq": item.idx,
            "itemCd": item.item_code,
            "itemClsCd": item_doc.custom_item_metadata[0].hsn_code,
            "itemNm": item.item_name,
            "bcd": "",
            "pkgUnitCd": frappe.get_value("Packaging Unit Of Measure", item_doc.custom_item_metadata[0].packaging_uom, "code"),
            "pkg": item_doc.custom_item_metadata[0].packing_unit,
            "qtyUnitCd": frappe.get_value("UOM", item_doc.stock_uom, "common_code"),
            "qty": qty,
            "rrp": rrp_rate,
            "prc": prc,
            "splyAmt": rrp_rate * flt(item.qty) if rrp_rate >= item.net_amount else item.net_amount*qty,
            "dcRt": item.discount_percentage,
            "dcAmt": item.discount_amount,
            "isrccCd": "",
            "isrccNm": "",
            "isrcRt": 0,
            "isrcAmt": 0.0,
            "vatCatCd": vat_cat_cd.strip(),
            "exciseTxCatCd": None,
            "vatTaxblAmt": tax_base_amount,
            "exciseTaxblAmt": 0.0,
            "vatAmt": vat_amt,
            "exciseTxAmt": 0.0,
            "totAmt": item.net_amount*qty
        }
    return payload, vat_amt, tax_base_amount