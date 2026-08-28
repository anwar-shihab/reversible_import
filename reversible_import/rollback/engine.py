"""Rollback engine."""

from __future__ import annotations

import traceback

import frappe

from reversible_import.exceptions import RollbackConflictError, RollbackFailedError
from reversible_import.rollback.registry import resolve_strategy


@frappe.whitelist()
def execute_rollback(run_name: str) -> None:
	"""Execute rollback for a reversible import run.

    Processes operations in reverse sequence, committing after each one.
    """
	run = frappe.get_doc("Reversible Data Import", run_name)

	if run.rollback_status not in {"Not Requested", "Queued", "Partial", "Conflict", "Failed"}:
		frappe.throw(f"Rollback cannot start from status '{run.rollback_status}'.")

	run.rollback_status = "Running"
	run.save()
	frappe.db.commit()

	operations = frappe.get_all(
		"Reversible Import Operation",
		filters={
			"import_run": run.name,
			"status": "Applied",
			"rollback_status": ["!=", "Rolled Back"],
		},
		order_by="sequence DESC",
		pluck="name",
	)

	success = conflict = failed = 0

	for operation_name in operations:
		operation = frappe.get_doc("Reversible Import Operation", operation_name)
		strategy = resolve_strategy(operation.reference_doctype, _map_operation_to_import_type(operation.operation))

		try:
			frappe.db.savepoint("rollback_operation")
			strategy.guard(operation)
			strategy.rollback(operation)
			operation.rollback_status = "Rolled Back"
			operation.rolled_back_at = frappe.utils.now()
			operation.save()
			success += 1
			frappe.db.commit()
		except RollbackConflictError as exc:
			frappe.db.rollback(save_point="rollback_operation")
			operation.rollback_status = "Conflict"
			operation.last_rollback_error = str(exc)
			operation.rollback_attempt_count = (operation.rollback_attempt_count or 0) + 1
			operation.save()
			frappe.db.commit()
			conflict += 1
		except RollbackFailedError as exc:
			frappe.db.rollback(save_point="rollback_operation")
			operation.rollback_status = "Failed"
			operation.last_rollback_error = str(exc)
			operation.rollback_attempt_count = (operation.rollback_attempt_count or 0) + 1
			operation.save()
			frappe.db.commit()
			failed += 1
		except Exception as exc:
			frappe.db.rollback(save_point="rollback_operation")
			operation.rollback_status = "Failed"
			operation.last_rollback_error = f"{exc}\n{traceback.format_exc()}"
			operation.rollback_attempt_count = (operation.rollback_attempt_count or 0) + 1
			operation.save()
			frappe.db.commit()
			failed += 1

	if failed == 0 and conflict == 0:
		run.rollback_status = "Complete"
	elif success == 0 and failed > 0:
		run.rollback_status = "Failed"
	elif conflict > 0 and failed == 0:
		run.rollback_status = "Conflict"
	else:
		run.rollback_status = "Partial"

	run.save()
	frappe.db.commit()


def _map_operation_to_import_type(operation: str) -> str:
	return "Insert New Records" if operation == "INSERT" else "Update Existing Records"
