import frappe

def sync_offline_invoice():
    try:
        filters = frappe._dict({"status": "Pending"})

        failed_invoices = frappe.db.get_all('Sales Invoice', filters=filters, pluck="name")
        for failed_invoice in failed_invoices:
            try:
                doc = frappe.get_doc("Sales Invoice", failed_invoice)
                doc.submit()
            except Exception as e:
                frappe.log_error(f"Failed to submit invoice {failed_invoice}: {str(e)}", "Offline Invoice Sync Error")

    except Exception as e:
        frappe.log_error(f"Error occurred while syncing offline invoices: {str(e)}", "Offline Invoice Sync Error")