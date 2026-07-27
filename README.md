# Driver Command Centre — ACE Car Freighters

> **Status:** Phase 2 Foundation Build (EB-06) — staging branch · `dcc-phase2-eb06`
> **Baseline release:** Phase 1 · `v0.1-phase1-baseline` (unchanged, on `main`)
> **Previous builds:** EB-01 · `dcc-phase2-eb01` · EB-02 · `dcc-phase2-eb02` · EB-03 · `dcc-phase2-eb03` · EB-04 · `dcc-phase2-eb04` · EB-05 · `dcc-phase2-eb05`

The **Driver Command Centre (DCC)** is ACE Car Freighters' operational control
surface. Phase 2 builds the canonical foundation registers underneath the
prototype modules established in Phase 1.

## Phase 2 status

| Milestone                            | State       |
| ------------------------------------ | ----------- |
| Business Blueprint                   | ✅ Complete |
| Technical Architecture               | ✅ Complete |
| Phase 2 Foundation Build             | 🟡 In progress |
| **EB-01** — App shell / branding / visual frame | ✅ Complete |
| **EB-02** — Foundation Registers | ✅ Complete |
| **EB-03** — Assignment & Relationship Layer | ✅ Complete |
| **EB-04** — Canonical Compliance Foundation | ✅ Complete |
| **EB-05** — Document Storage & Evidence Architecture | ✅ Complete |
| **EB-06** — Guided Spreadsheet Import & Migration Framework | ✅ **This build** |
| Real ACE spreadsheet import          | ⏳ Not performed |
| Notifications / alerts               | ⏳ Not performed |
| Production deployment                | ⏳ Not performed |

### EB-02 scope (this build)
- Four canonical master registers with UUID string ids and audit fields
  (`is_archived`, `created_at`, `created_by`, `updated_at`, `updated_by`)
- New collections: `owners`, `vehicles_register`, `equipment_register`
- `drivers` collection **shared** with the legacy prototype via an idempotent
  field-migration adapter (see technical note below)
- CRUD endpoints under `/api/{drivers|owners|vehicles|equipment}/*`
- Controlled status vocabularies enforced by Pydantic enums
- Uniqueness enforced: driver_code, active dispatch_number,
  registration_number, VIN, equipment_number
- Reserved dispatch numbers `0` and `13` rejected
- Cross-register integrity: `owner_id` must reference an existing Owner
- Role gating unchanged (ReadOnly cannot mutate; only Admin/Manager may archive)
- **Soft-delete only** — archive sets `is_archived=true` and status → Archived
- Frontend: four new Foundation Register pages at `/registers/{slug}` with
  heading, count, search, status filter, table, empty/loading/error states,
  Add / View / Edit / Archive actions and reusable `OwnerSelect` combobox
- Landing hub adds a "Foundation Registers" section above "Legacy Prototype
  Modules" (Phase 1 modules preserved intact)
- Development-only seed (idempotent): 3 drivers (existing, migrated),
  2 owners, 3 vehicles, 4 equipment. All non-driver seed rows prefixed `TEST ·`
  and tagged `_source: seed-eb02`. No real ACE data imported.

### What EB-02 explicitly does **not** change
- No ACE spreadsheet import
- No Compliance Intelligence changes
- No integrations (Blink, email, SMS, object storage, etc.)
- No changes to authentication credentials or the 5-role permission model
- No removal of prototype modules, records or routes
- No `main` branch changes; no production deployment

---

## EB-03 scope (this build) — Assignment & Relationship Layer

Three canonical relationship / assignment collections sit on top of the EB-02
registers. All are UUID-id, audit-fielded, soft-delete, and enforce their
uniqueness / cascade rules through a single service layer that is called by
both the HTTP routes and the startup reconciliation task — so business rules
live in exactly one place.

| Collection | Purpose | Key rules |
| ---------- | ------- | --------- |
| `driver_owner_relationships` | Which owner is the driver operating for (Company / Contractor / Self / Relief) | At most **one `is_current=true`** relationship per driver. Setting a new one auto-closes any prior current with an `end_date`. |
| `driver_vehicle_assignments` | Which driver is presently allocated to which vehicle | At most **one active + primary** assignment **per driver** and **per vehicle**. `display_on_dispatch=true` requires an active assignment on an unarchived driver + Active vehicle. Reassignment atomically closes both the outgoing driver's and the incoming vehicle's active-primary rows before creating the new one. |
| `driver_equipment_assignments` | Which driver holds which piece of ACE equipment | At most **one active** assignment per equipment_id. Creating a second active on the same equipment returns HTTP 409 unless the caller uses the `/reassign` endpoint. Assigning to equipment whose status is `Maintenance / Inactive / Archived` is rejected. |

### Equipment status synchronisation

Every equipment assignment mutation triggers `sync_equipment_status_after_change`:

- If the equipment has an active assignment and its status is `Available` → set to `Assigned`.
- If the equipment has no active assignment and its status is `Assigned` → set to `Available`.
- Blocked statuses (`Maintenance`, `Inactive`, `Archived`) are never overwritten.

### Cascades

- Archiving an assignment always closes the underlying `is_active` / `is_current` flag and stamps `end_date = today`.
- Archiving a driver / vehicle / equipment record (via the EB-02 register archive) does **not** hard-delete assignments; historical rows remain queryable via `?include_archived=true`.

### Routes added

```
GET    /api/driver-owner-relationships
GET    /api/driver-owner-relationships/{id}
POST   /api/driver-owner-relationships
PUT    /api/driver-owner-relationships/{id}
DELETE /api/driver-owner-relationships/{id}         (archive)

GET    /api/driver-vehicle-assignments
GET    /api/driver-vehicle-assignments/{id}
POST   /api/driver-vehicle-assignments
POST   /api/driver-vehicle-assignments/reassign     (atomic reassign)
PUT    /api/driver-vehicle-assignments/{id}
DELETE /api/driver-vehicle-assignments/{id}         (archive)

GET    /api/driver-equipment-assignments
GET    /api/driver-equipment-assignments/{id}
POST   /api/driver-equipment-assignments
POST   /api/driver-equipment-assignments/reassign   (atomic reassign)
PUT    /api/driver-equipment-assignments/{id}
DELETE /api/driver-equipment-assignments/{id}       (archive)
```

Every list endpoint accepts `?include_archived=true`, and supports
`driver_id`, plus register-specific filter (`owner_id` / `vehicle_id` /
`equipment_id`) and status filters (`is_current`, `is_active`, `is_primary`,
`display_on_dispatch`).

### Frontend surface

- New generic `RelationshipPage.jsx` at `/relationships/{driver-owner|driver-vehicle|driver-equipment}` — heading, count, search, status filter (All / Active-only / Historical-only), `Show archived` toggle, table with lookup labels for driver / owner / vehicle / equipment, and role-gated `Add` / `Reassign` / `View` / `Archive` actions.
- Hub now shows a "Relationships & Assignments" section between "Foundation Registers" and "Legacy Prototype Modules" so operators can pivot between master-data and relationship views.
- `DriverProfile.jsx` renders three canonical widgets (Current Owner, Vehicle Assignment, Equipment Assignments) sourced from the new endpoints, alongside the legacy grouped record list.

