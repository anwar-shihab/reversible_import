# Reversible Import

Reversible, auditable and resumable data imports for Frappe v15/v16 with compensating rollback.

This application is intentionally **not** a universal undo button for every Frappe/ERPNext document. It targets explicitly supported master-data DocTypes (for example: Customer Group, Supplier Group, Territory, UOM, Item Group, Customer, Supplier, Contact, Address, Bank, Bank Account) and provides safe rollback for Insert and Update operations via a durable operation journal.

For the full architecture, implementation and testing plan, see [`docs/plan.md`](docs/plan.md).

## Install

```bash
bench get-app https://github.com/anwar-shihab/reversible_import.git
bench --site <site> install-app reversible_import
```

## Status

Phase 0 — Compatibility Contract — is in progress. The repository now contains:

- A Frappe-version compatibility adapter (`reversible_import/compat/`).
- Parser and execution-path contract tests.
- A CI matrix covering Frappe `version-15` (Python 3.11) and `version-16` (Python 3.12).
- The implementation plan at [`docs/plan.md`](docs/plan.md) and parser contract notes at [`docs/parser-contract.md`](docs/parser-contract.md).

Phase 1 (foundation and Insert rollback) starts once the Phase 0 exit gate is green in CI.

## Development

See [`docs/dev-setup.md`](docs/dev-setup.md) for local bench instructions.

## License

MIT
