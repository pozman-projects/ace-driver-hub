# ACE Driver Hub — PRD

## Original Problem Statement
Build a modern transport operations web application called **ACE Driver Hub**.
The home screen is a central operational hub for a transport company with 8 large
clickable module cards. The visual language: white background, charcoal/black
modern operations style, clean Blink-style operational dashboard, minimal clutter,
modern soft cards, large readable buttons, widescreen desktop optimized.

Modules:
1. Driver Hub — driver profiles, contacts, status, master records
2. Driver Licences — licence expiry tracking, alerts, documents
3. Driver Truck Rego — truck registration tracking and due dates
4. Driver Insurance — insurance tracking, expiry dates, compliance alerts
5. ACE Equipment — equipment assigned to drivers and vehicles
6. ACE Maintenance — maintenance records, inspections, defects, service history
7. ACE Tilt Trays — tilt tray register and tray-specific compliance
8. Driver Start Profile — new driver onboarding workflow

## User Personas
- **Admin** — full system access
- **Manager** — full CRUD incl. delete
- **Allocator** — create + update operational records
- **Compliance** — create + update compliance records
- **ReadOnly** — list only

## Architecture
- **Backend:** FastAPI + Motor (async MongoDB) + PyJWT + bcrypt
- **Frontend:** React 19 + react-router-dom + axios + shadcn primitives + Phosphor Icons + sonner toasts
- **Database:** MongoDB with UUID string ids (no ObjectId leakage)
- **Auth:** JWT Bearer tokens stored in localStorage; 24h expiry; role on user document
- **Routing:** Generic `/api/modules/{slug}` endpoints back all 8 modules with role-based gating

## What's been implemented (Phase 1 — 2026-02-26)
- JWT auth: `/api/auth/login`, `/api/auth/register` (Admin-only), `/api/auth/me`
- Seeded admin: `admin@acedriverhub.com` / `Admin@123`
- Generic CRUD: `GET/POST/PUT/DELETE /api/modules/{slug}` for all 8 modules
- Role enforcement: ReadOnly can list but not create; only Admin/Manager can delete
- `/api/stats/overview` — aggregated record counts per module
- Sample seed data for all 8 modules on first startup
- Login page (split-screen brand + form, prototype credentials hint)
- Operational Hub landing page: hero greeting, system status bar, 8-card "Control Room Grid" (4-col widescreen), record counts, hover animations
- Generic ModulePage component: title, description, search filter, sortable table, Add Record dialog, delete row, role-aware actions
- Protected routes, axios 401 auto-redirect to /login
- Outfit (display) + IBM Plex Sans (body) typography
- 100% backend (34/34) + 100% frontend (18/18) test pass

### Iteration 2 — Expiring Soon compliance widget (2026-02-26)
- New backend endpoint `/api/compliance/expiring` — classifies licences/truck-rego/insurance records by date into expired / expiring (next 30d) / ok with full record breakdown
- Hub landing now shows a "Compliance · Next 30 Days" widget above the module grid: total at risk, red/amber/green tone, per-module sub-cards
- New `/compliance` page — full compliance risk view with summary tiles, filter chips (status + module), per-module link cards, sortable at-risk table with "Open" deep-link to each module
- 100% backend (39/39) + 100% frontend (16/16) test pass

### Iteration 3 — Driver-centric relationships (2026-02-26)
- Backend: added `/api/drivers/{driver_id}/profile` returning the driver + linked records grouped by 7 module slugs (licences, truck-rego, insurance, equipment, maintenance, tilt-trays, onboarding)
- Backend: seeded drivers enriched with `driver_number` (DRV-001…) and `company` (ACE Car Freighters)
- Backend: idempotent `backfill_driver_ids()` runs on startup — links existing records to the canonical driver by name
- Backend: `/api/compliance/expiring` records now include canonical `driver_id` + `driver_name` (with legacy text-field fallback)
- Frontend: new reusable `DriverSelect` searchable dropdown (shows name + driver number + company + base)
- Frontend: every Add Record dialog on the 7 linked modules now uses `DriverSelect` for the Driver field; legacy text fields removed
- Frontend: all module tables now show the canonical driver name in a virtual `driver` column that links to the profile
- Frontend: new `/drivers/:driverId` profile page — driver hero, contact strip, "Linked Records" total, and 7 grouped sections each with count + Open module deep-link
- Frontend: Compliance page Driver column links each row to the driver profile
- 100% backend (58/58) + 100% frontend test pass

