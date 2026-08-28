"""Background import runner."""

from __future__ import annotations

import json
from typing import Any

import frappe

from reversible_import.compat.registry import get_adapter
from reversible_import.importing.operation_service import (
	process_insert_payload,
	record_failed_payload,
)


@frappe.whitelist()
def run_import(run_name: str) -> None:
	"""Execute or resume a reversible import run.

    This function is designed to be enqueued as a background job.  It runs
    payload by payload, committing after each successful operation so that
    progress is durable and resume is safe.
    """
	run = frappe.get_doc("Reversible Data Import", run_name)
	_reconcile_run(run)

	if run.execution_status in {"Success", "Failed", "Stopped"}:
		return

	# Move from terminal-but-resumable states back into Running.
	if run.execution_status in {"Validated", "Queued", "Partial Success"}:
		run.execution_status = "Running"
		run.save()
		frappe.db.commit()

	settings = frappe.get_doc("Reversible Import Settings")
	payloads = _get_payloads(run)
	run.total_payloads = len(payloads)

	successful = run.successful_payloads or 0
	failed = run.failed_payloads or 0
	stop_requested = False

	for sequence, payload in enumerate(payloads, start=1):
		run.reload()
		if run.cancel_requested:
			stop_requested = True
			break

		operation_key = _operation_key(run.name, sequence, payload)
		if frappe.db.exists("Reversible Import Operation", {"operation_key": operation_key, "status": "Applied"}):
			successful += 1
			continue

		try:
			frappe.db.savepoint("payload_operation")
			process_insert_payload(run, payload, sequence)
			successful += 1
			frappe.db.commit()
		except Exception:
			frappe.db.rollback(save_point="payload_operation")
			failed += 1
			try:
				record_failed_payload(run, payload, sequence, None)
				frappe.db.commit()
			except Exception:
				frappe.db.rollback()

			if run.failure_policy == "Stop on First Error":
				break

		run.successful_payloads = successful
		run.failed_payloads = failed
		run.save()
		frappe.db.commit()

	if stop_requested:
		run.execution_status = "Stopped"
	elif failed == 0:
		run.execution_status = "Success"
	elif successful == 0:
		run.execution_status = "Failed"
	else:
		run.execution_status = "Partial Success"

	run.successful_payloads = successful
	run.failed_payloads = failed
	run.completed_at = frappe.utils.now()
	run.save()
	frappe.db.commit()


def _get_payloads(run) -> list[dict[str, Any]]:
	adapter = get_adapter()
	file_path = run.import_file
	template_options = json.loads(run.template_options) if run.template_options else None
	return adapter.get_payloads(
		run.reference_doctype,
		file_path,
		run.import_type,
		template_options=template_options,
	)


def _reconcile_run(run) -> None:
	"""Correct lightweight counters from the authoritative journal."""
	applied = frappe.db.count(
		"Reversible Import Operation",
		{"import_run": run.name, "status": "Applied"},
	)
	failed = frappe.db.count(
		"Reversible Import Operation",
		{"import_run": run.name, "status": "Failed"},
	)
	if run.successful_payloads != applied or run.failed_payloads != failed:
		run.successful_payloads = applied
		run.failed_payloads = failed
		run.save()
		frappe.db.commit()


def _operation_key(run_name: str, sequence: int, payload: dict[str, Any]) -> str:
	import hashlib

	hasher = hashlib.sha256()
	hasher.update(run_name.encode("utf-8"))
	hasher.update(str(sequence).encode("utf-8"))
	hasher.update(json.dumps(payload.get("row_indexes", []), sort_keys=True).encode("utf-8"))
	hasher.update("INSERT".encode("utf-8"))
	return hasher.hexdigest()
