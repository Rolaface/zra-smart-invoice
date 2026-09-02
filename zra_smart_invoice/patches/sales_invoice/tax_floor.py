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
        tax_base_amount = _get_rrp_floored_amount(self, item, tax_rate)
        current_tax_amount = abs(round((tax_rate / 100.0) * tax_base_amount,2))
        _cache_mtv_row_total(self, item, tax, tax_base_amount, tax_rate)

    elif tax.charge_type == "On Previous Row Amount":
        current_net_amount = self.doc.get("taxes")[cint(tax.row_id) - 1].tax_amount_for_current_item
        current_tax_amount = (tax_rate / 100.0) * current_net_amount

    elif tax.charge_type == "On Previous Row Total":
        cached_total = _get_cached_mtv_row_total(self, item, tax)
        current_net_amount = self.doc.get("taxes")[cint(tax.row_id) - 1].grand_total_for_current_item
        if cached_total is not None:
            tax_base_amount = abs(round(cached_total/(1+(tax_rate/100)),2))
        else:
            tax_base_amount = current_net_amount

        current_tax_amount = abs(round((tax_rate / 100.0) * tax_base_amount,2))

    elif tax.charge_type == "On Item Quantity":
        current_tax_amount = tax_rate * item.qty

    if not tax.get("dont_recompute_tax"):
        self.set_item_wise_tax(item, tax, tax_rate, current_tax_amount, current_net_amount)

    return current_net_amount, current_tax_amount


def _get_rrp_floored_amount(self, item, tax_rate):
    """Tax base = max(selling amount, RRP amount) for MTV items only."""
    if not hasattr(self, "_rrp_cache"):
        self._rrp_cache = {}

    if item.item_code not in self._rrp_cache:
        self._rrp_cache[item.item_code] = _fetch_rrp(self, item.item_code)

    rrp = self._rrp_cache[item.item_code]
    item_rate = item.price_list_rate + abs(round((item.price_list_rate*(tax_rate/100)),2))
    if rrp and rrp > flt(item_rate):
        rrp_tax = abs(round(rrp / (1+(tax_rate/100)), 2))
        tax_base_amount = abs(round(rrp_tax* flt(item.qty),2))
        return tax_base_amount

    return item.net_amount


def _fetch_rrp(self, item_code):
    if self.doc.doctype != "Sales Invoice":
        return 0.0
    item_doc = frappe.get_cached_doc("Item", item_code)
    metadata = item_doc.get("custom_item_metadata")

    if not metadata:
        return 0.0

    row = metadata[0]
    if not row.get("is_mtv"):
        return 0.0

    return flt(row.get("rrp_rate"))

def _cache_mtv_row_total(self, item, tax, tax_base_amount, tax_rate):
    item_doc = frappe.get_cached_doc("Item", item.item_code)

    metadata = item_doc.get("custom_item_metadata")
    if not metadata:
        return None
    row = metadata[0]
    if not row.get("is_mtv"):
        return None

    if item.item_code not in self._rrp_cache:
        self._rrp_cache[item.item_code] = _fetch_rrp(self, item.item_code)

    rrp = self._rrp_cache[item.item_code]
    if not rrp:
        return None
    elif not hasattr(self, "_mtv_row_totals"):
        self._mtv_row_totals = {}

    item_rate = item.price_list_rate + abs(round((item.price_list_rate*(tax_rate/100)),2))
    if rrp and rrp > flt(item_rate):
        self._mtv_row_totals.setdefault(item.name, {})[tax.idx] = tax_base_amount

def _get_cached_mtv_row_total(self, item, tax):
    if not hasattr(self, "_mtv_row_totals"):
        return None
    return self._mtv_row_totals.get(item.name, {}).get(cint(tax.row_id))

