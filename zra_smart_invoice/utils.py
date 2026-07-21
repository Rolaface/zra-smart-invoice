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
