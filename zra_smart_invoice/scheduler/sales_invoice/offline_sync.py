import frappe

def sync_offline_invoice():
    try:
        filters = frappe._dict({"status": "Pending"})

        failed_invoices = frappe.frappe.db.get_all('Sales Invoice', filters=filters, pluck="name")
        for failed_invoice in failed_invoices:
            try:
                doc = frappe.get_doc("Sales Invoice", failed_invoice)
                doc.submit()
            except Exception as e:
                pass
        print("Length = ",len(failed_invoices))

    except Exception as e:
        print("Error --> ",str(e))