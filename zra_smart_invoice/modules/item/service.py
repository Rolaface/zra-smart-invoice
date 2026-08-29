from zra_smart_invoice.modules.item.validate import validate_zra_taxes
from zra_smart_invoice.modules.item.utils import get_item_type_code, get_tax_template, tax_template_title
from zra_smart_invoice.utils import _zra_user_id
import frappe

def build_item_payload(doc):
    data = frappe.request.get_json()

    tax_templates = get_tax_template(doc)
    validate_zra_taxes(tax_templates)

    if doc.country_of_origin:
        orgn_nat_cd = frappe.get_value("Country", doc.country_of_origin, "code").upper()
    else:
        orgn_nat_cd = frappe.get_value("Country", frappe.defaults.get_user_default("country"), "code").upper()

    is_mtv_item = doc.custom_item_metadata[0].is_mtv if doc.custom_item_metadata else False

    return {
        # ── Identity ──────────────────────────────────────────────
        "itemCd":        doc.item_code,           # [STANDARD]
        "itemNm":        doc.item_name,           # [STANDARD]
        "itemStdNm":     doc.item_name,           # [STANDARD]

        # ── Classification ────────────────────────────────────────
        "itemClsCd":     doc.custom_item_metadata[0].hsn_code,
        "itemTyCd":      get_item_type_code(doc.item_group),
        "vatCatCd":      tax_template_title(tax_templates, "VAT"),
        "iplCatCd":      tax_template_title(tax_templates, "Insurance Premium Levy"),
        "tlCatCd":       tax_template_title(tax_templates, "Tourism levy"),
        "exciseTxCatCd": tax_template_title(tax_templates, "Excise"),

        # ── Units ─────────────────────────────────────────────────
        "pkgUnitCd":     frappe.get_value("Packaging Unit Of Measure", doc.custom_item_metadata[0].packaging_uom, "code"),
        "qtyUnitCd":     frappe.get_value("UOM", doc.stock_uom, "common_code"),

        # ── Pricing ───────────────────────────────────────────────
        "dftPrc":        data.get("sellingPrice") if data else 0,

        # ── Origin & flags ────────────────────────────────────────
        "orgnNatCd":     orgn_nat_cd,
        "btchNo":        None,
        "bcd":           None,
        "addInfo":       doc.description,
        "sftyQty":       None,
        "isrcAplcbYn":   "Y" if doc.custom_item_metadata[0].insurance else "N",
        "svcChargeYn":   "Y" if doc.custom_item_metadata[0].service_charge else "N",
        "rentalYn":      "Y" if doc.custom_item_metadata[0].rentalyn else "N",
        "useYn":         "Y" if doc.custom_item_metadata[0].useyn else "N",

        # MTV Item Details
        "manufacturerTpin": doc.custom_item_metadata[0].mtv_manufacturer_tpin if is_mtv_item else None,
        "manufacturerItemCd": doc.custom_item_metadata[0].manufactureritemcd if is_mtv_item else None,
        "rrp": doc.custom_item_metadata[0].rrp_rate if is_mtv_item else None,

        # ── Audit ─────────────────────────────────────────────────
        "regrId": _zra_user_id(),
        "regrNm": _zra_user_id(),
        "modrId": _zra_user_id(),
        "modrNm": _zra_user_id(),
    }
