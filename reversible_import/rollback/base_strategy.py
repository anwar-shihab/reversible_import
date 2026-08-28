"""Abstract base class for rollback strategies."""

from __future__ import annotations

from abc import ABC, abstractmethod


class RollbackStrategy(ABC):
	"""A rollback strategy knows how to safely reverse one import operation."""

	is_forbidden = False

	@abstractmethod
	def guard(self, operation) -> None:
		"""Raise RollbackConflict if reversing this operation is unsafe."""

	@abstractmethod
	def rollback(self, operation) -> None:
		"""Execute the compensating action. Raise RollbackFailedError on failure."""
