"""Create journal operations for successfully imported payloads."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import frappe

from reversible_import.exceptions import ReversibleImportError
from reversible_import.importing.normalization import hash_document_state, normalize_document_state
from reversible_import.rollback.registry import resolve_strategy


def process_insert_payload(run, payload: dict[str, Any], sequence: int):
	"""Insert a document and create the corresponding Applied journal operation.

    The document insert and journal creation happen inside the caller's
    transaction boundary; this function does not commit.
    """
	strategy = resolve_strategy(run.reference_doctype, run.import_type)
	if strategy.is_forbidden:
		raise ReversibleImportError(
			f"Rollback is unsupported for {run.reference_doctype}; import aborted."
		)

	doc = payload["doc"]
	new_doc = frappe.get_doc(doc).insert()

	# Reload to capture defaults and any server-side mutations.
	persisted = frappe.get_doc(run.reference_doctype, new_doc.name)

	operation_key = _make_operation_key(run.name, sequence, payload)
	operation = frappe.get_doc(
		{
			"doctype": "Reversible Import Operation",
			"import_run": run.name,
			"sequence": sequence,
			"operation_key": operation_key,
			"row_indexes": json.dumps(payload.get("row_indexes", [])),
			"source_key": _make_source_key(payload),
			"operation": "INSERT",
			"doctype": run.reference_doctype,
			"docname": persisted.name,
			"status": "Applied",
			"after_values": json.dumps(normalize_document_state(persisted)),
			"after_hash": hash_document_state(persisted),
			"modified_after": persisted.modified,
			"rollback_status": "Pending",
		}
	)
	operation.insert(ignore_permissions=True)
	return operation


def record_failed_payload(run, payload: dict[str, Any], sequence: int, exception: Exception):
	"""Create a Failed journal operation for a payload that could not be imported."""
	operation_key = _make_operation_key(run.name, sequence, payload)
	operation = frappe.get_doc(
		{
			"doctype": "Reversible Import Operation",
			"import_run": run.name,
			"sequence": sequence,
			"operation_key": operation_key,
			"row_indexes": json.dumps(payload.get("row_indexes", [])),
			"source_key": _make_source_key(payload),
			"operation": "INSERT",
			"doctype": run.reference_doctype,
			"docname": "",
			"status": "Failed",
			"after_values": json.dumps({}),
			"after_hash": "",
			"rollback_status": "Pending",
		}
	)
	operation.insert(ignore_permissions=True)
	return operation


def _make_operation_key(run_name: str, sequence: int, payload: dict[str, Any]) -> str:
	hasher = hashlib.sha256()
	hasher.update(run_name.encode("utf-8"))
	hasher.update(str(sequence).encode("utf-8"))
	hasher.update(json.dumps(payload.get("row_indexes", []), sort_keys=True).encode("utf-8"))
	hasher.update("INSERT".encode("utf-8"))
	return hasher.hexdigest()


def _make_source_key(payload: dict[str, Any]) -> str:
	# Future: derive from source_system mapping; for now use payload name if present.
	return str(payload.get("name") or "")
