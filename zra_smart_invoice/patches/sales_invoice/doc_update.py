import frappe
from frappe.model.document import Document
import json

def updated_doc_if_needed(self):
	doc = self.doc
	items = doc.items
	for item in items:
		item_tax_template = item.item_tax_template
		tax_template = frappe.get_doc("Item Tax Template", item_tax_template)
		title = tax_template.title
		categories_part = title.split("|")[-1].strip()
		categories = [c.strip() for c in categories_part.split(",") if c.strip()]
		if "Insurance Premium Levy" in categories:
			item_tax_rate = json.loads(item.item_tax_rate) if item.item_tax_rate else {}
			if item_tax_rate:
				index = categories.index("Insurance Premium Levy")
				keys = list(item_tax_rate.keys())
				if index < len(keys):
					key_to_keep = keys[index]
					item_tax_rate = {key_to_keep: item_tax_rate[key_to_keep]}
					item.item_tax_rate = json.dumps(item_tax_rate)
	return self