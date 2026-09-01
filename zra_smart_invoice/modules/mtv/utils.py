from zra_smart_invoice.config.constant import _ALL_TAX_FIELDS, SALES_INVOICE_CATEGORY_FIELD_MAP
from zra_smart_invoice.modules.sales_invoice.utils import cascade_forward, cascade_reverse
import frappe
from frappe.utils import flt

def get_item_tax_template(code):
    return frappe.get_value(
        "Item Tax Template",
        {"title": ["like", f"{code} |%"]},
        ["name", "title"],
        as_dict=True
    )

def create_mtv_item_payload(item, item_doc, qty, rrp_rate, mapped_tax):

    item_net_amt = abs(round(float(item.price_list_rate or 0), 2))

    item_unit_price, item_unit_breakdown = cascade_forward(item_net_amt, mapped_tax)

    use_rrp = rrp_rate >= item_unit_price

    if use_rrp:

        reverse_breakdown = cascade_reverse(rrp_rate, mapped_tax)
        unit_breakdown = {
            cat: {"base": v["taxbl"], "tax": v["tax"]}
            for cat, v in reverse_breakdown.items()
        }
    else:
        unit_breakdown = item_unit_breakdown

    total_tax_amt_unit = sum(v["tax"] for v in unit_breakdown.values())
    prc = abs(round(item_net_amt + total_tax_amt_unit, 2))

    totAmt = abs(round(prc * qty, 2))
    splyAmt = abs(round(rrp_rate * flt(item.qty), 2)) if use_rrp else totAmt

    tax_fields = dict(_ALL_TAX_FIELDS)
    for category, amounts in unit_breakdown.items():
        cfg = SALES_INVOICE_CATEGORY_FIELD_MAP[category]
        code = mapped_tax[category]["tax_code"]
        tax_fields[cfg["cat_field"]] = code
        tax_fields[cfg["taxbl_field"]] = abs(round(amounts["base"] * qty, 2))
        tax_fields[cfg["amt_field"]] = abs(round(amounts["tax"] * qty, 2))

    # ── Discount handling ─────────────────────────────────────────────────
    discounted_net_price = None
    discount_amount = 0
    if item.discount_amount or item.discount_percentage:
        discount_amount = abs(round(splyAmt * (item.discount_percentage / 100), 2))
        discounted_net_price = abs(round(splyAmt - discount_amount, 2))

        reverse_breakdown = cascade_reverse(discounted_net_price, mapped_tax)
        for category, amounts in reverse_breakdown.items():
            cfg = SALES_INVOICE_CATEGORY_FIELD_MAP[category]
            tax_fields[cfg["taxbl_field"]] = amounts["taxbl"]
            tax_fields[cfg["amt_field"]] = amounts["tax"]

        if use_rrp:

            discounted_net_price = abs(round(totAmt - discount_amount, 2))

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
        "rrp": rrp_rate,
        "prc": prc,
        "splyAmt": splyAmt,
        "dcRt": item.discount_percentage,
        "dcAmt": discount_amount,
        "isrccCd": "",
        "isrccNm": "",
        "isrcRt": 0,
        "isrcAmt": 0.0,
        "vatCatCd": tax_fields["vatCatCd"],
        "iplCatCd": tax_fields["iplCatCd"],
        "exciseTxCatCd": tax_fields["exciseTxCatCd"],
        "vatTaxblAmt": tax_fields["vatTaxblAmt"],
        "exciseTaxblAmt": tax_fields["exciseTaxblAmt"],
        "tlTaxblAmt": tax_fields["tlTaxblAmt"],
        "vatAmt": tax_fields["vatAmt"],
        "exciseTxAmt": tax_fields["exciseTxAmt"],
        "tlAmt": tax_fields["tlAmt"],
        "totAmt": totAmt if not item.discount_amount else discounted_net_price,
    }
    return payload, tax_fields