### Phase 2 · EB-01 Shell / Branding (2026-02-27)
- Rebranded ACE Driver Hub → **Driver Command Centre (DCC)**, navy header, light grey background, DCC monogram, version stamp
- App shell polish: 1920×1080-first layout, compact typography, top-bar user chip, module cards refit to no-scroll landing

### Phase 2 · EB-02 Foundation Registers (2026-02-27)
- Four canonical registers (`drivers`, `owners`, `vehicles_register`, `equipment_register`) with UUID ids and audit fields
- CRUD endpoints under `/api/{drivers|owners|vehicles|equipment}/*` with role gating and controlled status vocabularies
- Cross-register integrity (`owner_id` must reference an existing Owner), uniqueness enforced for driver_code / dispatch_number / registration_number / VIN / equipment_number
- Soft-delete only (archive sets `is_archived=true` + status → Archived)
- Idempotent seeder for 3 drivers (migrated from legacy) + 2 owners + 3 vehicles + 4 equipment
- Frontend: reusable `RegisterPage.jsx` + `OwnerSelect` combobox mounted at `/registers/{slug}`
- Hub gains a "Foundation Registers" section above the Legacy Prototype Modules
- Legacy Phase 1 collections retained side-by-side; driver record migration adapter runs on every boot

### Phase 2 · EB-03 Assignment & Relationship Layer (2026-02-28)
- Three new canonical collections: `driver_owner_relationships`, `driver_vehicle_assignments`, `driver_equipment_assignments`
- Single service layer enforces business rules for both HTTP routes and startup reconciliation:
  - At most one `is_current=true` driver-owner relationship per driver (setting a new one auto-closes any prior current)
  - At most one active + primary vehicle assignment per driver AND per vehicle (atomic `/reassign` closes both sides)
  - At most one active equipment assignment per equipment_id (conflict → HTTP 409 unless `/reassign` is used)
  - Blocked equipment statuses (`Maintenance`, `Inactive`, `Archived`) cannot be freshly assigned
  - Equipment status auto-syncs between `Available` ↔ `Assigned` on every assignment mutation
- Full CRUD + `/reassign` endpoints under `/api/driver-owner-relationships`, `/api/driver-vehicle-assignments`, `/api/driver-equipment-assignments` (all role-gated, soft-delete only)
- Startup reconciliation: logs duplicate-active warnings, re-syncs equipment status against active assignments
- Idempotent EB-03 seed: 3 current owner links, 3 active + 1 historical vehicle assignments, 3 active + 1 historical equipment assignments
- Frontend: generic `RelationshipPage.jsx` at `/relationships/{driver-owner|driver-vehicle|driver-equipment}` with search, active/historical filter, archived toggle, role-gated Add / Reassign / View / Archive actions
- Hub gains "Relationships & Assignments" section between Foundation Registers and Legacy Modules
- `DriverProfile.jsx` renders three canonical widgets (Current Owner, Vehicle Assignment, Equipment Assignments) sourced from the new endpoints
- Backend: **115 / 115 pytest pass** (24 new EB-03 tests)

### Phase 2 · EB-04 Canonical Compliance Foundation (2026-02-28)
- Seven new canonical compliance collections that monitor EB-02 masters via reference only:
  - `driver_licences`, `vehicle_registrations`, `vehicle_insurance_policies`,
  - `vehicle_inspections`, `vehicle_defects`, `vehicle_maintenance_tasks`,
  - `equipment_compliance_records`
- Every record uses immutable UUID ids + shared audit + optional `legacy_record_id` bridge + `evidence_document_id` placeholder (no file storage in this build)
- Controlled status vocabulary calculated by the service layer from `expiry_date` and a configurable `COMPLIANCE_WARNING_DAYS` window (default 30)
- Worst-Status-Wins severity ladder centralised in `compliance_records.STATUS_SEVERITY`
- Summary endpoints: `/api/compliance/drivers/{id}`, `/api/compliance/vehicles/{id}`, `/api/compliance/equipment/{id}`, `/api/compliance/overview` (filters: entity_type, status, due_within_days, company_ref, include_archived) — each returns overall_status, severity, components with record_id + reason + worst_component
- Business rules enforced: at most one active primary licence per driver, one current registration per vehicle, one current policy per vehicle per cover type, one current active equipment compliance per (equipment, type); failed inspections and critical open defects and overdue maintenance flow to worst-status
- Idempotent startup reconciliation re-classifies expiry-based statuses on every boot; overdue maintenance sweep
- Frontend: generic `CompliancePage.jsx` at `/compliance/records/{slug}` for all 7 types with search / status filter / due-date filter / archived toggle / role-gated Add · Edit · View · Archive
- `/compliance` upgraded to a Canonical vs Legacy Prototype tabbed view. Canonical tab shows entity tiles + worst-status-wins combined table with reasons. Legacy `/api/compliance/expiring` endpoint preserved untouched.
- Hub gains "Canonical Compliance" section with 7 tiles + overview link
- `DriverProfile.jsx` renders a canonical Driver Compliance card fed by `/api/compliance/drivers/{id}`
- Idempotent EB-04 seed: 3 primary licences (Compliant/Due Soon/Expired), 3 registrations, 3 insurance policies, 3 inspections, 2 defects (Critical open / Rectified), 3 maintenance tasks, 4 equipment compliance records
- Backend: **149 / 149 pytest pass** (34 new EB-04 tests, zero regression from prior 115)

