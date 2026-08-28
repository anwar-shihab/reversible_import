from __future__ import annotations

import json
import os
from pathlib import Path

import frappe

import pytest

from reversible_import.compat.registry import get_adapter


def pytest_sessionstart(session: pytest.Session) -> None:
    """Initialise Frappe and connect to the test site before any tests run.

    Using a session-start hook guarantees that site context is established in
    the same execution context that the tests will use.  This is more reliable
    than a session-scoped autouse fixture for Frappe, whose ``frappe.local``
    state is stored in thread-local / context-var storage.
    """
    site = os.environ.get("FRAPPE_SITE", "test_site")
    sites_path = os.environ.get("FRAPPE_SITES_PATH", os.path.abspath("sites"))
    os.environ.setdefault("FRAPPE_SITES_PATH", sites_path)

    frappe.init(site, sites_path=sites_path, force=True)
    frappe.connect()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Clean up the Frappe site connection after all tests finish."""
    try:
        frappe.destroy()
    except Exception:
        pass


@pytest.fixture(scope="session")
def frappe_site() -> str:
    """Return the name of the current Frappe test site.

    Actual initialisation is performed in :func:`pytest_sessionstart`; this
    fixture exists so that other fixtures can express an explicit dependency on
    the site being ready.
    """
    return os.environ.get("FRAPPE_SITE", "test_site")


@pytest.fixture(scope="session")
def site_name(frappe_site) -> str:
    """Return the current Frappe site name."""
    return frappe_site


@pytest.fixture(scope="session")
def frappe_version() -> tuple[int, int, int]:
    """Return the currently installed Frappe version as (major, minor, patch)."""
    return tuple(int(p) for p in frappe.__version__.split(".")[:3])


@pytest.fixture(scope="session")
def adapter(frappe_site):
    """Return the ImportAdapter subclass matching the current Frappe version."""
    return get_adapter()


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """Return the absolute path to the test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def reversible_settings():
    """Create default Reversible Import Settings with Note whitelisted for tests."""
    if not frappe.db.exists("Reversible Import Settings"):
        settings = frappe.get_doc(
            {
                "doctype": "Reversible Import Settings",
                "heartbeat_timeout_seconds": 300,
                "progress_event_interval_ops": 25,
                "progress_event_interval_seconds": 1,
            }
        )
        settings.insert(ignore_permissions=True)
    else:
        settings = frappe.get_doc("Reversible Import Settings")

    existing = {row.get("allowed_doctype") for row in settings.allowed_doctypes}
    if "Note" not in existing:
        settings.append("allowed_doctypes", {"allowed_doctype": "Note"})
        settings.save(ignore_permissions=True)
        frappe.db.commit()
    return settings


@pytest.fixture(scope="session")
def sample_file(fixtures_dir: Path):
    """Return a Frappe file_url for a named fixture file.

    Frappe's Data Import parser reads binary .xlsx files through the File
    doctype, so local disk paths only work for CSV when console=True.  Uploading
    fixtures once per session gives the adapter a proper file_url for both CSV
    and XLSX fixtures.
    """
    _cache: dict[str, str] = {}

    def _resolve(filename: str) -> str:
        if filename in _cache:
            return _cache[filename]

        path = fixtures_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Fixture not found: {path}")

        file_doc = frappe.get_doc(
            {
                "doctype": "File",
                "file_name": path.name,
                "content": path.read_bytes(),
                "is_private": 0,
            }
        )
        file_doc.insert(ignore_permissions=True)
        frappe.db.commit()

        _cache[filename] = file_doc.file_url
        return file_doc.file_url

    return _resolve


@pytest.fixture
def note_import_run(reversible_settings, sample_file):
    """Create a Reversible Data Import for the Note DocType."""
    run = frappe.get_doc(
        {
            "doctype": "Reversible Data Import",
            "reference_doctype": "Note",
            "import_type": "Insert New Records",
            "import_file": sample_file("notes.csv"),
            "source_system": "CSV",
            "template_options": json.dumps(
                {"column_to_field_map": {"0": "title", "1": "content"}}
            ),
            "failure_policy": "Continue on Error",
        }
    )
    run.insert(ignore_permissions=True)
    frappe.db.commit()
    run.validate_file_and_preview()
    return run
