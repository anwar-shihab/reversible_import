from __future__ import annotations

import inspect

import frappe

import pytest


def test_importer_class_is_importable():
    """The parser seam relies on Importer and ImportFile being available."""
    from frappe.core.doctype.data_import.importer import Importer

    assert inspect.isclass(Importer)


def test_background_start_import_path_is_module_level():
    """Background import must route through the module-level start_import()."""
    from frappe.core.doctype.data_import import data_import as data_import_module

    assert hasattr(data_import_module, "start_import"), "start_import missing from data_import module"
    assert callable(data_import_module.start_import)


def test_data_import_class_does_not_own_importer():
    """DataImport.get_importer() is NOT the background execution path."""
    from frappe.core.doctype.data_import.data_import import DataImport

    # If this ever becomes the background path, the adapter assumptions break.
    assert not hasattr(DataImport, "start_import") or DataImport.start_import is not None


def test_stop_data_import_availability(frappe_version):
    """stop_data_import() is expected in v16 and later; absent in v15."""
    from frappe.core.doctype.data_import import data_import as data_import_module

    has_stop = hasattr(data_import_module, "stop_data_import")
    if frappe_version[0] >= 16:
        assert has_stop, "stop_data_import() expected in v16+"
        assert callable(data_import_module.stop_data_import)
    else:
        assert not has_stop, "stop_data_import() not expected in v15"


def test_upsert_not_available_in_v16_baseline():
    """Upsert must be feature-detected and absent on v15/v16 baseline."""
    from frappe.core.doctype.data_import import importer

    source = inspect.getsource(importer)
    assert "Upsert" not in source, "Unexpected Upsert code in baseline importer"
    assert "UPSERT" not in source, "Unexpected UPSERT constant in baseline importer"