### Phase 2 · EB-05 Document Storage & Evidence Architecture (2026-07-26)
- Four new canonical collections: `documents`, `document_versions`, `document_links`, `document_access_events` — every id UUID, files versioned, links canonical-only
- Storage abstraction with local private filesystem adapter (`DOCUMENT_STORAGE_PATH`, default `/app/backend/document_storage`). `storage_key` / `storage_provider` never returned to browser; downloads and previews streamed via authorised endpoints (`Content-Disposition: attachment|inline`, `Cache-Control: private, no-store`)
- Upload validation: extension allow-list (pdf/jpg/jpeg/png/webp/doc/docx/xls/xlsx/csv), 15 MB default, zero-byte + oversize + mismatched MIME + mismatched content signature rejected, SHA-256 streaming checksum, filename sanitisation, duplicate-checksum warning without auto-merge, orphan-safe failure cleanup
- Immutable versioning: v1 on upload, new versions supersede previous and update the document pointer; existing bytes never overwritten (sharded storage key)
- Role/sensitivity gating: Standard/Internal → all roles; Confidential → Admin/Manager/Compliance; Restricted → Admin/Manager. Upload restricted to Admin/Manager/Allocator/Compliance; archive/restore Admin/Manager only; access history Admin/Manager/Compliance
- Evidence integration: primary Evidence links to `DriverLicence`, `VehicleRegistration`, `VehicleInsurancePolicy`, `VehicleInspection`, `VehicleDefect`, `VehicleMaintenanceTask`, `EquipmentCompliance` records now populate the `evidence_document_id` placeholder introduced by EB-04. Removing the primary link clears it. Additional supporting documents flow through `document_links`
- Append-only `document_access_events` records Upload · Preview · Download · CreateVersion · Archive · Restore · Link · Unlink (Success/Denied/Failed) with IP + UA
- Frontend: new `/documents` Document Library with search / type / status / sensitivity filters, archived toggle, upload dialog (drag-and-drop, entity picker, primary-evidence flag, live progress), preview modal (PDF/image inline blob URL), version history dialog with new-version upload; Hub gains "Documents & Evidence" section with 3 tiles (Library, Under Review, Archived)
- Malware scanning **not connected** — `_malware_scan_status` field reserved for future scanner; content signature + extension + MIME + size validation gate `Active` status. Limitation stated truthfully in README.
- Idempotent EB-05 seed: 1 licence PDF, 1 registration PDF, 1 insurance PDF, 1 inspection PNG, 1 defect PNG, 1 equipment cert PDF, 1 Driver Contract PDF (Restricted), 1 profile photo PNG
- Backend: **177 / 177 pytest pass** (28 new EB-05 tests, zero regression from prior 149)