### Startup reconciliation

`startup_reconciliation()` runs after `ensure_indexes()` on every backend boot:

1. Reports any duplicate active-primary assignments per driver / per vehicle (logged as warnings — never destructive).
2. Reports any duplicate active assignments per equipment.
3. Re-syncs `equipment_status` against active assignments for all non-blocked equipment.

### Development seed (idempotent, tagged `_source: seed-eb03`)

- 3 current driver-owner relationships (Company / Contractor / Company)
- 3 active + 1 historical driver-vehicle assignments
- 3 active + 1 historical driver-equipment assignments

Re-running the seeder never duplicates or overwrites data.

### Tests

- `backend/tests/test_relationships_eb03.py` — 24 new EB-03 tests
- Backend suite: **115 / 115 pytest pass** (auth, role gating, EB-02 registers, EB-03 relationships, legacy CRUD, compliance, driver profile, backfill)

### What EB-03 explicitly does **not** change

- No ACE spreadsheet import
- No Compliance Intelligence changes
- No new integrations (email, SMS, object storage, etc.)
- No changes to authentication credentials or the 5-role permission model
- No removal or migration of prototype modules or records
- No `main` branch changes; no production deployment

---

## EB-04 scope (this build) — Canonical Compliance Foundation

Seven new canonical compliance-record collections that **monitor** the EB-02
master registers. Compliance records never own driver / vehicle / equipment
identity — they carry immutable UUID ids (`licence_id`, `registration_id`,
`policy_id`, `inspection_id`, `defect_id`, `maintenance_task_id`,
`equipment_compliance_id`) and reference the master record ids only.

### Collections added

| Collection                        | Master ref     | Notes |
| --------------------------------- | -------------- | ----- |
| `driver_licences`                 | `driver_id`    | One active primary per driver. |
| `vehicle_registrations`           | `vehicle_id`   | One current registration per vehicle. |
| `vehicle_insurance_policies`      | `vehicle_id`   | One current policy per vehicle **per cover type**. |
| `vehicle_inspections`             | `vehicle_id`   | Retains full history; fails feed vehicle compliance. |
| `vehicle_defects`                 | `vehicle_id`   | Severity ladder; critical opens block Compliant. |
| `vehicle_maintenance_tasks`       | `vehicle_id`   | Overdue tasks affect vehicle compliance. |
| `equipment_compliance_records`    | `equipment_id` | Multiple compliance types per equipment item. |

Every record carries the shared audit fields: `id`, `is_archived`,
`created_at`, `updated_at`, `created_by`, `updated_by`, `_source`, plus
optional `legacy_record_id` (compat bridge) and `evidence_document_id`
placeholder (no file storage in this build).

### Controlled compliance status vocabulary

```
Compliant · Due Soon · Expired · Missing · Incomplete · Under Review ·
Not Applicable · Archived
```

Status is **calculated** by the service layer from `expiry_date` and the
configurable warning window (env `COMPLIANCE_WARNING_DAYS`, default 30):

- Expired  — expiry before today
- Due Soon — expiry within warning window
- Compliant — expiry beyond warning window
- Missing — a required current/primary record does not exist
- Archived — record has been soft-deleted

### Worst-Status-Wins severity ordering

```
Not Applicable   0
Compliant       10
Due Soon        20
Under Review    25
Incomplete      30
Missing         40
Expired         50
Archived        excluded from active calculations
```

### Summary endpoints

```
GET /api/compliance/drivers/{driver_id}     → per-driver summary
GET /api/compliance/vehicles/{vehicle_id}   → per-vehicle summary
GET /api/compliance/equipment/{equipment_id}→ per-equipment summary
GET /api/compliance/overview                → filterable canonical rollup
```

Each summary returns `overall_status`, `severity`, `components[]`
(with `record_id`, `reason`, `expiry_date` where relevant),
`worst_component` and `calculated_at`.

Overview filters: `entity_type` (driver|vehicle|equipment, comma-separated),
`status`, `due_within_days`, `company_ref`, `include_archived`.

- **Driver summary** currently considers: Primary Driver Licence.
- **Vehicle summary** considers: Registration, Insurance, Latest Inspection,
  Open Defects, Overdue Maintenance.
- **Equipment summary** considers: all current active `equipment_compliance_records`
  (marked `is_mandatory` when required).

The pre-existing `GET /api/compliance/expiring` legacy endpoint is preserved
untouched — the frontend exposes it via a "Legacy Prototype" tab on the
Compliance page.

### CRUD routes added

```
/api/driver-licences                 GET, POST                (list + create)
/api/driver-licences/{id}            GET, PUT, DELETE         (archive on DELETE)

/api/vehicle-registrations           GET, POST
/api/vehicle-registrations/{id}      GET, PUT, DELETE

/api/vehicle-insurance               GET, POST
/api/vehicle-insurance/{id}          GET, PUT, DELETE

/api/vehicle-inspections             GET, POST
/api/vehicle-inspections/{id}        GET, PUT, DELETE

/api/vehicle-defects                 GET, POST
/api/vehicle-defects/{id}            GET, PUT, DELETE

/api/vehicle-maintenance-tasks       GET, POST
/api/vehicle-maintenance-tasks/{id}  GET, PUT, DELETE

/api/equipment-compliance            GET, POST
/api/equipment-compliance/{id}       GET, PUT, DELETE
```

Every list route accepts `?include_archived=true`, plus the relevant master
filter (`driver_id`, `vehicle_id`, `equipment_id`) and `status`.

DELETE is **soft archive only** (sets `is_archived=true`, status → Archived,
closes `is_primary` / `is_current` flags where applicable). Admin/Manager
only.

### Frontend surface

- New `CompliancePage.jsx` at `/compliance/records/{slug}` for all 7 record
  types — heading, count, search, status filter, due-date filter, archived
  toggle, role-gated Add / Edit / View / Archive with reusable driver /
  vehicle / equipment selects.
- Upgraded `/compliance` page — Canonical / Legacy Prototype tabs.
  Canonical tab shows entity tiles + status filters + due-within filter +
  worst-status-wins combined table with worst-component reason.
- Hub gains a "Canonical Compliance" section between "Relationships &
  Assignments" and "Legacy Prototype Modules" with 7 tiles and an "Open
  overview" link.
- `DriverProfile.jsx` now renders a canonical Driver Compliance card showing
  overall status + primary licence component.
- Legacy `/m/{slug}` prototype module routes remain accessible unchanged.

### Legacy compatibility bridge

- Legacy `licences`, `truck_regos`, `insurances`, `equipment`, `tilt_trays`,
  `maintenance`, `onboarding` collections and their `/api/modules/{slug}`
  routes are preserved untouched.
- Every canonical compliance record can carry a `legacy_record_id` pointing
  back at the originating legacy prototype record.
- No destructive migration runs on startup. Ambiguous legacy records remain
  for the future ACE spreadsheet import work — no silent auto-migration.

### Startup reconciliation

`compliance_records.startup_reconciliation()` runs after `ensure_indexes()`:

- Re-classifies status on every active licence / registration / insurance /
  equipment compliance record from its `expiry_date`.
