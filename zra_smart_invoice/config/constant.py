PAYMENT_TYPE_CODE_MAP = {
    "Cash": "01",
    "Credit": "02",
    "Cash/Credit": "03",
    "Bank cheque": "04",
    "Cheque": "04", # alias
    "Check": "04", # alias
    "Debit card": "05",
    "Credit card": "05",
    "Card": "05", # alias
    "Mobile money": "06",
    "Bank transfer": "08",
    "Other": "07",
}

ITEM_TYPE_CODE_MAP = {
    "Raw Material":     "1",
    "Finished Product": "2",
    "Service":          "3",
}

SALES_INVOICE_CATEGORY_FIELD_MAP = {
    "Insurance Premium Levy": {"cat_field": "iplCatCd", "taxbl_field": "iplTaxblAmt", "amt_field": "iplAmt"},
    "VAT":                    {"cat_field": "vatCatCd", "taxbl_field": "vatTaxblAmt", "amt_field": "vatAmt"},
    "Excise":                 {"cat_field": "exciseTxCatCd", "taxbl_field": "exciseTaxblAmt", "amt_field": "exciseTxAmt"},
    "Turnover Levy":          {"cat_field": "tlCatCd", "taxbl_field": "tlTaxblAmt", "amt_field": "tlAmt"},
}

_ALL_TAX_FIELDS = {}
for _cfg in SALES_INVOICE_CATEGORY_FIELD_MAP.values():
    _ALL_TAX_FIELDS[_cfg["cat_field"]] = None
    _ALL_TAX_FIELDS[_cfg["taxbl_field"]] = 0.0
    _ALL_TAX_FIELDS[_cfg["amt_field"]] = 0.0

PURCHASE_INVOICE_CATEGORY_FIELD_MAP = {
    "Insurance Premium Levy": {"cat_field": "iplCatCd", "taxbl_field": "iplTaxblAmt", "amt_field": "iplAmt"},
    "VAT":                    {"cat_field": "vatCatCd", "taxbl_field": "taxblAmt", "amt_field": "taxAmt"},
    "Excise":                 {"cat_field": "exciseCatCd", "taxbl_field": "exciseTaxblAmt", "amt_field": "exciseTxAmt"},
    "Turnover Levy":          {"cat_field": "tlCatCd", "taxbl_field": "tlTaxblAmt", "amt_field": "tlAmt"},
}

_ALL_PURCHASE_TAX_FIELDS = {}
for _cfg in PURCHASE_INVOICE_CATEGORY_FIELD_MAP.values():
    _ALL_PURCHASE_TAX_FIELDS[_cfg["cat_field"]] = None
    _ALL_PURCHASE_TAX_FIELDS[_cfg["taxbl_field"]] = 0.0
    _ALL_PURCHASE_TAX_FIELDS[_cfg["amt_field"]] = 0.0