### Phase 2 · EB-06 Guided Spreadsheet Import & Migration Framework (2026-07-26)
- Seven new canonical collections: `import_jobs`, `import_files`, `import_mappings`, `import_rows`, `import_conflicts`, `import_commits`, `import_rollback_events` — every id UUID
- File parser **openpyxl 3.1.5** with `data_only=True`, `read_only=True`, `keep_links=False`, `keep_vba=False` — formulas never executed, external workbook links never followed, macros never executed. CSV via stdlib. Limits: 50,000 rows / 250 cols / 20 MB.
- 7 initial domain configs (drivers, owners, vehicles, equipment, driver-licences, vehicle-registrations, vehicle-insurance) with match priorities, required / unique / high-risk field flags, controlled-value enums
- Reusable normaliser library: whitespace collapse, title-case names, email lower-case, Australian mobile fix, ABN digit-only, upper-case for rego/VIN/equipment, Excel serial-date, Australian date-format parsing, boolean, percentage — every transform visible in the dry-run row report
- Dry-run pipeline (`POST /validate`): normalise → match → detect duplicates → validate required + controlled → assign action (Create/Update/Skip/Review/No Change) → block on Multiple Candidate Matches or Unique-Field-Conflict → produce per-row / per-conflict artefacts
- Explicit commit (`POST /commit`) returns HTTP 409 while any Blocking conflict is Unresolved; blank sources never overwrite non-empty fields; high-risk field changes annotated with HIGH-RISK warnings on the row
- Commit records `record_actions` including before-state on updates → safe rollback (`POST /rollback`, Admin/Manager only) soft-archives created records and restores prior update values, returns Completed/Partially Completed/Failed with per-record error list
- Compliance imports (driver-licences, vehicle-registrations, vehicle-insurance) run through EB-04 `_classify_expiry` so status is calculated from source dates, never trusted from spreadsheet colour
- Frontend: `/imports` Import Centre (jobs list, status tiles, new-import dialog); `/imports/{id}` guided Wizard with stepper (Upload → Sheet → Map → Validate → Conflicts → Commit), auto-guess mapping, row table with validation/match/action badges, conflict resolution buttons, explicit-confirm commit dialog, commit history + role-gated rollback; Hub gains "Data Import & Migration" section
- Role gating: ReadOnly can only list. Allocator/Compliance/Manager/Admin create + upload + map + validate. Compliance/Manager/Admin resolve conflicts + commit. Manager/Admin rollback + archive job.
- Backend: **197 / 197 pytest pass** (20 new EB-06 tests, zero regression from prior 177)
- **No real ACE spreadsheet data imported** — all tests use small generated fixtures. Real ACE migration remains a future task per user instructions.

### Phase 2 · Full Frontend Verification Pass (2026-07-26)
- Ran `testing_agent_v3_fork` twice across EB-03 · EB-04 · EB-05 · EB-06 UI. First pass (iteration_4) flagged 4 defects; second pass (iteration_5) verified all 4 fixes PASS with zero console errors on 8 routes.
- Fix 1 — **EB-03 DriverProfile canonical widgets**: `DriverProfile.jsx` was fetching `driver-owner-relationships`, `driver-vehicle-assignments` and `driver-equipment-assignments` into local state but never rendering them. Added a new `driver-canonical-widgets` section with three testable tiles (`driver-widget-current-owner`, `driver-widget-vehicle`, `driver-widget-equipment`), each with count pill, empty state, and `Open` deep-link to the corresponding `/relationships/*` page.
- Fix 2 — **EB-06 New Import description**: added a `new-import-description` textarea to `ImportCentre.jsx` new-import dialog. Backend `imports_module.py` `POST /imports` now accepts an optional trimmed `description` field on the job doc (backwards compatible — 20/20 EB-06 pytest still pass).
- Fix 3 — **EB-05 ↔ EB-04 evidence chip**: `CompliancePage.jsx` renders a per-row Paperclip chip that hrefs to `/documents?doc=<evidence_document_id>` when present, or a dimmed placeholder when missing. `DocumentLibrary.jsx` now honours the `?doc=<id>` query param via `useSearchParams` and auto-opens the preview modal.
- Fix 4 — **Registers → DriverProfile navigation**: on `/registers/drivers` the Full Name cell is now a `Link` (`register-name-link-<id>`) and an extra person-icon action (`register-profile-<id>`) both route to `/drivers/<id>`.
- Zero console errors on `/imports`, `/imports/{id}`, `/registers/drivers`, `/drivers/{id}`, `/compliance/records/{driver-licences,vehicle-registrations,vehicle-insurance}`, `/documents?doc=<id>`.

