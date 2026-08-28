# Reversible Data Import for Frappe
## Corrected Architecture, Implementation and Testing Plan

**Working app name:** `reversible_import`  
**Alternative package name:** `import_rollback`  
**Target:** Frappe v15 and Frappe v16  
**Initial scope:** Master-data migration and controlled reversible imports  
**License:** MIT  
**Architecture:** Compensating rollback / durable operation journal  
**Core principle:** No Frappe core patches, no global monkey patches, no single long-running database transaction
**Revision:** v2 — open grey areas resolved (see amendments throughout)

---

# 1. Executive Summary

Frappe's standard Data Import intentionally processes data as individual document payloads and commits successful payloads progressively. A payload can represent one CSV row or multiple rows when child-table rows belong to the same parent document. In both Frappe v15 and v16, successful payloads are committed before processing continues, while failure rolls back only the currently active transaction.

Therefore, Drupal-style rollback cannot be implemented reliably by calling `frappe.db.rollback()` after an import has partially completed.

The proposed application will implement **compensating rollback**:

```text
Import operation
      │
      ├── INSERT
      │      └── remember exactly what was created
      │
      └── UPDATE
             └── remember exactly what was changed
                       │
                       ▼
                 COMMIT operation
                       │
                       ▼
             Durable Operation Journal
```

Rollback works later by reading the operation journal in reverse sequence:

```text
Last successful operation
          ↓
       Reverse
          ↓
Previous operation
          ↓
       Reverse
          ↓
         ...
```

The application will deliberately avoid promising universal rollback.

Instead:

> Rollback is guaranteed only for explicitly supported scenarios where the application can prove that reversing the operation is safe.

Unsafe or ambiguous situations become **Rollback Conflicts** rather than forced changes.

---

# 2. Evaluation of the Previous Plan

The previous design already made several correct architectural choices: compensating rollback, reverse-order execution, per-document commit boundaries, pluggable strategies, background execution, and explicit acknowledgement that rollback cannot be fully atomic.

Those concepts should remain.

However, several parts should be changed before implementation.

## 2.1 Keep: Compensating rollback

The previous plan correctly rejected a single database transaction covering an entire import.

Keep this decision.

Each imported document and its rollback metadata should commit together.

```text
BEGIN

perform document operation
write journal entry

COMMIT
```

On failure:

```text
ROLLBACK current operation
record failure separately
continue / stop according to policy
```

This aligns with Frappe's normal transaction model and avoids holding enormous transactions open. Background jobs are committed when successfully completed and rolled back when uncaught exceptions occur; because this application deliberately catches per-operation failures, it must explicitly manage each operation's transaction boundary.

---

## 2.2 Change: Do not make standard `Data Import` the application's primary execution object

The previous plan centers the application around extending/overriding the existing `Data Import` DocType.

That creates unnecessary coupling.

More importantly, standard Frappe's module-level background `start_import()` directly creates the core `Importer`. It does not call `DataImport.get_importer()` to execute the background import.

Therefore simply overriding:

```python
get_importer()
```

is insufficient.

The application would also need to replace or redirect the start-job path.

That brings the app closer to Frappe internals than necessary.

### Corrected design

Create a dedicated DocType:

```text
Reversible Data Import
```

Users explicitly choose:

```text
Standard Data Import
        or
Reversible Data Import
```

Standard Frappe behavior remains completely untouched.

This gives the custom application control over:

- execution;
- transaction boundaries;
- journaling;
- cancellation;
- retries;
- rollback;
- conflict detection;
- compatibility handling.

---

# 3. Core Architectural Principles

The application should follow ten non-negotiable principles.

### P1 — No Frappe core modification

Never modify:

```text
frappe/core/doctype/data_import/*
```

directly.

### P2 — No runtime monkey patching

Do not replace:

```python
Importer.import_data
Importer.insert_record
Importer.update_record
```

globally.

### P3 — Own the execution loop

The reversible importer must control each payload from immediately before the document operation until journal creation and commit.

### P4 — Document and journal are one transaction

An imported document must never be committed without its corresponding rollback journal entry.

### P5 — Rollback uses normal Frappe document APIs

Prefer:

```python
doc.insert()
doc.save()
doc.cancel()
frappe.delete_doc()
```

over direct database modification.

### P6 — Default to unsupported, not supported

A DocType is rollback-capable only when explicitly allowed.

### P7 — Never silently overwrite post-import changes

Conflicts stop that specific rollback operation.

### P8 — Rollback itself must be resumable

Every successfully reverted operation is committed independently.

### P9 — Cancellation must normally be cooperative

Do not normally kill the RQ worker halfway through an operation.

### P10 — Audit information survives rollback

Rollback does not erase the journal proving what happened.

---

# 4. Supported Frappe Versions

## Frappe v15

Baseline capabilities:

```text
Insert New Records
Update Existing Records
```

The v15 importer commits every successful document payload individually.

There is no standard Data Import Cancel Import API equivalent to v16.

However, this custom application does not need to backport Frappe's hard-stop implementation because it will have its own cooperative cancellation mechanism.

---

## Frappe v16

Baseline capabilities:

```text
Insert New Records
Update Existing Records
Cancel standard Data Import RQ job
```

The stable `version-16` implementation contains `stop_data_import()`, which sends an RQ stop command to the running job.

That should be treated as an emergency worker termination mechanism, not as the primary design for reversible imports.

### Important correction to previous plan: Upsert

The earlier plan treated Upsert as a Frappe v16 feature.

The currently verified stable `version-16` importer exposes Insert and Update, while the newer `develop` implementation contains the Upsert pathway.

Therefore:

```text
v15 baseline    Insert / Update
v16 baseline    Insert / Update
Future/develop  Feature-detected Upsert
```

Upsert must not be hardcoded as a v16 assumption.

---

# 5. Product Scope

## Phase-one supported use case

Migration and bulk import of master data such as:

```text
Customer Group
Supplier Group
Territory
UOM
Item Group
Customer
Supplier
Contact
Address
Bank
Bank Account
selected custom Streamline masters
```

The whitelist must be configurable.

---

# 6. Explicit Non-Goals for Initial Release

The application will initially refuse generic rollback for:

```text
Sales Invoice
Purchase Invoice
Payment Entry
Journal Entry
Stock Entry
Delivery Note
Purchase Receipt
Stock Reconciliation
GL Entry
Stock Ledger Entry
payment reconciliation
submitted accounting transactions
submitted stock transactions
```

Also excluded:

- undoing emails already delivered;
- undoing HTTP requests already sent;
- undoing third-party API actions;
- restoring naming-series counters;
- automatically reversing arbitrary Server Script side effects;
- automatically reversing arbitrary custom-app hooks;
- restoring deleted files from external storage;
- retroactively providing safe Update rollback for historical standard Data Imports where no before-state was captured.

These can later receive explicit strategies where justified.

---

# 7. High-Level Architecture

