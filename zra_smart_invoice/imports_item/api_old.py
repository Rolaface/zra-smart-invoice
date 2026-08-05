import json
from typing import Any, Dict, List, Optional, Union
import math

import frappe
from frappe.utils import cint, flt, now
from zra_smart_invoice.config.constant import PAYMENT_TYPE_CODE_MAP
from zra_smart_invoice.config import is_zra_enabled, get_zra_config
from zra_smart_invoice.client import make_vsdc_request
from zra_smart_invoice.utils import _zra_user_id
from custom_api.utils.response import send_response, send_response_list
from .imported_items_pi import create_purchase_invoices_for_imports


def _format_import_item(item: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    return {
        "itemSeq": int(item.get("itemSeq", 0)),
        "hsCd": str(item.get("hsCd", "")).strip(),
        "itemClsCd": str(item.get("itemClsCd", "")).strip(),
        "itemCd": str(item.get("itemCd", "")).strip(),
        "imptItemSttsCd": str(item.get("imptItemSttsCd", "")).strip(),
        "remark": str(item.get("remark", "")).strip()[:400],
        "modrNm": user_id,
        "modrId": user_id,
    }


@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_import_items(
    page=1,
    page_size=10,
    last_req_dt="20160523000000",
    dcl_ref_num: Optional[str] = None,
):
    data = frappe.local.form_dict
    search = (data.get("search") or "").strip()

    try:
        try:
            page = int(page)
            page_size = int(page_size)

            if page < 1 or page_size < 1:
                raise ValueError
        except ValueError:
            return send_response(
                status="fail",
                message="Page constraints must be positive integers.",
                status_code=400,
                http_status=400,
            )

        if not is_zra_enabled():
            return send_response(
                status="fail",
                message="ZRA integration is not configured for this site.",
                status_code=400,
                http_status=400,
            )

        config = get_zra_config()

        payload = {
            "tpin": config.get("tpin"),
            "bhfId": config.get("bhf_id"),
            "lastReqDt": str(last_req_dt).strip(),
        }

        if dcl_ref_num:
            payload["dclRefNum"] = str(dcl_ref_num).strip()

        response = make_vsdc_request("imports/selectImportItems", payload)

        items = response.get("data", {}).get("itemList", [])

        if search:
            search = search.lower()
            items = [
                item
                for item in items
                if any(
                    search in str(item.get(field, "")).lower()
                    for field in (
                        "dclNo",
                        "taskCd",
                        "itemNm",
                        "hsCd",
                        "agntNm",
                        "spplrNm",
                        "orgnNatCd",
                        "exptNatCd",
                    )
                )
            ]

        total_records = len(items)
        total_pages = max(1, math.ceil(total_records / page_size))

        start = (page - 1) * page_size
        end = start + page_size

        response_data = {
            "success": True,
            "message": "Import items retrieved successfully",
            "data": items[start:end],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total_records,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
            },
        }

        return send_response_list(
            status="success",
            message="Import items retrieved successfully",
            status_code=200,
            data=response_data,
            http_status=200,
        )

    except Exception as e:
        frappe.log_error(
            frappe.get_traceback(),
            "Get Import Items Error",
        )
        return send_response(
            status="error",
            message=f"Internal Server Error: {str(e)}",
            status_code=500,
            http_status=500,
        )


@frappe.whitelist()
def update_import_items(
    task_cd: str, dcl_de: str, import_item_list: Union[str, List[Dict[str, Any]]]
) -> Dict[str, Any]:

    # if not is_zra_enabled():
    #     frappe.throw("ZRA integration is not configured for this site.")

    if not task_cd or not dcl_de:
        frappe.throw("Task Code (task_cd) and Declaration Date (dcl_de) are required.")

    try:
        if isinstance(import_item_list, str):
            import_item_list = frappe.parse_json(import_item_list)

        if not isinstance(import_item_list, list) or len(import_item_list) == 0:
            frappe.throw("import_item_list must be a non-empty list of items.")

        # config = get_zra_config()
        user_id = 1
        # config = get_zra_config()
        # user_id = _zra_user_id()

        formatted_items = [
            _format_import_item(item, user_id) for item in import_item_list
        ]

        payload = {
            # "tpin": config.get("tpin"),
            # "bhfId": config.get("bhf_id"),
            "taskCd": str(task_cd).strip(),
            "dclDe": str(dcl_de).strip(),
            "importItemList": formatted_items,
        }

        # TEMP: Sandbox stub
        frappe.logger().info("Skipping ZRA update_import_items call (sandbox)")
        return {"resultCd": "000", "resultMsg": "OK (Sandbox Stub)", "data": payload}

    except frappe.exceptions.ValidationError:
        raise
    except Exception as e:
        frappe.log_error(
            title=f"ZRA API Error: Update Imports (Task {task_cd})",
            message=frappe.get_traceback(),
        )
        frappe.throw(f"An unexpected error occurred while syncing with ZRA: {str(e)}")

