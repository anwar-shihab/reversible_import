from __future__ import annotations

from pathlib import Path
from typing import Any

from reversible_import.compat.base import ImportAdapter


class FutureAdapter(ImportAdapter):
    """Placeholder adapter for Frappe `develop` or future stable versions.

    This adapter refuses to perform operations that have not been explicitly
    verified on the running version. It is a safety guard against silent
    behavioral drift.
    """

    version_label = "future"

    def _raise(self, feature: str) -> None:
        raise NotImplementedError(
            f"{feature} is not yet supported for Frappe {self.version_label}. "
            "Add a dedicated adapter or extend an existing one after verifying parser behavior."
        )

    def validate_file(
        self,
        reference_doctype: str,
        import_file_path: str | Path,
        import_type: str,
        template_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._raise("validate_file")

    def get_preview(
        self,
        reference_doctype: str,
        import_file_path: str | Path,
        import_type: str,
        template_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._raise("get_preview")

    def get_payloads(
        self,
        reference_doctype: str,
        import_file_path: str | Path,
        import_type: str,
        template_options: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self._raise("get_payloads")

    def describe_child_table_semantics(self) -> str:
        self._raise("describe_child_table_semantics")