- Sweeps scheduled maintenance tasks whose `scheduled_date` is in the past
  and flips their status to `Overdue`.

The task is fully idempotent — running it repeatedly produces the same
result.

### Development seed (idempotent, tagged `_source: seed-eb04`)

- 3 primary driver licences (Compliant / Due Soon / Expired)
- 3 vehicle registrations (Compliant / Due Soon / Expired)
- 3 vehicle insurance policies
- 3 vehicle inspections (Pass / Pass with observations / Fail)
- 2 vehicle defects (Critical Open / Rectified)
- 3 vehicle maintenance tasks (Scheduled / Overdue / Completed)
- 4 equipment compliance records (Compliant / Due Soon / Expired / Compliant)

### Tests

- `backend/tests/test_compliance_eb04.py` — 34 new EB-04 tests
- Full backend suite: **149 / 149 pytest pass** (was 115; zero regression)

### What EB-04 explicitly does **not** change

- No ACE spreadsheet import
- No file / document storage integration (`evidence_document_id` field is a placeholder)
- No automated numbering
- No notification / escalation engine
- No integrations (Blink, email, SMS, external APIs)
- No changes to authentication credentials or the 5-role permission model
- No removal or migration of prototype modules or records
- No `main` branch changes; no production deployment

---

## EB-05 scope (this build) — Document Storage & Evidence Architecture

Canonical secure evidence layer that separates **metadata** (Mongo) from
**binary content** (filesystem-backed private storage adapter). Every
document is versioned, links to canonical master / compliance records only
by id, and is fetched exclusively through authorised, streamed endpoints.

### Collections added

| Collection | Notes |
| ---------- | ----- |
| `documents` | Header record with current-version pointer, sensitivity, category, sha256 checksum, storage key. |
| `document_versions` | Immutable per-version blob metadata. Only one `is_current=true` per document. |
| `document_links` | Canonical bridge to Drivers, Owners, Vehicles, Equipment and every EB-04 compliance record; supports Evidence / Contract / Identification / Photo / Supporting / Generated Export / Other. |
| `document_access_events` | Append-only audit trail (Upload · View Metadata · Preview · Download · CreateVersion · Archive · Restore · Link · Unlink · Reject · Approve). |

### Storage abstraction

- Dev mode adapter writes into `${DOCUMENT_STORAGE_PATH:-/app/backend/document_storage}` (outside the web root, private).
- The API never returns `storage_key` or `storage_provider` in responses.
- Files are streamed through `GET /api/documents/{id}/download` and `/preview` with `Content-Disposition: attachment` (or `inline` for preview) and `Cache-Control: private, no-store`.
- A Production-ready adapter interface is prepared (`upload`, `download`, `preview`, `delete`, `exists`, `metadata`, `checksum`). **No external object-storage provider is connected** in this build.
- The `_malware_scan_status` field is prepared for a future scanning service. **No malware scanner is connected.** Files pass extension + declared-MIME + content-signature + size + non-empty checks before status is set to Active. This limitation is disclosed truthfully; nothing pretends a scanner is running.

### Upload rules

- Allowed extensions: `pdf, jpg, jpeg, png, webp, doc, docx, xls, xlsx, csv`.
- Default max size: **15 MB** (env `MAX_UPLOAD_BYTES`).
- Rejected: zero-byte, oversized, unsupported extension, mismatched declared MIME, mismatched content signature.
- Filenames sanitised (path traversal / control chars stripped).
- SHA-256 computed while streaming to disk.
- Duplicate checksum returns a warning (`duplicate_of`, `duplicate_of_title` in response) but does not auto-merge.
- Failed uploads clean up temporary files — no orphaned metadata or bytes remain.

### Versioning

- New file → version 1, status Active.
- `POST /api/documents/{id}/versions` creates a new version, closes the prior current with status Superseded, updates the document header pointer + new checksum + size + filename.
- Old versions remain queryable through `GET /api/documents/{id}/versions` and downloadable through `GET /api/documents/{id}/versions/{version_id}/download`.
- Existing bytes are never overwritten (sharded storage key: `xx/{document_id}/v{n}.{ext}`).

### Sensitivity defaults

| Document type | Default |
| ------------- | ------- |
| Profile Photo | Internal |
| Driver Licence | Confidential |
| Vehicle Registration | Internal |
| Vehicle Insurance | Confidential |
| Driver Contract | **Restricted** |
| Driver Pass | Confidential |
| Vehicle Defect | Internal |
| Supporting Document | Internal |

Role → sensitivity access table (download / preview):

| Sensitivity | Admin | Manager | Compliance | Allocator | ReadOnly |
| ----------- | :---: | :-----: | :--------: | :-------: | :------: |
| Standard      | ✅ | ✅ | ✅ | ✅ | ✅ |
| Internal      | ✅ | ✅ | ✅ | ✅ | ✅ |
| Confidential  | ✅ | ✅ | ✅ | ❌ | ❌ |
| Restricted    | ✅ | ✅ | ❌ | ❌ | ❌ |

- Only Admin / Manager / Allocator / Compliance may upload.
- Only Admin / Manager may archive / restore.
- Access history endpoint restricted to Admin / Manager / Compliance.

### Evidence integration

- Every EB-04 compliance record already carried an `evidence_document_id` placeholder. When a document is uploaded / linked as **primary Evidence** for a `DriverLicence`, `VehicleRegistration`, `VehicleInsurancePolicy`, `VehicleInspection`, `VehicleDefect`, `VehicleMaintenanceTask` or `EquipmentCompliance` record, that placeholder is now wired to the `documents.id`.
- Removing (archiving) that primary link clears the placeholder — no orphan reference remains.
- Compliance records may still carry unlimited supporting documents through `document_links`.
- Driver Contract is a supported document type with sensitivity **Restricted**; one primary contract per Driver is enforced through the primary-link uniqueness rule.
- Driver Pass evidence foundation is in place — the full operational Driver Pass module remains a future milestone.
- Profile photos flow through the same document architecture. Old profile photos remain as historical versions.

### Routes added

```
GET    /api/documents                                     list + filters
POST   /api/documents/upload                              multipart upload
GET    /api/documents/{id}                                metadata (audits ViewMetadata)
PUT    /api/documents/{id}                                metadata update
DELETE /api/documents/{id}                                soft archive (Admin/Manager)
POST   /api/documents/{id}/restore                        restore (Admin/Manager)
GET    /api/documents/{id}/download                       stream current version
GET    /api/documents/{id}/preview                        inline current version (PDF/image)

GET    /api/documents/{id}/versions                       version history
POST   /api/documents/{id}/versions                       upload new version
GET    /api/documents/{id}/versions/{vid}                 version metadata
GET    /api/documents/{id}/versions/{vid}/download        stream a specific version
GET    /api/documents/{id}/versions/{vid}/preview         inline a specific version

GET    /api/document-links                                filterable link list
POST   /api/document-links                                create link (auto-clears prior primary)
DELETE /api/document-links/{id}                           soft archive the link

GET    /api/documents/{id}/access-history                 append-only audit (Admin/Manager/Compliance)
```

### Frontend surface