```text
                  Reversible Data Import
                           │
                           ▼
                 ┌──────────────────┐
                 │ Parser Adapter   │
                 │ Frappe v15/v16   │
                 └────────┬─────────┘
                          │ payloads
                          ▼
                 ┌──────────────────┐
                 │ Import Runner    │
                 └────────┬─────────┘
                          │
             ┌────────────┴────────────┐
             │                         │
           INSERT                    UPDATE
             │                         │
             ▼                         ▼
       Normal Frappe ORM         Capture before state
             │                         │
             ▼                         ▼
        Insert document           Save document
             │                         │
             └──────────┬──────────────┘
                        │
                        ▼
              Operation Journal
                        │
                        ▼
                      COMMIT
```

Rollback:

```text
                  Rollback Engine
                        │
                        ▼
             Journal ORDER BY sequence DESC
                        │
                        ▼
                 Strategy Resolver
                        │
               ┌────────┴────────┐
               │                 │
             INSERT            UPDATE
               │                 │
          safety guard      conflict guard
               │                 │
             delete             restore
               │                 │
               └────────┬────────┘
                        │
                update journal
                        │
                      COMMIT
```

---

# 8. Compatibility Layer

We still want to reuse Frappe's import-file parsing wherever practical because reproducing its entire CSV/XLSX/child-table parsing behavior would create unnecessary maintenance.

However, those imports are implementation details.

Therefore create:

```text
compat/
    base.py
    frappe_v15.py
    frappe_v16.py
    future.py
```

with a stable application-owned interface:

```python
class ImportAdapter:
    def validate_file(...): ...
    def get_preview(...): ...
    def get_payloads(...): ...
    def get_row_indexes(payload): ...
```

Only these adapter modules may import Frappe's internal Data Import parser classes.

The remaining application must not know whether Frappe changed:

```text
Importer
ImportFile
Row
Payload
template options
CSV sniffer parameters
```

between releases.

This creates one intentionally controlled compatibility seam.

Each adapter MUST document, per Frappe version, how update imports treat child tables that are not mentioned in the payload:

```text
merged
replaced
left untouched
```

That documented behavior determines what must be snapshotted (see Child-Table Strategy).

---

# 9. Data Model

## 9.1 `Reversible Data Import`

Main execution record.

Recommended fields:

| Field | Purpose |
|---|---|
| `reference_doctype` | Target DocType |
| `import_type` | Insert / Update |
| `import_file` | CSV/XLSX |
| `source_system` | Fresa / CSV / Manual Migration / etc. |
| `file_hash` | Detect source-file replacement |
| `template_options` | Mapping information |
| `execution_status` | Import lifecycle |
| `rollback_status` | Rollback lifecycle |
| `failure_policy` | Continue / Stop / Stop + Rollback |
| `mute_emails` | Match normal import behavior |
| `cancel_requested` | Cooperative stop flag |
| `rollback_requested` | Rollback request |
| `requested_by` | User |
| `started_at` | Audit |
| `completed_at` | Audit |
| `job_id` | Background job |
| `total_payloads` | Count |
| `successful_payloads` | Count |
| `failed_payloads` | Count |
| `rollback_success_count` | Count |
| `rollback_conflict_count` | Count |
| `rollback_failure_count` | Count |
| `frappe_version` | Compatibility audit |
| `app_version` | Schema/behavior audit |
| `journal_schema_version` | Future rollback compatibility |

Use separate `execution_status` and `rollback_status`.

Do not try to combine everything into one giant status field.

---

# 10. Execution State Machine

## Execution status

```text
Draft
  ↓
Validated
  ↓
Queued
  ↓
Running
  ├────→ Stop Requested
  │          ↓
  │       Stopped
  │
  ├────→ Success
  ├────→ Partial Success
  └────→ Failed
```

## Rollback status

```text
Not Requested
      ↓
Queued
      ↓
Running
   ├──→ Complete
   ├──→ Partial
   ├──→ Conflict
   └──→ Failed
```

State transitions must be validated server-side.

The browser cannot arbitrarily set status values.

---

# 11. Operation Journal

Create a normal DocType:

```text
Reversible Import Operation
```

Do **not** make this a child table.

A 100,000-record migration must not require loading 100,000 rows into the parent document.

One journal record represents one document payload operation.

Recommended fields:

| Field | Purpose |
|---|---|
| `import_run` | Parent import |
| `sequence` | Strict operation ordering |
| `operation_key` | Unique idempotency key |
| `row_indexes` | Original source rows |
| `source_key` | Optional Fresa/source ID |
| `operation` | INSERT / UPDATE |
| `doctype` | Destination DocType |
| `docname` | Destination name |
| `status` | Applied / Failed |
| `before_values` | Previous scalar values |
| `after_values` | Imported scalar values |
| `child_before` | Snapshot of touched child tables |
| `child_after` | Post-import child-table snapshot |
| `before_hash` | Normalized state |
| `after_hash` | Normalized post-import state |
| `modified_before` | Audit |
| `modified_after` | Audit |
| `docstatus_before` | Audit |
| `docstatus_after` | Audit |
| `rollback_status` | Pending / Rolled Back / Conflict / Failed |
| `rollback_attempt_count` | Retry information |
| `last_rollback_error` | Latest error |
| `rolled_back_at` | Audit |

Recommended uniqueness:

```text
(import_run, sequence)
operation_key
```

---

# 12. Important Change from Previous Design: Journal Inserts Too

The earlier plan proposed storing update snapshots separately while using Frappe's standard `Data Import Log` to identify inserted records.

That works technically for many inserts, but it creates two competing systems of record.

Instead:

```text
INSERT  → Reversible Import Operation
UPDATE  → Reversible Import Operation
```

Everything goes into the same journal.

Advantages:

- one rollback worklist;
- one audit format;
- one retention policy;
- independent of Frappe Data Import Log changes;
- easier retries;
- better source-to-destination mapping;
- easier future migration-run rollback;
- no dependency on deleting/retaining a standard Data Import record.

---

# 13. Snapshot Format

Do not simply persist Frappe's `get_diff()` structure and assume it can later be fed to:

```python
doc.update(old_values)
```

particularly for child tables.

Create an application-owned snapshot format.

## Scalar fields

Store only fields changed by the import:

```json
{
  "credit_limit": {
    "before": 10000,
    "after": 50000
  },
  "territory": {
    "before": "Dubai",
    "after": "Abu Dhabi"
  }
}
```

This keeps updates compact.

## No-op updates

An update payload that changes nothing is still journaled as:

```text
status = Applied
before_values = {}
after_values = {}
before_hash == after_hash
```

and counts as a successful payload.

Rollback of a no-op operation is trivially safe: the guard sees current state equal to the recorded `after_hash` and restores nothing.

Rationale: run counters then always equal payloads processed, and retry reasoning stays simple.

---

# 14. Child-Table Strategy

Child-table changes are more complicated.

An import could:

```text
insert child
update child
delete child
reorder child
```

For every **touched child-table field**, store:

```text
complete normalized BEFORE table
complete normalized AFTER table
before hash
after hash
```

Example:

```json
{
  "contacts": {
    "before": [...],
    "after": [...],
    "before_hash": "...",
    "after_hash": "..."
  }
}
```

Rollback rule:

