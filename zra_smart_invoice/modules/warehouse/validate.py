import frappe
from zra_smart_invoice.config import is_zra_enabled
from zra_smart_invoice.client import make_vsdc_request

def validate(doc, method):
    if not is_zra_enabled():
        return

    # Group warehouses never hold stock, so they never reach ZRA
    if doc.is_group:
        return

    code = (doc.get("custom_warehouse_code") or "").strip()
    if not code:
        frappe.throw("ZRA Warehouse Code is mandatory.", title="ZRA Smart Invoice")

    doc.custom_warehouse_code = code

    # Only hit ZRA when the code is new or has changed
    if not doc.is_new() and not doc.has_value_changed("custom_warehouse_code"):
        return

    branch_ids = _get_zra_branch_ids()
    if code not in branch_ids:
        frappe.throw(
            f"ZRA Warehouse Code <b>{code}</b> does not exist as a branch in ZRA. "
            f"Valid branch codes: {', '.join(sorted(branch_ids)) or 'none'}.",
            title="ZRA Smart Invoice",
        )


def _get_zra_branch_ids():
    result = make_vsdc_request("branches/selectBranches", {"lastReqDt": "20231215000000"})

    if result.get("resultCd") != "000":
        frappe.throw(
            f"Could not fetch branches from ZRA ({result.get('resultCd')}): {result.get('resultMsg')}",
            title="ZRA Smart Invoice",
        )

    bhf_list = (result.get("data") or {}).get("bhfList") or []
    return {b.get("bhfId") for b in bhf_list if b.get("bhfId")}
