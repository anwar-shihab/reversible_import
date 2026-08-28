from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

from reversible_import.importing.normalization import (
	hash_document_state,
	normalize_document_state,
)


class TestNormalization:
	def test_volatile_fields_are_excluded(self):
		state = normalize_document_state(
			{
				"name": "CUST-001",
				"customer_name": "Acme",
				"creation": datetime(2024, 1, 1, 10, 0, 0),
				"modified": datetime(2024, 1, 2, 10, 0, 0),
				"modified_by": "Administrator",
				"owner": "Administrator",
				"idx": 1,
				"docstatus": 0,
				"_user_tags": "tag",
			}
		)
		assert state == {"customer_name": "Acme"}

	def test_nested_dicts_are_normalized(self):
		state = normalize_document_state(
			{
				"name": "PARENT",
				"first_name": "John",
				"child": {"name": "CHILD", "email_id": "john@example.com", "modified": datetime.now()},
			}
		)
		assert state == {"child": {"email_id": "john@example.com"}, "first_name": "John"}

	def test_lists_are_normalized(self):
		state = normalize_document_state(
			{
				"name": "PARENT",
				"items": [
					{"name": "A", "value": 1, "modified": datetime.now()},
					{"name": "B", "value": 2, "modified": datetime.now()},
				],
			}
		)
		assert state == {"items": [{"value": 1}, {"value": 2}]}

	def test_special_types_are_serialized(self):
		state = normalize_document_state(
			{
				"customer_name": "Acme",
				"credit_limit": Decimal("10000.50"),
				"birth_date": date(1990, 5, 15),
				"last_order": datetime(2024, 1, 1, 12, 30, 45),
				"preferred_time": time(9, 0),
			}
		)
		assert state["credit_limit"] == "10000.50"
		assert state["birth_date"] == "1990-05-15"
		assert state["last_order"] == "2024-01-01T12:30:45"
		assert state["preferred_time"] == "09:00:00"

	def test_hash_is_deterministic(self):
		hash1 = hash_document_state({"name": "A", "value": 1, "modified": datetime.now()})
		hash2 = hash_document_state({"name": "B", "value": 1, "modified": datetime(2099, 1, 1)})
		assert hash1 == hash2

	def test_different_states_yield_different_hashes(self):
		hash1 = hash_document_state({"value": 1})
		hash2 = hash_document_state({"value": 2})
		assert hash1 != hash2