> Restore a touched child table only when its current normalized hash still equals the recorded imported `after_hash`.

If not:

```text
ROLLBACK CONFLICT
```

This is intentionally more conservative than attempting a clever merge.

What counts as a touched child table depends on the adapter's documented update semantics (see Compatibility Layer): whether child tables not mentioned in an update import are merged, replaced, or left untouched for that Frappe version. The snapshot scope follows that documentation.

---

# 15. Normalized Hashing

Never hash raw `doc.as_dict()` directly.

Exclude volatile metadata such as:

```text
modified
modified_by
creation
owner where irrelevant
idx where irrelevant
__last_sync_on
internal framework fields
```

Create one deterministic serializer:

```python
normalize_document_state(doc)
```

and version it:

```text
normalization_version = 1
```

This is important because rollback performed after an application upgrade must be able to reproduce the hash semantics used when the operation was originally imported.

## Normalizer version lifetime

Hash compatibility is guaranteed only for normalizer versions still bundled with the app. Every old normalizer implementation must remain bundled as long as any journal record within its rollback-eligibility window could reference it.

This ties normalizer lifetime to retention (see Data Retention): once `rollback eligibility days` has passed for all runs written by a normalizer version, that version's code path may be removed in a later release.

---

# 16. Correct Post-Import Modification Guard

This corrects a significant problem in the previous plan.

The old guard proposed comparing current `modified` against `modified_before`.

That is not sufficient because a successful import itself changes `modified`.

The relevant timestamp would be:

```text
modified_after
```

not:

```text
modified_before
```

Even `modified_after` is only an advisory guard.

The primary guard should be field-level state.

Example:

```text
Import:
credit_limit 10,000 → 50,000

Current:
credit_limit = 50,000

Safe to restore:
50,000 → 10,000
```

But:

```text
Import:
credit_limit 10,000 → 50,000

Human later changes:
credit_limit 50,000 → 75,000

Current != recorded after value

Result:
ROLLBACK CONFLICT
```

---

# 17. Allow Unrelated Human Changes Where Safe

Suppose import modifies:

```text
credit_limit
```

and a user subsequently modifies:

```text
phone
```

A full-document timestamp test would incorrectly block rollback.

The safer field-level algorithm is:

```text
Imported field:
credit_limit

Expected current value:
50,000

Actual:
50,000

Rollback allowed.

phone is untouched.
```

Result:

```text
credit_limit: 50,000 → 10,000
phone: preserve current value
```

This is substantially safer than replacing an entire old document snapshot.

---

# 18. Insert Rollback Guard

An inserted document should not automatically be deleted merely because its name exists in the journal.

Before deletion:

1. Verify it still exists.
2. Compare normalized current state with imported `after_hash`.
3. Check the selected policy for post-import modifications.
4. Attempt normal Frappe deletion.
5. Allow Frappe Link validation to block deletion where downstream references exist.

Example:

```text
Import creates Customer CUST-001
        ↓
User creates Sales Order against CUST-001
        ↓
Rollback requested
        ↓
Deletion blocked by link validation
        ↓
ROLLBACK CONFLICT
```

Do not force-delete the Sales Order or Customer.

## Cross-run dependency preflight

Rollback preflight must also detect links to this run's imported documents that were created by OTHER reversible import runs, using the operation journal. When found, preflight advises rolling back the dependent run first, instead of only surfacing:

```text
LINK_EXISTS
```

conflicts at execution time.

---

# 19. Rollback Strategy Registry

Custom Frappe hook:

```python
reversible_import_strategies = {
    "Customer": "...CustomerStrategy",
    "Supplier": "...SupplierStrategy",
}
```

Strategy interface:

```python
class RollbackStrategy:
    def preflight(self, operation):
        ...

    def guard(self, operation):
        ...

    def rollback(self, operation):
        ...
```

---

# 20. Strategy Resolution Must Be Whitelist-Based

The previous plan used:

```text
exact DocType
→ *submittable*
→ generic DeleteStrategy
```

including a generic Cancel + Delete fallback for submittable documents.

Remove that.

Correct policy:

```text
Exact registered strategy
        ↓
Explicitly allowed generic master strategy
        ↓
ForbiddenStrategy
```

Default:

```text
UNSUPPORTED
```

not:

```text
DELETE
```

---

# 21. Initial Strategies

### GenericMasterInsertStrategy

For explicitly whitelisted non-submittable masters.

Behavior:

```text
guard
delete using Frappe API
```

### GenericMasterUpdateStrategy

For explicitly whitelisted draft/master records.

Behavior:

```text
field conflict checks
child-table conflict checks
restore touched fields
save normally
```

### ForbiddenStrategy

Used whenever no safe strategy exists.

Returns:

```text
Rollback unsupported for this DocType.
```

### CustomStrategy

Used by future extensions.

Examples:

```text
Sales Invoice Strategy
Payment Entry Strategy
Stock Strategy
```

Those are deliberately outside v1.

If a restore fails document `validate()` during rollback, the operation becomes `Rollback Failed` and follows the manual remediation path defined in Rollback Algorithm — validation failures are never bypassed generically.

---

# 22. Never Use Generic `ignore_validate_update_after_submit`

The earlier plan proposed restoring updates with flags capable of bypassing update-after-submit validation.

Do not do this generically.

That bypasses an important ERP invariant.

If:

```text
docstatus != 0
```

and there is no registered safe strategy:

```text
ForbiddenStrategy
```

---

# 23. Import Execution Algorithm

For every payload:

```text
1. Check cancellation flag.

2. Check whether operation already succeeded.
   If yes → skip.

3. Determine INSERT / UPDATE.

4. Validate DocType strategy/support.

5. Begin operation work.

6. For UPDATE:
      load current document
      calculate intended changes
      create before representation

7. Execute normal Frappe ORM operation.

8. Read actual persisted in-memory document state.

9. Generate:
      before values
      after values
      hashes
      child snapshots
      docstatus
      modified timestamps

10. Create Reversible Import Operation.

11. Update lightweight run counters.

12. COMMIT.

13. Publish progress (throttled).
```

Progress events are throttled: publish every N operations or T seconds, whichever comes first (initial values N=25, T=1s) — never one event per payload. A 100,000-row migration must not emit 100,000 realtime events.

A no-op update (payload changes nothing) is still journaled as `Applied` and counts as a successful payload (see Snapshot Format — No-op updates).

Failure:

```text
ROLLBACK current transaction

create failure operation/log
commit failure information

apply configured failure policy
```

The document and successful journal entry must always cross the commit boundary together.

---

# 24. Failure Policies

Expose three modes:

| Mode | Behavior |
|---|---|
| Continue on Error | Continue remaining payloads |
| Stop on First Error | Stop new operations, keep successful imports |
| Stop and Roll Back | Stop new operations and start compensating rollback |

For the first stable release, I recommend enabling:

```text
Continue on Error
Stop on First Error
```

first.

Enable automatic:

```text
Stop and Roll Back
```

only after manual rollback has passed the full reliability test suite.

---

# 25. Cooperative Cancellation

The standard v16 Data Import can issue an RQ stop command.

