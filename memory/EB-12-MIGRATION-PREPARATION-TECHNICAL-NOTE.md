# EB-12 — Real ACE Data Migration Preparation, Mapping & Dry-Run Control

## Purpose
Prepare the DCC for a controlled, reviewable real ACE migration (EB-13) by
providing a complete migration-control layer. EB-12 inspects, maps, validates,
reconciles and previews sanitised workbook data. **No canonical record is
mutated anywhere in EB-12**, and **no commit endpoint exists**. Only sanitised,
fictional fixtures are permitted as input.

## Module layout
```
backend/
├── migration_prep_module.py           ← Service + FastAPI router + collections
└── tests/
    └── test_migration_prep_eb12.py    ← 32 pytest cases (sanitised fixtures only)

frontend/
└── src/pages/
    ├── MigrationPreparationHub.jsx    ← /migration-preparation
    ├── MigrationWorkbooksPage.jsx     ← /migration-preparation/workbooks
    ├── MigrationMappingsPage.jsx      ← /migration-preparation/mappings
    ├── MigrationDryRunsPage.jsx       ← /migration-preparation/dry-runs
    └── MigrationDryRunDetailPage.jsx  ← /migration-preparation/dry-runs/:id
```

## Source authority
Every workbook is registered with an ``authority_level``: `Authoritative`,
`Supporting`, `Historical`, `Reference Only`, `Unknown`. Approval logic and
Go/No-Go gating respect this authority when weighting proposed values.

## Workbook profiling
Uploaded .xlsx / .csv are read with openpyxl / stdlib csv. The first non-empty
row is treated as the header row; duplicate header cells are marked with
`duplicate_of` in the column profile. Detected sheets are persisted as
`migration_source_sheets` linked to the workbook. Raw file bytes are cached
inside the workbook document under the private `_data` key (never returned
by any API) so subsequent dry runs can re-read the data without re-upload.

## Mapping versioning
`migration_mapping_profiles` are versioned per (workbook, sheet, target_entity)
tuple. Every profile enters the world as `Draft`. Approval requires
Manager/Admin. Approving a second profile for the same tuple sets the
previously-approved one to `Superseded` and inactive. Approved profiles are
**immutable**: any attempt to update or add/edit/delete field mappings on an
Approved profile returns 400. Cloning creates a fresh Draft with the next
version number and copies all field mappings.

## Transform rules
13 deterministic pure-Python functions are pre-seeded (`seed-eb12`):
trim, upper/lower/title, phone, email, date, currency, percentage, bool,
integer, driver_code, registration, VIN, ABN, status_map, blank_to_null,
state_abbr, control_chars. Functions are stateless, deterministic, and
independently unit-testable. Custom rules can be added; only known
`rule_type` values are accepted.

## Matching hierarchy
Deterministic, explainable, per-entity:

| Entity     | Match order                                                            |
| ---------- | ---------------------------------------------------------------------- |
| Driver     | canonical id → driver_code → dispatch_number → email + mobile          |
| Owner      | canonical id → ABN → business name                                     |
| Vehicle    | canonical id → VIN → registration + state → fleet_number               |
| Equipment  | canonical id → equipment_number → serial                               |

Multiple matches → Blocking. Probable matches → `Manual Review`. Name-only
matches never auto-update. Match evidence and confidence are always returned.

## Duplicate handling
Within-source duplicates are detected per key (driver_code, dispatch_number,
VIN, ABN, email) as rows are processed. Cross-workbook / canonical duplicates
surface as `DUPLICATE_*` issues with `severity=Error` and `blocking=True`.
Duplicates are never auto-merged; the resolution UI prompts a human choice.

## Source lineage
Every proposed value has an entry in `migration_source_lineage` with the
workbook id, checksum, file name, sheet id, sheet name, source row number,
source column name/index, original value, transformed value, applied
transform rule ids, mapping profile id + version, target entity type, and
proposed target field. Lineage rows are append-only for completed dry runs
and are cleared+rewritten on rerun to keep results deterministic for
unchanged inputs.

## Dry-run architecture
1. Create → row inserted with status `Queued`.
2. Execute → status `Validating`; row-by-row processing:
   - Apply per-field transforms → `transformed_snapshot`.
   - Validate required + null_handling; write issues.
   - Run matching (see hierarchy above); write match_status/evidence.
   - Check duplicates and reserved values (dispatch 0/13).
   - Check driver_code integer shape (non-integer → Warning, historical only).
   - Persist row, changes, and lineage.
3. Update totals + set status `Preview Ready`.

Re-executing (`/rerun`) clears prior rows/changes/issues/lineage and
regenerates them; result totals are deterministic for unchanged inputs.

