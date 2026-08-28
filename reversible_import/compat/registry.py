from __future__ import annotations


def _parse_version(version: str) -> tuple[int, int, int]:
    """Parse a Frappe version string into (major, minor, patch).

    Handles branch names like '15.0.0-dev' and '16.34.0'.
    """
    parts = version.replace("-dev", "").replace("-beta", "").split(".")
    return tuple(int(p) for p in parts[:3])


def get_adapter(version: str | None = None):
    """Return the ImportAdapter subclass matching the running Frappe version."""
    import frappe

    if version is None:
        version = frappe.__version__

    major = _parse_version(version)[0]

    if major == 15:
        from reversible_import.compat.frappe_v15 import FrappeV15Adapter

        return FrappeV15Adapter()
    if major == 16:
        from reversible_import.compat.frappe_v16 import FrappeV16Adapter

        return FrappeV16Adapter()

    from reversible_import.compat.future import FutureAdapter

    return FutureAdapter()
