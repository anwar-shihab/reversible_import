"""Whitelisted API endpoints for reversible imports."""

from __future__ import annotations

from typing import Any

import frappe

from reversible_import.importing.runner import run_import
from reversible_import.rollback.engine import execute_rollback


@frappe.whitelist()
def preview(run_name: str) -> dict[str, Any]:
	"""Validate file and return preview metadata."""
	frappe.has_permission("Reversible Data Import", doc=run_name, throw=True)
	run = frappe.get_doc("Reversible Data Import", run_name)
	return run.validate_file_and_preview()


@frappe.whitelist()
def start_import(run_name: str) -> dict[str, str]:
	"""Enqueue the import runner for a run."""
	frappe.has_permission("Reversible Data Import", doc=run_name, throw=True)
	run = frappe.get_doc("Reversible Data Import", run_name)
	run.start_import()
	return {"status": run.execution_status, "job_id": f"reversible_import||{run.name}"}


@frappe.whitelist()
def request_cancel(run_name: str) -> dict[str, str]:
	"""Request cooperative cancellation of a running import."""
	frappe.has_permission("Reversible Data Import", doc=run_name, throw=True)
	run = frappe.get_doc("Reversible Data Import", run_name)
	run.request_cancel()
	return {"status": run.execution_status}


@frappe.whitelist()
def request_rollback(run_name: str) -> dict[str, str]:
	"""Enqueue rollback for a run."""
	frappe.has_permission("Reversible Data Import", doc=run_name, throw=True)
	run = frappe.get_doc("Reversible Data Import", run_name)
	run.request_rollback()
	return {"status": run.rollback_status, "job_id": f"reversible_rollback||{run.name}"}


@frappe.whitelist()
def retry_rollback(run_name: str) -> dict[str, str]:
	"""Retry a rollback that ended in Partial, Conflict, or Failed state."""
	frappe.has_permission("Reversible Data Import", doc=run_name, throw=True)
	run = frappe.get_doc("Reversible Data Import", run_name)
	if run.rollback_status not in {"Partial", "Conflict", "Failed"}:
		frappe.throw(f"Rollback cannot be retried from status '{run.rollback_status}'.")
	run.rollback_status = "Queued"
	run.save()
	frappe.db.commit()
	frappe.enqueue(
		method=execute_rollback,
		queue="long",
		job_id=f"reversible_rollback||{run.name}",
		run_name=run.name,
	)
	return {"status": run.rollback_status, "job_id": f"reversible_rollback||{run.name}"}


@frappe.whitelist()
def get_progress(run_name: str) -> dict[str, Any]:
	"""Return current run counters and statuses."""
	frappe.has_permission("Reversible Data Import", doc=run_name, throw=True)
	run = frappe.get_doc("Reversible Data Import", run_name)
	return {
		"execution_status": run.execution_status,
		"rollback_status": run.rollback_status,
		"total_payloads": run.total_payloads,
		"successful_payloads": run.successful_payloads,
		"failed_payloads": run.failed_payloads,
		"cancel_requested": run.cancel_requested,
		"rollback_requested": run.rollback_requested,
	}
