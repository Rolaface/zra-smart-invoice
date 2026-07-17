from custom_api.config import zra_exception
import frappe
import requests
from zra_smart_invoice.config import get_zra_config


def make_vsdc_request(endpoint, payload):
    """
    Common VSDC HTTP client used by all ZRA API calls.
    Automatically injects tpin and bhfId into every request.
    """
    config = get_zra_config()

    if not config:
        frappe.throw("ZRA is not configured for this site.")

    # Auto inject credentials into every request
    payload["tpin"] = config["tpin"]
    payload["bhfId"] = config["bhf_id"]

    url = f"{config['vsdc_url']}/{endpoint}"

    # frappe.logger().info(f"ZRA Request → {url}")
    print(f"ZRA Request → {url}")

    try:
        response = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        response.raise_for_status()
        result = response.json()

        print(f"ZRA Response ← {result.get('resultCd')}: {result.get('resultMsg')}")
        return result

    except requests.exceptions.ConnectionError:
        raise zra_exception.ZRAConnectionError("ZRA Network Error.")

    except requests.exceptions.Timeout:
        frappe.throw("VSDC request timed out.")

    except Exception as e:
        frappe.log_error(
            title="ZRA VSDC Error",
            message=frappe.get_traceback()
        )
        raise zra_exception.ZRAConnectionError(str(e))
