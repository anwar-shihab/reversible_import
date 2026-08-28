from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class ImportAdapter(ABC):
    """Stable, application-owned interface for Frappe's Data Import parser.

    Only subclasses in `reversible_import.compat` may import Frappe's internal
    Data Import classes. The rest of the application must work against this
    interface so that parser differences between Frappe v15, v16, and future
    releases stay inside this module.
    """

    version_label: str

    @abstractmethod
    def validate_file(
        self,
        reference_doctype: str,
        import_file_path: str | Path,
        import_type: str,
        template_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Validate a source file and return basic metadata.

        Returns a dict with keys such as:
            - file_type: "csv" or "xlsx"
            - total_rows: int
            - errors: list[str]
        """

    @abstractmethod
    def get_preview(
        self,
        reference_doctype: str,
        import_file_path: str | Path,
        import_type: str,
        template_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return a preview summary without performing any import.

        Returns a dict with keys such as:
            - total_rows
            - total_payloads
            - warnings
        """

    @abstractmethod
    def get_payloads(
        self,
        reference_doctype: str,
        import_file_path: str | Path,
        import_type: str,
        template_options: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Return the list of document payloads parsed from the file.

        Each payload is a dict with at least:
            - doctype: destination DocType
            - name: document name (may be None for inserts)
            - row_indexes: list[int] — source row numbers grouped into this payload
            - doc: a plain dict representation of the document to import
            - source_index: int — zero-based payload sequence
        """

    @abstractmethod
    def describe_child_table_semantics(self) -> str:
        """Describe how this Frappe version treats child tables during update imports.

        Must be one of:
            - "merged"
            - "replaced"
            - "left untouched"
            - a composite statement such as "replaced when supplied, left untouched when absent"
        """

    def get_payload_row_indexes(self, payload: dict[str, Any]) -> list[int]:
        return payload.get("row_indexes", [])

    def _coerce_doc(self, doc: Any) -> dict[str, Any]:
        """Convert a Frappe Document or dict into a plain dict."""
        if isinstance(doc, dict):
            return dict(doc)
        if hasattr(doc, "as_dict"):
            return doc.as_dict()
        raise TypeError(f"Cannot coerce payload doc of type {type(doc)}")