- New `/documents` route → **Document Library** (search, type / status / sensitivity filters, archived toggle, upload, per-row preview / download / archive / restore, version history dialog with new-version upload).
- Hub gains a **Documents & Evidence** section with 3 tiles (Library, Under Review, Archived).
- Upload dialog supports drag-and-drop, file picker, entity type + entity id lookup for Driver / Vehicle / Equipment, relationship type + primary-evidence toggle, real-time upload progress, and safe error surfacing.
- Preview modal renders PDFs inside an iframe and images inline through the authenticated preview endpoint (blob URL, no permanent public URL).

### Development seed (idempotent, tagged `_source: seed-eb05`)

- 1 Driver Licence evidence PDF (primary evidence linked to first EB-04 licence)
- 1 Vehicle Registration evidence PDF
- 1 Vehicle Insurance evidence PDF
- 1 Vehicle Inspection PNG
- 1 Vehicle Defect PNG
- 1 Equipment Compliance PDF
- 1 Driver Contract PDF (Restricted)
- 1 Driver Profile Photo PNG

Each includes a real tiny binary written to the dev storage directory and a
primary `document_links` row. Restart-safe — the seed is skipped when
`_source: "seed-eb05"` documents already exist.

### Tests

- `backend/tests/test_documents_eb05.py` — 28 new EB-05 tests (upload validation · versioning · links · evidence integration · download / preview / sensitivity gating · seed idempotency)
- Full backend suite: **177 / 177 pytest pass** (was 149; zero regression)

### Legacy compatibility

- All legacy prototype modules and their 8 CRUD routes remain untouched.
- Legacy file paths on prototype records are **not** silently migrated. When ACE spreadsheet import lands in a future build, a reporting helper is planned to identify verifiably matchable dev records; no canonical document is fabricated without a real source file.

### Known limitations (EB-05)

1. **Malware scanning is not connected.** File-signature sniff + extension / MIME cross-check + size checks are enforced, and the `_malware_scan_status` metadata field is reserved for the future scanner. Documents are marked Active immediately after passing local validation.
2. Dev storage adapter uses the local filesystem inside the container. Files persist across supervisor reloads but are not replicated. Production migration to a private object-storage bucket is a separate future task.
3. Preview supports PDF and image mime types only. Office documents can be downloaded but not previewed inline.
4. No electronic signing, expiry automation or OCR / AI extraction — deferred by design.

### What EB-05 explicitly does **not** change

- No ACE spreadsheet import
- No production object-storage integration
- No OCR / AI extraction
- No automated numbering
- No notification / alerts engine
- No electronic signing of Driver Contracts
- No changes to authentication credentials or the 5-role permission model
- No removal or migration of prototype modules or records
- No `main` branch changes; no production deployment

---

## EB-06 scope (this build) — Guided Spreadsheet Import & Migration Framework

Canonical import pipeline that safely loads XLSX / XLSM / CSV spreadsheets
into the DCC canonical registers. Every commit follows a mandatory dry-run;
blocking conflicts must be resolved before commit is allowed; created records
are reversible for a period after commit via soft-archive rollback.

### Collections added

| Collection | Notes |
| ---------- | ----- |
| `import_jobs` | Header record with target domain, mode, status, row counts, commit / rollback timestamps. |
| `import_files` | Uploaded workbook / CSV metadata + private inline binary (kept server-only, never returned). |
| `import_mappings` | Versioned source-header → canonical-field mapping profiles. |
| `import_rows` | One row per source spreadsheet row: raw values, normalised values, validation status, match status, action, errors, warnings, conflict ids, commit status, created / updated record ids. |
| `import_conflicts` | Row-level conflicts (Blocking / Warning / Information) with resolution + resolved-by / resolved-at. |
| `import_commits` | Per-commit batch — created / updated / skipped / failed counts + record_actions (before-state for updates) enabling safe rollback. |
| `import_rollback_events` | Append-only rollback history: restored count, archived-created count, failed count. |

All identifiers are immutable UUID strings (`import_job_id`, `import_file_id`, `mapping_id`, `import_row_id`, `conflict_id`, `import_commit_id`, `rollback_event_id`).

### File parser & safety

- **openpyxl 3.1.5** with `data_only=True`, `read_only=True`, `keep_links=False`, `keep_vba=False`.
  - Formulas are **never executed** — the parser returns cached values only.
  - External workbook links are **never followed**.
  - Macros are **never executed** — the VBA payload is ignored.
- CSV via Python's stdlib `csv` reader.
- Row / column / file-size limits enforced: 50,000 rows, 250 columns, 20 MB per file.
- Hidden sheets are surfaced with a `hidden=true` flag; the operator must consciously select them.
- Unsupported or unreadable workbooks are rejected with a safe error.
- Empty rows are dropped from validation.

### Supported target domains

`drivers`, `owners`, `vehicles`, `equipment`, `driver-licences`,
`vehicle-registrations`, `vehicle-insurance` — each with typed field specs,
required flags, unique-field detection, controlled-value enums, high-risk
update flags and a match priority. The `DOMAIN_CONFIGS` registry can be
extended in code to add relationship domains (`driver-owner`, `driver-vehicle`,
`driver-equipment`) and further compliance record types.

### Normalisation

Reusable helpers cover whitespace collapse, title-case names, email
lower-casing, Australian mobile digit-only + leading-zero fix, ABN
digit-only, registration / VIN / equipment-number upper-casing, Excel serial
date conversion, Australian date-format parsing (`DD/MM/YYYY`, `D/M/YYYY`,
`DD-MM-YYYY`, `YYYY-MM-DD`, `DD/MM/YY`), boolean and percentage parsing,
blank handling. **All transformations are visible in the dry-run row report**
— nothing is silently changed.

### Matching priorities

- **Drivers**: driver_code → dispatch_number → email → full_name
- **Owners**: abn → name → email
- **Vehicles**: vin → registration_number
- **Equipment**: equipment_number
- **Compliance rows**: licence_number / registration_number_snapshot / policy_number, then canonical entity id.

The canonical resolver returns `Exact Match` (1 hit), `Multiple Matches`
(2+ hits — Blocking conflict), or `No Match`. Probable matches remain a
future enhancement — nothing is auto-merged.

### Duplicate & conflict detection

- Within-file duplicates by business identifier produce warnings.
- Cross-record unique-field conflicts (e.g. an incoming `driver_code` already
  held by a different canonical record) create a **Blocking** conflict with
  the existing record reference.
- Multiple candidate matches on the mapped fields produce a **Blocking**
  `Multiple Candidate Matches` conflict.

### Dry-run validation

Every job runs `POST /api/imports/{id}/validate` before commit. The endpoint
clears prior rows and conflicts, then produces per-row `validation_status`
(Valid / Warning / Error / Skipped), `match_status`, `action`
(Create / Update / Skip / Review / No Change) and lifts summary counts onto
the job. Commit is only allowed once the job is `Ready to Commit` and no
Blocking conflict remains `Unresolved`.

### Commit safeguards

- Confirmation dialog on the frontend; explicit endpoint (`POST /commit`) on the backend.
- 409 Conflict returned if any Blocking conflict is still `Unresolved`.
- Blank source values **never overwrite** an existing non-empty field.
- High-risk field updates (Driver Code, Dispatch Number, Registration, VIN)
  raise HIGH-RISK warnings visible on the row.
