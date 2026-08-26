import math
import time
from typing import Any, Dict, List, Optional, Union

import frappe
from frappe.utils import cint, flt, getdate, now, now_datetime

from zra_smart_invoice.client import make_vsdc_request
from zra_smart_invoice.config import get_zra_config, is_zra_enabled
from zra_smart_invoice.utils import _zra_user_id
from custom_api.utils.response import send_response, send_response_list


# ═══════════════════════════════════════════════════════════════════
#  HELPER MAPPINGS & BUILDERS
# ═══════════════════════════════════════════════════════════════════

STOCK_IN_OUT_TYPE_MAP = {
    # Incoming Types
    "Import": "01",
    "Purchase": "02",
    "Material Receipt": "02",
    "Return In": "03",
    "Stock Movement In": "04",
    "Processing In": "05",
    "Adjustment In": "06",
    # Outgoing Types
    "Sales": "11",
    "Material Issue": "11",
    "Return Out": "12",
    "Material Transfer": "13",
    "Stock Movement Out": "13",
    "Processing Out": "14",
    "Discarding": "15",
    "Write Off": "15",
    "Adjustment Out": "16",
}


def _get_next_sar_no() -> int:
    """Generates a unique Stock Accounting Record Number (sarNo)."""
    return int(time.time())


def _format_stock_item_row(item: Dict[str, Any], idx: int) -> Dict[str, Any]:
    """Formats a single line item for the saveStockItems payload as per ZRA Spec v1.0.8."""
    qty = flt(item.get("qty", 0))
    prc = flt(item.get("prc", 0) or item.get("basic_rate", 0) or item.get("valuation_rate", 0))
    sply_amt = flt(item.get("splyAmt", round(qty * prc, 2)))
    
    # Calculate tax components if not provided (Default 16% VAT Rate)
    taxbl_amt = flt(item.get("taxblAmt", round(sply_amt / 1.16, 4)))
    tax_amt = flt(item.get("taxAmt", round(sply_amt - taxbl_amt, 4)))

    return {
        "itemSeq": int(item.get("itemSeq", idx)),
        "itemCd": str(item.get("itemCd") or item.get("item_code", "")).strip(),
        "itemClsCd": str(item.get("itemClsCd") or item.get("hsn_code", "43322555")).strip(),
        "itemNm": str(item.get("itemNm") or item.get("item_name", "")).strip(),
        "bcd": str(item.get("bcd", "") or "").strip(),
        "pkgUnitCd": str(item.get("pkgUnitCd", "BX")).strip(),
        "pkg": flt(item.get("pkg", qty)),
        "qtyUnitCd": str(item.get("qtyUnitCd", "U")).strip(),
        "qty": qty,
        "itemExprDt": str(item.get("itemExprDt", "")).strip(),
        "prc": prc,
        "splyAmt": sply_amt,
        "totDcAmt": flt(item.get("totDcAmt", 0)),
        "iplCatCd": item.get("iplCatCd"),
        "tlCatCd": item.get("tlCatCd"),
        "exciseTxCatC": item.get("exciseTxCatCd") or item.get("exciseTxCatC"),
        "taxblAmt": taxbl_amt,
        "vatCatCd": str(item.get("vatCatCd", "A")).strip(),
        "taxAmt": tax_amt,
        "iplAmt": flt(item.get("iplAmt", 0)),
        "tlAmt": flt(item.get("tlAmt", 0)),
        "exciseTxAmt": flt(item.get("exciseTxAmt", 0)),
        "totAmt": sply_amt,
    }


# ═══════════════════════════════════════════════════════════════════
#  API ENDPOINTS — STOCK MANAGEMENT
# ═══════════════════════════════════════════════════════════════════

@frappe.whitelist(allow_guest=False, methods=["GET"])
def select_stock_items(
    page: int = 1,
    page_size: int = 10,
    last_req_dt: str = "20160523000000",
) -> Dict[str, Any]:
    """
    Endpoint: /stock/selectStockItems
    Retrieves stock item records from ZRA Smart Invoice VSDC.
    """
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

        response = make_vsdc_request("stock/selectStockItems", payload)
        stock_list = response.get("data", {}).get("stockList", []) or []

        # Local search filtering
        if search:
            search_term = search.lower()
            stock_list = [
                row
                for row in stock_list
                if any(
                    search_term in str(row.get(f, "")).lower()
                    for f in ("itemCd", "itemNm", "itemClsCd", "sarNo", "remark")
                )
            ]

        total_records = len(stock_list)
        total_pages = max(1, math.ceil(total_records / page_size))
        start = (page - 1) * page_size
        end = start + page_size

        response_data = {
            "success": True,
            "message": "Stock items retrieved successfully",
            "data": stock_list[start:end],
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
            message="Stock items retrieved successfully",
            status_code=200,
            data=response_data,
            http_status=200,
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "ZRA Get Stock Items Error")
        return send_response(
            status="error",
            message=f"Internal Server Error: {str(e)}",
            status_code=500,
            http_status=500,
        )