### Phase 2 · EB-07a Notifications, Alerts & Escalation Engine (backend only) (2026-07-27)
- **11 canonical collections**: `notification_rules`, `notification_events`, `notifications`, `notification_recipients`, `notification_deliveries`, `notification_acknowledgements`, `notification_snoozes`, `notification_escalations`, `notification_job_runs`, `notification_dead_letters`, `notification_preferences`. Immutable UUID ids across the board.
- **Rule engine**: 19 controlled `event_type` values × 15 `entity_type` values × 5 severities × 3 channels × 12 recipient strategies × 15 template keys. 13 default rules seeded idempotently.
- **Deterministic events**: SHA-256 truncated `event_key` + separate `deduplication_key` — repeated events collapse into the active notification; scheduled scans are fully idempotent.
- **Recipient resolver** walks canonical `users`, `drivers`, `owners` — no personal contact data duplicated as authoritative; snapshots stored on `notification_recipients` for delivery history only.
- **Compliance scan** reads EB-04 licences, registrations, insurance policies → emits Due Soon / Expired / Missing. **Critical scan** reads EB-04 defects + maintenance tasks → emits Critical / High / Due Soon / Overdue. **Reconciliation** auto-resolves notifications whose source condition no longer holds.
- **Lifecycle**: New → Active → (Acknowledged | Snoozed | Escalated | Resolved | Delivery Failed | Archived) → Reopen. Per-severity snooze ceilings (Critical 24h ↔ Info/Low 30d) enforced with HTTP 400 on excess. Escalations policy configurable per-rule; defaults defined for Due Soon, Expired, Critical Defect, Maintenance Overdue.
- **Deliveries**: In-app real (status `Sent`), Email/SMS **Simulated** — provider `simulated`, rendered subject/body captured, no external call. Retry schedule 0/5/30/120/720 minutes with max 5 attempts → dead letter. `simulate-failure` / `simulate-success` outbox endpoints for QA.
- **Preferences**: per-user event × channel preferences with `minimum_severity`, `digest_mode`, quiet hours. Critical alerts cannot be fully disabled by ordinary users.
- **Scheduler abstraction**: 6 job endpoints (`compliance-scan`, `critical-scan`, `process-snoozes`, `process-escalations`, `retry-deliveries`, `reconcile`) — manual + startup-one-shot. **No live in-process cron.** Production requires a durable scheduler (Kubernetes CronJob / Cloud Scheduler). This is a **documented limitation**.
- **Permissions**: ReadOnly = list-only; Allocator = ack; Compliance = compliance + critical scans, ack/snooze/resolve; Manager = all jobs, reopen, archive, outbox retry; Admin = full.
- **Seed** (`_source: "seed-eb07"`): 12 fictional example notifications covering every lifecycle state (due soon, expired, missing, critical, overdue, doc under review, import validation failed, acknowledged, snoozed, escalated, failed delivery, resolved). Idempotent — no duplicates on restart.
- **Tests**: `backend/tests/test_notifications_eb07a.py` — **40 new pytest cases**. **237 / 237 backend pytest pass** (previous 197 baseline preserved + 40 new). Two stale legacy tests in `test_driver_relationships.py` hardened to tolerate EB-06 imported drivers (only `full_name`, no `name`) — no behavioural change.
- **Frontend intentionally NOT built** in EB-07a. Bell, Notifications Centre, cross-module indicators are deferred to EB-07b.
- **No external providers**, **no real ACE data**, **no production deploy**, `main` untouched. `/app/VERSION` bumped to `dcc-phase2-eb07a`.

### Phase 2 · EB-07b Notifications Centre & Frontend Integration (2026-07-27)
- **Header notification bell** (`NotificationBell.jsx`) mounted in `AppHeader`. Unread badge + Critical/High severity dot + recent-notification dropdown with severity dot, title, time and source deep-link. Polls `/notifications/counts` every 60s.
- **Notifications Centre** at `/notifications/:view` with 10 route slugs (my/all/critical/snoozed/resolved/rules/preferences/outbox/failed/jobs). Summary tiles (Active/Unread/Critical/High/Snoozed/Delivery Failures), search + status/severity/event/entity/unread/archived filters, list rows with severity/status/times/entity, detail drawer with recipients/deliveries/acks/snoozes/escalations + Mark-read/Acknowledge/Snooze/Resolve/Reopen actions all role-gated.
- **Severity-aware snooze ceiling** enforced in the UI (Critical 24h → Info/Low 30d), backed by backend HTTP 400 on excess. Explicit disclaimer: ack/snooze do not change source compliance.
- **Rules editor** with full CRUD dialog + toggle + archive + client-side "Test Rule" (simulated toast, no external delivery). **Preferences** page with per-user event × channel × min-severity × digest configuration and dev-mode banner.
- **Delivery Outbox** with "Development Simulation Only" banner, filters, simulate-success/simulate-failure per row, and inline detail modal showing rendered subject/body. **Failed Deliveries** view + one-click retry. **Job History** with six manual job-run buttons (compliance-scan/critical-scan/process-snoozes/process-escalations/retry-deliveries/reconcile), confirmation dialog, run history table.
- **Cross-module alert indicators**: Hub notification strip, per-row `register-alert-<id>` on `/registers/{drivers,vehicles,equipment}`, `driver-alerts-card` on DriverProfile, `canonical-tile-*-alerts` on Compliance canonical overview, `import-alert-<id>` on Import Centre. All derived from notifications — canonical status is never replaced.
- Backend `seed_examples` updated to emit the ImportJob validation-failed seed against a **real** `import_jobs.id` on every startup (dedup-safe via `event_key`).
- **Tests**: `testing_agent_v3_fork` — iteration_6 (full flow: 77 PASS, 0 console errors) → iteration_7 (targeted re-verification of two low-priority fixes: PASS). Backend pytest remains at **237/237**.
- **No external providers activated**, **no live cron loop**, **no real ACE data imported**, **no production deploy**, `main` untouched. `/app/VERSION` → `dcc-phase2-eb07b`.