This application's normal cancellation flow should instead be:

```text
User clicks Cancel Import
        ↓
cancel_requested = 1
        ↓
worker finishes current operation transaction
        ↓
worker checks flag
        ↓
no additional payload accepted
        ↓
status = Stopped
```

Pseudo-flow:

```python
for payload in payloads:
    if cancellation_requested(run):
        mark_stopped()
        break

    process_payload(payload)
```

This creates predictable transaction boundaries.

---

# 26. Emergency Worker Stop

An administrator can still need an emergency RQ termination if:

- a custom hook hangs;
- a document save deadlocks indefinitely;
- external code blocks;
- worker does not reach the cooperative check.

Treat this as:

```text
Emergency Stop
```

not:

```text
Cancel Import
```

After an emergency stop, run a reconciliation process before allowing rollback/resume.

Reconciliation triggers are defined in Reconciliation: a scheduled stale-run scan (heartbeat threshold, default 5 minutes) and an on-demand check before any resume or rollback of a run whose worker is not alive.

---

# 27. Reconciliation

A worker can die:

```text
after COMMIT
before status update
```

Therefore UI state alone cannot determine reality.

Create:

```python
reconcile_import_run(run)
```

It derives counts/status from committed operation journal rows.

For example:

```text
Run says:
successful = 499

Journal says:
500 Applied operations

Correct run counter to:
500
```

The journal is authoritative.

## When reconciliation runs

1. A scheduled task:

```text
tasks/reconciliation.py
```

scans for stale `Running` runs — heartbeat older than a configurable threshold (default 5 minutes) — and reconciles them automatically.

2. Reconciliation also runs on-demand before any resume or rollback request for a run whose worker is not alive.

---

# 28. Rollback Algorithm

Rollback worklist:

```sql
WHERE
    import_run = ?
    AND status = 'Applied'
    AND rollback_status != 'Rolled Back'

ORDER BY sequence DESC
```

For each operation:

```text
1. Resolve rollback strategy.

2. Run guard.

3. If guard detects modification:
      Conflict
      continue

4. Execute compensation.

5. Mark operation Rolled Back.

6. Write rollback result.

7. COMMIT.

8. Publish progress.
```

If compensation throws:

```text
ROLLBACK current rollback transaction

mark operation Rollback Failed
commit failure record

continue
```

## Validation-failure remediation

A restore can also fail `validate()` — for example a before-value was empty but the field became mandatory since import, or restoring a subset of fields violates a cross-field validation. Such operations are marked:

```text
Rollback Failed
```

Operator path:

```text
fix the blocking condition manually
→ retry the rollback

or

explicitly skip-with-acknowledgement
```

A run remains in rollback status `Partial` until every operation reaches a terminal state:

```text
Rolled Back
acknowledged-skipped
Conflict accepted
```

## Save race guard

The rollback engine loads a FRESH document, checks the field/hash guards, then saves — relying on Frappe's `TimestampMismatch` optimistic concurrency check to catch any modification that lands between the guard check and the save (see Concurrency Protection). A `TimestampMismatch` during rollback save becomes:

```text
Conflict
```

never a forced write.

---

# 29. Why Reverse Sequence Matters

Suppose import creates:

```text
Customer
   ↓
Address
   ↓
Contact
```

Import sequence:

```text
1 Customer
2 Address
3 Contact
```

Rollback:

```text
3 Contact
2 Address
1 Customer
```

The `sequence` field is therefore fundamental and must never be reconstructed from creation timestamp.

---

# 30. Rollback Idempotency

Every operation must have a stable:

```text
operation_key
```

Example:

```text
SHA256(
    import_run
    + payload sequence
    + source rows
    + operation type
)
```

Rollback behavior:

```text
Already Rolled Back
→ skip safely
```

Do not expose a general `force=True` option in v1.

The previous design included a force flag. That is unnecessarily dangerous for the first release.

---

# 31. Retry Semantics

## Import retry

Retry processes only:

```text
Failed
Unprocessed
```

operations.

Already Applied operations are skipped using the operation journal.

## Rollback retry

Retry processes only:

```text
Rollback Failed
Conflict where conflict has been resolved
```

Already Rolled Back operations are skipped.

Because `file_hash` locks the source file, retries cannot fix data errors. Source-data failures require a corrected file and a NEW import run. Retries only help transient failures such as locking, temporary link validation, or worker interruptions.

---

# 32. Duplicate Target Detection

For Update imports, detect multiple payloads targeting the same destination document during preflight.

Example:

```text
row 5 → Customer CUST-001
row 30 → Customer CUST-001
```

For v1:

```text
Reject as ambiguous.
```

This greatly simplifies:

- snapshot ordering;
- field ownership;
- conflict resolution;
- rollback reasoning.

A future version can support repeated updates to the same document through ordered journal operations.

---

# 33. Source-to-Destination Mapping

Borrow one of the strongest concepts from Drupal.

Every operation should optionally record:

```text
source_system
source_doctype
source_key

destination_doctype
destination_name
```

Example:

```text
Fresa
Customer
58129
    ↓
ERPNext
Customer
CUST-00481
```

Never rediscover mappings later from names.

This eventually enables:

- idempotent migration;
- incremental migration;
- source audit;
- cross-import dependency tracking.

---

# 34. Permissions

Recommended roles:

```text
Reversible Import User
Reversible Import Manager
Reversible Rollback Manager
```

Capabilities:

| Capability | User | Import Manager | Rollback Manager |
|---|---:|---:|---:|
| Create import | ✓ | ✓ | ✓ |
| Preview | ✓ | ✓ | ✓ |
| Start import | ✓ | ✓ | ✓ |
| Cancel own import | ✓ | ✓ | ✓ |
| View journal | Limited | ✓ | ✓ |
| Request rollback | — | ✓ | ✓ |
| Execute rollback | — | — | ✓ |
| Retry rollback | — | — | ✓ |
| Purge snapshot data | — | — | ✓ |

Do not run business-document changes with blanket:

```python
ignore_permissions=True
```

Internal journal writes can use privileged internal logic.

Business objects should remain governed by explicit application authorization and normal document rules.

Because background jobs execute as the enqueuing user, the Rollback Manager role must additionally carry write permission on the target DocTypes (see Background Jobs — Worker user context).

---

# 35. Background Jobs

Use Frappe's normal background queue.

Frappe documents `enqueue`, queues, timeouts and job execution as standard application mechanisms.

Do not use the earlier pseudocode parameter:

```python
is_idempotent=True
```

as though it were a standard Frappe enqueue control. It appeared in the previous plan's pseudocode.

Instead use:

```text
deterministic job ID
+
database state validation
+
operation idempotency
```

True idempotency must come from application state, not an RQ option.

## Worker user context

RQ jobs execute as the enqueuing user. Rollback jobs therefore run with the Rollback Manager's business-document permissions: the manager must also hold write permission on the target DocTypes, or operations fail with:

```text
PERMISSION_DENIED
```

Permission tests must verify the background-job context, not only direct API calls (see Permission Tests).

---

# 36. Suggested Job IDs

