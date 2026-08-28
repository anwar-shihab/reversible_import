from __future__ import annotations

import frappe

import pytest


class TestStateMachine:
    def test_unsupported_import_type_is_rejected(self, reversible_settings):
        with pytest.raises(frappe.ValidationError):
            frappe.get_doc(
                {
                    "doctype": "Reversible Data Import",
                    "reference_doctype": "Note",
                    "import_type": "Update Existing Records",
                    "import_file": "/files/placeholder.csv",
                }
            ).insert(ignore_permissions=True)

    def test_unallowed_doctype_is_rejected(self, reversible_settings):
        with pytest.raises(frappe.ValidationError):
            frappe.get_doc(
                {
                    "doctype": "Reversible Data Import",
                    "reference_doctype": "Sales Invoice",
                    "import_type": "Insert New Records",
                    "import_file": "/files/placeholder.csv",
                }
            ).insert(ignore_permissions=True)
