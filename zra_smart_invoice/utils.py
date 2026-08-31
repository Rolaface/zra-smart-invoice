import frappe
from typing import Any, Dict, List, Optional, Tuple

def _zra_user_id(max_len=20):
    user = frappe.session.user or "Administrator"
    if "@" in user:
        user = user.split("@")[0]
    return user[:max_len]


def _safe_set(doc: Any, field: str, value: Any) -> None:
    """Safely set a field on a document only if the DB column exists."""
    try:
        if frappe.db.has_column(doc.doctype, field):
            doc.set(field, value)
    except Exception:
        pass

def sanitize_zra_message(message: str) -> str:
    # Escape angle brackets so `<vatCatCd>` can't be parsed as an HTML tag
    return message.replace("<", "").replace(">", "")

def clean_mapped_taxes(mapped_tax):
    if "Insurance Premium Levy" in mapped_tax:
        mapped_tax = {"Insurance Premium Levy": mapped_tax["Insurance Premium Levy"]}

    return mapped_tax
