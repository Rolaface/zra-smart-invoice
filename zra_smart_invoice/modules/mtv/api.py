from zra_smart_invoice.api import get_item_type_name
from zra_smart_invoice.client import make_vsdc_request
import frappe

@frappe.whitelist(allow_guest = True, methods=["GET"])
def get_rrp_items(mfg_tpin):
    try:
        payload = {"tpin":mfg_tpin,  "lastReqDt":"20231215000000"}
        # result = make_vsdc_request("trnsSales/saveSales", payload)
        
        result =  {
                    "tpin": "1000000000",
                    "bhfId": "000",
                    "itemList": [
                      {
                        "itemCd": "itemCode1",
                        "itemClsCd": "50102515",
                        "itemTyCd": "3",
                        "itemNm": "Item Name Example",
                        "itemDesc": "This is\nfanta",
                        "orgnNatCd": "ZM",
                        "pkgUnitCd": "BG",
                        "qtyUnitCd": "BX",
                        "rrp": 123.6789,
                        "useYn": "Y",
                        "regrId": "admin",
                        "regrNm": "Admin",
                        "modrNm": "Admin",
                        "modrId": "1231"
                      },
                      {
                        "itemCd": "itemCode2",
                        "itemClsCd": "50102515",
                        "itemTyCd": "3",
                        "itemNm": "frooti",
                        "itemDesc": "This is fanta",
                        "orgnNatCd": "ZM",
                        "pkgUnitCd": "BG",
                        "qtyUnitCd": "BX",
                        "rrp": 123.6789,
                        "useYn": "Y",
                        "regrId": "admin",
                        "regrNm": "Admin",
                        "modrNm": "Admin",
                        "modrId": "1231"
                      }
                    ]
                  }
        for item in result.get("itemList"):
            if item.get("itemTyCd"):
                item["itemTyCd"] = get_item_type_name(item.get("itemTyCd"))
            if item.get("orgnNatCd"):
                item["orgnNatCd"] = frappe.get_value("Country", {"code": item.get("orgnNatCd")}, "country_name")
            if item.get("qtyUnitCd"):
                item["qtyUnitCd"] = frappe.get_value("UOM", {"common_code": item.get("qtyUnitCd")}, "uom_name")
        return result   
    except Exception as e:
        raise e

