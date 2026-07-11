app_name = "zra_smart_invoice"
app_title = "Zra Smart Invoice"
app_publisher = "Sudeep Panchpuri"
app_description = "ZRA Smart Invoice Integration for ERPNext"
app_email = "sudeep.panchpuri@rolaface.com"
app_license = "mit"

# ─────────────────────────────────────────────────────────────────
# Document Events
# ─────────────────────────────────────────────────────────────────
#
# Flow for Item:
#   before_insert  → ZRA first, then ERPNext creates  ✅ / throws ❌
#   before_save    → ZRA first (on edit), then ERPNext saves ✅ / throws ❌
#
# Flow for Sales Invoice:
#   before_submit  → ZRA first, then ERPNext submits  ✅ / throws ❌
#   on_cancel      → notifies ZRA (does NOT block ERPNext cancel)
#
# ─────────────────────────────────────────────────────────────────

doc_events = {
    "Item": {
        "after_insert": "zra_smart_invoice.api.on_item_save",  # ✅
        "on_update":    "zra_smart_invoice.api.on_item_save",  # edits ke liye
    },

    "Sales Invoice": {
        # Fires when user clicks Submit — ZRA must succeed first
        "before_submit": "zra_smart_invoice.api.on_sales_invoice_submit",
        # Fires when user cancels — warns but doesn't block
        "on_cancel":     "zra_smart_invoice.api.on_sales_invoice_cancel",
    },


    # ✅ Purchase Invoice
    "Purchase Invoice": {
        "before_submit": "zra_smart_invoice.api.on_purchase_invoice_submit",
        "on_cancel":     "zra_smart_invoice.api.on_purchase_invoice_cancel",
    },
    # ✅ Stock Entry — auto banta hai Purchase pe
    "Stock Entry": {
        "before_submit": "zra_smart_invoice.api.on_stock_entry_submit",
    },
    "Customer": {
        "validate": "zra_smart_invoice.patches.customer.before_validate_hooks.before_validate",
    },
}