```text
reversible_import||RUN-0001
reversible_rollback||RUN-0001
```

Before enqueue:

```text
validate database state
check currently registered job
set status Queued
commit
enqueue_after_commit
```

Rollback and import jobs for the same run must never execute simultaneously.

---

# 37. Concurrency Protection

There are three separate concurrency problems.

## Two imports touching the same document

Normal Frappe optimistic document checks should still operate, but tests must verify TimestampMismatch behavior.

The app should not bypass those protections.

## Import and rollback on same run

Forbidden by state machine.

## Two rollback requests

Use:

```text
database status transition
+
deterministic job ID
```

The second request returns:

```text
Rollback already queued/running.
```

---

# 38. Side Effects

Set contextual flags:

```python
frappe.flags.in_import = True
frappe.flags.in_reversible_import = True
```

and optionally:

```python
frappe.flags.mute_emails = True
```

Custom Streamline hooks can use:

```python
if frappe.flags.in_reversible_import:
    ...
```

where appropriate.

However this does **not** make arbitrary hooks reversible.

Possible irreversible effects include:

```text
email
webhook
external API call
background job enqueue
file creation
third-party synchronization
```

The UI and documentation must state this clearly.

---

# 39. Explicit Commit Inside Third-Party Hooks

This is an especially important unsupported condition.

The app's guarantee depends on:

```text
document operation
+
journal write
```

remaining inside one transaction.

If custom code invoked during document save manually performs:

```python
frappe.db.commit()
```

the application can no longer guarantee atomic document+journal behavior.

Therefore:

> Explicit commits inside hooks executed during reversible import are unsupported.

This should be included in the deployment checklist and integration tests for Streamline-specific apps.

---

# 40. Data Retention

Do not purge snapshots immediately after rollback.

Recommended lifecycle:

```text
Rollback window active
→ full journal + rollback information

Rollback window expired
→ optionally purge heavy snapshots

Audit retention
→ preserve operation metadata and summary
```

Never purge a run when:

```text
Running
Rollback Running
Partially Rolled Back
Rollback Failed
Conflict unresolved
```

Retention settings:

```text
rollback eligibility days
snapshot retention days
metadata retention days
```

---

# 41. App Structure

```text
reversible_import/
│
├── hooks.py
│
├── api.py
│
├── permissions.py
│
│
├── compat/
│   ├── base.py
│   ├── frappe_v15.py
│   └── frappe_v16.py
│
├── importing/
│   ├── runner.py
│   ├── operation_service.py
│   ├── snapshot_service.py
│   ├── normalization.py
│   ├── reconciliation.py
│   └── cancellation.py
│
├── rollback/
│   ├── engine.py
│   ├── registry.py
│   ├── base_strategy.py
│   ├── master_insert.py
│   ├── master_update.py
│   └── forbidden.py
│
├── doctype/
│   ├── reversible_data_import/
│   ├── reversible_import_operation/
│   ├── rollback_attempt/
│   └── reversible_import_settings/
│
├── public/
│   └── js/
│       └── reversible_data_import.js
│
├── tasks/
│   ├── reconciliation.py
│   └── retention.py
│
└── tests/
```

This keeps Frappe compatibility concerns isolated from rollback business logic.

## API surface

`api.py` exposes the following whitelisted endpoints, each enforcing server-side permission checks:

```text
start
preview
cancel
resume
retry
request_rollback
execute_rollback
retry_rollback
get_progress
purge
```

---

# 42. Rollback Attempt Audit

Create:

```text
Rollback Attempt
```

one record per user-triggered rollback execution.

Fields:

```text
import_run
requested_by
requested_at
started_at
completed_at
status

total_operations
rolled_back
conflicts
failed
skipped

job_id
summary
```

The individual Operation records retain their current rollback state and last error.

If regulatory requirements later require every historical result of every retry, add an append-only:

```text
Rollback Operation Event
```

in a later release.

Avoid doubling the journal table from day one unless required.

---

# 43. User Interface

## Import form

Show:

```text
Reference DocType
Import Type
Source System
File
Failure Policy
Email suppression
```

Preview:

```text
Total payloads
Rows
Warnings
Unsupported conditions
Duplicate target IDs
Rollback support classification
```

---

# 44. Preflight Safety Classification

Before the import can start:

```text
Rollback Support: FULL
Rollback Support: LIMITED
Rollback Support: UNSUPPORTED
```

Example:

```text
Customer
Operation: Insert
Strategy: Generic Master Insert
Support: FULL
```

versus:

```text
Sales Invoice
Operation: Insert
Submitted document support: unavailable

Support: UNSUPPORTED
```

The user must not discover this after importing.

---

# 45. Rollback Confirmation Screen

Display:

```text
Import: RDI-00032

Applied:                 10,000
Already rolled back:          0
Potentially reversible:   9,970
Known conflicts:             30

Operation types:
Insert:                    8,500
Update:                    1,500
```

Confirmation should state clearly:

> Rollback will attempt to reverse supported operations. Documents changed or linked after import may be preserved and reported as conflicts.

The confirmation screen also warns when the operation journal shows this run's documents are linked from documents created by another reversible import run, and advises rolling back the dependent run first (see Insert Rollback Guard — Cross-run dependency preflight).

---

# 46. Conflict Review

Provide a filtered view:

```text
Rollback Conflicts
```

Columns:

```text
Sequence
DocType
Document
Operation
Conflict type
Expected value/hash
Current value/hash
Error
```

Common conflict types:

```text
DOCUMENT_MODIFIED
IMPORTED_FIELD_CHANGED
CHILD_TABLE_CHANGED
LINK_EXISTS
DOCUMENT_RENAMED_OR_MISSING
UNSUPPORTED_STRATEGY
DOCSTATUS_CHANGED
PERMISSION_DENIED
```

## Tree-master conflict messaging

Tree masters (Customer Group, Territory) use NestedSet; deleting a node rebuilds `lft`/`rgt`. A human-created child under an imported parent blocks the parent's deletion as `LINK_EXISTS` — conflict messages for tree DocTypes must name the blocking child document(s) (see Insert Integration Tests).

---

# 47. Production Safety Controls

For production sites:

```text
rollback requires Rollback Manager
rollback requires explicit typed confirmation
rollback button disabled while import active
automatic rollback configurable by site
submitted DocTypes blocked unless registered
```

Optional future feature:

```text
require second-person approval above N records
```

for large production rollbacks.

---

# 48. Implementation Phases

## Phase 0 — Compatibility Contract

Before business features:

- establish v15 fixture environment;
- establish v16 fixture environment;
- capture representative standard import templates;
- verify parser behavior;
- document internal parser interfaces used;
- document child-table update semantics per adapter (merged / replaced / left untouched);
- introduce compatibility adapter;
- create CI matrix;
- define CI concretely as a GitHub Actions workflow: matrix over Frappe v15 on Python 3.11 and v16 on Python 3.14, service containers for MariaDB and Redis, Frappe installed via bench, running the parser contract tests (see Parser Contract Tests) and the execution-path contract tests (see Frappe Upgrade Contract Tests);
- add contract tests.

