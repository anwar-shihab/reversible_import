# Parser Contract

This document records exactly which Frappe internal APIs the compatibility
adapter uses, and how they map to the application's stable
`reversible_import.compat.base.ImportAdapter` interface.

## Internal APIs used

### `frappe.core.doctype.data_import.importer.Importer`

Constructor (v15):

```python
Importer(doctype, data_import=None, file_path=None, import_type=None, console=False)
```

Constructor (v16):

```python
Importer(
    doctype,
    data_import=None,
    file_path=None,
    import_type=None,
    console=False,
    use_sniffer=False,
)
```

The adapter creates an in-memory `Data Import` document, sets its
`import_type` and `template_options`, and passes it together with the local
file path to the constructor. It never calls `Importer.import_data()` — that
would perform the real import. Only the parsing machinery is used.

### `frappe.core.doctype.data_import.importer.ImportFile`

Constructor (v15):

```python
ImportFile(doctype, file, template_options=None, import_type=None, *, console=False)
```

Constructor (v16):

```python
ImportFile(
    doctype,
    file,
    template_options=None,
    import_type=None,
    *,
    console=False,
    use_sniffer=False,
)
```

Methods used:

- `get_data_for_import_preview()` — returns preview columns/rows/warnings.
- `get_payloads_for_import()` — returns list of `frappe._dict(doc=..., rows=[...])`.
- `get_warnings()` — returns validation warnings produced during parsing.

### `frappe.core.doctype.data_import.importer.Row`

Attribute used:

- `row_number` — the 1-based source row index.

## Mapping to `ImportAdapter`

| Adapter method | Internal API / logic |
|---|---|
| `validate_file` | `ImportFile(file_path)` → `len(import_file.data)`, extension from path, `import_file.get_warnings()` |
| `get_preview` | `Importer.get_data_for_import_preview()` + `ImportFile.get_payloads_for_import()` |
| `get_payloads` | `ImportFile.get_payloads_for_import()` → coerce `doc` to dict, collect `row.row_number` |
| `get_payload_row_indexes` | `payload["row_indexes"]` |
| `describe_child_table_semantics` | Hard-coded per-version observation (see below) |

## Child-table update semantics

For both v15 and v16 the observed behavior is:

```text
replaced when supplied, left untouched when absent
```

Rows supplied for a child table in an update import replace the existing
child table list for that document. Rows not supplied leave the child table
untouched.

This is derived from `ImportFile.parse_next_row_for_import()` and
`Row._parse_doc()` behavior, and is verified by the contract tests.

## What is intentionally hidden

The rest of the application must not depend directly on:

- `Importer` method signatures beyond the parsing path.
- `ImportFile` row/header/column internals.
- CSV sniffer parameters (v16 exposes `use_sniffer`).
- Template option formats beyond the `column_to_field_map` used by the adapter.

If a future Frappe release changes any of the above, only the files in
`reversible_import/compat/` should normally require modification.
