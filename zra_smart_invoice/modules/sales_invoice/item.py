from .utils import cascade_forward, cascade_reverse
from zra_smart_invoice.config.constant import _ALL_TAX_FIELDS, SALES_INVOICE_CATEGORY_FIELD_MAP
import frappe

def create_item_payload(item, qty, item_doc, mapped_tax):

    net_amt = abs(round(float(item.price_list_rate or 0), 2))

    prc, unit_breakdown = cascade_forward(net_amt, mapped_tax)
    tot_amt = abs(round(prc * qty, 2))

    tax_fields = dict(_ALL_TAX_FIELDS)
    for category, amounts in unit_breakdown.items():
        cfg = SALES_INVOICE_CATEGORY_FIELD_MAP[category]
        code = mapped_tax[category]["tax_code"]
        tax_fields[cfg["cat_field"]] = code
        tax_fields[cfg["taxbl_field"]] = abs(round(amounts["base"] * qty, 4))
        tax_fields[cfg["amt_field"]] = abs(round(amounts["tax"] * qty, 4))

    discounted_net_price = None
    discount_amount = 0
    if item.discount_amount or item.discount_percentage:
        discount_amount = abs(round(tot_amt * (item.discount_percentage / 100), 4))
        discounted_net_price = abs(round(tot_amt - discount_amount, 4))

        reverse_breakdown = cascade_reverse(discounted_net_price, mapped_tax)
        for category, amounts in reverse_breakdown.items():
            cfg = SALES_INVOICE_CATEGORY_FIELD_MAP[category]
            tax_fields[cfg["taxbl_field"]] = amounts["taxbl"]
            tax_fields[cfg["amt_field"]] = amounts["tax"]

    payload = {
        "itemSeq": item.idx,
        "itemCd": item.item_code,
        "itemClsCd": item_doc.custom_item_metadata[0].hsn_code,
        "itemNm": item.item_name,
        "bcd": "",
        "pkgUnitCd": frappe.get_value("Packaging Unit Of Measure", item_doc.custom_item_metadata[0].packaging_uom, "code"),
        "pkg": item_doc.custom_item_metadata[0].packing_unit,
        "qtyUnitCd": frappe.get_value("UOM", item_doc.stock_uom, "common_code"),
        "qty": qty,
        "prc": prc,
        "splyAmt": tot_amt,
        "dcRt": item.discount_percentage,
        "dcAmt": discount_amount,
        "isrccCd": "",
        "isrccNm": "",
        "isrcAmt": 0.0,
        "vatCatCd": tax_fields["vatCatCd"],
        "iplCatCd": tax_fields["iplCatCd"],
        "exciseTxCatCd": tax_fields["exciseTxCatCd"],
        "vatTaxblAmt": tax_fields["vatTaxblAmt"],
        "exciseTaxblAmt": tax_fields["exciseTaxblAmt"],
        "tlTaxblAmt": tax_fields["tlTaxblAmt"],
        "iplTaxblAmt": tax_fields["iplTaxblAmt"],
        "iplAmt": tax_fields["iplAmt"],
        "tlAmt": tax_fields["tlAmt"],
        "vatAmt": tax_fields["vatAmt"],
        "exciseTxAmt": tax_fields["exciseTxAmt"],
        "totAmt": tot_amt if not item.discount_amount else discounted_net_price,
    }

    return payload, tax_fields