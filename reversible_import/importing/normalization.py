"""Deterministic document-state normalization and hashing for rollback.

The normalizer excludes volatile framework metadata so that two semantically
identical documents produce the same hash even if their `modified` timestamps
or internal Frappe fields differ.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

import frappe


VOLATILE_FIELDS = frozenset(
	{
		"name",
		"creation",
		"modified",
		"modified_by",
		"owner",
		"idx",
		"docstatus",
		"__islocal",
		"_user_tags",
		"_comments",
		"_assign",
		"_liked_by",
		"_seen",
	}
)

INTERNAL_PREFIXES = ("_",)


def normalize_document_state(doc_or_dict: Any, version: int = 1) -> dict[str, Any]:
	"""Return a deterministic, JSON-serializable dict representing document state."""
	if version != 1:
		raise ValueError(f"Unsupported normalization version: {version}")

	data = _coerce_to_dict(doc_or_dict)
	return _normalize_dict(data)


def hash_document_state(doc_or_dict: Any, version: int = 1) -> str:
	"""Return a SHA-256 hex digest of the normalized document state."""
	normalized = normalize_document_state(doc_or_dict, version=version)
	canonical = json.dumps(normalized, sort_keys=True, separators=(",", ":"), default=_json_default)
	return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _coerce_to_dict(doc_or_dict: Any) -> dict[str, Any]:
	if isinstance(doc_or_dict, dict):
		return dict(doc_or_dict)
	if hasattr(doc_or_dict, "as_dict"):
		return doc_or_dict.as_dict()
	raise TypeError(f"Cannot normalize document state of type {type(doc_or_dict)}")


def _normalize_dict(data: dict[str, Any]) -> dict[str, Any]:
	out: dict[str, Any] = {}
	for key, value in sorted(data.items()):
		if key in VOLATILE_FIELDS or key.startswith(INTERNAL_PREFIXES):
			continue
		out[key] = _normalize_value(value)
	return out


def _normalize_value(value: Any) -> Any:
	if value is None:
		return None
	if isinstance(value, dict):
		return _normalize_dict(value)
	if isinstance(value, list | tuple):
		return [_normalize_value(v) for v in value]
	return _serialize_value(value)


def _serialize_value(value: Any) -> Any:
	if isinstance(value, datetime):
		return value.isoformat()
	if isinstance(value, date):
		return value.isoformat()
	if isinstance(value, time):
		return value.isoformat()
	if isinstance(value, Decimal):
		return str(value)
	if isinstance(value, bytes):
		return value.decode("utf-8", errors="replace")
	return value


def _json_default(value: Any) -> Any:
	return _serialize_value(value)
