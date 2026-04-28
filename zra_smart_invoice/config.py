import frappe


def is_zra_enabled():
    """Check if ZRA is configured for this site"""
    return bool(frappe.conf.get("zra_tpin"))


def get_zra_config():
    """
    Read ZRA credentials from site_config.json / secrets.
    Returns None if ZRA is not configured for this site.
    """
    tpin = frappe.conf.get("zra_tpin")

    if not tpin:
        return None

    return {
        "tpin": tpin,
        "bhf_id": frappe.conf.get("zra_bhf_id", "000"),
        "dvc_srl_no": frappe.conf.get("zra_dvc_srl_no"),
        "vsdc_url": frappe.conf.get("zra_vsdc_url", "").rstrip("/"),
        "environment": frappe.conf.get("zra_environment", "sandbox")
    }