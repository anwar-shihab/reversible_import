from __future__ import annotations

import frappe


class TestSettings:
    def test_allowed_doctypes_lookup(self, reversible_settings):
        settings = frappe.get_doc("Reversible Import Settings")
        allowed = [row.get("allowed_doctype") for row in settings.allowed_doctypes if row.get("allowed_doctype")]
        assert "Note" in allowed
