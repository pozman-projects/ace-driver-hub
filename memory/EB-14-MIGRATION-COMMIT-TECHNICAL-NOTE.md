# EB-14 — Migration Commit Engine · Technical Note

## Purpose
EB-14 is the controlled bridge between an **approved EB-12 dry run** and
the canonical DCC record layer. It writes canonical Owners, Vehicles,
Equipment, Drivers, relationships, compliance, activation and documents
using dependency-safe batching, immutable migration packages and stored
rollback packages.

Stage A (this build) delivers the engine, safety rails and test coverage
using **sanitised fictional fixtures only**. No real ACE data is imported
by EB-14 code. Stage B (real ACE commit) is executed only after Paul
explicitly delivers the real workbook, approves the dry-run and instructs
Emergent in a separate action.

## Commit modes
| Mode | Writes canonical DCC records? | Required role |
|-|-|-|
| **Rehearsal** | No — actions written with `state=Skipped` (audit trail) | Manager+ |
| **Controlled Commit** | Yes — canonical writes with rollback package | Admin |
| **Rollback** | Reverses a prior commit (see Rollback runbook) | Admin |

## Environment mode
The `/api/migration-commit/environment` endpoint truthfully reports:
```
{
  "transactions_enabled": false,
  "commit_mode": "staged-idempotent",
  "banner": "Staged idempotent commit mode. Multi-document transactions are
             NOT active in this environment. Partial-completion, pause and
             resume are truthful."
}
```
Set `MIGRATION_COMMIT_TRANSACTIONS=true` at deploy time only when the
target MongoDB deployment is a replica set that supports multi-document
transactions. Do not toggle this locally.

## Data model
| Collection | Purpose | Immutable? |
|-|-|-|
| `migration_commit_jobs` | Top-level commit job | Package field frozen once approved |
| `migration_commit_batches` | Per-entity-type batch inside a job | Yes once complete |
| `migration_commit_rows` | Per-source-row snapshot | Yes |
| `migration_commit_actions` | Idempotent per-canonical-record action | Append-only |
| `migration_commit_events` | Audit trail | Append-only |
| `migration_rollback_packages` | Reverse-operation manifest | Immutable once commit starts |
| `migration_rollback_actions` | Individual reverse steps | Append-only |
| `migration_post_commit_reconciliation` | Verification runs | Append-only |
| `migration_approvals` | Approval records | Append-only |
| `storage_backfill_jobs` | Legacy asset backfill jobs | Append-only |
| `storage_backfill_actions` | Per-asset backfill outcome | Append-only |

All IDs are UUID-shaped, never sequential.

## Immutable Migration Package
Built at job creation and re-verified at preflight. Contains:
- Source workbook IDs + `file_sha256`
- Mapping profile IDs + `profile_version`
- Go/No-Go report ID + `result`
- Row/create/update/preserve counts
- `package_sha256` = deterministic hash of the entire package payload

Any change to workbook checksum, mapping profile version or Go/No-Go
result invalidates the approval and the commit is blocked by preflight.

## Preflight controls
Every one of the following must pass before canonical writes begin:
1. Approval status is `Approved` and not expired
2. Go/No-Go report is present, not `NO-GO`
3. Every mapping profile in the package is still `Approved` with the same version
4. Every workbook still has the same `file_sha256`
5. Referenced storage objects exist and are `Available`
6. No open blocking issues on the dry-run
7. No rows still target reserved Dispatch 0 or 13
8. Rollback package has been built

Failures set job status to `Preflight Failed` and record every check in
the job's `preflight_result` document.

## Commit ordering
Batches are executed strictly in this order so foreign-key resolution
always finds a canonical parent:
```
Owner → Vehicle → Equipment → Driver
     → DriverCode → DispatchNumber
     → DriverOwnerRelationship → DriverVehicleAssignment
     → DriverEquipmentAssignment → CommunicationPreference
     → DriverLicence → VehicleRegistration → VehicleInsurance
     → VehicleInspection → VehicleDefect → VehicleMaintenance
     → EquipmentCompliance → DocumentLink
```

## Cross-sheet FK resolution
- **Owner ↔ Driver** by exact ABN match, then by canonical Owner ID reference
- **Vehicle ↔ Driver** by VIN, then by registration plus state
- Multiple matches or ambiguous ABN/VIN block the affected row
- No name-only automatic relationship

Every relationship writes lineage back to the source row + workbook.

## Idempotency
Every action carries a stable `commit_action_key` (e.g. `driver:9007:502`,
`owner:12345678901`). Repeated commit or resume checks `commit_action_key`
+ job ID before writing. Retry does not double-create.

## Rollback package
Built as canonical writes happen — never after the fact. Each action
records:
- Reverse action (`Delete | Restore | CloseRelationship | ReleaseNumber`)
- Prior value (nullable for creates)
- Expected current value (for conflict detection)
- Dependency order (reverse of commit order)

Rollback executes in reverse dependency order. Any target record whose
`updated_at` or `_source` has changed since commit is treated as a
**later-edit conflict** and left in place — the rollback action is
marked `Failed / conflict` and audited.

## Post-commit reconciliation
Runs after commit or on demand. Counts:
- Expected creates vs actual canonical records present
- Missing records
- Field mismatches (extensible)

Result: `Reconciled | Reconciled with Warnings | Failed Reconciliation`.
A job is not finalised to `Completed` until reconciliation reports
`Reconciled`.

## Legacy Storage Backfill
Scope-selectable:
- `Documents` — EB-05 documents missing `storage_object_id`
- `Exports` — EB-11 PDF exports missing `storage_object_id`
- `Migration Workbooks` — legacy `_data` workbooks not yet in storage
- `All Legacy Development Assets` — union of the above

Rules:
- Copy first, verify checksum by reading the stored bytes back
- Only then update the canonical reference to point at the storage object
- **Legacy source is retained** — never delete `_data`, never delete
  local filesystem originals. The backfill is idempotent — reruns skip
  assets that already carry a `storage_object_id`.

## Security & privacy
- No plaintext credentials in any response
- No PII in object keys — UUIDs only
- ReadOnly cannot see the immutable package or source-row snapshots
- Only Admin may approve real commits, execute Controlled Commit or Rollback
- Self-approval blocked for real commits (requester ≠ approver)
- All destructive actions require typed confirmation on the UI

## Remaining limitations (EB-15 scope)
- MongoDB multi-document transactions require deploy-time replica-set
  configuration. Staged idempotent mode is the current default.
- Real Blink integration, real email/SMS notification delivery and OCR
  document extraction remain out of scope.
- Cross-sheet resolution currently supports Owner and Vehicle FKs by
  ABN/VIN/registration. Equipment cross-sheet and Licence FKs use direct
  ID references only in EB-14; full name-normalisation matcher deferred
  to EB-15.
