from __future__ import annotations

import frappe

import pytest

from reversible_import import api


class TestPermissions:
    def test_preview_requires_permission(self, reversible_settings, sample_file):
        run = frappe.get_doc(
            {
                "doctype": "Reversible Data Import",
                "reference_doctype": "Note",
                "import_type": "Insert New Records",
                "import_file": sample_file("notes.csv"),
            }
        )
        run.insert(ignore_permissions=True)
        frappe.db.commit()

        # Guest user should not be able to call the API.
        frappe.set_user("Guest")
        with pytest.raises(frappe.PermissionError):
            api.preview(run.name)
        frappe.set_user("Administrator")
