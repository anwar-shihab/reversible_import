import pytest

import frappe

from reversible_import.doctype.reversible_import_settings.reversible_import_settings import (
	ReversibleImportSettings,
)
from reversible_import.rollback.forbidden import ForbiddenStrategy
from reversible_import.rollback.master_insert import GenericMasterInsertStrategy
from reversible_import.rollback.registry import resolve_strategy


@pytest.fixture
def allow_note():
	settings = frappe.get_doc("Reversible Import Settings")
	settings.append("allowed_doctypes", {"doctype": "Note"})
	settings.save()
	frappe.db.commit()
	yield
	settings.allowed_doctypes = []
	settings.save()
	frappe.db.commit()


class TestStrategyRegistry:
	def test_allowed_doctype_insert_uses_generic_strategy(self, allow_note):
		strategy = resolve_strategy("Note", "Insert New Records")
		assert isinstance(strategy, GenericMasterInsertStrategy)

	def test_unallowed_doctype_is_forbidden(self):
		strategy = resolve_strategy("Note", "Insert New Records")
		assert isinstance(strategy, ForbiddenStrategy)
		assert strategy.is_forbidden

	def test_update_is_forbidden_in_phase_1(self, allow_note):
		strategy = resolve_strategy("Note", "Update Existing Records")
		assert isinstance(strategy, ForbiddenStrategy)
