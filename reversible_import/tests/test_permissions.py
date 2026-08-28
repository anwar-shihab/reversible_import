from __future__ import annotations

import frappe

import pytest

from reversible_import import api


class TestPermissions:
    def test_preview_requires_permission(self, note_import_run):
        # Guest user should not be able to call the API.
        frappe.set_user("Guest")
        with pytest.raises(frappe.PermissionError):
            api.preview(note_import_run.name)
        frappe.set_user("Administrator")
