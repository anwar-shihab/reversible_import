from __future__ import annotations

import frappe
import pytest

from reversible_import.importing.runner import run_import
from reversible_import.rollback.engine import execute_rollback


class TestInsertIntegration:
    def test_import_creates_documents_and_journal(self, note_import_run):
        run_import(note_import_run.name)
        run = frappe.get_doc("Reversible Data Import", note_import_run.name)

        assert run.execution_status == "Success"
        assert run.successful_payloads == 3
        assert run.failed_payloads == 0

        operations = frappe.get_all(
            "Reversible Import Operation",
            filters={"import_run": run.name},
            order_by="sequence ASC",
        )
        assert len(operations) == 3
        for op in operations:
            doc = frappe.get_doc("Reversible Import Operation", op.name)
            assert doc.status == "Applied"
            assert doc.operation == "INSERT"
            assert doc.reference_doctype == "Note"
            assert frappe.db.exists("Note", doc.docname)

        assert frappe.db.exists("Note", {"title": "Test Note A"})
        assert frappe.db.exists("Note", {"title": "Test Note B"})
        assert frappe.db.exists("Note", {"title": "Test Note C"})

    def test_rollback_deletes_documents_and_marks_journal(self, note_import_run):
        run_import(note_import_run.name)
        run = frappe.get_doc("Reversible Data Import", note_import_run.name)

        execute_rollback(run.name)
        run.reload()

        if run.rollback_status != "Complete":
            operations = frappe.get_all(
                "Reversible Import Operation",
                filters={"import_run": run.name},
                fields=["name", "sequence", "rollback_status", "last_rollback_error"],
                order_by="sequence ASC",
            )
            details = "\n".join(
                f"seq {op.sequence}: {op.rollback_status} - {op.last_rollback_error}"
                for op in operations
            )
            pytest.fail(f"Rollback ended with {run.rollback_status}:\n{details}")

        operations = frappe.get_all(
            "Reversible Import Operation",
            filters={"import_run": run.name},
            order_by="sequence ASC",
        )
        for op in operations:
            doc = frappe.get_doc("Reversible Import Operation", op.name)
            assert doc.rollback_status == "Rolled Back"
            assert not frappe.db.exists("Note", doc.docname)

        assert not frappe.db.exists("Note", {"title": "Test Note A"})
        assert not frappe.db.exists("Note", {"title": "Test Note B"})
        assert not frappe.db.exists("Note", {"title": "Test Note C"})
