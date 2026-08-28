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

This repository currently contains the Frappe app scaffold and the implementation plan. Functional features will land incrementally following the phases documented in `docs/plan.md`.

## License

MIT
