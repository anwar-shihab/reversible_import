from __future__ import annotations

import frappe

import pytest

from reversible_import.importing.runner import run_import


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


class TestCancellationAndResume:
	def test_cancel_stops_import_and_leaves_partial_journal(self, note_import_run):
		# Simulate cancellation after the first payload.
		original_runner = run_import.__wrapped__ if hasattr(run_import, "__wrapped__") else None

		def _process_then_cancel(run_name):
			# Process first payload, then request cancel, then continue.
			from reversible_import.importing.operation_service import process_insert_payload
			from reversible_import.compat.registry import get_adapter
			import json

			run = frappe.get_doc("Reversible Data Import", run_name)
			run.execution_status = "Running"
			run.save()
			frappe.db.commit()

			adapter = get_adapter()
			template_options = json.loads(run.template_options) if run.template_options else None
			payloads = adapter.get_payloads(
				run.reference_doctype, run.import_file, run.import_type, template_options=template_options
			)
			process_insert_payload(run, payloads[0], 1)
			run.cancel_requested = 1
			run.save()
			frappe.db.commit()

			# Continue the runner from where it left off.
			from reversible_import.importing.runner import run_import as real_runner

			real_runner(run_name)

		_process_then_cancel(note_import_run.name)

		run = frappe.get_doc("Reversible Data Import", note_import_run.name)
		assert run.execution_status == "Stopped"
		assert run.successful_payloads >= 1
		assert run.successful_payloads < 3

		operations = frappe.get_all(
			"Reversible Import Operation",
			filters={"import_run": run.name, "status": "Applied"},
		)
		assert len(operations) == run.successful_payloads

	def test_resume_skips_already_applied_operations(self, note_import_run):
		# Process one payload, then resume to completion.
		from reversible_import.importing.operation_service import process_insert_payload
		from reversible_import.compat.registry import get_adapter
		import json

		run = frappe.get_doc("Reversible Data Import", note_import_run.name)
		run.execution_status = "Running"
		run.save()
		frappe.db.commit()

		adapter = get_adapter()
		template_options = json.loads(run.template_options) if run.template_options else None
		payloads = adapter.get_payloads(
			run.reference_doctype, run.import_file, run.import_type, template_options=template_options
		)
		process_insert_payload(run, payloads[0], 1)
		run.successful_payloads = 1
		run.save()
		frappe.db.commit()

		run_import(run.name)
		run.reload()

		assert run.execution_status == "Success"
		assert run.successful_payloads == 3
		operations = frappe.get_all(
			"Reversible Import Operation",
			filters={"import_run": run.name, "status": "Applied"},
		)
		assert len(operations) == 3
