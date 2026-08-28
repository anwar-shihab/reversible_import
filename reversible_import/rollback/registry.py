"""Strategy resolution for rollback operations."""

from __future__ import annotations

import frappe

from reversible_import.rollback.base_strategy import RollbackStrategy
from reversible_import.rollback.forbidden import ForbiddenStrategy
from reversible_import.rollback.master_insert import GenericMasterInsertStrategy


class StrategyResolver:
	"""Resolves the rollback strategy for a given DocType and import operation."""

	def resolve(self, doctype: str, import_type: str) -> RollbackStrategy:
		if import_type != "Insert New Records":
			return ForbiddenStrategy()

		allowed = self._get_allowed_doctypes()
		if doctype in allowed:
			return GenericMasterInsertStrategy()
		return ForbiddenStrategy()

	def _get_allowed_doctypes(self) -> set[str]:
		try:
			settings = frappe.get_doc("Reversible Import Settings")
			return {row.doctype for row in settings.allowed_doctypes if row.doctype}
		except Exception:
			frappe.log_error("Failed to load reversible import settings whitelist")
			return set()


_default_resolver = StrategyResolver()


def resolve_strategy(doctype: str, import_type: str) -> RollbackStrategy:
	return _default_resolver.resolve(doctype, import_type)
