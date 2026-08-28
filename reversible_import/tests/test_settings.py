from __future__ import annotations

from reversible_import.doctype.reversible_import_settings.reversible_import_settings import (
    ReversibleImportSettings,
)


class TestSettings:
    def test_allowed_doctypes_lookup(self, reversible_settings):
        allowed = ReversibleImportSettings.get_allowed_doctypes()
        assert "Note" in allowed