**Exit gate:** the same supported templates produce equivalent application payloads on v15 and v16.

---

## Phase 1 — Foundation and Insert Rollback

Implement:

```text
Reversible Data Import
Reversible Import Operation
Settings
state machine
background runner
file parser adapter
Insert support
Generic Master Insert Strategy
operation journal
reverse-order rollback
permissions
basic UI
```

Allow only a small whitelist.

Example:

```text
Customer Group
Supplier Group
Territory
UOM
```

**Exit gate:** an Insert import can be stopped, resumed and completely rolled back without leaving untracked inserted documents.

---

## Phase 2 — Update Rollback

Implement:

```text
scalar before/after deltas
normalized hashing
modified_after
field-level conflict detection
Generic Master Update Strategy
```

Initially support DocTypes without child-table changes.

**Exit gate:** imported fields can be safely restored while unrelated later user edits remain untouched.

---

## Phase 3 — Child Tables

Implement:

```text
touched-table detection
before table snapshot
after table snapshot
normalized child hashing
restore
conflict detection
```

**Exit gate:** child insert/update/delete/reorder scenarios round-trip exactly when no post-import modification exists.

---

## Phase 4 — Cancellation, Resume and Auto-Rollback

Implement:

```text
cooperative cancel
stop status
reconciliation
resume
retry
manual rollback retry
Stop on First Error
Stop + Rollback
```

Automatic rollback is enabled only after manual rollback is considered stable.

**Exit gate:** worker interruption at every tested transaction boundary produces a recoverable state.

---

## Phase 5 — Hardening

Implement:

```text
retention
audit improvements
conflict review
large-import UI
permissions hardening
indexes
query optimization
operational documentation
disaster-recovery runbook
```

---

## Phase 6 — Optional Transactional Strategies

Only after explicit business analysis.

Potential:

```text
Sales Invoice
Purchase Invoice
Payment Entry
Journal Entry
Stock Entry
```

Each becomes its own engineering feature.

There is no generic submittable fallback.

---

# 49. Detailed Testing Strategy

Testing is not a final phase.

Tests must be built alongside each implementation phase.

The release should be considered unsafe until crash-recovery and conflict tests pass, even if normal import/rollback tests pass.

---

# 50. Test Environment Matrix

CI minimum:

| Environment | Required |
|---|---:|
| Latest supported Frappe v15 patch | Yes |
| Latest supported Frappe v16 patch | Yes |
| MariaDB supported by corresponding Frappe release | Yes |
| Redis/RQ worker | Yes |
| Background scheduler | Yes |
| Developer/test synchronous worker mode | Yes |

PostgreSQL is explicitly unsupported and untested for v1. Snapshot fields (`before_values`, `child_before`, etc.) are JSON columns whose behavior differs between MariaDB and PostgreSQL; supporting both would double the CI matrix. This is a deliberate scope decision.

Future compatibility:

```text
Frappe develop
```

Purpose:

> Early detection of future compatibility breakage.

`develop` is not included in CI because its current Python requirement is not available on standard GitHub Actions runners. Compatibility with future stable versions will be validated when a new release branch is cut.

---

# 51. Unit Tests

## Strategy resolution

Verify:

```text
whitelisted Customer → correct strategy
unsupported Sales Invoice → ForbiddenStrategy
unregistered DocType → ForbiddenStrategy
```

No default Delete strategy for arbitrary DocTypes.

## State machine

Invalid:

```text
Draft → Rolling Back
Running → Rollback Running
Rolled Back → Running
```

must fail.

## Snapshot serialization

Verify:

- dates;
- datetimes;
- decimals;
- currency;
- check fields;
- select;
- link;
- dynamic link;
- JSON;
- null versus empty string;
- child data.

## Normalization

Ensure two semantically identical documents create the same hash despite different:

```text
modified
modified_by
creation
volatile metadata
```

## Field delta

Verify:

```text
before
after
restore
```

for each supported field type.

## Operation key

Same payload:

```text
same operation key
```

different payload:

```text
different operation key
```

---

# 52. Parser Contract Tests

These tests protect the internal Frappe parser seam.

For v15 and v16 test:

```text
simple parent records
parent + one child
parent + multiple child rows
multiple parent records
blank child rows
date parsing
datetime parsing
link fields
select fields
mandatory fields
invalid link
CSV
XLSX
UTF-8
Arabic text
special characters
quoted CSV delimiters
empty values
```

Very important assertion:

```text
number of payloads
payload document structure
source row indexes
```

must match expectations.

A payload may contain multiple physical rows; tests and user-facing terminology should therefore say **payload/document**, not assume every CSV row is an independent transaction. Frappe's parser explicitly groups multiple rows into one document when child tables are present.

---

# 53. Insert Integration Tests

For each supported master DocType:

```text
Import N records
verify documents
verify N journal operations
verify operation hashes
rollback
verify documents removed
verify operation rollback statuses
```

Test:

```text
manual names
autonaming
naming series
mandatory fields
defaults
unique fields
links
tree masters where supported
```

---

# 54. Insert Atomicity Fault Tests

This is critical.

Inject failures at:

### F1 — Before document insert

Expected:

```text
document absent
journal absent/applied operation absent
```

### F2 — Immediately after document insert but before journal creation

Raise exception deliberately.

Expected after rollback:

```text
document absent
successful journal absent
```

### F3 — After journal creation but before commit

Raise exception.

Expected:

```text
document absent
journal absent
```

### F4 — Immediately after commit

Simulate worker crash before progress/status update.

Expected:

```text
document exists
journal exists
reconciliation detects operation
```

### F5 — Before next payload

Expected:

```text
previous payload durable
next payload untouched
resume starts correctly
```

These tests prove the application's fundamental guarantee.

---

# 55. Update Integration Tests

Basic:

```text
A = original value
import A → B
verify B
rollback
verify A
```

Multiple fields:

```text
A,B,C
↓
A2,B2,C2
↓ rollback
A,B,C
```

Only imported fields should restore.

---

# 56. Post-Import Modification Tests

### Same imported field changed later

```text
10K → 50K import
50K → 75K human
rollback
```

Expected:

```text
Conflict
value remains 75K
```

### Unrelated field changed later

```text
credit_limit 10K → 50K import
phone AAA → BBB human

rollback
```

Expected:

```text
credit_limit → 10K
phone remains BBB
```

### Imported field changed back manually

```text
10K → 50K import
human sets 50K → 10K
rollback
```

Expected:

Define explicitly.

Recommended:

```text
Already effectively restored
mark as No Action / Rolled Back
```

after validation.

---

# 57. Child-Table Tests

Test independently:

### Child insert

```text
A,B
import adds C
rollback
A,B
```

### Child update

```text
A(value=1)
import → A(value=2)
rollback → 1
```

### Child delete

```text
A,B,C
import removes B
rollback restores B
```

### Reorder

```text
A,B,C
→ C,A,B
→ rollback
A,B,C
```

### Multiple operations

```text
update A
delete B
insert D
reorder
```

Rollback must recreate exact normalized original table.

---

