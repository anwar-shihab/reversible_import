"""Application-specific exceptions."""

from __future__ import annotations


class ReversibleImportError(Exception):
	"""Base exception for reversible import errors."""


class RollbackConflictError(ReversibleImportError):
	"""Raised when rollback cannot proceed safely because the document changed."""


class RollbackFailedError(ReversibleImportError):
	"""Raised when rollback compensation fails."""
