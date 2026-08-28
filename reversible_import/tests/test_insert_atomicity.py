from __future__ import annotations

from unittest.mock import patch

import frappe

from reversible_import.importing.operation_service import process_insert_payload
from reversible_import.importing.runner import run_import


class TestInsertAtomicity:
    def test_failure_after_insert_rolls_back_document(self, note_import_run):
        """If journal creation fails after document insert, the doc must not persist."""
        calls = {"count": 0}

        def _fail_after_insert(run, payload, sequence):
            process_insert_payload(run, payload, sequence)
            calls["count"] += 1
            raise RuntimeError("Simulated journal failure")

        with patch("reversible_import.importing.runner.process_insert_payload", side_effect=_fail_after_insert):
            run_import(note_import_run.name)

        run = frappe.get_doc("Reversible Data Import", note_import_run.name)
        assert run.failed_payloads == 3
        assert run.successful_payloads == 0

        # No Note documents should remain from this run.
        operations = frappe.get_all(
            "Reversible Import Operation",
            filters={"import_run": run.name},
        )
        assert len(operations) == 3
        for op in operations:
            doc = frappe.get_doc("Reversible Import Operation", op.name)
            assert doc.status == "Failed"
            if doc.docname:
                assert not frappe.db.exists("Note", doc.docname)
