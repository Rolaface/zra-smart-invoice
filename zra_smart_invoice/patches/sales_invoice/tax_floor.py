"""
For flagged "MTV items," tax must be calculated on the item's RRP rather than the actual selling price 
whenever the selling price is lower than the RRP — while the invoice/document still displays and totals the real selling price. 
Standard ERPNext tax calculation always uses the entered rate as the tax base, 
so it needed to be overridden to floor the tax base at RRP for these items only.
"""

import frappe
from frappe.utils import cint, flt
from erpnext.controllers.taxes_and_totals import NOT_APPLICABLE_TAX


def get_current_tax_and_net_amount(self, item, tax, item_tax_map):
    tax_rate = self._get_tax_rate(tax, item_tax_map)
    current_tax_amount = 0.0
    current_net_amount = 0.0

    if tax_rate == NOT_APPLICABLE_TAX:
        return current_net_amount, current_tax_amount

    if tax.charge_type == "Actual":
        current_net_amount = item.net_amount
        actual = flt(tax.tax_amount, tax.precision("tax_amount"))
        current_tax_amount = item.net_amount * actual / self.doc.net_total if self.doc.net_total else 0.0

    elif tax.charge_type == "On Net Total":
        if tax.account_head in item_tax_map:
            current_net_amount = item.net_amount
        tax_base_amount = _get_rrp_floored_amount(self, item)
        current_tax_amount = (tax_rate / 100.0) * tax_base_amount

    elif tax.charge_type == "On Previous Row Amount":
        current_net_amount = self.doc.get("taxes")[cint(tax.row_id) - 1].tax_amount_for_current_item
        current_tax_amount = (tax_rate / 100.0) * current_net_amount

    elif tax.charge_type == "On Previous Row Total":
        current_net_amount = self.doc.get("taxes")[cint(tax.row_id) - 1].grand_total_for_current_item
        current_tax_amount = (tax_rate / 100.0) * current_net_amount

    elif tax.charge_type == "On Item Quantity":
        current_tax_amount = tax_rate * item.qty

    if not tax.get("dont_recompute_tax"):
        self.set_item_wise_tax(item, tax, tax_rate, current_tax_amount, current_net_amount)

    return current_net_amount, current_tax_amount


def _get_rrp_floored_amount(self, item):
    """Tax base = max(selling amount, RRP amount) for MTV items only."""
    if not hasattr(self, "_rrp_cache"):
        self._rrp_cache = {}

    if item.item_code not in self._rrp_cache:
        self._rrp_cache[item.item_code] = _fetch_rrp(item.item_code)

    rrp = self._rrp_cache[item.item_code]
    if rrp and rrp > flt(item.rate):
        return rrp * flt(item.qty)

    return item.net_amount


def _fetch_rrp(item_code):
    item_doc = frappe.get_cached_doc("Item", item_code)
    metadata = item_doc.get("custom_item_metadata")

    if not metadata:
        return 0.0

    row = metadata[0]
    if not row.get("is_mtv"):
        return 0.0

    return flt(row.get("rrp_rate"))