# 58. Child-Table Conflict Tests

After import, user:

```text
adds child
edits child
deletes child
reorders child
```

Expected:

```text
child-table hash mismatch
Rollback Conflict
no partial child restoration
```

The parent scalar fields can be handled separately only if the strategy explicitly supports partial rollback.

---

# 59. Link Conflict Tests

Scenario:

```text
import Customer
create Sales Order referencing Customer
rollback Customer
```

Expected:

```text
Customer preserved
operation = Conflict
linking document identified where possible
other rollback operations continue
```

Never cascade-delete unrelated downstream records.

---

# 60. Missing Document Test

Scenario:

```text
import Customer
administrator manually deletes Customer
rollback
```

Recommended outcome:

```text
Already Missing
```

For an Insert operation this can generally be treated as already compensated after validating there is no ambiguity.

For Update:

```text
missing destination
→ Conflict
```

because previous state cannot be restored without recreating a business object unexpectedly.

---

# 61. Rename Test

Scenario:

```text
import CUST-001
rename → CUST-NEW
rollback
```

Initial recommended behavior:

```text
original destination missing
→ Conflict
```

Do not attempt fuzzy rediscovery.

Future support could explicitly integrate with rename history.

---

# 62. Rollback Order Tests

Construct:

```text
Master A
Master B links A
Master C links B
```

Import order:

```text
A
B
C
```

Verify rollback sequence:

```text
C
B
A
```

Also intentionally test ascending order to prove that it would fail.

---

# 63. Cancellation Tests

### Cancel before job starts

Expected:

```text
no payload executed
Stopped
```

### Cancel after 1 payload

Expected:

```text
payload 1 committed
payload 2+ not started
```

### Cancel after many payloads

Verify exact journal/document consistency.

### Cancel while current operation is saving

The flag is not acted on until operation boundary.

Expected:

```text
current document + journal either both commit
or both rollback
```

Never half-state.

---

# 64. Cancel + Rollback Tests

```text
1...500 imported
cancel requested
current operation finishes
status Stopped
rollback starts
500...1 compensated
```

Verify:

```text
no new import operation begins after stop boundary
rollback does not run concurrently with importer
```

---

# 65. Hard Worker Termination Tests

Separate from cooperative cancellation.

Terminate worker:

```text
during insert
during update
during journal write
after commit
during rollback
```

After restart:

```text
run reconciliation
```

Expected result must always fall into one of:

```text
operation fully absent
operation fully committed
rollback fully absent
rollback fully committed
```

Never undocumented document mutation.

---

# 66. Rollback Fault-Injection Tests

### R1 — guard failure

Expected:

```text
Conflict
no mutation
```

### R2 — rollback action throws before save/delete

Expected:

```text
original imported state remains
Rollback Failed
```

### R3 — rollback action succeeds but journal status update throws before commit

Expected:

```text
database rollback restores imported state
operation remains pending/failed
```

### R4 — rollback commit succeeds but worker dies before UI update

Expected:

```text
document compensated
journal says Rolled Back
reconciliation updates parent run
```

---

# 67. Idempotency Tests

Call:

```text
Start Import
Start Import
Start Import
```

concurrently.

Only one execution begins.

Call:

```text
Rollback
Rollback
Rollback
```

concurrently.

Only one rollback begins.

Retry completed rollback:

```text
no document receives a second compensation
```

---

# 68. Duplicate Update Tests

Import file:

```text
row 10 → CUST-001
row 20 → CUST-001
```

Expected v1:

```text
Preflight Error:
Duplicate target document in update import.
```

Child rows belonging to one parent payload must not trigger this false-positive.

---

# 69. Concurrency Tests

Run two different imports modifying the same Customer.

Verify:

- Frappe's document concurrency controls are not bypassed;
- one cannot silently overwrite the other;
- journals represent only committed changes;
- rollback of Run A does not incorrectly overwrite Run B.

This is one of the highest-risk test categories for Update support.

---

# 70. Permission Tests

Test:

```text
ordinary user
import user
import manager
rollback manager
system manager
```

Verify API endpoints directly, not only hidden buttons.

Attempt:

```text
forged rollback POST
foreign import ID
unsupported DocType
cancel another user's restricted run
journal data access
```

The server must reject unauthorized operations.

Repeat the rollback-execution checks inside an enqueued background job to verify the worker user context (RQ jobs execute as the enqueuing user), not only direct API calls.

---

# 71. Submitted Document Tests

Attempt reversible import against unsupported submitted DocType.

Expected before import:

```text
Preflight:
Unsupported for reversible import
```

It must not import first and only discover rollback is impossible afterward.

---

# 72. Side-Effect Tests

Create test hooks that:

```text
send queued event
write related DocType
enqueue job
perform after_commit action
```

Record which effects are:

```text
transactional
non-transactional
compensated
not compensated
```

This becomes part of the developer documentation.

---

# 73. Explicit-Commit Hook Test

Install a deliberate test hook performing:

```python
frappe.db.commit()
```

during reversible import.

Confirm the test demonstrates why this violates the application's transaction guarantee.

The compatibility documentation should then explicitly classify such hooks as unsupported.

---

# 74. Retry Tests

Import:

```text
1 success
2 success
3 fail
4 fail
```

Retry after correcting problem.

Expected:

```text
1 skipped
2 skipped
3 imported
4 imported
```

No duplicate journal for the original successful operations.

---

# 75. Reconciliation Tests

Artificially corrupt parent counters:

```text
successful_payloads = 90
```

while journal has:

```text
100 Applied
```

Run reconciliation.

Expected:

```text
100
```

Also test stale:

```text
Running
```

record with no corresponding worker.

Reconciliation should classify it safely, not blindly resume.

---

# 76. Retention Tests

Verify:

- active rollback data never purged;
- partially rolled-back run never purged;
- failed rollback never purged;
- expired completed run can purge heavy snapshot content;
- audit summary survives;
- purge is restartable;
- purge is permission controlled.

---

# 77. File Integrity Tests

Calculate:

```text
file_hash
```

at validation/start.

Attempt replacing attachment afterward.

Expected:

```text
Hash mismatch
Import blocked
```

The import cannot preview File A and execute File B without revalidation.

---

# 78. Security Tests

Test:

```text
malformed CSV
formula-like spreadsheet values
unexpected JSON
very long text
invalid file extension
oversized file
path-like filenames
unauthorized attachment access
API parameter tampering
```

Also verify rollback errors shown to users do not unnecessarily expose sensitive tracebacks.

Full traceback remains server-side/audit-only.

---

# 79. Performance Tests

Run representative datasets:

```text
1,000
10,000
50,000
100,000 where infrastructure allows
```

For:

```text
Insert
Update
Rollback Insert
Rollback Update
```

Measure:

- documents/second;
- total wall time;
- worker memory;
- database CPU;
- journal table growth;
- snapshot bytes/operation;
- rollback throughput;
- query latency;
- realtime event overhead.

Compare:

```text
standard Frappe import
vs
reversible import
```

The purpose is not necessarily identical performance.

The requirement is:

> overhead must be bounded, measured and operationally acceptable.