- Each commit records enough before-state on `updated` rows to reverse.
- Failed rows are marked `Failed` and left with an appended error; the job
  status becomes `Partially Committed`; `POST /retry-failed` flips them back
  to `Not Committed` for re-attempt.

### Rollback

`POST /api/imports/{id}/rollback` (Admin/Manager only) soft-archives
records created by this import (matching by `_import_job_id`) and restores
the captured `before` field state on updates. Result reported as `Completed`,
`Partially Completed`, `Failed` or `Not Supported`, plus per-record error
list.

### Compliance imports

For `driver-licences`, `vehicle-registrations` and `vehicle-insurance`, the
importer feeds committed records through the EB-04 `_classify_expiry` helper
so `status` is derived from source dates rather than trusted verbatim from
the spreadsheet. Spreadsheet colour / visual status is never treated as
authoritative.

### Evidence-reference handling

The importer never invents a document. Optional evidence-filename source
columns land as unresolved references in the row payload. Only where an
EB-05 document's checksum, filename or explicit `document_id` unambiguously
matches will the wiring be proposed for review. External file paths are never
converted to public links.

### Routes added

```
GET    /api/imports                              list + filters
POST   /api/imports                              create job
GET    /api/imports/{id}                         job detail
DELETE /api/imports/{id}                         archive (Admin/Manager)

POST   /api/imports/{id}/file                    upload source spreadsheet
GET    /api/imports/{id}/sheets                  safe workbook inspection
POST   /api/imports/{id}/inspect                 pick sheet
POST   /api/imports/{id}/mapping                 attach mapping profile

POST   /api/imports/{id}/validate                dry-run
GET    /api/imports/{id}/validation-summary
GET    /api/imports/{id}/rows                    paginated
GET    /api/imports/{id}/conflicts

PUT    /api/import-conflicts/{cid}               resolve one
POST   /api/imports/{id}/commit                  explicit commit (409 on blocking)
GET    /api/imports/{id}/commit-history
POST   /api/imports/{id}/retry-failed
POST   /api/imports/{id}/rollback                Admin/Manager

GET    /api/import-templates                     list domain templates
GET    /api/import-templates/{domain}            fields + required + unique + high-risk metadata
```

### Frontend surface

- **Import Centre** at `/imports` — new-job button, status summary tiles
  (In Progress / Committed / Failed / Rolled Back) and a jobs table with
  domain, mode, status badge, row totals and open link.
- **Guided Wizard** at `/imports/{id}` — stepper (Upload → Sheet → Map → Validate → Conflicts → Commit) with drag-and-drop upload, sheet chooser (row/column count + header preview), auto-guess column mapping, dry-run + row-level results table (validation status / match status / action / normalised values / errors + warnings), conflict resolution buttons (Skip / Keep Existing / Map to Existing), explicit-confirm commit dialog, commit history + rollback (role-gated).
- **Hub** gains a "Data Import & Migration" section between Documents & Evidence and Canonical Compliance.

### Permissions

| Action | Admin | Manager | Compliance | Allocator | ReadOnly |
| ------ | :---: | :-----: | :--------: | :-------: | :------: |
| List jobs                     | ✅ | ✅ | ✅ | ✅ | ✅ |
| Create job / upload / map     | ✅ | ✅ | ✅ | ✅ | ❌ |
| Resolve conflicts             | ✅ | ✅ | ✅ | ❌ | ❌ |
| Commit                        | ✅ | ✅ | ✅ | ❌ | ❌ |
| Rollback                      | ✅ | ✅ | ❌ | ❌ | ❌ |
| Archive job                   | ✅ | ✅ | ❌ | ❌ | ❌ |

### Tests

- `backend/tests/test_imports_eb06.py` — 20 new EB-06 tests
- Full backend suite: **197 / 197 pytest pass** (was 177; zero regression)

### Known limitations (EB-06)

1. **No real ACE spreadsheets loaded.** All tests use small generated fictional
   fixtures. Real ACE data migration is a separate future task.
2. Import file bytes are stored inline on the `import_files` document to keep
   private storage strictly internal to this module. When large real-world
   files land, migration to the EB-05 document-storage adapter is
   straightforward.
3. Probable / fuzzy matching is not implemented — matches must be exact on
   the canonical priority fields. Multiple candidates always block for
   manual review.
4. Relationship domains (`driver-owner`, `driver-vehicle`, `driver-equipment`)
   are architecturally supported by the framework but their domain configs
   are not wired in this build.
5. Rollback restores the `before` state captured at commit time; if a
   downstream user has edited the record after import, those manual edits
   are lost on rollback of that field.
6. Historical import mappings are versioned but the framework does not yet
   surface a mapping browser page — profiles are created inline per job.

### What EB-06 explicitly does **not** change

- No real ACE spreadsheet data was imported.
- No external integrations (Blink, email, SMS, LLMs, Power BI, cloud object storage).
- No automated numbering, alerts, notifications, OCR or AI extraction.
- No changes to authentication credentials or the 5-role permission model.
- No removal or migration of prototype modules or records.
- No `main` branch changes; no production deployment.

---

## Technical Note — EB-02 compatibility approach

**Canonical collections**

| Register  | Route                | Mongo collection      | Notes                                                   |
| --------- | -------------------- | --------------------- | ------------------------------------------------------- |
| Drivers   | `/api/drivers/*`     | `drivers`             | **Shared** with legacy `/api/modules/drivers`. Migrated. |
| Owners    | `/api/owners/*`      | `owners`              | New.                                                    |
| Vehicles  | `/api/vehicles/*`    | `vehicles_register`   | New. Distinct from the legacy `truck_regos` collection. |
| Equipment | `/api/equipment/*`   | `equipment_register`  | New. Distinct from the legacy `equipment` collection.   |

**Why the split for vehicles & equipment.** The legacy `truck_regos` and
`equipment` collections model different concerns (rego tracking, kit
assignments). The canonical registers model *the asset itself* with
ownership. Keeping them in separate collections avoids shape collisions and
keeps the prototype API fully backward-compatible.

**Driver migration.** On every startup, `migrate_existing_drivers()` copies
legacy → canonical fields on any doc missing them:

- `name` → `full_name`
- `driver_number` → `driver_code`
- `phone` → `mobile_number`
- `status` → `driver_status` (mapped to controlled values)
- `company` → `company_ref`
- `is_archived` defaulted to `false`

Legacy fields are **not removed**, so `/api/modules/drivers`, the compliance
lookup and the driver-profile page continue to read the same records. New
writes via `/api/drivers` update both canonical and legacy mirror fields.

**Seed behaviour.** `seed_registers()` runs on every startup but only inserts
rows that don't already exist (dedup by `name`, `registration_number`,
`equipment_number`). Restarting the pod never duplicates seeded data.

**Routes added**

