# Copyright (c) 2026, Anwar Shihab and contributors
# For license information, please see license.txt

from __future__ import annotations

import hashlib
import json
from typing import Any

import frappe
from frappe.model.document import Document

from reversible_import.importing.runner import run_import
from reversible_import.rollback.engine import execute_rollback


EXECUTION_STATUSES = {
	"Draft",
	"Validated",
	"Queued",
	"Running",
	"Stop Requested",
	"Stopped",
	"Success",
	"Partial Success",
	"Failed",
}

ROLLBACK_STATUSES = {
	"Not Requested",
	"Queued",
	"Running",
	"Complete",
	"Partial",
	"Conflict",
	"Failed",
}

# Valid transitions for execution_status: current -> {allowed next statuses}
EXECUTION_TRANSITIONS: dict[str, set[str]] = {
	"Draft": {"Validated"},
	"Validated": {"Queued", "Draft"},
	"Queued": {"Running", "Stopped", "Failed"},
	"Running": {"Stop Requested", "Stopped", "Success", "Partial Success", "Failed"},
	"Stop Requested": {"Stopped", "Success", "Partial Success", "Failed"},
	"Stopped": {"Queued"},
	"Success": set(),
	"Partial Success": {"Queued"},
	"Failed": {"Queued"},
}

ROLLBACK_TRANSITIONS: dict[str, set[str]] = {
	"Not Requested": {"Queued"},
	"Queued": {"Running", "Not Requested"},
	"Running": {"Complete", "Partial", "Conflict", "Failed"},
	"Complete": set(),
	"Partial": {"Queued"},
	"Conflict": {"Queued"},
	"Failed": {"Queued"},
}


class ReversibleDataImport(Document):
	def validate(self):
		from reversible_import.doctype.reversible_import_settings.reversible_import_settings import (
			ReversibleImportSettings,
		)
		from reversible_import.rollback.registry import resolve_strategy

		if self.is_new() or self.has_value_changed("reference_doctype"):
			allowed = ReversibleImportSettings.get_allowed_doctypes()
			if self.reference_doctype not in allowed:
				frappe.throw(
					f"DocType '{self.reference_doctype}' is not enabled for reversible imports.",
					title="Unsupported DocType",
				)

		if self.import_type != "Insert New Records":
			frappe.throw("Only 'Insert New Records' is supported in Phase 1.")

		strategy = resolve_strategy(self.reference_doctype, self.import_type)
		if strategy.is_forbidden:
			frappe.throw(f"Rollback is not supported for {self.reference_doctype} {self.import_type}.")

		if self.import_file:
			self._compute_file_hash()

	def before_insert(self):
		if not self.requested_by:
			self.requested_by = frappe.session.user
		if not self.app_version:
			self.app_version = frappe.get_attr("reversible_import.__version__") or "0.0.1"
		if not self.frappe_version:
			self.frappe_version = frappe.__version__

	def _compute_file_hash(self):
		file_doc = frappe.get_doc("File", {"file_url": self.import_file})
		content = file_doc.get_content()
		self.file_hash = hashlib.sha256(content.encode("utf-8") if isinstance(content, str) else content).hexdigest()

	def validate_file_and_preview(self) -> dict[str, Any]:
		from reversible_import.compat.registry import get_adapter

		self._ensure_transition("execution_status", "Draft", "Validated")
		adapter = get_adapter()
		file_path = self._resolve_file_path()
		preview = adapter.get_preview(
			self.reference_doctype,
			file_path,
			self.import_type,
			template_options=self._template_options(),
		)
		self.total_payloads = preview["total_payloads"]
		self.execution_status = "Validated"
		self.save()
		return {
			"total_payloads": preview["total_payloads"],
			"total_rows": preview["total_rows"],
			"warnings": preview.get("warnings", []),
			"rollback_support": "FULL",
		}

	def start_import(self):
		self._ensure_transition("execution_status", "Validated", "Queued")
		self.started_at = frappe.utils.now()
		self.execution_status = "Queued"
		self.save()
		frappe.db.commit()
		job_id = f"reversible_import||{self.name}"
		frappe.enqueue(
			method=run_import,
			queue="long",
			job_id=job_id,
			run_name=self.name,
		)

	def request_cancel(self):
		if self.execution_status not in {"Running", "Queued", "Stop Requested"}:
			frappe.throw(f"Cannot cancel import in status '{self.execution_status}'.")
		self.cancel_requested = 1
		if self.execution_status == "Queued":
			self.execution_status = "Stopped"
		else:
			self.execution_status = "Stop Requested"
		self.save()

	def request_rollback(self):
		self._ensure_transition("rollback_status", "Not Requested", "Queued")
		self.rollback_requested = 1
		self.rollback_status = "Queued"
		self.save()
		frappe.db.commit()
		job_id = f"reversible_rollback||{self.name}"
		frappe.enqueue(
			method=execute_rollback,
			queue="long",
			job_id=job_id,
			run_name=self.name,
		)

	def _resolve_file_path(self) -> str:
		if not self.import_file:
			frappe.throw("Import file is required.")
		return self.import_file

	def _template_options(self) -> dict[str, Any] | None:
		if self.template_options:
			return json.loads(self.template_options)
		return None

	def _ensure_transition(self, field: str, current: str, next_status: str):
		transitions = EXECUTION_TRANSITIONS if field == "execution_status" else ROLLBACK_TRANSITIONS
		statuses = EXECUTION_STATUSES if field == "execution_status" else ROLLBACK_STATUSES
		actual = self.get(field)
		if actual != current:
			frappe.throw(f"Invalid transition: {field} is '{actual}', expected '{current}'.")
		if next_status not in transitions.get(current, statuses):
			frappe.throw(f"Invalid transition: {field} cannot move from '{current}' to '{next_status}'.")

	@frappe.whitelist()
	def preview(self):
		return self.validate_file_and_preview()

	@frappe.whitelist()
	def start(self):
		self.start_import()

	@frappe.whitelist()
	def cancel(self):
		self.request_cancel()

	@frappe.whitelist()
	def rollback(self):
		self.request_rollback()