@frappe.whitelist()
def save_stock_items(stock_data: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Endpoint: /stock/saveStockItems
    Transmits stock movements (Stock In/Out) to ZRA Smart Invoice.
    """
    if not is_zra_enabled():
        frappe.throw("ZRA integration is not configured for this site.")

    try:
        if isinstance(stock_data, str):
            stock_data = frappe.parse_json(stock_data)

        if not isinstance(stock_data, dict):
            frappe.throw("stock_data must be a valid dictionary or JSON object.")

        items = stock_data.get("itemList", [])
        if not items:
            frappe.throw("itemList cannot be empty.")

        config = get_zra_config()
        user_id = _zra_user_id()

        formatted_items = [
            _format_stock_item_row(item, idx) for idx, item in enumerate(items, start=1)
        ]

        tot_taxbl_amt = round(sum(flt(i["taxblAmt"]) for i in formatted_items), 4)
        tot_tax_amt = round(sum(flt(i["taxAmt"]) for i in formatted_items), 4)
        tot_amt = round(sum(flt(i["totAmt"]) for i in formatted_items), 2)

        sar_type = stock_data.get("sarTyCd") or STOCK_IN_OUT_TYPE_MAP.get(
            stock_data.get("stock_entry_type"), "02"
        )

        payload = {
            "tpin": config.get("tpin"),
            "bhfId": config.get("bhf_id"),
            "sarNo": stock_data.get("sarNo") or _get_next_sar_no(),
            "orgSarNo": cint(stock_data.get("orgSarNo", 0)),
            "regTyCd": str(stock_data.get("regTyCd", "M")),
            "custTpin": stock_data.get("custTpin"),
            "custNm": stock_data.get("custNm"),
            "custBhfId": stock_data.get("custBhfId"),
            "sarTyCd": str(sar_type),
            "ocrnDt": str(stock_data.get("ocrnDt") or getdate(now()).strftime("%Y%m%d")),
            "totItemCnt": len(formatted_items),
            "totTaxblAmt": tot_taxbl_amt,
            "totTaxAmt": tot_tax_amt,
            "totAmt": tot_amt,
            "remark": str(stock_data.get("remark", ""))[:400],
            "regrId": user_id,
            "regrNm": user_id,
            "modrId": user_id,
            "modrNm": user_id,
            "itemList": formatted_items,
        }

        return make_vsdc_request("stock/saveStockItems", payload)

    except frappe.exceptions.ValidationError:
        raise
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "ZRA Save Stock Items Error")
        frappe.throw(f"Failed to save stock items to ZRA: {str(e)}")


@frappe.whitelist()
def save_stock_master(stock_master_data: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Endpoint: /stockMaster/saveStockMaster
    Updates current remaining stock balances in ZRA Smart Invoice.
    """
    if not is_zra_enabled():
        frappe.throw("ZRA integration is not configured for this site.")

    try:
        if isinstance(stock_master_data, str):
            stock_master_data = frappe.parse_json(stock_master_data)

        if not isinstance(stock_master_data, dict):
            frappe.throw("stock_master_data must be a valid dictionary or JSON object.")

        stock_items = stock_master_data.get("stockItemList", [])
        if not stock_items:
            frappe.throw("stockItemList cannot be empty.")

        config = get_zra_config()
        user_id = _zra_user_id()

        formatted_stock_items = []
        for item in stock_items:
            formatted_stock_items.append({
                "itemCd": str(item.get("itemCd") or item.get("item_code", "")).strip(),
                "rsdQty": flt(item.get("rsdQty") or item.get("actual_qty", 0)),
            })

        payload = {
            "tpin": config.get("tpin"),
            "bhfId": config.get("bhf_id"),
            "regrId": user_id,
            "regrNm": user_id,
            "modrId": user_id,
            "modrNm": user_id,
            "stockItemList": formatted_stock_items,
        }

        return make_vsdc_request("stockMaster/saveStockMaster", payload)

    except frappe.exceptions.ValidationError:
        raise
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "ZRA Save Stock Master Error")
        frappe.throw(f"Failed to save stock master to ZRA: {str(e)}")


# ═══════════════════════════════════════════════════════════════════
#  TRANSACTIONAL WORKFLOW — FULL STOCK SYNC
# ═══════════════════════════════════════════════════════════════════

@frappe.whitelist()
def process_stock_sync(**kwargs) -> Dict[str, Any]:
    """
    Executes a complete 2-step ZRA Stock Synchronization Workflow:
    Step 1 -> saveStockItems (Stock Movement)
    Step 2 -> saveStockMaster (Current Quantities Balance)
    
    If either fails, the transaction is rolled back.
    """
    if getattr(frappe.request, "json", None):
        data = frappe.request.json
    else:
        data = frappe._dict(kwargs) or frappe.local.form_dict

    try:
        stock_items_payload = data.get("stockItemsData") or data
        stock_master_payload = data.get("stockMasterData") or data

        # Step 1: Save Stock Items
        res_items = save_stock_items(stock_items_payload)
        if res_items.get("resultCd") != "000":
            frappe.throw(f"ZRA Save Stock Items Failed: {res_items.get('resultMsg')}")

        # Step 2: Save Stock Master
        res_master = save_stock_master(stock_master_payload)
        if res_master.get("resultCd") != "000":
            frappe.throw(f"ZRA Save Stock Master Failed: {res_master.get('resultMsg')}")

        frappe.db.commit()

        return {
            "status": "success",
            "message": "ZRA Stock items and master updated successfully.",
            "data": {
                "stockItemsResponse": res_items,
                "stockMasterResponse": res_master,
            },
        }

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "ZRA Stock Sync Workflow Error")
        frappe.throw(f"Stock processing failed: {str(e)}")