```
GET    /api/drivers            (extends prior canonical listing)
POST   /api/drivers
GET    /api/drivers/{id}       (does not collide with .../profile)
PUT    /api/drivers/{id}
DELETE /api/drivers/{id}       (soft delete — sets is_archived + status)

GET    /api/owners
POST   /api/owners
GET    /api/owners/{id}
PUT    /api/owners/{id}
DELETE /api/owners/{id}

GET    /api/vehicles
POST   /api/vehicles
GET    /api/vehicles/{id}
PUT    /api/vehicles/{id}
DELETE /api/vehicles/{id}

GET    /api/equipment
POST   /api/equipment
GET    /api/equipment/{id}
PUT    /api/equipment/{id}
DELETE /api/equipment/{id}
```

Every list endpoint accepts `?include_archived=true` to include soft-deleted
records.

**Legacy limitations remaining.** The `driver_id` field on legacy licence /
truck-rego / insurance / equipment / tilt-tray / maintenance records still
points at the driver's UUID (unchanged behaviour). Cross-linking legacy
tracking records to canonical vehicles / equipment is out of scope for EB-02.

---

## Tech Stack

| Layer        | Stack                                                                |
| ------------ | -------------------------------------------------------------------- |
| Frontend     | React 19, React Router v7, TailwindCSS, shadcn/ui primitives, Phosphor Icons, sonner toasts, Axios |
| Backend      | FastAPI, Motor (async MongoDB), PyJWT, bcrypt, Pydantic v2          |
| Database     | MongoDB                                                              |
| Auth         | JWT Bearer tokens (localStorage), 24h expiry                         |
| Build / Dev  | Yarn, CRA (CRACO), Uvicorn                                           |

---

## Current Features

### Authentication & Roles
- JWT-based login (`/api/auth/login`, `/api/auth/me`, `/api/auth/register`)
- Five-role structure: **Admin**, **Manager**, **Allocator**, **Compliance**, **ReadOnly**
- Role-gated endpoints (ReadOnly cannot mutate; only Admin/Manager can delete)
- Seeded admin on first start (see "Seeded prototype login" below)

### Operational Hub (`/`)
- Hero greeting + system status strip
- "Compliance · Next 30 Days" rollup widget (red / amber / green)
- 4-column "Control Room Grid" of 8 operational modules with live record counts

### 8 Module Pages — full CRUD-ready
1. **Driver Hub** — driver profiles, contacts, status, master records
2. **Driver Licences** — expiry tracking, alerts
3. **Driver Truck Rego** — registration tracking and due dates
4. **Driver Insurance** — policy tracking, expiry, compliance
5. **ACE Equipment** — equipment assigned to drivers and vehicles
6. **ACE Maintenance** — service history, defects, inspections
7. **ACE Tilt Trays** — tray register and tray-specific compliance
8. **Driver Start Profile** — new driver onboarding workflow

### Compliance
- `/compliance` — full risk view with status + module filters, summary tiles,
  per-module link cards and an at-risk table (Expired / Due Soon badges)
- Backend endpoint `/api/compliance/expiring` classifies records by expiry date
  (default 30-day horizon)

### Driver-centric Relationships
- Every operational record links back to a canonical **Driver** via `driver_id`
- Searchable Driver dropdown in every Add/Edit dialog (name + driver number + company)
- `/drivers/:driverId` profile page — driver hero + all linked records grouped
  by section (Licences, Truck Rego, Insurance, Equipment, Maintenance,
  Tilt Trays, Onboarding)
- Compliance and module tables show the canonical driver name, clickable to profile

### Tests
- Backend: **58/58** pytest pass (auth, role enforcement, generic CRUD for all 8
  modules, compliance, driver profile, backfill)
- Frontend: 100% pass via Playwright (login → hub → modules → driver profile →
  compliance flow)

---

## Seeded Prototype Login

The startup seeder creates a default Admin if no users exist:

```
Email:    admin@acedriverhub.com
Password: Admin@123
Role:     Admin
```

> ⚠️ **Security note — prototype only.**
> The seeded credentials are intentionally weak so that the prototype can be
> demoed out-of-the-box. **They must be changed before any real-world
> deployment.** Override via the `ADMIN_EMAIL` / `ADMIN_PASSWORD` env vars
> in `backend/.env`. The seeder rotates the stored bcrypt hash automatically
> on next startup when the env values change.

---

## Repository Layout

```
ace-driver-hub/
├── backend/                # FastAPI app
│   ├── server.py           # All routes, auth, CRUD, compliance, driver profile
│   ├── requirements.txt
│   └── .env.example
├── frontend/               # React app
│   ├── src/
│   │   ├── App.js
│   │   ├── pages/          # Login, Hub, ModulePage, Compliance, DriverProfile
│   │   ├── components/
│   │   │   ├── app/        # AppHeader, ProtectedRoute, DriverSelect
│   │   │   └── ui/         # shadcn primitives
│   │   ├── context/        # AuthContext
│   │   └── lib/            # api.js, modules.js
│   ├── package.json
│   └── .env.example
├── memory/                 # PRD + credentials notes (test_credentials.md is git-ignored)
└── README.md
```

---

## Setup Instructions

### Prerequisites
- Node.js 18+ and **Yarn** (npm is not supported)
- Python 3.10+
- MongoDB running locally (default `mongodb://localhost:27017`) or a remote URI

### 1. Clone
```bash
git clone <your-fork-url> ace-driver-hub
cd ace-driver-hub
```

### 2. Backend
```bash
cd backend
cp .env.example .env

# Generate a JWT secret
python3 -c "import secrets; print(secrets.token_hex(32))"
# Paste the result into JWT_SECRET in .env

pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```

The backend will:
- Connect to MongoDB
- Create unique indexes on `users.email` and `id` per collection
- Seed the default Admin user if missing
- Seed sample data (3 drivers + records for every module) on the very first run
- Run an idempotent `backfill_driver_ids()` to link existing records to drivers

### 3. Frontend
```bash
cd frontend
cp .env.example .env
# Adjust REACT_APP_BACKEND_URL if your backend is not on localhost:8001

yarn install
yarn start
```

The app runs on `http://localhost:3000`.

### 4. First login
Open `http://localhost:3000/login` and sign in with the seeded admin
credentials above. You will land on the operational hub.

---

## API Surface (summary)

All routes prefixed with `/api`.

### Auth
- `POST /api/auth/login` — `{ email, password }` → `{ access_token, token_type, user }`
- `GET  /api/auth/me` — current user (Bearer required)
- `POST /api/auth/register` — Admin-only, body `{ email, password, full_name, role }`

### Modules (`{slug}` ∈ `drivers`, `licences`, `truck-rego`, `insurance`, `equipment`, `maintenance`, `tilt-trays`, `onboarding`)
- `GET    /api/modules/{slug}` — list
- `GET    /api/modules/{slug}/{id}` — single record
- `POST   /api/modules/{slug}` — create (any role except ReadOnly)
- `PUT    /api/modules/{slug}/{id}` — update (any role except ReadOnly)
- `DELETE /api/modules/{slug}/{id}` — delete (Admin or Manager only)

### Compliance & Profile
- `GET /api/compliance/expiring?horizon=30` — rollup + at-risk records
- `GET /api/drivers/{driver_id}/profile` — driver + linked records grouped by module

### Stats
- `GET /api/stats/overview` — count of records per module

---

## Test Summary

