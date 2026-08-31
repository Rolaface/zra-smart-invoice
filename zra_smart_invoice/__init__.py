__version__ = "0.0.1"

def _apply_tax_floor_patch():
    import erpnext.controllers.taxes_and_totals as tax_and_totals
    from zra_smart_invoice.patches.sales_invoice.tax_floor import get_current_tax_and_net_amount

    tax_and_totals.calculate_taxes_and_totals.get_current_tax_and_net_amount = (
        get_current_tax_and_net_amount
    )

def _apply_mtv_discount_patch():
    import erpnext.controllers.taxes_and_totals as tax_and_totals
    from zra_smart_invoice.patches.sales_invoice.mtv_discount import calculate_item_values

    tax_and_totals.calculate_taxes_and_totals.calculate_item_values = calculate_item_values

def _apply_calculate_taxes_patch():
    import erpnext.controllers.taxes_and_totals as tax_and_totals
    from zra_smart_invoice.patches.sales_invoice.doc_update import updated_doc_if_needed

    original_calculate_taxes = tax_and_totals.calculate_taxes_and_totals.calculate_taxes

    def custom_doc_update(self):
        # self.doc = doc
        self = updated_doc_if_needed(self)
        original_calculate_taxes(self)

    tax_and_totals.calculate_taxes_and_totals.calculate_taxes = custom_doc_update

_apply_tax_floor_patch()
_apply_mtv_discount_patch()
_apply_calculate_taxes_patch()