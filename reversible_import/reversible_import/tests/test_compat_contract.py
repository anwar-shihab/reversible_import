from __future__ import annotations

import json

import frappe

import pytest


def _contact_template_options():
    """Map generic CSV columns to Contact fields.

    Column indexes are strings because Frappe stores `column_to_field_map`
    keys as strings.
    """
    return {
        "column_to_field_map": {
            "0": "first_name",
            "1": "last_name",
            "2": "email_ids.email_id",
            "3": "email_ids.is_primary",
        }
    }


def _make_payload_key(payload: dict) -> tuple:
    """Stable key for comparing payloads across versions."""
    doc = payload.get("doc", {})
    emails = tuple(
        sorted(
            (e.get("email_id"), e.get("is_primary"))
            for e in doc.get("email_ids", [])
            if e.get("email_id")
        )
    )
    return (
        payload.get("doctype"),
        payload.get("name"),
        doc.get("first_name"),
        doc.get("last_name"),
        payload.get("row_indexes"),
        emails,
    )


class TestParserContract:
    """Contract tests that must pass on every supported Frappe version."""

    def test_validate_file_csv(self, adapter, sample_file):
        path = sample_file("contacts.csv")
        result = adapter.validate_file("Contact", path, "Insert New Records")
        assert result["file_type"] == "csv"
        assert result["total_rows"] == 3

    def test_validate_file_xlsx(self, adapter, sample_file):
        path = sample_file("contacts.xlsx")
        result = adapter.validate_file("Contact", path, "Insert New Records")
        assert result["file_type"] == "xlsx"
        assert result["total_rows"] == 3

    def test_simple_parent_payloads(self, adapter, sample_file):
        payloads = adapter.get_payloads(
            "Contact",
            sample_file("contacts.csv"),
            "Insert New Records",
            template_options=_contact_template_options(),
        )
        assert len(payloads) == 3
        for idx, payload in enumerate(payloads):
            assert payload["doctype"] == "Contact"
            assert payload["source_index"] == idx
            assert len(payload["row_indexes"]) == 1
            assert "first_name" in payload["doc"]

    def test_csv_and_xlsx_produce_equivalent_payloads(self, adapter, sample_file):
        template_options = _contact_template_options()
        csv_payloads = adapter.get_payloads(
            "Contact",
            sample_file("contacts.csv"),
            "Insert New Records",
            template_options=template_options,
        )
        xlsx_payloads = adapter.get_payloads(
            "Contact",
            sample_file("contacts.xlsx"),
            "Insert New Records",
            template_options=template_options,
        )
        assert len(csv_payloads) == len(xlsx_payloads)
        assert {_make_payload_key(p) for p in csv_payloads} == {
            _make_payload_key(p) for p in xlsx_payloads
        }

    def test_parent_with_child_rows(self, adapter, sample_file):
        payloads = adapter.get_payloads(
            "Contact",
            sample_file("contacts_with_emails.csv"),
            "Insert New Records",
            template_options=_contact_template_options(),
        )
        assert len(payloads) == 2

        by_name = {p["doc"].get("first_name"): p for p in payloads}
        assert "Alpha" in by_name
        assert "Beta" in by_name

        alpha = by_name["Alpha"]
        assert alpha["row_indexes"] == [2, 3]
        assert len(alpha["doc"].get("email_ids", [])) == 2

        beta = by_name["Beta"]
        assert beta["row_indexes"] == [4]
        assert len(beta["doc"].get("email_ids", [])) == 1

    def test_multiple_parent_records(self, adapter, sample_file):
        payloads = adapter.get_payloads(
            "Contact",
            sample_file("contacts_multi.csv"),
            "Insert New Records",
            template_options={"column_to_field_map": {"0": "first_name", "1": "last_name"}},
        )
        assert len(payloads) == 3
        assert [p["doc"].get("first_name") for p in payloads] == ["One", "Two", "Three"]

    def test_blank_child_rows_are_skipped(self, adapter, sample_file):
        payloads = adapter.get_payloads(
            "Contact",
            sample_file("contacts_blank_rows.csv"),
            "Insert New Records",
            template_options=_contact_template_options(),
        )
        assert len(payloads) == 1
        assert payloads[0]["doc"].get("first_name") == "Gamma"

    def test_utf8_and_arabic_text(self, adapter, sample_file):
        payloads = adapter.get_payloads(
            "Contact",
            sample_file("contacts_arabic.csv"),
            "Insert New Records",
            template_options={"column_to_field_map": {"0": "first_name", "1": "last_name"}},
        )
        assert len(payloads) == 2
        names = {p["doc"].get("first_name") for p in payloads}
        assert "دبي" in names
        assert "أبوظبي" in names

    def test_child_table_semantics_is_documented(self, adapter):
        semantics = adapter.describe_child_table_semantics()
        assert semantics in (
            "merged",
            "replaced",
            "left untouched",
            "replaced when supplied, left untouched when absent",
        )

    def test_preview_returns_summary(self, adapter, sample_file):
        preview = adapter.get_preview(
            "Contact",
            sample_file("contacts.csv"),
            "Insert New Records",
            template_options=_contact_template_options(),
        )
        assert preview["total_rows"] == 3
        assert preview["total_payloads"] == 3
        assert isinstance(preview["warnings"], list)