| Suite                                                | Status        |
| ---------------------------------------------------- | ------------- |
| Backend pytest (auth, CRUD ×8, compliance, profile, backfill) | **58 / 58 pass** |
| Frontend Playwright (login → hub → modules → driver profile → compliance) | **all flows green** |

Reports archived in `test_reports/` (git-ignored). Test suites live in
`backend/tests/`.

---

## Roadmap (post-baseline)

Captured in `memory/PRD.md`. Not part of this baseline:

- Edit row dialog (reusing field config + DriverSelect)
- Inline expiry alert badges (red/amber/green) per row
- Admin user management page
- Driver Risk Score badge
- Email/SMS digests
- Document upload / object storage
- Audit log + CSV export

---

## Status

**Phase 1 Baseline complete.** All listed features implemented and tested. No
new functionality added beyond this baseline in this commit — this version is
the secure checkpoint for future iterations.

---

## Phase 2 · EB-07a — Notifications, Alerts & Escalation Engine (backend) — 2026-07-27

Canonical DCC notification engine. In-app notifications are real; email and
SMS deliveries are **Simulated** — no external provider is contacted in
development. Rendered content is visible via the authenticated development
outbox.

### Collections added
`notification_rules`, `notification_events`, `notifications`,
`notification_recipients`, `notification_deliveries`,
`notification_acknowledgements`, `notification_snoozes`,
`notification_escalations`, `notification_job_runs`,
`notification_dead_letters`, `notification_preferences`. Immutable UUID ids,
audit fields, `_source` tagging, soft-archive semantics preserved.

### Engine
- 19 controlled `event_type` values, 15 `entity_type` values, 5 severities,
  3 channels, 8 notification statuses, 9 delivery statuses, 5 digest modes,
  9 recipient types, 12 recipient strategies.
- Deterministic `event_key` (SHA-256 truncated) — repeated processing of the
  same logical event is idempotent.
- Deduplication key on the notification collapses repeated events into a
  single Active notification with `last_triggered_at` updates.
- Recipient resolver walks canonical `users`, `drivers`, `owners` only —
  **no personal contact information is duplicated** into notification data.
  Recipient snapshots are stored on `notification_recipients` for delivery
  history only.
- 15 versioned templates (`compliance_due_soon`, `compliance_expired`,
  `compliance_missing`, `critical_defect`, `high_defect`,
  `maintenance_due_soon`, `maintenance_overdue`,
  `driver_activation_incomplete`, `document_under_review`,
  `document_rejected`, `import_validation_failed`, `import_ready_to_commit`,
  `import_partial_commit`, `import_commit_failed`, `manual_notification`).
  Placeholders are safe — no arbitrary code execution.
- Scheduler abstraction with **manual + startup-one-shot** entrypoints. No
  live in-process cron loop is enabled in EB-07a. Production requires a
  durable worker (e.g. Kubernetes CronJob or Cloud Scheduler) — documented
  as a known limitation.

### Compliance & critical scans
- Idempotent compliance scan reads EB-04 canonical records
  (`driver_licences`, `vehicle_registrations`, `vehicle_insurance_policies`)
  and emits Due Soon / Expired / Missing events.
- Idempotent critical scan reads EB-04 defects and maintenance tasks and
  emits Critical / High / Due Soon / Overdue events.
- Reconciliation job auto-resolves notifications whose source is no longer
  triggering the condition.

### Escalation
- Configurable per-rule `escalation_policy`. Defaults:
  Due Soon → escalate to **High** after 23 days.
  Expired → escalate to **Critical** after 3 days.
  Critical Defect → repeat every 4h; expand recipients to Admin after 24h.
  Maintenance Overdue → escalate to Critical after 3 days.
- Every escalation writes an immutable `notification_escalations` row and
  updates the notification severity + status.

### Snooze
- Ceiling per severity (configurable): Information/Low 30d, Medium 14d,
  High 7d, Critical 24h. Excess is rejected with HTTP 400.
- Snooze does not touch the source record. When the snooze expires the
  `process-snoozes` job returns the notification to Active if the source
  condition still holds.

### Delivery
- In-app deliveries are recorded as `Sent` immediately.
- Email/SMS deliveries are recorded as `Simulated` — provider stored as
  `simulated`, rendered subject/body captured, no network call made.
- Retry schedule (configurable): 0m, 5m, 30m, 2h, 12h. After 5 attempts a
  delivery is failed and a `notification_dead_letters` row is created. If
  **all** deliveries for a notification are Failed, the notification moves
  to `Delivery Failed`.
- Development outbox exposes `simulate-failure` / `simulate-success` per
  delivery, gated to Admin/Manager.

### Routes (all under `/api/…`)
- Notifications: `GET /notifications`, `GET /notifications/{id}`, `PUT /notifications/{id}/read`, `POST /notifications/{id}/acknowledge`, `POST /notifications/{id}/snooze`, `POST /notifications/{id}/resolve`, `POST /notifications/{id}/reopen`, `DELETE /notifications/{id}`, `GET /notifications/overview`, `GET /notifications/counts`, `GET /notifications/my-notifications`.
- Rules: `GET/POST/PUT/DELETE /notification-rules[/{id}]`.
- Preferences: `GET/PUT /notification-preferences/me`, `GET /notification-preferences`, `PUT /notification-preferences/{id}`.
- Jobs: `POST /notification-jobs/{compliance-scan|critical-scan|process-snoozes|process-escalations|retry-deliveries|reconcile}`, `GET /notification-jobs`, `GET /notification-jobs/{id}`.
- Outbox: `GET /notification-outbox`, `GET /notification-outbox/{id}`, `POST /notification-outbox/{id}/simulate-failure`, `POST /notification-outbox/{id}/simulate-success`.

### Permissions
| Role | Rules | Jobs | Outbox | Ack/Snooze | Resolve | Reopen | Archive |
| --- | :-: | :-: | :-: | :-: | :-: | :-: | :-: |
| ReadOnly | list-only | ✕ | ✕ | ✕ | ✕ | ✕ | ✕ |
| Allocator | list-only | ✕ | ✕ | ✓ | ✕ | ✕ | ✕ |
| Compliance | list-only | compliance-scan / critical-scan | ✓ (view) | ✓ | ✓ | ✕ | ✕ |
| Manager | full | all | ✓ | ✓ | ✓ | ✓ | ✓ |
| Admin | full | all | ✓ | ✓ | ✓ | ✓ | ✓ |

Critical notifications cannot be fully disabled by ordinary users via
`/notification-preferences/me` (HTTP 400).

### Seed data (`_source: "seed-eb07"`, idempotent)
1 Due Soon licence · 1 Expired registration · 1 Missing insurance ·
1 Critical defect · 1 Overdue maintenance · 1 Document Under Review ·
1 Import Validation Failed · 1 Acknowledged · 1 Snoozed · 1 Escalated ·
1 Failed simulated delivery · 1 Resolved. All fictional; **no real ACE
data was imported**.

### Testing
- `backend/tests/test_notifications_eb07a.py` — **40 new pytest cases**
  covering rules/events/dedup/lifecycle/deliveries/retry/dead-letter/
  escalation/snooze/preferences/permissions/jobs.
- **237 / 237 backend pytest pass** — zero regression from the previous
  197 baseline. Two legacy tests in `test_driver_relationships.py` were
  hardened to tolerate drivers created via EB-06 import (which use only
  `full_name`) — no behavioural change.