@frappe.whitelist()
def process_imported_declarations(**kwargs) -> Dict[str, Any]:

    # Fetch flat JSON payload gracefully from Frappe request handling
    if getattr(frappe.request, "json", None):
        data = frappe.request.json
    else:
        data = frappe._dict(kwargs) or frappe.local.form_dict

    try:
        task_cd = data.get("taskCd")
        dcl_de = data.get("dclDe")
        dcl_no = data.get("dclNo")

        items = data.get("importItemList", [])
        if isinstance(items, str):
            items = frappe.parse_json(items)

        if not task_cd or not dcl_de or not items:
            frappe.throw("Missing required fields: taskCd, dclDe, or importItemList")

        # _create_stock_entry(items)

        zra_response = update_import_items(task_cd, dcl_de, items)

        created_pis = create_purchase_invoices_for_imports(items, dcl_no, dcl_de)

        _create_import_logs(data, items, status_label="Processed")

        frappe.db.commit()

        return {
            "status": "success",
            "message": "Import declaration processed and logged successfully.",
            "data": zra_response,
        }

    except Exception as e:
        frappe.db.rollback()

        task_cd_log = (
            data.get("taskCd", "Unknown") if isinstance(data, dict) else "Unknown"
        )
        frappe.log_error(
            frappe.get_traceback(), f"Import Processing Failed (Task {task_cd_log})"
        )

        frappe.throw(f"Processing failed: {str(e)}")


def _get_default_warehouse():
    """Fetches a default target warehouse if not explicitly provided by the UI."""
    default_warehouse = frappe.db.get_single_value(
        "Stock Settings", "default_warehouse"
    )
    if not default_warehouse:
        frappe.throw(
            "No Default Warehouse set in Stock Settings. Please provide a target warehouse."
        )
    return default_warehouse


def _create_stock_entry(items: List[Dict[str, Any]]):
    stock_entry_items = []

    for item in items:
        if str(item.get("imptItemSttsCd")) == "3" and item.get("mapped_erp_item"):
            item_code = item.get("mapped_erp_item")
            if not frappe.db.exists("Item", item_code):
                frappe.throw(f"Mapped ERP Item '{item_code}' does not exist.")

            target_warehouse = item.get("target_warehouse") or _get_default_warehouse()

            stock_entry_items.append(
                {
                    "item_code": item_code,
                    "qty": flt(item.get("qty", 0)),
                    # "uom": item.get("qtyUnitCd"),
                    "t_warehouse": target_warehouse,
                }
            )

    if not stock_entry_items:
        return

    se = frappe.new_doc("Stock Entry")
    se.stock_entry_type = "Material Receipt"
    se.purpose = "Material Receipt"
    se.set("items", stock_entry_items)
    frappe.logger().info(
        f"Creating Stock Entry for {len(stock_entry_items)} approved items."
    )
    frappe.logger().info(f"stock entry doc: {se.as_dict()}")

    se.insert(ignore_permissions=True)
    se.submit()

def _create_import_logs(
    payload: Dict[str, Any], items: List[Dict[str, Any]], status_label: str
):
    task_cd = payload.get("taskCd")
    dcl_de = payload.get("dclDe")
    dcl_no = payload.get("dclNo")

    for item in items:
        foreign_amount = flt(item.get("invcFcurAmt", 0))
        exchange_rate = flt(item.get("invcFcurExcrt", 1))

        status_code = str(item.get("imptItemSttsCd", ""))
        human_status = (
            "Approved"
            if status_code == "3"
            else "Rejected" if status_code == "4" else status_label
        )

        doc = frappe.new_doc("Custom Imported Item Logs")
        doc.update(
            {
                "task_code": task_cd,
                "declaration_no": dcl_no,
                "declaration_date": dcl_de,
                "item_sequence": cint(item.get("itemSeq", 0)),
                "hs_code": item.get("hsCd"),
                "item_name": item.get("itemNm"),
                "origin_country": item.get("orgnNatCd"),
                "export_country": item.get("exptNatCd"),
                "quantity": flt(item.get("qty", 0)),
                "quantity_unit": item.get("qtyUnitCd"),
                "package_count": cint(item.get("pkg", 0)),
                "package_unit": item.get("pkgUnitCd"),
                "total_weight": flt(item.get("totWt", 0)),
                "net_weight": flt(item.get("netWt", 0)),
                "invoice_amount": foreign_amount,
                "currency": item.get("invcFcurCd"),
                "exchange_rate": exchange_rate,
                "base_invoice_amount": foreign_amount * exchange_rate,
                "supplier_name": item.get("spplrNm"),
                "agent_name": item.get("agntNm"),
                "status": human_status,
                "status_code": status_code,
                "mapped_erp_item": item.get("mapped_erp_item"),
                "mapped_erp_supplier": item.get("mapped_erp_supplier"),
                "remarks": item.get("remark"),
                "checker": frappe.session.user,
                "checked_at": now(),
            }
        )
        doc.insert(ignore_permissions=True)
