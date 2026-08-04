__version__ = "0.0.1"

def _apply_tax_floor_patch():
    import erpnext.controllers.taxes_and_totals as tax_and_totals
    from zra_smart_invoice.patches.sales_invoice.tax_floor import get_current_tax_and_net_amount

    tax_and_totals.calculate_taxes_and_totals.get_current_tax_and_net_amount = (
        get_current_tax_and_net_amount
    )


_apply_tax_floor_patch()