## Issue resolution
`migration_issues` has controlled `severity` (Info/Warning/Error/Critical),
`status` (Open/In Review/Resolved/Accepted Risk/Rejected/Archived), and
`resolution_type` (10 controlled values). Only Manager/Admin/Compliance can
resolve. Critical or Open Blocking issues prevent GO.

## Identifier impact
Peek-only projection of live sequences (`number_sequences` read, never
written). Reports:
- Valid vs invalid Driver Codes
- Duplicates
- Historical (non-integer) Codes to be preserved as history only
- Reserved dispatch hits (0, 13)
- Active proposed dispatch numbers
- Projected next live sequence value

## Relationship impact
Rows with target `DriverOwnerRelationship`, `DriverVehicleAssignment`,
`DriverEquipmentAssignment` are collected and returned with their proposed
action + match status. No relationship is opened or closed.

## Compliance impact
Rows with compliance target entities are surfaced with proposed statuses.
The Worst-Status-Wins figure is *inferred* from the proposed rows but
never written back to any compliance record.

## Activation impact
For each Driver-target row, project a preview:
- projected activation status (Ready if key identifiers present, else Blocked)
- projected readiness status
- projected blocking items
No checklist is instantiated, no activation event is emitted, no notification
fires, no Driver Status changes.

## Document manifest
Document rows are collected as a manifest of *proposed* document entries
(type, entity match, expected file availability, source checksum). No file
is uploaded in EB-12.

## Go / No-Go logic
```
open_blockers   = migration_issues where status=Open and blocking=True
critical_issues = migration_issues where severity=Critical and status != Resolved
warnings        = migration_issues where severity=Warning and status=Open
all_approved    = every profile in dry-run has status=Approved

if open_blockers > 0 OR critical_issues > 0 OR not all_approved:
    result = "NO-GO"
elif warnings > 0:
    result = "CONDITIONAL GO"
else:
    result = "GO"
```
NO-GO reports cannot be approved (backend enforces 400). Approval /
rejection of GO or CONDITIONAL GO is recorded with actor and timestamp.

## Rollback design
`GET /dry-runs/{id}/rollback-manifest` returns a deterministic preview
enumerating: would-create field count, would-update field count, and the
prior values for every update. `applied` is always `false` in EB-12. The
same input produces the same output; safe to re-run any number of times.

## Permissions
| Action                                | ReadOnly | Allocator | Compliance | Manager | Admin |
| ------------------------------------- | :------: | :-------: | :--------: | :-----: | :---: |
| View workbooks / profiles / dry-runs  | ✅       | ✅        | ✅         | ✅      | ✅    |
| Upload workbook                       |          |           |            | ✅      | ✅    |
| Create / edit Draft profile           |          |           |            | ✅      | ✅    |
| Approve profile                       |          |           |            | ✅      | ✅    |
| Execute / rerun dry run               |          |           | ✅         | ✅      | ✅    |
| Resolve / reopen issues               |          |           | ✅         | ✅      | ✅    |
| Approve or reject Go / No-Go          |          |           |            | ✅      | ✅    |
| Rollback preview                      |          |           |            | ✅      | ✅    |

Backend enforces all of the above. Frontend forms may render for all viewers
but API calls return 403 when permission is denied.

## Privacy & sanitisation
- Only sanitised fictional workbooks may be uploaded.
- No real ACE names, addresses, phone numbers, emails, VINs, ABNs, or licence
  numbers are stored anywhere.
- All seed rows carry `_source: "seed-eb12"`.
- Raw workbook bytes are cached privately under the workbook document
  `_data` key; the value is stripped from every API response by `_clean_wb`.

## Known limitations
- Raw file bytes are held inside the workbook document — acceptable for
  development because sanitised fixtures are small. Production should move
  to object storage (S3/GCS) via the same abstraction used elsewhere.
- Sheet classification (mapping a sheet to its target entity type) is a
  manual step; automated inference is not implemented.
- Cross-sheet foreign-key resolution (e.g. Driver→Owner via ABN across
  multiple sheets in one workbook) is scoped to EB-13.
- Fuzzy matching is intentionally not implemented; only deterministic
  exact-key matching is supported.

## EB-13 commit requirements
For EB-13 to consume this preparation layer it must:
1. Read only Approved mapping profiles that have `is_active=True`.
2. Fetch the corresponding Preview-Ready dry run and its Go/No-Go report.
3. Refuse to run unless `approval_status = Approved` on a GO or
   CONDITIONAL GO report.
4. Consume `proposed_target_snapshot` for each row (not the raw source).
5. Advance number sequences and reserve dispatch numbers atomically at
   commit time (never before).
6. Write `driver_activation_records` and instantiate checklists via the
   normal EB-10 pathway — not through the migration module.
7. Persist the rollback manifest before applying any change so it can
   actually be applied if a commit fails halfway.
