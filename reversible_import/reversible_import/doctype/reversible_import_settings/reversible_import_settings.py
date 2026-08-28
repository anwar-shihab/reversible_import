# Copyright (c) 2026, Anwar Shihab and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ReversibleImportSettings(Document):
	@classmethod
	def get_allowed_doctypes(cls) -> list[str]:
		"""Return the list of whitelisted DocType names."""
		settings = frappe.get_doc("Reversible Import Settings")
		return [row.doctype for row in settings.allowed_doctypes if row.doctype]