### Phase 2 · EB-08 Automated Driver Code & Dispatch Number Allocation (2026-07-27)
- **3 canonical collections**: `number_sequences`, `number_allocation_events`, `dispatch_number_reservations` (immutable UUIDs, audit fields).
- **Atomic Driver Code allocation** via `findOneAndUpdate($inc)` — safe against concurrent double-allocation (verified with a 5-way concurrent pytest).
- **Rules**: automatic sequence initialised from `max(existing integer driver_code)+1`; manual historical override never advances; explicit live override advances to `max(current, override)`; duplicate rejects with HTTP 409.
- **Dispatch**: 0 and 13 are permanently reserved (HTTP 400 on any attempt); reusable-first then next-new suggestion; inactive numbers count down from 999 → 100; historical assignment snapshots preserved.
- **Reservations** with configurable TTL (default 15 min); `expire-reservations` job flips stale rows and emits a dedup-safe notification. `reconcile` job detects duplicate dispatch + sequence drift, idempotent across repeated runs.
- **~15 new routes** under `/api/numbering/…`. Role gating: ReadOnly=0, Compliance=read-only, Allocator=reserve, Manager=jobs, Admin=sequence-edit.
- **Notifications**: reservation-expiry + reconciliation-conflict events via EB-07 engine, dedup-safe.
- **Frontend**: new `/administration/numbering` page (sequence, dispatch stats, reusable pills, permanent-reserved pills, active reservations table, recent events, Expire/Reconcile buttons — role-gated). Driver Register Add/Edit dialog gains `DriverCodeAssist` (Suggest + Automatic badge + historical / advance warnings) and `DispatchAssist` (reusable list, next-new, permanent 0/13 warning + submit block). `IdentifierCard` on DriverProfile with code/dispatch/source/history-count and Numbering-admin deep-link.
- **Seed** (`_source: "seed-eb08"`) covers all 11 required scenarios; idempotent across restart.
- **Tests**: `backend/tests/test_numbering_eb08.py` — **33 new pytest cases**. Backend total **270/270 PASS**. Frontend `testing_agent_v3_fork` iteration_8 — **10/10 PASS**, zero console errors on 8 sanity routes.
- **No external providers**, **no real ACE data**, **no production deploy**, `main` untouched. `/app/VERSION` → `dcc-phase2-eb08`.

## Prioritized Backlog

### P1 (next iteration)
- **Real ACE spreadsheet migration** — use the EB-06 framework to import the actual ACE driver / owner / vehicle / equipment / licence / registration / insurance registers with per-workbook mapping profiles and full audit trail.
- **Notifications / Alerts** — email/SMS alerts for canonical Due Soon and Expired records, using the EB-04 summary engine as source of truth.
- **Production object-storage adapter** — swap the local filesystem storage adapter (EB-05) and the inline import-file bytes (EB-06) for a private cloud bucket while preserving the storage abstraction.

### P2
- Automated numbering (auto Driver Code allocation, auto Dispatch Number allocation with reserved-number guard)
- Malware / AV scanning integration for uploaded evidence
- Fuzzy / probable matching for the import framework (currently exact-only)
- Relationship-domain import profiles (`driver-owner`, `driver-vehicle`, `driver-equipment`)
- Final three-row DCC Driver profile interface mock-up with the canonical Documents & Compliance panels
- OCR / expiry extraction from uploaded licences / registrations
- Compliance record edit dialogs already present — add bulk actions and CSV export
- Audit log surface (who created/updated/archived) across canonical collections

### P3
- Mobile responsive driver-facing portal
- Bulk import (CSV)
- Reports & analytics
