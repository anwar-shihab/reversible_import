from __future__ import annotations

import os
from pathlib import Path

import frappe

import pytest

from reversible_import.compat.registry import get_adapter


@pytest.fixture(scope="session", autouse=True)
def frappe_site() -> str:
    """Initialise Frappe and connect to the test site.

    The site name is read from the FRAPPE_SITE environment variable and
    defaults to ``test_site`` so CI can run pytest directly from the bench
    environment without ``bench run-tests``.
    """
    site = os.environ.get("FRAPPE_SITE", "test_site")
    frappe.init(site, sites_path="sites")
    frappe.connect()
    yield site
    frappe.destroy()


@pytest.fixture(scope="session")
def site_name(frappe_site) -> str:
    """Return the current Frappe site name."""
    return frappe_site


@pytest.fixture(scope="session")
def frappe_version() -> tuple[int, int, int]:
    """Return the currently installed Frappe version as (major, minor, patch)."""
    return tuple(int(p) for p in frappe.__version__.split(".")[:3])


@pytest.fixture(scope="session")
def adapter():
    """Return the ImportAdapter subclass matching the current Frappe version."""
    return get_adapter()


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """Return the absolute path to the test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_file(fixtures_dir: Path):
    """Return the absolute path to a named fixture file."""

    def _resolve(filename: str) -> str:
        path = fixtures_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Fixture not found: {path}")
        return str(path)

    return _resolve