### Known limitations / Production requirements
- No external email/SMS provider is activated. All non-in-app deliveries
  are `Simulated`.
- No live in-process cron. Production must run the six job endpoints via
  a durable scheduler (Kubernetes CronJob / Cloud Scheduler / equivalent).
- Fuzzy or probable matching is not implemented — event keys are exact.
- Digest modes are stored on preferences but not yet acted on (no digest
  sender in EB-07a).
- Driver Activation event surfaces are prepared but source records for
  activation still live in the existing legacy onboarding module. Full
  activation-readiness scanning is deferred to a later milestone.
- Frontend integration (bell, Notifications Centre, cross-module
  indicators) is intentionally **not** built in EB-07a — that is EB-07b.

## Phase 2 · EB-07b — Notifications Centre & Frontend Integration — 2026-07-27

Full DCC notification user experience built against the EB-07a backend.
The approved DCC shell, branding, header, canonical registers,
relationships, compliance, documents and import wizard are all
preserved — the notification frontend adds a header bell, a full
Notifications Centre, and compact cross-module alert indicators.

### Header notification bell
- `NotificationBell` mounted in `AppHeader`. Shows unread count badge,
  Critical/High severity indicator dot, and a recent-notification
  dropdown with severity dots, titles, human-friendly times, and
  source-record deep-links.
- Polls `/api/notifications/counts` every 60 seconds.
- Mark-all-read acts on the visible dropdown rows.

### Notifications Centre (`/notifications/:view`)
Route slugs: `my`, `all`, `critical`, `snoozed`, `resolved`, `rules`,
`preferences`, `outbox`, `failed`, `jobs`. Tabbed single page — each
slug is a real URL and preserves browser navigation.

- Summary tiles: Active, Unread, Critical, High, Snoozed, Delivery
  Failures.
- List filters: search, status, severity, event type, entity type,
  unread-only, include-archived, refresh.
- Detail drawer: title, message, severity, status, entity meta,
  first/last triggered, next repeat, recipients, deliveries (rendered
  subject + body), acknowledgements, snoozes, escalations. Actions
  gated by role: Mark read, Acknowledge (with note), Snooze
  (preset + custom hours, severity ceiling enforced), Resolve (reason
  required), Reopen (Admin / Manager only).
- Explicit disclaimers: acknowledgement and snooze track operator
  awareness only — they do not modify canonical compliance status.

### Rules
- Full CRUD dialog with all engine fields (event type, entity type,
  severity, channels, recipient strategy, warning days, repeat
  interval, template key, priority, active).
- Toggle active/inactive without archive.
- Archive with confirmation.
- Test rule — client-side simulated toast; no external delivery.

### Preferences
- Per-user event × channel preferences with minimum severity, digest
  mode, enabled toggle. Development banner explains that Email/SMS
  are simulated and Critical cannot be fully disabled.

### Delivery Outbox
- "Development Simulation Only" banner.
- Filters by status and channel.
- Row-level Simulate Success / Simulate Failure actions.
- Detail modal renders subject and body inline; provider credentials
  are never displayed.

### Failed Deliveries
- Filtered outbox view (Failed + Retry Scheduled).
- One-click retry.

### Job History
- Six manual job-run buttons with confirmation dialog:
  compliance-scan, critical-scan, process-snoozes,
  process-escalations, retry-deliveries, reconcile.
- Runs appear in the history table with status, timing, counts and
  triggered-by. **No live in-process cron** — messaging that
  Production requires a durable scheduler stays visible on the page.

### Cross-module indicators (source of truth = notifications, not
copied master fields)
- Hub: `hub-notification-strip` with Active / Critical / High /
  Delivery-failures counters and deep-links.
- Register (`/registers/drivers|vehicles|equipment|owners`): per-row
  `register-alert-<id>` badge fed by a single bulk fetch grouped by
  `entity_id` (no N+1).
- Driver Profile: `driver-alerts-card` with `driver-alert-badge` and
  `driver-alerts-open` deep-link.
- Compliance Overview canonical tiles: `canonical-tile-*-alerts`
  badges (do not replace canonical compliance status).
- Import Centre: per-job `import-alert-<id>` badge.
- Document Library: deep-linked from notification detail via
  `/documents?doc=<id>` (existing EB-05b fix).

### Backend touch
- `notifications_module.seed_examples` now emits the ImportJob
  validation-failed seed against a **real** `import_jobs.id` on
  every startup (dedup-safe via `event_key`). Fixes the previously
  orphaned `IMP-SEED-01` reference.
- No other backend changes. All 237 EB-07a tests remain green
  (40 EB-07a + 197 baseline).

### Files added
- `frontend/src/lib/notifications.js`
- `frontend/src/components/app/NotificationBell.jsx`
- `frontend/src/components/app/NotificationBadge.jsx`
- `frontend/src/pages/NotificationsCentre.jsx`
- `frontend/src/pages/NotificationRules.jsx`
- `frontend/src/pages/NotificationPreferences.jsx`
- `frontend/src/pages/NotificationOutbox.jsx`
- `frontend/src/pages/NotificationFailedDeliveries.jsx`
- `frontend/src/pages/NotificationJobs.jsx`

### Files modified
- `frontend/src/App.js` — new `/notifications/:view` route.
- `frontend/src/components/app/AppHeader.jsx` — mounts the bell.
- `frontend/src/pages/Hub.jsx` — adds the notification alert strip.
- `frontend/src/pages/RegisterPage.jsx` — per-row alert badge with
  bulk entity fetch.
- `frontend/src/pages/DriverProfile.jsx` — Active alerts card.
- `frontend/src/pages/Compliance.jsx` — per-tile alert badge on
  canonical Overview.
- `frontend/src/pages/ImportCentre.jsx` — per-job alert badge.
- `backend/notifications_module.py` — real-job link for the
  ImportJob seed emission.

### Testing
- Two frontend QA passes via `testing_agent_v3_fork`:
  - Iteration 6 — full end-to-end frontend flow verification:
    77 flows PASS, zero console errors, dedup verified via repeated
    compliance scans, snooze/ack/resolve/reopen full lifecycle
    verified against seed notifications, cross-module badges
    verified on drivers (70), vehicles (50), compliance tiles (38 +
    32), driver profile, and imports.
  - Iteration 7 — targeted re-verification of the two low-priority
    fixes: Unread summary tile now wired to
    `/notifications/counts.unread`; ImportJob alert badge renders
    on a real `/imports` row. PASS.
- **Backend: 237/237 pytest still green** — no regression.

### Known limitations / Production requirements
- Email/SMS providers are not activated. All non-in-app deliveries
  remain `Simulated`. The outbox surfaces the rendered content only.
- No live cron loop. Production must invoke the six notification
  job endpoints from a durable scheduler (Kubernetes CronJob /
  Cloud Scheduler / equivalent).
- Rules "Test Rule" produces a client-side simulated toast — a full
  server-side dry-run endpoint remains a future enhancement.
- Digest modes are stored but the digest sender is not yet built.
- No real ACE data was imported. No Production deployment
  occurred. `main` remains untouched.