---

# 80. Memory Tests

Frappe's current import parsing may materialize payloads before execution.

Because the compatibility layer may initially reuse that behavior, verify large-file memory consumption explicitly.

If memory grows beyond acceptable limits, introduce a future:

```text
streaming/chunked parser adapter
```

rather than silently changing transaction behavior.

---

# 81. Index Tests

At minimum evaluate indexes for:

```text
Reversible Import Operation:
    import_run + sequence
    import_run + status
    import_run + rollback_status
    doctype + docname
    operation_key

Rollback Attempt:
    import_run
    status
```

Benchmark reverse-worklist query on large runs.

---

# 82. Upgrade Compatibility Tests

This is critical because rollback metadata may outlive the application release that created it.

Scenario:

```text
App v1.0 creates import
↓
upgrade app v1.1
↓
rollback old run
```

Must still work.

Therefore every journal record stores:

```text
journal_schema_version
normalization_version
app_version
frappe_version
```

Migration patches must never silently invalidate old rollback data.

Likewise, old normalizer versions must remain bundled for the full rollback-eligibility window of any journal record that references them (see Normalized Hashing — Normalizer version lifetime).

---

# 83. Frappe Upgrade Contract Tests

For each supported Frappe release:

verify:

```text
parser import path
parser constructor
payload structure
row index behavior
child grouping
date parsing
file parsing
background queue API
document insertion behavior
```

Also verify execution-path contracts:

```text
stop_data_import() availability and behavior
background start_import() execution path (module-level, not via DataImport.get_importer())
Upsert availability (feature-detected, currently develop only)
```

If an internal parser contract changes:

```text
only compat/frappe_vXX.py
```

should normally require modification.

Frappe v16 provides `extend_doctype_class` as a cooperative standard-class extension mechanism, but this architecture intentionally needs very little standard DocType extension because it owns its own DocTypes and execution path.

---

# 84. UI / End-to-End Tests

Automate:

```text
create reversible import
attach file
preview
start
watch progress
cancel
resume
rollback
view conflict
retry rollback
```

Verify browser refresh during:

```text
Running
Rollback Running
```

does not lose state because the server journal is authoritative.

---

# 85. User Acceptance Tests

Migration-team UAT should include realistic Fresa data:

```text
messy customer exports
duplicate suppliers
missing links
incorrect territories
contacts
addresses
bank accounts
multi-company data where applicable
```

For every migration trial:

1. count source records;
2. count imported records;
3. verify mapping;
4. intentionally introduce errors;
5. stop;
6. rollback;
7. verify pre-import database state;
8. fix source;
9. re-import.

---

# 86. Production Simulation

Before first production use, restore a recent anonymized or staging copy of the actual site and execute the complete migration sequence.

Test:

```text
import
partial failure
cancel
rollback
retry
dependency conflict
large rollback
worker restart
```

Do not make the first realistic rollback exercise the production migration itself.

---

# 87. Release Gates

## Alpha

Requirements:

```text
Insert only
small master whitelist
journal atomicity tests pass
manual rollback
reverse order
permissions
v15 + v16 CI
```

No Update support.

---

## Beta

Add:

```text
scalar Update
field conflict detection
retry
cooperative cancellation
reconciliation
```

---

## Release Candidate

Add:

```text
child-table update
crash tests
large-data tests
retention
UI conflict handling
operational documentation
```

---

## General Availability

Requires all critical test suites passing:

```text
atomicity
crash recovery
idempotency
concurrency
permissions
conflict protection
v15 compatibility
v16 compatibility
performance baseline
upgrade compatibility
```

Transactional ERP DocTypes are **not** required for GA.

They remain separate opt-in strategy packages/features.

---

# 88. Critical Test Gate Categories

The following failures are release blockers:

```text
document committed without journal
journal committed without document
rollback overwrites a post-import user change
rollback bypasses a link constraint
duplicate rollback compensation
concurrent import/rollback execution
permission bypass
old journal becomes unreadable after upgrade
worker crash creates undocumented state
unsupported DocType accepted as safely reversible
```

A performance slowdown is fixable.

Any of the above is a correctness failure.

---

# 89. Operational Runbook

Before large production migration:

```text
verify backup
verify rollback support classification
verify worker health
verify scheduler/Redis health
verify disk space
verify journal retention
verify users/roles
freeze custom code changes during run where possible
```

During:

```text
monitor import progress
monitor worker
monitor error count
avoid changing imported masters until validation completes
```

After:

```text
validate record counts
validate links
validate financial implications if any
mark migration accepted
retain rollback journal for agreed window
```

A database backup remains complementary protection.

It does not replace operation-level rollback.

---

# 90. Migration-Level Extension

Once individual imports are proven stable, introduce:

```text
Migration Run
```

Example:

```text
FRESA-MIG-0001

1 Customer Groups
2 Supplier Groups
3 Territories
4 Customers
5 Suppliers
6 Contacts
7 Addresses
8 Banks
9 Bank Accounts
```

Each `Reversible Data Import` belongs to the Migration Run.

Whole-migration rollback:

```text
9 Bank Accounts
8 Banks
7 Addresses
6 Contacts
5 Suppliers
4 Customers
3 Territories
2 Supplier Groups
1 Customer Groups
```

This should be a later layer built on top of the exact same operation journal.

Do not duplicate rollback logic at migration-run level.

---

# 91. Final Recommended Scope

The application's first stable promise should be:

> Reversible, auditable and resumable Frappe master-data imports for explicitly supported DocTypes, with safe Insert deletion, field-aware Update restoration, conflict detection, cooperative cancellation and reverse-order compensating rollback.

It should **not** promise:

> Any Frappe/ERPNext document can always be rolled back.

The latter is impossible to guarantee safely once accounting, stock, submissions, external effects and subsequent user activity are involved.

---

# 92. Final Architecture Decision

The corrected implementation should therefore be:

```text
                         Frappe
                           │
             standard ORM / validation / hooks
                           │
                           ▼
              Reversible Data Import
                           │
                ┌──────────┴──────────┐
                │                     │
          Parser Adapter         Import Runner
                                      │
                                one payload
                                      │
                       ┌──────────────┴─────────────┐
                       │                            │
                    document                    journal
                       │                            │
                       └────────────┬───────────────┘
                                    │
                                  COMMIT
                                    │
                                    ▼
                              next payload
```

Rollback:

```text
                         Journal
                            │
                       sequence DESC
                            │
                            ▼
                    Strategy Resolver
                            │
                     Safety Guards
                            │
                ┌───────────┴───────────┐
                │                       │
             compensate              conflict
                │                       │
         update operation          preserve data
                │                       │
              COMMIT                   COMMIT
```

The important architectural shift from the original proposal is that **Frappe Data Import becomes a reference implementation and parser source, not the execution object that the rollback app has to override**.

That removes the highest-risk dependency while preserving the parts of Frappe that are valuable:

```text
DocType metadata
standard templates
document lifecycle
validation
permissions
background jobs
database transactions
link checking
Desk UI
realtime events
```

This is the version of the plan I would use as the technical baseline before implementation.