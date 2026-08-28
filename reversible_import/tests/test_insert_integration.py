from __future__ import annotations

import frappe

import pytest

from reversible_import.importing.runner import run_import
from reversible_import.rollback.engine import execute_rollback


@pytest.fixture
def note_import_run(reversible_settings, sample_file):
	file_url = sample_file("notes.csv")
	run = frappe.get_doc(
		{
			"doctype": "Reversible Data Import",
			"reference_doctype": "Note",
			"import_type": "Insert New Records",
			"import_file": file_url,
			"source_system": "CSV",
			"failure_policy": "Continue on Error",
		}
	)
	run.insert(ignore_permissions=True)
	frappe.db.commit()
	run.validate_file_and_preview()
	return run


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
			assert doc.doctype == "Note"
			assert frappe.db.exists("Note", doc.docname)

		assert frappe.db.exists("Note", "Test Note A")
		assert frappe.db.exists("Note", "Test Note B")
		assert frappe.db.exists("Note", "Test Note C")

	def test_rollback_deletes_documents_and_marks_journal(self, note_import_run):
		run_import(note_import_run.name)
		run = frappe.get_doc("Reversible Data Import", note_import_run.name)

		execute_rollback(run.name)
		run.reload()

		assert run.rollback_status == "Complete"

		operations = frappe.get_all(
			"Reversible Import Operation",
			filters={"import_run": run.name},
			order_by="sequence ASC",
		)
		for op in operations:
			doc = frappe.get_doc("Reversible Import Operation", op.name)
			assert doc.rollback_status == "Rolled Back"
			assert not frappe.db.exists("Note", doc.docname)

		assert not frappe.db.exists("Note", "Test Note A")
		assert not frappe.db.exists("Note", "Test Note B")
		assert not frappe.db.exists("Note", "Test Note C")
