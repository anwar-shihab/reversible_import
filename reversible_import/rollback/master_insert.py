"""Rollback strategy for inserted non-submittable master documents."""

from __future__ import annotations

import frappe

from reversible_import.exceptions import RollbackConflictError, RollbackFailedError
from reversible_import.importing.normalization import hash_document_state
from reversible_import.rollback.base_strategy import RollbackStrategy


class GenericMasterInsertStrategy(RollbackStrategy):
	"""Reverse an INSERT by deleting the created document.

    The guard verifies the document still exists and has not been modified
    since import.  Deletion itself is delegated to Frappe's normal document
    API so that link-validation rules are respected.
    """

	def guard(self, operation) -> None:
		if not frappe.db.exists(operation.doctype, operation.docname):
			raise RollbackConflictError(
				f"Document {operation.doctype} {operation.docname} no longer exists."
			)

		current = frappe.get_doc(operation.doctype, operation.docname)
		current_hash = hash_document_state(current)
		if current_hash != operation.after_hash:
			raise RollbackConflictError(
				f"Document {operation.doctype} {operation.docname} has been modified after import."
			)

	def rollback(self, operation) -> None:
		try:
			frappe.delete_doc(operation.doctype, operation.docname)
		except frappe.exceptions.LinkExistsError as exc:
			raise RollbackConflictError(
				f"Cannot delete {operation.doctype} {operation.docname}: linked documents exist."
			) from exc
		except Exception as exc:
			raise RollbackFailedError(
				f"Failed to delete {operation.doctype} {operation.docname}: {exc}"
			) from exc
