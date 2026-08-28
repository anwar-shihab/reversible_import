"""Fallback strategy that refuses to roll back."""

from __future__ import annotations

from reversible_import.exceptions import ReversibleImportError
from reversible_import.rollback.base_strategy import RollbackStrategy


class ForbiddenStrategy(RollbackStrategy):
	"""Strategy used when no safe rollback strategy exists."""

	is_forbidden = True

	def guard(self, operation) -> None:
		raise ReversibleImportError("Rollback is unsupported for this DocType.")

	def rollback(self, operation) -> None:
		raise ReversibleImportError("Rollback is unsupported for this DocType.")
