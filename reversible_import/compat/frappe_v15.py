from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from reversible_import.compat.base import ImportAdapter


class FrappeV15Adapter(ImportAdapter):
    """Adapter for Frappe `version-15` Data Import parser."""

    version_label = "v15"

    def _make_importer(
        self,
        reference_doctype: str,
        import_file_path: str | Path,
        import_type: str,
        template_options: dict[str, Any] | None,
    ):
        import frappe
        from frappe.core.doctype.data_import.importer import Importer

        data_import = frappe.get_doc(
            {
                "doctype": "Data Import",
                "import_type": import_type,
                "template_options": json.dumps(template_options or {}),
            }
        )
        return Importer(
            reference_doctype,
            data_import=data_import,
            file_path=self._ensure_file_url(import_file_path),
        )

    def validate_file(
        self,
        reference_doctype: str,
        import_file_path: str | Path,
        import_type: str,
        template_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        importer = self._make_importer(
            reference_doctype, import_file_path, import_type, template_options
        )
        import_file = importer.import_file
        extension = Path(import_file_path).suffix.lstrip(".").lower()
        return {
            "file_type": extension,
            "total_rows": len(import_file.data),
            "errors": [w.get("message") for w in import_file.get_warnings() if w.get("type") == "error"],
        }

    def get_preview(
        self,
        reference_doctype: str,
        import_file_path: str | Path,
        import_type: str,
        template_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        importer = self._make_importer(
            reference_doctype, import_file_path, import_type, template_options
        )
        preview = importer.get_data_for_import_preview()
        return {
            "total_rows": len(importer.import_file.data),
            "total_payloads": len(importer.import_file.get_payloads_for_import()),
            "warnings": preview.warnings,
            "columns": preview.columns,
        }

    def get_payloads(
        self,
        reference_doctype: str,
        import_file_path: str | Path,
        import_type: str,
        template_options: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        importer = self._make_importer(
            reference_doctype, import_file_path, import_type, template_options
        )
        raw_payloads = importer.import_file.get_payloads_for_import()
        return [
            {
                "doctype": reference_doctype,
                "name": self._coerce_doc(payload.doc).get("name"),
                "row_indexes": [row.row_number for row in payload.rows],
                "doc": self._coerce_doc(payload.doc),
                "source_index": idx,
            }
            for idx, payload in enumerate(raw_payloads)
        ]

    def describe_child_table_semantics(self) -> str:
        return "replaced when supplied, left untouched when absent"
