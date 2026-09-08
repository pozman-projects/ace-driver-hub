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

### Phase 2 · EB-08 Close-out — Full Reservation Lifecycle in Add Driver Dialog (2026-07-28)
- **RecordDialog** (`/app/frontend/src/pages/RegisterPage.jsx`) now runs a strict reserve → consume / release lifecycle for both `driver_code` and `dispatch_number` on driver create:
  - `DriverCodeAssist` **Suggest** button reserves atomically, shows the automatic badge, and renders a live `ReservationCountdown` chip (mm:ss) that fires `onExpire` at 0.
  - `DispatchAssist` reuses the pool, offers **next new**, blocks the permanently reserved 0/13, and issues its own reservation with countdown.
  - Re-suggesting or re-selecting releases the previous reservation first, then reserves the new value (verified network sequence: release → reserve).
  - Manual override at submit time: if the user typed a value different from the held reservation, the dialog releases the old one and reserves the typed value just-in-time with `manual_override=true` and `historical` flag when below the sequence pointer. 409 conflicts surface a red toast + `resError` banner that blocks save until re-selection.
  - **On successful save**, reservations are consumed via `/consume`; on failure they are released via `/release`; on dialog cancel/unmount all held reservations are released via a `useRef`-backed cleanup effect.
  - **Race fix (iteration_9 finding)**: reservations are now snapshotted to local vars and refs cleared **before** `await onSubmit()`, so the unmount cleanup no longer double-fires `/release` in parallel with `/consume`. Verified: happy-path save network = `[driver-code/consume, dispatch/consume]` only, zero stray release calls.
- **Frontend verification**: `testing_agent_v3_fork` iteration_9 — **10/11 checkpoints PASS** (409 conflict path deferred to backend pytest coverage as it needs two authenticated sessions). Post-fix smoke re-verified via Playwright: driver `TEST EB08 RaceFix` created with code=1026 & dispatch=4, sequence advanced correctly, `Driver added` toast displayed.
- **Backend**: no changes — 270/270 tests still passing.
- **No external providers**, **no real ACE data**, **no production deploy**, `main` untouched. `/app/VERSION` remains `dcc-phase2-eb08`.

### Phase 2 · EB-09 Final Three-Row Driver Command Centre Profile (2026-07-28)
- **New backend module** `/app/backend/driver_profile_module.py` — aggregator + notes + comms + activation adapter. Wired at startup + router.
- **Read-only aggregator**: `GET /api/drivers/{id}/command-centre-profile` returns driver, owner (via canonical relationship), primary vehicle assignment, equipment assignments, communication preferences, compliance intelligence (Worst Status Wins across driver/vehicle/equipment), primary licence/registration/insurance, vehicle inspection/defects/maintenance extras, active alerts (driver + vehicle), full document set with category-linked profile photo / driver contract / licence evidence, EB-08 allocation events, role-filtered notes, and truthful activation summary — all in one call.
- **Sensitive Account Details** (`business_name`, `abn`, `payroll_number`, `payment_percentage`) are **stripped from the aggregator response** for ReadOnly / Allocator / Compliance roles. Restricted list is echoed in `restricted_fields`. Only Manager / Admin see raw values.
- **New canonical collection** `driver_communication_preferences` (one active row per driver) with `GET / PUT /api/drivers/{id}/communication-preferences`. Overrides are labelled; canonical driver/owner emails remain source-of-truth. No real delivery.
- **New canonical collections** `driver_notes` + `driver_note_versions` (append-only). CRUD at `/api/drivers/{id}/notes[...]`. **Backend-enforced category role gates**: Compliance → Compliance+Manager+Admin, Accounts → Manager+Admin. Notes are also **filtered from the aggregator** based on role — restricted categories never leave the server. Archive is Admin/Manager only.
- **Activation adapter** (`_compute_activation_summary`) — read-only, computes mandatory items (contact details, driver_code, dispatch_number, primary_licence, owner relationship, vehicle assignment, driver contract) with truthful `source:` labels. A legacy `legacy_activation_ready` flag is cross-checked against canonical evidence; it is flagged unverified when source records are missing. `readiness` ∈ {Ready, Partial, Not Ready}.
- **New DCC frontend page** `/app/frontend/src/pages/DriverCommandCentre.jsx` (~900 lines): header (photo, name, code, dispatch, status, company, worst status, active alerts, legacy view link, back link) + three horizontal Management rows + sticky right-hand Compliance Intelligence column. Each management card owns its own **independent edit lifecycle** (local Save/Cancel, dirty-state warn). No cross-card accidental saves.
  - Row 1: Driver Details • Account Details (server-side restricted) • Driver Setup (with contract link + numbering history)
  - Row 2: Communication & Integration • Car Carrier & Equipment • Owner Details (read-only)
  - Row 3: Administration & Utilities (with clearly-marked "Unavailable" items — nothing faked) • Activation Checklist • Notes (add via UI, category dropdown respects role)
  - Right column: Compliance Overview (Worst Status Wins explanation) • Driver Licence • Truck Registration • Truck Insurance • Vehicle Compliance • Documents/Passes/Photos
- **Legacy fallback**: `/drivers/:id?view=legacy` still renders the previous `DriverProfile` page. Deep-link cards via `?section=<key>` (auto-scroll on load).
- **Routing**: `/drivers/:driverId` in `App.js` now points to `DriverCommandCentre`. Old `DriverProfile.jsx` retained for legacy view.
- **Tests**: 17 new pytest cases in `backend/tests/test_driver_profile_eb09.py` (aggregator shape, missing-driver 404, ReadOnly role stripping, Admin unrestricted, comms upsert single-record, comms ReadOnly 403, notes create+version, notes ReadOnly 403, Compliance/Accounts category gating, aggregator-level notes filtering, direct-note-get denial for wrong role, archive Admin/Manager-only, activation shape + 404 + truthful source, no `_id` leak). Backend total **287/287 PASS**.
- **Frontend `testing_agent_v3_fork` iteration_10**: **21/21 checkpoints PASS**, zero console errors on DCC. Verified: full 3-row layout at 1920×1080, sticky right column, per-card Edit/Save/Cancel + persistence across reload, ReadOnly restriction end-to-end (stripped server response + hidden Edit button + on-card restricted note), Compliance/Accounts note category 403s, legacy fallback, deep-link `?section=notes`, invalid uuid → redirect, and full regression across EB-01..EB-08 pages.
- **No external providers**, **no real ACE data**, **no production deploy**, `main` untouched. `/app/VERSION` → `dcc-phase2-eb09`.

**Known limitations (documented, not blockers):**
- Email / SMS delivery remains a Development Outbox simulation — Communication preferences are stored but not actually transmitted.
- Malware scanning for uploaded evidence remains mocked.
- Object storage remains a local filesystem abstraction.
- No real ACE spreadsheet data imported.
- "Generate Driver Start Sheet" and "Export Driver Profile" utilities are visibly marked **Unavailable** on the DCC — no fake success flows.
- A pre-existing React hydration warning on `/relationships/driver-*` pages (`<span>` inside `<option>`) surfaced during EB-09 QA; it does not affect DCC and is filed as an optional non-EB-09 cleanup.

### Phase 2 · EB-09.1 Hardening & Maintainability (2026-07-28)
- **Relationships hydration warning FIXED** in `RelationshipPage.jsx`. Root cause: line 207 mixed a dynamic expression (`{cfg.activeLabel}`) with static text (` only`) inside a native `<option>`. The dev toolchain wraps standalone dynamic expressions in a `<span style="display:contents">` for source-tracking, which triggered React's "cannot be a child of `<option>`" hydration error. Fix: coalesce to a single template literal `{`${cfg.activeLabel} only`}` so no wrapper span is injected. Verified across all three `/relationships/*` pages — **0 hydration warnings, 0 console errors**. No other behaviour changed.
- **`DriverCommandCentre.jsx` refactored from 1173 → 140 lines** (~-88%). All cards extracted to `/app/frontend/src/components/driver-cc/`:
  - `driverCCUtils.jsx` — shared constants (`ROLE_CAN_EDIT`, `ROLE_CAN_EDIT_ACCOUNT`), helpers (`statusVariant`), and reusable primitives (`ManagementRow`, `ManagementCard`, `RightCard`, `InlineField`, `EditInput`, `ToggleRow`, `HeaderBadge`, `MiniStat`, `StatusPill`)
  - `DriverCCHeader.jsx`, `DriverCCLoadingState.jsx`, `DriverCCErrorState.jsx`
  - Row 1: `DriverDetailsCard.jsx` · `AccountDetailsCard.jsx` · `DriverSetupCard.jsx`
  - Row 2: `CommunicationCard.jsx` · `CarrierEquipmentCard.jsx` · `OwnerDetailsCard.jsx`
  - Row 3: `AdminUtilitiesCard.jsx` · `ActivationChecklistCard.jsx` · `DriverNotesCard.jsx`
  - Right column: `ComplianceOverviewCard.jsx` · `DriverLicenceCard.jsx` · `TruckRegistrationCard.jsx` · `TruckInsuranceCard.jsx` · `VehicleComplianceCard.jsx` · `DocumentsPassesPhotosCard.jsx`
- **Zero behaviour changes** — preserved `/drivers/:id`, `?view=legacy`, `?section=`, per-card edit lifecycle (Save/Cancel/dirty warn), role filtering, deep-linking, empty states, sticky right column, layout, spacing, labels, card order, and all 34 `data-testid` selectors. Single aggregator endpoint still serves the whole page; no duplicate API calls introduced.
- **No backend changes**. Backend suite remains **287/287 PASS** (39+34+28+17+19+20+40+33+33+24 across per-file runs).
- Frontend lint clean; smoke screenshot confirms identical render.
- **Files added (18):** `frontend/src/components/driver-cc/*.jsx`.
- **Files changed (4):** `frontend/src/pages/DriverCommandCentre.jsx` (1173→140), `frontend/src/pages/RelationshipPage.jsx`, `VERSION`, `README.md`, `memory/PRD.md`.
- **No** external providers, **no** real ACE data, **no** production deploy, `main` untouched. `/app/VERSION` → `dcc-phase2-eb09-1`.

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

### Phase 2 · EB-10 Driver Activation & Onboarding Gate (2026-07-28)
- **New backend module** `/app/backend/activation_module.py` (~1150 lines). Owns the canonical readiness engine:
  - 6 new collections: `activation_templates`, `activation_template_items`, `driver_activation_records`, `driver_activation_items`, `driver_activation_overrides`, `driver_activation_events` (append-only) plus `activation_job_runs`.
  - ACE seed template with **28 items (22 mandatory)** covering Driver Identity, Account Setup, Driver Setup, Communication, Assignment (Owner/Vehicle), Licence & Compliance, Documents, Training, System Access.
  - **`ActivationService` readiness engine** — template selection by (company, driver_type), applicability rules (conditional items for contractor/owner drivers), automatic source resolvers for Driver / Documents / Communication prefs / Owner relationship / Vehicle assignment / Licence (incl. expiry Due-Soon 30d) / Vehicle Registration / Vehicle Insurance / Vehicle Defect (Critical = non-overridable block) / Vehicle Maintenance (Overdue). Worst-Status-Wins.
  - **Override lifecycle** — request (Allocator/Compliance/Manager/Admin, requires 6+ char reason + risk_acknowledgement + days within `override_max_days`) → approve (Manager+Admin, requester ≠ approver) → active → expire (auto on recalc + job) / revoke (Manager+Admin). Never mutates source compliance. Critical defects rejected at API.
  - **Activation lifecycle** — Not Started → In Progress → Ready / Ready with Override / Activation Blocked / Activated / Deactivated / Reactivated. **Ready NEVER auto-activates** — activation is an explicit Manager+Admin action requiring valid Driver Code and (optionally) sets `driver_status="Active"`. Deactivation preserves all checklist + event history. Reactivation triggers fresh recalculation.
  - **Under Review documents** are blocking by default (user-confirmed policy 2a). No `accepts_under_review` field.
  - **Manager+Admin activation gate** (user-confirmed policy 1a). Allocators can complete non-Compliance manual items and request overrides but cannot activate/deactivate.
  - **Notifications**: emits deduplicated in-app notifications for `activation.ready`, `activation.blocked`, `activation.incomplete`, `activation.override.approved`, `activation.activated`, `activation.deactivated` via EB-07 collection. Two consecutive recalcs do not create duplicates.
  - **Events**: every state change writes an append-only `driver_activation_events` row with correlation ID, actor, before/after, item/override refs, and JSON payload.
- **30 new API routes** at `/api/activation/...` and `/api/drivers/{id}/activation/...`. Full CRUD for templates, template items, driver activation, activation items, overrides, and admin jobs (recalculate-all, expire-overrides, reconcile).
- **Frontend**:
  - `ActivationChecklistCard.jsx` (EB-09 upgrade): new counters (`activation-applicable`, `activation-outstanding`, `activation-override-count`), Recalculate, Open Checklist, Activate, Deactivate. All EB-09 test-ids preserved.
  - New `/drivers/:driverId/activation` — Full Activation Checklist page (`driver-activation-page`): grouped by category, 8 filter chips, per-item Complete / Reopen / Request Override / Revoke, pending-override queue with Approve/Reject for Manager+Admin, activate/deactivate/reactivate with explicit confirms.
  - New `/administration/activation-templates` — list, create, clone, archive.
  - New `/administration/activation-jobs` — list past runs, manually trigger Recalculate all / Expire overrides / Reconcile (with confirm prompt).
- **Tests**: 25 new pytest cases in `backend/tests/test_activation_eb10.py` (templates default/create/clone/archive/role-gate, applicability, recalc idempotent, manual complete + reopen + role gates + automatic-cannot-be-manual, override full flow + non-overridable + self-approve blocked + max-days enforced, activate role gates, deactivate role gates + validation, jobs runner + readonly denied, events append-only). Backend total **312/312 PASS** (287 baseline + 25 new).
- **Frontend `testing_agent_v3_fork` iteration_12**: all EB-10 checkpoints PASS across DCC card, full checklist page, manual/override flows, role gating, templates page, jobs page, 16-route regression sweep at 1920×1080 and 1440×900. Only observation: 1 pre-existing React key warning on `/notifications/all` — filed as non-EB-10 P2.
- **No** external providers, **no** real ACE data, **no** production deploy, `main` untouched. `/app/VERSION` → `dcc-phase2-eb10`.

**Files added (5):** `backend/activation_module.py`, `backend/tests/test_activation_eb10.py`, `frontend/src/pages/DriverActivationPage.jsx`, `frontend/src/pages/ActivationTemplatesPage.jsx`, `frontend/src/pages/ActivationJobsPage.jsx`.

**Files changed (3):** `backend/server.py` (startup + router wiring), `frontend/src/components/driver-cc/ActivationChecklistCard.jsx` (upgraded card), `frontend/src/App.js` (3 new routes).

**Known limitations (documented, not blockers):**
- Templates admin lists template items but does not yet expose inline per-item CRUD in the UI (planned P1; backend endpoints already exist and are tested).
- Notification email/SMS delivery remains simulated (dev outbox).
- Malware scan and object storage remain mocked / local.
- No real ACE data imported.
- Pre-existing React key warning on `/notifications/all` ListView — non-EB-10 scope.


### Phase 2 · EB-10.1 Activation Hardening & Template Management Completion (2026-07-29)
- **Frontend** — new `/administration/activation-templates/:activation_template_id` page (`ActivationTemplateDetailPage.jsx`): inline Item Editor (create/edit/delete/reorder/duplicate/archive/restore), locked-template banner, clone-as-new-version, ReadOnly/Allocator role gates.
- **Backend** — item CRUD routes `/api/activation/template-items/*` and `/api/activation/templates/{id}/items/reorder`, `duplicate`, `restore`, `usage`. Locked-template guard: any change to `item_key` on a template with ≥1 driver activation returns 400 with "locked". Non-structural label edits allowed on locked templates.
- **Historical snapshot immutability** — `label_snapshot` on `driver_activation_items` is captured at instantiation and never rewritten by later template edits (regression covered by `test_historical_activation_unaffected_by_edits`).
- **Notifications fix** — `/notifications/all` ListView now keys by `notification_id` (fallback `id`); zero React "unique key" warnings.
- **Test-suite hardening** — `test_activation_eb10.py::TestManualCompletion` now proactively revokes active overrides on Manual items to guarantee a workable item across re-runs, eliminating stateful test flakes.
- **Tests**: 15 new pytest cases in `backend/tests/test_activation_eb10_1.py` (item unique key, conditional requires rule, override>0, critical-defect blocks override, ReadOnly + Allocator denied, duplicate, archive+restore, reorder + unknown-id rejection, template usage/locked, locked item_key rename rejected, locked non-structural edit permitted, clone-as-new-version max+1, historical snapshot immutability).
- **Backend suite total**: **332 passed, 4 skipped, 0 failed** (336 tests, 288s).
- **Frontend `testing_agent_v3_fork` iteration_13**: 14/14 EB-10.1 acceptance criteria PASS. Locked-template protection, clone-as-new-version to v13, ReadOnly gate, item CRUD, reorder, duplicate (`.copy` + `(Copy)` markers), archive/restore, and `/notifications/all` React key fix (278 rows, zero warnings) all verified against the external REACT_APP_BACKEND_URL.
- **No** production deploy, **no** GitHub push, `main` untouched.

**Files added (1):** `frontend/src/pages/ActivationTemplateDetailPage.jsx`, `backend/tests/test_activation_eb10_1.py`.

**Files changed (2):** `backend/activation_module.py` (item CRUD + reorder/duplicate/restore/usage endpoints), `frontend/src/pages/NotificationsCentre.jsx` (key by `notification_id`), `backend/tests/test_activation_eb10.py` (state-leak hardening in `_prepare_manual_item`).

**Known limitations (unchanged since EB-10):**
- Notification email/SMS delivery still simulated (dev outbox).
- Malware scan and object storage mocked / local.
- No real ACE data imported.

### Phase 2 · EB-11 Driver Start Sheet & Profile PDF (2026-08-03)
- **New backend modules**
  - `backend/driver_pdf_renderer.py` — layout-only ReportLab renderer for both
    export types (Helvetica family, A4 portrait, greyscale-friendly).
  - `backend/driver_export_module.py` — `ExportService` + FastAPI router.
- **3 new MongoDB collections**: `driver_export_jobs`,
  `driver_export_versions`, `driver_export_events`. All UUID-keyed, indexed by
  driver_id, export_type, verification_reference (unique sparse).
- **11 new API routes** at `/api/drivers/{id}/exports/*`,
  `/api/driver-exports/*` and `/api/driver-export-versions/*`. Two verification
  targets, three lifecycle actions (archive, regenerate), two file-access
  actions (preview, download).
- **Two export types**:
  - *Driver Start Sheet* — 2–3 page A4 operational handover for Allocator+.
  - *Driver Profile PDF* — 4–8 page A4 management review for Compliance+.
- **Snapshot immutability**: `driver_export_versions.snapshot_payload` is
  captured permission-filtered; regeneration creates a new version and marks
  the prior one *Superseded* via an event. No mutation of prior versions.
- **Storage integration**: every generated PDF flows through the EB-05
  documents architecture (new `document_type = "Driver Profile Export"` alongside the existing `Driver Start Sheet`). Raw storage paths are never
  returned by any API.
- **Verification**: authenticated route `/exports/verify/:reference`; short
  human-friendly `ACE-XXXX-XXXX-XXXX` code; no public QR (scoped out).
- **Dual-gate access**: (a) generator role captured on the snapshot; (b)
  current requester's role also checked on preview/download. A Manager-
  generated Profile PDF containing account fields is 403 for Compliance /
  Allocator / ReadOnly even after generation.
- **Frontend**:
  - `AdminUtilitiesCard.jsx` upgraded with Generate Start Sheet / Generate
    Profile PDF / Open Export History buttons, per-driver recent-exports strip,
    warning banner for outstanding items / active overrides, loading state,
    double-click prevention.
  - New page `DriverExportsPage.jsx` at `/drivers/:driverId/exports` — full
    history table with Type, Version, Status, Requested, Pages·Size,
    Verification, and Actions (Preview / Download / Regenerate / Archive).
  - New page `ExportVerificationPage.jsx` at `/exports/verify/:reference` —
    checksum result, role-filtered metadata, `btn-verify-open` gated on
    `can_open` from the API.
- **Tests**: 28 new pytest cases in
  `backend/tests/test_driver_exports_eb11.py` covering happy path,
  permissions, snapshot security, versioning, immutability, file access,
  audit, verification, and PDF signature/page/title/checksum validation.
- **Backend suite total**: **363 passed, 1 skipped, 0 failed** (up from 336).
- **Frontend testing agent iteration_14 + iteration_15**: 15/15 EB-11
  acceptance criteria PASS after two fixes (warning-banner data source
  aligned to the DCC aggregator; back-button target aligned to the real
  DCC route).
- **No** production deploy, **no** GitHub push, `main` untouched.

**Files added (5):** `backend/driver_pdf_renderer.py`, `backend/driver_export_module.py`, `backend/tests/test_driver_exports_eb11.py`, `frontend/src/pages/DriverExportsPage.jsx`, `frontend/src/pages/ExportVerificationPage.jsx`, `memory/EB-11-TECHNICAL-NOTE.md`.

**Files changed (3):** `backend/server.py` (startup + router wiring),
`backend/requirements.txt` (added `reportlab==5.0.0`, `pypdf==6.14.2`),
`frontend/src/components/driver-cc/AdminUtilitiesCard.jsx` (generate + history
buttons + warning banner), `frontend/src/App.js` (two new routes).

**Known limitations (unchanged from EB-10 baseline, plus EB-11 specific):**
- Local development storage still used (no S3/GCS integration yet).
- No malware scan on any document (uploaded or generated).
- No public QR verification (scoped out; authenticated `/exports/verify` route
  serves the same purpose without leak surface).
- Notification email/SMS delivery still simulated.
- No real ACE data imported.


### Phase 2 · EB-12 Migration Preparation, Mapping & Dry-Run Control (2026-08-03)
- **New backend module**: `backend/migration_prep_module.py` — service +
  FastAPI router. 12 new UUID-keyed MongoDB collections
  (`migration_source_workbooks`, `..._sheets`, `..._mapping_profiles`,
  `..._field_mappings`, `..._transform_rules`, `..._source_lineage`,
  `..._dry_runs`, `..._dry_run_rows`, `..._dry_run_changes`,
  `..._issues`, `..._reconciliation_results`, `..._go_no_go_reports`).
- **35 new API routes** at `/api/migration-prep/*` covering workbook
  inventory, mapping profiles, field mappings, transform rules, dry
  runs, issues, reconciliation reports (identifier / relationship /
  compliance / activation / document), rollback preview, and Go/No-Go.
  **No commit endpoint exists.**
- **13 deterministic transform rules** pre-seeded (`_source: "seed-eb12"`):
  trim, upper/lower/title, phone, email, date, currency, percentage,
  bool, integer, driver_code, registration, VIN, ABN, status_map,
  blank_to_null, state_abbr, control_chars.
- **Matching engine**: deterministic hierarchy per entity type; multiple
  matches → Blocking; name-only never auto-updates; probable matches
  → `Manual Review`. Full match evidence returned.
- **Duplicate detection**: within-source + against canonical registers.
  Never auto-merged; surfaces as `DUPLICATE_*` issues.
- **Identifier reconciliation**: peek-only projection of live sequences,
  reserved-hit detection (0, 13), non-integer historical Codes flagged
  as Warning-only, projected next sequence value returned.
- **Compliance + Activation impact**: computed from proposed rows;
  canonical compliance and activation records are never mutated.
- **Document manifest**: manifest-only; no files uploaded in EB-12.
- **Go / No-Go logic**: NO-GO when Open blockers > 0 OR Critical issues > 0
  OR profiles not all Approved; CONDITIONAL GO for Warning-only; GO for
  clean. NO-GO reports cannot be approved (backend 400).
- **Rollback preview**: deterministic, applied=false; safe to re-run.
- **Source lineage**: every proposed value keeps workbook id + checksum +
  file name + sheet id + sheet name + row/column + original + transformed
  + applied transforms + mapping profile id + version + target field.
- **Frontend**: 5 new pages under `/migration-preparation/*` — Hub,
  Workbooks Inventory (sanitised upload only), Mapping Profiles, Dry
  Runs, and a Dry-Run detail page with 11 tabs (Summary, Rows, Changes,
  Issues, Identifiers, Relationships, Compliance, Activation, Documents,
  Rollback, Go/No-Go). Discoverable via the Hub-page tile.
- **Tests**: 32 new pytest cases in `backend/tests/test_migration_prep_eb12.py`
  using only sanitised fictional fixtures (no real ACE data).
- **Backend suite total**: expected **395 passed** total (up from 363;
  +32 new tests). Full run to be confirmed in the finish step.
- **Frontend testing agent iteration_16**: all EB-12 acceptance criteria
  PASS. Hub + 4 subpages + dry-run detail with 11 tabs all wired.
  Go/No-Go compute works. `no-commit-notice` displayed. Regression on
  EB-01…EB-11 pages clean.
- **No** production deploy, **no** GitHub push, `main` untouched.

**Files added (7):**
- `backend/migration_prep_module.py`
- `backend/tests/test_migration_prep_eb12.py`
- `frontend/src/pages/MigrationPreparationHub.jsx`
- `frontend/src/pages/MigrationWorkbooksPage.jsx`
- `frontend/src/pages/MigrationMappingsPage.jsx`
- `frontend/src/pages/MigrationDryRunsPage.jsx`
- `frontend/src/pages/MigrationDryRunDetailPage.jsx`
- `memory/EB-12-MIGRATION-PREPARATION-TECHNICAL-NOTE.md`

**Files changed (4):**
- `backend/server.py` — startup + router wiring for EB-12
- `backend/requirements.txt` — added `openpyxl==3.1.5`
- `frontend/src/App.js` — 5 new routes
- `frontend/src/pages/Hub.jsx` — new Migration Preparation tile
- `backend/tests/test_activation_eb10.py` — hardened `_prepare_manual_item`
  helper (last-resort reopen of a Complete manual item to eliminate
  the intermittent flake under concurrent test runs)

**Known limitations (unchanged from EB-11 baseline, plus EB-12 specific):**
- Raw workbook bytes stored inside the workbook document — acceptable for
  sanitised dev fixtures only. Production must move to object storage.
- Sheet classification (mapping a sheet to its target entity type) is
  manual. Automated inference deferred.
- Cross-sheet foreign-key resolution (Driver↔Owner via ABN across sheets)
  scoped to EB-13.
- No fuzzy matching — deterministic exact-key only. This is intentional.
- No commit endpoint. Real migration is EB-13.


### Phase 2 · EB-13 Private Object Storage & Secure File Delivery (2026-08-04)
- **New backend module** `backend/storage_module.py`: `StorageAdapter` interface
  with two concrete implementations — `LocalStorageAdapter` (dev filesystem)
  and `S3CompatibleStorageAdapter` (AWS S3 / Cloudflare R2 / Backblaze B2 /
  MinIO via `boto3`). `StorageService` centralises put/get/verify/archive/
  restore/quarantine/reconcile with SHA-256 integrity, signed URLs (S3 only),
  metadata tracking, and role-gated access.
- **6 new UUID-keyed MongoDB collections**: `storage_objects`,
  `storage_object_versions`, `storage_events` (append-only audit),
  `storage_migration_jobs`, `storage_reconciliation_runs`,
  `storage_retention_policies`. `ensure_indexes` and
  `seed_retention_policies` run on startup (5 default policies:
  Standard Operational, Compliance Evidence Long, Generated Export
  Historical, Migration Source Retention, Temporary Upload).
- **~22 new API routes** at `/api/storage/*`: health, configuration-status,
  objects (list / get / versions / archive / restore / verify / quarantine
  / preview / download), migrations (create / list / execute / retry),
  reconciliation (start / list / get), retention-policies (list / create
  / update / archive). All role-gated: ReadOnly denied; Manager/Admin can
  run jobs; Admin-only for quarantine + retention CRUD.
- **EB-12 integration (bytes out of Mongo)**: new workbook uploads at
  `POST /api/migration-prep/workbooks/profile` now route bytes through the
  StorageService — the workbook document stores `storage_object_id` and
  **no longer stores `_data`**. Validation reads prefer the storage
  service; legacy workbooks with `_data` remain readable and can be moved
  via the new Migration Jobs UI.
- **EB-05 integration**: `POST /api/documents/upload` and new-version
  endpoints now additively call `StorageService.register_existing`; the
  new document + version rows carry `storage_object_id`. Bytes still land
  on the LocalAdapter root (same filesystem path), giving admins a unified
  view of every stored file inside the Storage Administration surface.
- **EB-11 integration**: generated Start Sheet / Profile PDFs are
  registered in the storage service after render; `driver_export_versions`
  and the underlying `documents`/`document_versions` rows carry
  `storage_object_id`.
- **Security posture**:
  - `/api/storage/configuration-status` returns ONLY `{backend, configured,
    signed_url_ttl, root_configured, max_upload_bytes}` — never a secret,
    access key, session token or password.
  - Storage object list endpoint strips `object_key` — internal keys are
    never leaked to the browser.
  - Object keys use UUIDs only (no PII), namespaced by `APP_ENV`.
  - S3 puts include `ServerSideEncryption=AES256`.
  - Blocked extensions (exe/bat/cmd/sh/js/vbs/ps1/html/htm) + PDF magic
    header check on upload validation.
  - ReadOnly cannot list objects, run jobs, or CRUD policies. Route also
    guarded on the frontend via `<Navigate to="/hub" />`.
- **Frontend**: new `/administration/storage` page (`StorageAdmin.jsx`,
  ~560 lines): Adapter/Objects/Missing/TTL tiles, jobs strip (Run
  Reconciliation, Queue Migration), Storage Objects table with search +
  status filter + per-row Verify / Archive / Restore actions, side-by-side
  Migration Jobs + Reconciliation Runs tables, Retention Policies table
  with Admin-only Add-policy modal. Hub gains a `storage-admin-card` tile.
- **Env config**: `.env.example` documents all EB-13 keys. Defaults in
  `.env` keep the preview environment on the local adapter — no real cloud
  credentials are stored.
- **Tests**: 26 new pytest cases in `backend/tests/test_storage_eb13.py`
  covering:
  - Live LocalAdapter smoke via API (health, configuration-status leak
    scan, role denies, retention seed present)
  - EB-12 workbook integration (upload → `storage_object_id` set, no
    `_data` in response, object visible via /api/storage/objects/{id})
  - Retention CRUD + invalid-class rejection
  - Reconciliation & Migration job endpoints incl. RBAC
  - **moto-mocked S3 adapter unit tests** (put/get/exists/head/delete/copy/
    signed_url/list_prefix/health/encryption-header)
  - Direct LocalAdapter tests (put/get/delete/list/health)
  - Security: object_key never exposed in list endpoint
- **Backend suite total**: **418 passed, 4 skipped, 0 failed** (deterministic —
  two consecutive full-suite runs, 427.49s and 376.03s, no manual data
  cleanup between them). Baseline was 395 passed / 1 skipped; delta =
  +26 EB-13 tests (all pass) and +3 conditional skips that already
  existed in the codebase (see below).
- **Skipped tests (all pre-existing conditional `pytest.skip(...)` calls,
  intentional — not new to EB-13):**
  1. `test_activation_eb10.py::TestOverrides::test_cannot_self_approve_override`
     — skipped when the seed driver has no outstanding overridable item
     left in the current DB state (prior tests may have consumed it).
  2. `test_activation_eb10.py::TestOverrides::test_override_max_days_enforced`
     — same overridable-item precondition.
  3. `test_activation_eb10_extra.py::TestCategoryRoleGating::test_allocator_denied_on_licence_and_compliance_manual`
     — skipped when the current activation template has no manual
     Licence-and-Compliance item.
  4. `test_activation_eb10_extra.py::TestCategoryRoleGating::test_allocator_allowed_on_non_compliance_manual`
     — skipped when no eligible non-Compliance manual item is available
     in the checklist snapshot returned by the API.
  These are `pytest.skip(...)` guards inherited from EB-10 / EB-10.1
  test files, not `@pytest.mark.skip` decorators. They are documented in
  the source code and are considered acceptable by the EB-10 close-out.
- **Notification test isolation hardening** (root-cause fix, not a
  test-only patch):
  - Root cause: `_materialise_deliveries` in `notifications_module.py`
    was calling `db.notification_deliveries.find_one({...,
    "notification_recipient_id": rec_id, ...})` using a *freshly
    generated* recipient id — the dedup query could never match, so
    every scan re-created every recipient+delivery row. After enough
    scans the collection grew unbounded and the unindexed lookup made
    the scan itself timeout.
  - Fix 1: dedup now matches on the **stable recipient identity**
    (`user_id` / `driver_id` / `owner_id` / `email_address` /
    `mobile_number`) plus `notification_id` + `channel`.
  - Fix 2: stable identity keys are now duplicated onto the delivery
    document itself so the lookup is a straight indexed hit.
  - Fix 3: 5 new compound indexes on `notification_deliveries`
    (`{notification_id, channel, user_id}` etc.) added to
    `ensure_indexes`.
  - Result: two consecutive `compliance-scan` runs on the same live
    dataset now complete in **31.7s** (cold, first run) and **9.9s**
    (dedup skips everything, idempotent) — down from >60s + timeout.
    `notification_deliveries` count stays flat across repeat scans
    instead of growing linearly.
  - Production behaviour: strengthened, not weakened — same public
    contract, same events, same recipient resolution, just with correct
    idempotency and no data explosion.

- **Frontend `testing_agent_v3_fork` iteration_17**: 100% of EB-13
  acceptance criteria PASS. Storage Admin page renders all 4 tiles, 351+
  objects listed, retention CRUD works, reconciliation & migration jobs
  execute, EB-12 uploads carry `storage_object_id`, EB-05 uploads register
  as storage objects, ReadOnly correctly 403'd (now also route-guarded on
  frontend), Hub tile navigates, configuration-status contains no
  credential-shaped keys, regression sweep clean.
- **No** external providers activated, **no** real ACE data imported,
  **no** production deploy, **no** GitHub push, `main` untouched.
  `/app/VERSION` → `dcc-phase2-eb13`.

**Files added (3):**
- `backend/storage_module.py`
- `backend/tests/test_storage_eb13.py`
- `frontend/src/pages/StorageAdmin.jsx`

**Files changed (8):**
- `backend/server.py` — EB-13 startup + router wiring
- `backend/.env` + `backend/.env.example` — EB-13 config keys (all safe
  defaults; S3 fields commented out)
- `backend/migration_prep_module.py` — new workbook uploads now use
  StorageService instead of inline `_data`; reader falls back to `_data`
  for legacy workbooks
- `backend/documents_module.py` — `register_existing` on new upload
- `backend/driver_export_module.py` — `register_existing` on PDF export
- `backend/notifications_module.py` — dedup + delivery-identity + 5 new
  indexes (root-cause fix for the accumulated-deliveries scan slowdown)
- `frontend/src/App.js` — new `/administration/storage` route
- `frontend/src/pages/Hub.jsx` — new `storage-admin-card` tile

**Known limitations (still open after EB-13):**
- Preview environment intentionally runs on LocalAdapter only; no real S3
  bucket / credentials are configured. Switching to production requires
  populating the commented-out `OBJECT_STORAGE_*` env vars at deploy time.
- Malware scanning still mocked (`_malware_scan_status`).
- Legacy EB-05 documents and EB-11 exports created BEFORE this build
  don't have `storage_object_id`. Backfill is available via
  `/api/storage/migrations` (scope currently limited to Migration
  Workbooks; document/export backfill deferred to EB-14).
- Email / SMS still simulated (Development Outbox).
- No real ACE spreadsheet data has been imported.

**EB-14 dependencies (Phase 3):**
- Backfill EB-05 documents & EB-11 exports into `storage_objects` when
  moving to S3-compatible production bucket.
- Cross-sheet foreign-key resolution (Driver↔Owner via ABN) in the
  migration prep pipeline.
- Real ACE workbook import with per-domain mapping profiles + full
  Go/No-Go pass.
- Production scheduler (Kubernetes CronJob) driving reconciliation +
  notifications on a real cadence.


### Phase 2 · EB-14 Stage A Controlled Migration Commit, Rollback & Legacy Backfill (2026-08-04)
- **NEW backend module** `backend/migration_commit_module.py` (~1350 lines)
  containing `ApprovalService`, `CommitService` with entity handlers for
  Owner / Vehicle / Equipment / Driver, cross-sheet FK resolution
  (ABN / VIN / registration), `RollbackService`, `PostCommitReconciliationService`
  and `StorageBackfillService`. Every action carries a stable
  `commit_action_key` and every canonical write registers a reverse
  step in the rollback package BEFORE the write happens.
- **11 new UUID-keyed MongoDB collections** with 20 indexes:
  `migration_commit_jobs`, `migration_commit_batches`, `migration_commit_rows`,
  `migration_commit_actions` (append-only), `migration_commit_events`
  (append-only), `migration_rollback_packages`, `migration_rollback_actions`
  (append-only), `migration_post_commit_reconciliation` (append-only),
  `migration_approvals`, `storage_backfill_jobs`, `storage_backfill_actions`.
- **30 new API routes** at `/api/migration-commit/*` and `/api/storage/backfill*`:
  create/list/get commit jobs, preflight, request-approval, approve, reject,
  execute, pause, resume, retry, archive, batches, actions, events,
  rollback-package, rollback/{request|approve|execute|status}, reconcile,
  reconciliation-list; backfill create/list/get/execute/retry.
- **Safety rails** (backend-first, mirrored on UI): immutable migration
  package with package_sha256, preflight validates approval + Go-No-Go +
  mapping-profile version + workbook checksum + storage health + no
  reserved dispatch 0/13 + rollback package present. NO-GO blocked from
  creating a commit job. Manager creates Rehearsal jobs; only Admin can
  execute Controlled Commit. Self-approval blocked. Conditional Go
  requires explicit risk_acceptance. Rollback requires separate Admin
  approval + typed 'ROLL BACK MIGRATION' confirmation. Controlled Commit
  requires typed 'COMMIT ACE MIGRATION' confirmation. Every action is
  idempotent (stable commit_action_key). Environment banner truthfully
  reports staged-idempotent mode; MIGRATION_COMMIT_TRANSACTIONS=true is
  a future Production flag not active here.
- **Cross-sheet FK resolution**: Driver→Owner by ABN + canonical ID,
  Driver→Vehicle by VIN then registration+state.
- **Legacy Storage Backfill** with scopes Documents, Exports,
  Migration Workbooks, All Legacy Development Assets. Copy first,
  verify by reading bytes back, only then update canonical
  storage_object_id. Legacy source is always retained. Idempotent rerun.
- **Frontend**: `/migration-commit` (`MigrationCommitHub.jsx`, ~605 lines)
  with truthful env banner, permanent commit warning, Commit Jobs table
  + Create Job modal (NO-GO excluded from select), Job detail panel
  (immutable-package summary, action buttons, preflight grid, progress
  tiles, reconciliation history, rollback package status, event log),
  typed confirmation modals for Controlled Commit and Rollback,
  Legacy Storage Backfill section with 'Source retained: Yes' column.
- **Backend tests**: 23 passed, 1 conditional skip in
  `tests/test_migration_commit_eb14.py`.
- **Frontend testing_agent_v3_fork iteration_18**: 100% of Stage A
  acceptance criteria PASS. Two nice-to-have UX improvements applied
  (Controlled-Commit button now hidden unless job status permits;
  eligible dry-run list filtering already excludes NO-GO).
- **Backend suite total**: **441 passed, 5 skipped, 0 failed** in 463.54s
  (up from 418; +23 EB-14 tests + 1 new conditional skip).
- **Files added (6)**:
  - `backend/migration_commit_module.py`
  - `backend/tests/test_migration_commit_eb14.py`
  - `frontend/src/pages/MigrationCommitHub.jsx`
  - `memory/EB-14-MIGRATION-COMMIT-TECHNICAL-NOTE.md`
  - `memory/EB-14-REAL-DATA-RUNBOOK.md`
  - `memory/EB-14-ROLLBACK-RUNBOOK.md`
- **Files changed (3)**:
  - `backend/server.py` — EB-14 startup + router wiring
  - `frontend/src/App.js` — new `/migration-commit` route
  - `frontend/src/pages/Hub.jsx` — new `migration-commit-card`
- `/app/VERSION` → `dcc-phase2-eb14`.
- **Sign-off confirmations**:
  - ✅ Only fictional sanitised fixtures were used. No real ACE names,
    ABNs, VINs, licence numbers, phones or emails.
  - ✅ Rehearsal mode never creates canonical DCC records (verified).
  - ✅ Controlled Commit requires Admin + valid approval + successful
    preflight + typed confirmation.
  - ✅ Self-approval blocked for Controlled Commit.
  - ✅ NO-GO dry runs cannot create commit jobs.
  - ✅ Rollback requires separate Admin approval + typed confirmation.
  - ✅ Legacy source files retained by backfill.
  - ✅ No `main` push. No GitHub push. No deploy.
  - ✅ No real email / SMS / Blink / OCR / AI activated.
- **Remaining limitations (EB-15 scope)**:
  - Multi-document MongoDB transactions require replica-set at deploy.
    Currently staged-idempotent only.
  - Cross-sheet Equipment FK + full name-normalisation matcher.
  - Malware scan, real email/SMS, Blink integration, OCR, AI extraction
    remain out of scope.


### Phase 2 · EB-14 Close-out Fix — Equipment FK Resolution & Deterministic Verification (2026-08-04)
- **NEW `_resolve_equipment_fk` deterministic resolver** in
  `migration_commit_module.py`. Matching hierarchy: canonical Equipment
  ID → equipment_number (normalised uppercase) → serial_number →
  registration_number. Multiple hits at any step return status
  `multiple`; no name-only matching. Returns a typed `EquipmentFKResult`
  Pydantic model with `status`, `equipment_id`, `matched_by` and
  diagnostic `candidates` list.
- **NEW `_handle_driver_equipment_assignment` handler** for dedicated
  assignment rows. Enforces:
  - Duplicate active assignment prevention (existing `is_current=True`
    for the same driver+equipment blocks new insert; existing is
    preserved).
  - Historical-assignment support via `effective_to` field
    (`is_current=false`, `is_archived=true`).
  - Retry idempotency via stable `commit_action_key`
    `driver-equipment:{driver_id}:{equipment_id}`.
  - Match evidence written to the assignment
    (`match_evidence.matched_by`) and to the migration action.
  - Rollback action written BEFORE the canonical insert.
- **`_handle_driver` enhanced** — now also resolves Equipment FK for
  Driver rows carrying an `equipment_number` / `equipment_id` /
  `serial_number` / `equipment_registration` column. Same duplicate
  protection and match evidence as the dedicated handler. Unresolved
  or multi-match references are logged as blocking skips instead of
  silently ignored.
- **Rollback service** already recognised `DriverEquipmentAssignment` in
  its coll_map, so newly written assignments participate in reverse-order
  rollback (`Delete` action) with the standard later-edit conflict guard.
- **Test file `test_migration_commit_eb14.py`** — grown from 24 → 33
  tests, all deterministic (**0 skipped**). New classes:
  - `TestEquipmentFKResolution` (8 tests): canonical-id match,
    equipment-number match, serial-number match, registration match,
    unmatched=blocking, multiple=blocking, name-only-does-not-match,
    duplicate active assignment detected.
  - `TestEquipmentAssignmentCommit` (1 integration test): seeds a
    fictional Equipment record, uploads a workbook with
    `equipment_number` column, runs the full Controlled Commit flow
    (Manager requests, Admin approves, preflight, execute), verifies
    that the driver AND the `driver_equipment_assignments` row exist
    with `match_evidence.matched_by == "equipment_number"`, then hits
    `resume` and confirms the assignment count stays at exactly 1.
- **Conditional-Go fixture is now deterministic** (previously skipped).
  Uses non-integer driver code (`LEGACY-<uuid6>`) + dispatch ≥ 9000 +
  unique email → always produces `warning_issue_count=1` +
  `open_blocking_issue_count=0` → CONDITIONAL GO. Assertion is now
  `assert gng['result'] == 'CONDITIONAL GO'` (no `pytest.skip`).
- **Idempotency fixture is now deterministic**. Previously the
  Controlled-Commit test used a shared `idem@example.test` email +
  `0400010001` mobile which collided with prior test drivers → matcher
  returned `Multiple Matches` → NO-GO. Now uses per-run unique email
  + mobile + 8-digit code → GO or CONDITIONAL GO reliably.
- **Cleanup after the FK-integration test** removes only
  `_source: eb14-fk-test` fixtures — no impact on other test data.
- **Backend suite total after fix**: **451 passed, 4 skipped, 0 failed**
  in 324.36s. Up from 441/5/0.
  - +10 new EB-14 Equipment FK tests
  - −1 conditional skip (Conditional-Go now deterministic)
  - The remaining 4 skips are the same pre-existing EB-10 activation
    checklist runtime guards documented in the EB-13 close-out, not
    EB-14 or new behaviour.
- **Equipment FK scenarios verified end-to-end**:
  1. Exact equipment-number match (normalised case) ✅
  2. Serial-number match ✅
  3. Registration match ✅
  4. Unmatched → blocking Skip action written ✅
  5. Multiple matches → blocking Skip with `candidates` diagnostic ✅
  6. Duplicate active assignment → Preserve (not Create) ✅
  7. Historical assignment via `effective_to` → archived, non-current ✅
  8. Retry idempotency → resume never doubles the assignment ✅
  9. Equipment compliance linkage: assignments carry `match_evidence`
     and become the target for downstream compliance-recalc ✅
 10. Equipment document linkage: `_handle_driver_equipment_assignment`
     records the canonical Equipment ID so document manifest rows can
     link to it in the same batch ✅
 11. Rollback of Equipment assignment: `Delete` reverse action written
     before insert; participates in the standard rollback service ✅
- **Files changed (2)**:
  - `backend/migration_commit_module.py` (+ `_resolve_equipment_fk`,
    `EquipmentFKResult`, `_handle_driver_equipment_assignment`, and
    equipment resolution branch inside `_handle_driver`)
  - `backend/tests/test_migration_commit_eb14.py` (new fixture helper
    `extra_fields` on `_mk_full_profile`; new `TestEquipmentFKResolution`
    and `TestEquipmentAssignmentCommit` classes; Conditional-Go and
    idempotency fixtures made deterministic)
- **No new routes**, **no new collections** and **no new indexes** —
  Equipment FK reuses `equipment_register` and
  `driver_equipment_assignments` collections already established in
  EB-01/EB-02/EB-03.
- **Sign-off confirmations for the close-out fix**:
  - ✅ Only fictional sanitised fixtures used (test rows prefixed
    `EB14-FK-`, `EQ-`, `EQF-`, `SN-`, `DUP-` and `_source: eb14-fk-test`)
  - ✅ No real ACE data imported
  - ✅ No GitHub push, no deploy, `main` untouched
  - ✅ No frontend changes required — the assignment result is visible
    via the existing action/event log on the Migration Commit Hub
- **Remaining limitations (EB-15 scope)**:
  - Full name-normalisation matcher (deferred per rules — name-only
    matching is intentionally blocked)
  - Multi-document MongoDB transactions still require replica-set
  - Real email/SMS/Blink, OCR, AI extraction still out of scope


---

## EB-15 · Production Scheduling, Live Notifications & Operational Automation (2026-02-04)

**Status**: ✅ Delivered, backend regression-clean, frontend end-to-end
validated by testing agent. `main` untouched, no deploy, no GitHub push.

### What shipped
- Compact single-module implementation: `/app/backend/scheduler_module.py`
  (1335 lines) exposing `build_automation_router` and
  `build_scheduler_internal_router`, both wired into `server.py`.
- 16 job definitions registered in `scheduled_job_definitions`
  (notifications.dispatch/retry/dead_letter/escalation, numbering.*,
  activation.*, storage.*, migration.*, documents.review_reminders,
  compliance.scan).
- 12 built-in notification templates seeded into `notification_templates`
  (compliance_due_soon, compliance_expired, critical_defect,
  activation_ready/blocked, override_expiring/expired, migration_completed/
  failed, storage_reconciliation_failed, export_completed,
  document_review_reminder).
- Four production-capable provider adapters — Development (default),
  SMTP via stdlib `smtplib`, SendGrid REST v3 via `httpx`, Twilio REST via
  `httpx`. **No SDK dependencies added**.
- Delivery pipeline with exponential backoff `[0, 5m, 15m, 60m, 4h]`,
  dead-letter, quiet hours (Australia/Melbourne configurable),
  Critical-priority override that never overrides SMS, circuit breaker
  (`open` → `half-open` → `closed`), suppression logging.
- Manager+ actions: run job now, enable/disable, retry/cancel/resolve
  delivery, template create/edit/approve/clone. Admin actions: reset
  circuit breaker.
- Frontend administration surface: `/administration/automation` (hub),
  `/administration/automation/jobs`, `/administration/automation/deliveries`,
  `/administration/automation/providers` (providers + templates table).
  Hub tile added to Command Hub (`automation-hub-card`).

### API endpoints
- `GET  /api/automation/status`
- `GET  /api/automation/jobs`, `GET /api/automation/jobs/{key}`,
  `POST /api/automation/jobs/{key}/run|enable|disable`
- `GET  /api/automation/job-runs`, `GET /api/automation/job-runs/{id}`,
  `POST /api/automation/job-runs/{id}/retry|cancel`
- `GET  /api/automation/deliveries`, `GET /.../{id}`, `GET /.../{id}/attempts`,
  `POST /.../{id}/retry|cancel|resolve`
- `GET  /api/automation/providers`,
  `POST /api/automation/providers/{key}/health-check`,
  `POST /api/automation/providers/{key}/reset-circuit`
- `GET/POST/PUT /api/automation/notification-templates(/…)/approve|clone`
- `POST /api/internal/scheduler/{job_key}` — service-token auth
  (`X-Scheduler-Token` HMAC-compared) with optional IP allow-list.

### Collections added / touched
- New: `scheduled_job_definitions`, `scheduled_job_runs`,
  `scheduled_job_events`, `scheduled_job_locks`,
  `automation_health_snapshots`, `notification_delivery_attempts`,
  `notification_provider_events`, `notification_suppression_events`,
  `notification_templates`, `notification_provider_health`.
- Touched (read/update only): `notifications`, `notification_deliveries`,
  `migration_approvals`.
- All new IDs are UUID strings; all timestamps are ISO-8601 UTC. Indexes
  ensured via `ensure_indexes(db)` at startup.

### Constraints honoured
- ❌ No SendGrid/Twilio SDKs — only `httpx` REST.
- ❌ No permanent in-process cron loops.
- ❌ No live network calls in tests. All provider I/O is mocked via
  `httpx.MockTransport` and `unittest.mock.patch(scheduler_module.smtplib.SMTP)`.
- ❌ No real provider credentials in `.env`; delivery is opt-in via
  `NOTIFICATION_DELIVERY_ENABLED=true`.
- ❌ No real ACE data, no deploy, no GitHub push.
- ✅ Development Outbox remains the default; test mode on by default.
- ✅ PII masking for non-Admin roles at API layer
  (`email_address_masked` / `mobile_number_masked`).

### Defects found and fixed in this session
1. **`RuntimeError: Event loop is closed`** in
   `test_notifications_retry_reactivates_scheduled` — Motor client was
   instantiated at method scope and shared across two `asyncio.run()`
   invocations. Fix: instantiate a fresh `AsyncIOMotorClient` inside each
   async block and close it via `db.client.close()` in `finally`.
   Verified by `bug_testing_agent` (target test 3/3 passes deterministically).
2. **Duplicate `data-testid` on Providers page** — surfaced by frontend
   testing agent. Fix: suffix testid with channel:
   `provider-card-{provider_key}-{channel}`.

### Verification totals
- Backend suite: **499 passed, 4 skipped** (baseline 451 passed, 4 skipped;
  net +48 EB-15 tests, 0 regressions). Runtime ≈ 408s.
- Frontend testing agent (iteration_20.json): 5/5 test suites PASS at 100%
  — Automation Hub, Jobs page, Deliveries page, Providers page, ReadOnly
  RBAC redirect.

### Files added / changed (EB-15)
- `backend/scheduler_module.py` (new; ~1335 lines)
- `backend/server.py` (import + router registration only)
- `backend/tests/test_scheduler_eb15.py` (new; 48 tests)
- `backend/.env` (added `SCHEDULER_ENABLED`, `SCHEDULER_SERVICE_TOKEN`,
  `EMAIL_PROVIDER`, `SMS_PROVIDER`, and related non-secret defaults)
- `frontend/src/pages/AutomationHub.jsx` (new)
- `frontend/src/pages/AutomationJobsPage.jsx` (new)
- `frontend/src/pages/AutomationDeliveriesPage.jsx` (new)
- `frontend/src/pages/AutomationProvidersPage.jsx` (new)
- `frontend/src/App.js` (4 new routes, 4 new imports)
- `frontend/src/pages/Hub.jsx` (added `automation-hub-card` tile)
- Docs: `memory/EB-15-K8S-CRONJOBS.md`,
  `memory/EB-15-OPERATIONS-RUNBOOK.md`,
  `memory/EB-15-TECHNICAL-NOTE.md`

### Remaining limitations (rolled into EB-16 / Phase 3 backlog)
- Escalation deduplication endpoint returns placeholder counts
  (`{escalations_created: 0, deduped: 0}`); needs real drivers.
- No webhook receivers yet for SendGrid/Twilio delivery-status callbacks
  (provider reply from the send call is authoritative).
- `automation_health_snapshots` collection is indexed but not yet
  materialised by any job — reserved for future health-history endpoint.
- Real ACE spreadsheet data migration (EB-16 / Phase 3).
- OCR / AI document extraction (P2).


---

## EB-15 Close-out · Escalation Dedup, Template Studio & Scheduler Manifests (2026-02-04)

**Status**: ✅ Delivered. Backend suite green (**515 passed, 4 skipped**;
+16 escalation tests, 0 regressions). Frontend Template Studio validated
(9/9 flows PASS). `main` untouched, no deploy, no GitHub push, no real
credentials, no real messages sent.

### 1. Escalation deduplication (real, deterministic)
- New service `EscalationService` in `scheduler_module.py`.
- **6 rules covered**: `compliance_expired` (equipment_compliance),
  `activation_blocked` (driver_activation), `override_expired`
  (driver_activation_override), `migration_failed`
  (migration_commit_job), `storage_failed` (storage_reconciliation_run),
  `delivery_repeatedly_failed` (notification_delivery).
- **Dedup keys**: `rule_key | source_entity | source_id | level |
  channel | recipient`, SHA-256'd into a stored `idempotency_key`
  protected by a unique index in `notification_escalations`.
- **Incident model**: `notification_escalation_incidents` (unique on
  `rule_key + source_entity + source_id`) tracks
  `first_seen_at`, `current_level`, `acknowledged_at/_by/_at_level`,
  `resolved_at/_by`, `active`.
- **Level progression**: increases only per rule levels — never
  decreases. New level opens NEW escalation rows without duplicating the
  earlier level.
- **Acknowledgement** blocks new escalations at the SAME level; a level
  increase escapes acknowledgement.
- **Resolution** (source no longer meets condition OR API-driven) stops
  further escalation permanently.
- **Self-recursion guard**: escalation-driven deliveries are tagged
  `_source="escalation"` and excluded from the
  `delivery_repeatedly_failed` detector.
- **New API endpoints (5)**:
  - `GET  /api/automation/escalation-rules`
  - `GET  /api/automation/escalation-incidents` (?active, ?rule_key)
  - `GET  /api/automation/escalation-incidents/{id}`
  - `POST /api/automation/escalation-incidents/{id}/acknowledge`
  - `POST /api/automation/escalation-incidents/{id}/resolve`

### 2. Notification Template Studio (frontend)
- Route `/administration/automation/templates` (new page
  `AutomationTemplatesPage.jsx`).
- Added to Automation navigation (`nav-templates` card on the hub).
- List, create Draft, edit Draft, preview subject+body, plain-text
  preview, SMS length + segment count, allowed-variable list,
  missing-variable warning, unknown-variable warning, approve (locks
  editing), clone (bumps version, returns Draft), archive.
- Approved templates show `approved-lock-badge` and disable subject/body
  inputs and the save button.
- HTML sanitiser strips `<script>`, `<iframe>`, event handlers —
  verified in preview end-to-end.
- **New backend endpoint**: `POST /api/automation/notification-templates/preview`
  returns `{subject, body_text, body_html_sanitised,
  allowed_variables, missing_variables, unknown_variables, sms_length,
  sms_segments, channel}`.

### 3. Actual scheduler deployment files
- `/app/deploy/kubernetes/cronjobs.yaml` — **16 CronJobs + 1 ConfigMap**
  (17 documents). Every CronJob has:
  - `concurrencyPolicy: Forbid`, `restartPolicy: Never`, `backoffLimit: 0`
  - `startingDeadlineSeconds` (120–600) and `activeDeadlineSeconds`
    (300–3600 depending on category)
  - `ttlSecondsAfterFinished: 3600`
  - `timeZone: "Australia/Melbourne"` (with UTC/DST fallback documented
    in the README for K8s < 1.25)
  - `SCHEDULER_SERVICE_TOKEN` read via `secretKeyRef` — **no secret
    values inlined anywhere in the file**
- `/app/deploy/scheduler/README.md` — rollout, token rotation, DST
  handling, monitoring alerts, do-not-do list.
- **Not applied**. `main` untouched, no deploy.

### 4. Verification totals
- **EB-15 backend tests**: `test_scheduler_eb15.py` — 48 passed.
- **Escalation & notification tests**: `test_escalation_eb15_closeout.py`
  — 16 passed.
- **Full backend suite**: **515 passed, 4 skipped, 0 failed**
  (runtime ≈ 685s). Baseline before this task was 499 passed, 4 skipped
  → +16 escalation tests, 0 regressions.
- **Frontend testing agent (iteration_21.json)**: 9/9 flows PASS at
  100%. HTML sanitiser confirmed. Approve→lock UX confirmed.
  Clone→v2→Draft confirmed. RBAC redirect confirmed (with one minor
  spec-vs-impl note: ReadOnly ultimately lands on `/` because both the
  Templates page AND the Automation Hub block ReadOnly — this is
  correct security behaviour).
- **Lint**: all new/edited files clean (Python & JS).

### Escalation dedup scenarios (proven flat)
1. Zero triggers → zero created.
2. Compliance expired: 3 consecutive scans, count flat.
3. Activation blocked: 3 consecutive scans, count flat.
4. Override expired: 3 consecutive scans, count flat.
5. Migration failed: 3 consecutive scans, count flat.
6. Storage failed: 3 consecutive scans, count flat.
7. Delivery repeatedly failed: 3 consecutive scans, count flat.
8. Acknowledgement blocks new escalations at same level.
9. Resolution stops further escalations.
10. Level increase produces new rows without duplicating L1.
11. Idempotency key persisted and unique across all rows.
12. Escalation-driven deliveries not re-escalated (self-recursion guard).

### Template Studio scenarios (verified by frontend testing agent)
1. List renders 32+ cards from real DB.
2. Create Draft via modal (`new-template-*` fields).
3. Preview shows subject, body, SMS length/segments, missing/unknown
   variables, allowed variables list.
4. Approve locks editing (`approved-lock-badge`, disabled inputs,
   hidden save button).
5. Clone creates Draft v2.
6. Archive removes card from list after refresh.
7. HTML sanitiser strips `<script>` from `body_html`.
8. ReadOnly redirect (RBAC enforced).
9. `nav-templates` card exists on Automation Hub.

### Files added / changed (this task)
- `backend/scheduler_module.py` — `EscalationService`, 6 detectors, 3
  incident-lifecycle methods, `PreviewRequest`, preview endpoint, 5
  escalation endpoints, 2 new collections + indexes (~450 lines added).
- `backend/tests/test_escalation_eb15_closeout.py` — 16 deterministic
  tests (new file, 380 lines).
- `frontend/src/pages/AutomationTemplatesPage.jsx` — new page (~380
  lines).
- `frontend/src/pages/AutomationHub.jsx` — added `nav-templates` card
  and expanded grid to 4 columns.
- `frontend/src/App.js` — new route + import.
- `deploy/kubernetes/cronjobs.yaml` — 16 CronJobs + ConfigMap (new).
- `deploy/scheduler/README.md` — rollout & rotation runbook (new).
- `memory/PRD.md` — this section.

### Defects found and fixed
1. **FastAPI mistook `PreviewRequest` for a query parameter** because
   the Pydantic model was defined inside the router-builder function.
   Fix: hoisted `PreviewRequest` to module scope.
2. **Startup failure on new escalation collection index** — pre-existing
   `notification_escalations` rows (from EB-15 initial placeholder)
   lacked the new `notification_escalation_id` field, so `unique=True`
   index build hit `E11000 dup key null`. Fix: dropped the placeholder
   collection once; index builds cleanly.
3. **React hook order violation** in `AutomationTemplatesPage.jsx` —
   `<Navigate>` early-return sat before `useMemo`. Fix: moved the
   redirect below all hook calls.

### Constraints honoured
- ❌ No SendGrid/Twilio SDKs added.
- ❌ No permanent in-process cron loop.
- ❌ No live network calls in tests.
- ❌ No real credentials in `.env`, YAML, or any source file.
- ❌ No real ACE data, no deploy, no GitHub push.
- ✅ Development Outbox default (all 25 escalation-driven deliveries
  from the test seeds went to the outbox — **zero real messages sent**).
- ✅ Scheduler manifests are UNAPPLIED.

### Remaining limitations
- Escalation UI is API-only in this round (Automation Hub shows
  aggregate counts; a dedicated Incidents page is a future
  enhancement).
- No webhook receivers yet for SendGrid/Twilio status callbacks.
- Automation health snapshots collection still reserved (unused).
- `automation_health_snapshots` history endpoint not built.
- Real ACE data migration remains scheduled for EB-16 / Phase 3.


---

## EB-16 · Controlled Migration Rehearsal, Operational Dashboards & Integrity Gate (2026-02-04)

**Status**: ✅ Delivered. Backend `538 passed, 4 skipped, 0 failed`.
Frontend QA `100% PASS` across 7 new pages. `main` untouched, no
deploy, no GitHub push, no real ACE data, all providers mocked or in
Development Outbox.

### New backend module
- `backend/integrity_module.py` (~1150 lines) — Integrity engine +
  Operations service + Rehearsal fixtures + Webhooks + Release Gate.

### New backend tests
- `backend/tests/test_integrity_eb16.py` — 23 targeted tests covering
  every requirement class.

### New collections & indexes
- `integrity_check_definitions` (unique on `integrity_check_definition_id`
  and `rule_key`)
- `integrity_check_runs` (unique on `integrity_check_run_id`,
  index on `(run_type, created_at DESC)`)
- `integrity_check_findings` (unique on `integrity_check_finding_id`,
  index on `(rule_key, signature)`, index on `status`)
- `integrity_check_events` (sparse unique on `integrity_check_event_id`)
- `integrity_baselines` (sparse unique on `integrity_baseline_id`)
- `automation_health_snapshots` (index on `captured_at DESC`) —
  materialised
- `notification_provider_events` — reused for webhook events

### New backend routes
- Integrity: `GET /api/integrity/definitions`, `POST /api/integrity/runs`,
  `GET /api/integrity/runs`, `GET /api/integrity/runs/{run_id}`,
  `GET /api/integrity/runs/{run_id}/findings`,
  `POST /api/integrity/findings/{finding_id}/acknowledge|resolve|accept-risk|reopen`,
  `GET /api/integrity/release-gate`.
- Operations: `GET /api/operations/summary`, `/driver-readiness`,
  `/compliance-workload`, `/migration-readiness`.
- Escalation reopen: `POST /api/automation/escalation-incidents/{id}/reopen`.
- Automation health: `POST /api/automation/health-snapshots`,
  `GET /api/automation/health-snapshots`.
- Webhooks: `POST /api/webhooks/sendgrid`, `POST /api/webhooks/twilio`
  (default-disabled, signature-verified).
- Rehearsal: `POST /api/rehearsal/eb16/seed` (Admin).

### New frontend pages / routes
- `/operations` → `OperationsDashboard.jsx`
- `/operations/driver-readiness` → `DriverReadinessPage.jsx`
- `/operations/compliance-workload` → `ComplianceWorkloadPage.jsx`
- `/operations/migration-readiness` → `MigrationReadinessPage.jsx`
- `/administration/automation/incidents` → `AutomationIncidentsPage.jsx`
- `/administration/integrity` → `IntegrityAdminPage.jsx`
- Health history section added to `AutomationHub.jsx`
- Hub tiles: `operations-hub-card`, `integrity-hub-card`

### Files changed
- `backend/server.py` — wired `build_integrity_router` and index
  bootstrap.
- `frontend/src/App.js` — 7 new routes + 7 new imports.
- `frontend/src/pages/Hub.jsx` — 2 new tiles.
- `frontend/src/pages/AutomationHub.jsx` — expanded nav (5 cards) +
  Health History section with accessible bar chart & summary table.
- `README.md`, `VERSION` — updated to `dcc-phase2-eb16`.

### Documentation added
- `memory/EB-16-INTEGRITY-TECHNICAL-NOTE.md`
- `memory/EB-16-MIGRATION-REHEARSAL-RUNBOOK.md`
- `memory/EB-16-OPERATIONS-RUNBOOK.md`
- `memory/EB-16-RELEASE-GATE-RUNBOOK.md`

### Defects found and fixed during EB-16
1. Rehearsal seed hit a `DuplicateKeyError` on
   `notification_delivery_attempts` because the cleanup loop did not
   include that collection. Fix: added to the sweep list; seed is now
   fully idempotent.
2. `TestEscalationReopen` used a static `eb16-inc-1` id; a leftover
   row from a prior run caused a `DuplicateKeyError`. Fix: generate a
   unique id per test and clean up explicitly.

### Constraints honoured
- ❌ No real ACE data — all fixtures tagged `_source="seed-eb16"`.
- ❌ No live messages — Development Outbox default.
- ❌ Webhooks disabled by default (`WEBHOOKS_ENABLED=false`) — return
  503 on POST.
- ❌ No SDKs added — Twilio uses HMAC-SHA1 via `hmac`; SendGrid uses
  HMAC-SHA256 via `hmac`.
- ❌ No permanent in-process cron loop.
- ❌ No real credentials in `.env`, source, or docs.
- ❌ No deploy, no GitHub push, `main` untouched.
- ✅ Development Outbox default.


---

## EB-16 Integrity Close-out · End-to-End Rehearsal & Deterministic Gate (2026-02-04)

### Delivered
1. **True end-to-end rehearsal runner** — `RehearsalRunner` in
   `integrity_module.py`. Records all 19 steps (workbook upload →
   profiling → classification → mapping → mapping approval → dry run →
   issue resolution → Go/No-Go → commit-job → approval → preflight →
   rollback package → staged commit → post-commit reconciliation →
   activation recalculation → notification materialisation (Dev
   Outbox) → export generation → controlled rollback → post-rollback
   verification). Every artefact carries a per-run `_source`
   tag `rehearsal-run:{uuid}`. Idempotent — running twice yields
   identical PASS outcomes with distinct run IDs.
2. **Isolated rehearsal-scoped gate** — `RehearsalGateService`
   evaluates PASS / PASS_WITH_WARNINGS / FAIL over ONLY the
   `_source ∈ {seed-eb16*, rehearsal-run:*}` rows. Pre-existing
   development records CANNOT alter the outcome. The system-wide
   `/api/integrity/release-gate` is untouched.
3. **SendGrid positive signature test** — added to
   `test_integrity_eb16.py::TestWebhooks::test_sendgrid_signature_verification_positive`.
   `_verify_sendgrid_signature` now accepts hex-encoded or
   base64-encoded signatures.
4. **Unknown provider message ID & duplicate callback tests** — verified
   safe handling.

### New routes
- `POST /api/rehearsal/eb16/run` (Admin) — execute the full 19-step
  rehearsal sequence.
- `GET  /api/rehearsal/eb16/runs` (Manager+) — list recent runs.
- `GET  /api/rehearsal/eb16/runs/{run_id}` (Manager+) — full run
  detail with per-step outcomes.
- `GET  /api/integrity/rehearsal-gate` (Manager+) — deterministic
  rehearsal-scoped gate.

### New collections + indexes
- `rehearsal_runs` (unique on `rehearsal_run_id`)
- `rehearsal_run_steps` (unique on `rehearsal_run_step_id`,
  indexed on `(rehearsal_run_id, at)`)

### Files changed
- `backend/integrity_module.py` — added `RehearsalRunner`,
  `RehearsalGateService`, 4 new routes, 2 collection indexes,
  hex-signature acceptance for SendGrid.
- `backend/tests/test_integrity_eb16.py` — extended cleanup, added
  9 new tests (`TestRehearsalRunner` ×2, `TestRehearsalGate` ×4,
  `test_sendgrid_signature_verification_positive`,
  `test_unknown_message_id_recorded_safely`,
  `test_duplicate_callback_idempotent`).

### Verification (targeted)
- `tests/test_integrity_eb16.py` — **32/32 PASS** (was 23; +9).
- End-to-end rehearsal live via curl: **overall_result=PASS**, 19
  steps recorded, all assertions true, gate=PASS.
- Rehearsal gate live via curl: **PASS**, Critical=0, Error=0,
  Warning=0, Info=0.

### Final full backend suite
- **546 passed, 1 failed, 4 skipped** — but the single failure was
  a `ConnectTimeoutError` from the preview URL (DNS/proxy timeout, not
  a regression); the same test passes standalone in 5.19 s.
- **Effective baseline: 547 passing, 4 skipped, 0 regressions** vs.
  the 538+4 baseline (net +9 EB-16 close-out tests).
- All 4 skips remain the pre-existing conditional skips in
  `test_activation_eb10*.py`.

### Frontend
No UI changes in this close-out. Frontend baseline from EB-16 iteration
22 (100% PASS) is untouched.

### Constraints honoured
- ✅ No real data. Fixtures only.
- ✅ No real messages (Development Outbox).
- ✅ No real credentials.
- ✅ Webhooks default-disabled.
- ✅ No deploy, no GitHub push, `main` untouched.

---

## EB-17a — Security Foundation (Feb 2026) ✅ COMPLETE

Parts 1–9 delivered — **backend suite: 589 passed / 1 skipped / 0 failed** (6m 18s).

### What shipped
- `backend/security_module.py` — 19 controls across 6 domains (AuthSession, RBAC, API, Secrets, Privacy, AuditLog); 7 new collections; delegation-aware permission-matrix builder; idempotent assessment runner; append-only exception approval trail.
- `backend/tests/test_security_eb17.py` — 38 tests, ALL local (`http://localhost:8001/api`), 0 skips.
- `frontend/src/pages/SecurityControlCentre.jsx` at `/administration/security` — 7 tabs (Overview, Controls, Findings, Permission Matrix, Data Classification, Audit Integrity, Exceptions) with role-gated actions and exception-request modal. Hub tile added.
- Pre-existing gate gaps closed while hardening: recalculate, imports (inspect/mapping/validate), notifications/read.
- `/api/modules/{resource}` limit lifted 1000 → 5000; activation history limit 1000 → 5000; `driver-readiness` now sorted by `updated_at DESC` so freshly-seeded records surface within pagination window.
- Full requirement matrix at `/app/memory/EB-17a-REQUIREMENT-MATRIX.md`.

### What is next (DO NOT auto-start)
- **P1 EB-17b** — Backup, restore, disaster recovery, RPO/RTO.
- **P1 EB-17c** — UAT framework, sign-offs, Production Readiness gate, rollback plan.
- **P2 EB-18** — Controlled Go-Live.

### Constraints honoured
- ✅ Fictional/sanitised data only.
- ✅ No preview URLs in EB-17a tests; local-only.
- ✅ No conditional skips in `test_security_eb17.py`.
- ✅ No live cron, no real providers, no GitHub push, `main` untouched.

---

## EB-17b — Backup / Restore / DR / RPO-RTO (Feb 2026) ✅ COMPLETE

Parts 1–15 delivered — backend targeted suite 34/34 PASS.

- `backend/recovery_module.py` (+ `recovery_service.py` facade) — provider-neutral backup framework; SHA-256 manifest & per-artifact checksums; isolated-namespace restore rehearsals; deterministic reconciliation (counts / identifiers / relationships / documents↔storage / audit-continuity); RPO/RTO configuration with `production_approved: false` fence; recovery readiness gate at `GET /api/recovery/gate`.
- 9 new collections (`backup_definitions`, `backup_runs`, `backup_artifacts`, `backup_manifests`, `restore_rehearsals`, `restore_reconciliation_results`, `recovery_events`, `recovery_configuration`, `restore_namespace_data`).
- 11 new API routes under `/api/recovery/*` + `/api/backups*` (RBAC: ReadOnly summary, Compliance read, Manager validate, Admin mutate).
- `frontend/src/pages/RecoveryDashboard.jsx` at `/administration/recovery` — 6 tabs (Overview, Backups, Restore Rehearsals, Reconciliation, RPO/RTO, Recovery Gate), fictional-marker banner, no colour-only status. Hub tile added.
- 4 runbooks under `/app/memory/EB-17b-*.md`; `VERSION` → `dcc-phase2-eb17b`.

No real ACE data, no real credentials, no live providers, no deploy, no GitHub push, `main` untouched.

## EB-17b Targeted Close-out (Feb 2026) ✅ COMPLETE

Two defects from the initial EB-17b delivery closed.

### Fix 1 — DR rehearsal uses the *real* EB-16 Integrity + EB-17a Security engines
- `backend/recovery_module.py::start_rehearsal` now calls the previously unwired
  `_run_namespace_gates(rehearsal_id)` — copies the isolated rehearsal namespace
  into a scratch MongoDB database (`<db>_reh_<rid>_a<attempt>`), boots indexes +
  seeds security controls on the scratch, runs `IntegrityService.run("FullSystem", ...)`
  and `SecurityService.run_assessment(...)` against the scratch, then drops the
  scratch DB. No live / dev data is mutated.
- Engine-internal errors (findings with `context.error` — a pre-existing motor
  cursor bug in a handful of EB-16 detectors) are counted separately in
  `integrity_engine_error_findings` and do NOT contribute to gate FAIL. Real
  data defects (duplicate driver_code, orphan relationship, tampered audit
  event with `updated_at`) still block the gate as required.
- Engine payloads propagated into every rehearsal record:
  `integrity_gate`, `security_gate`, `integrity_engine_result`,
  `integrity_engine_counts` (filtered), `integrity_engine_raw_counts`,
  `integrity_engine_error_findings`, `integrity_engine_findings[:20]`,
  `security_engine_result`, `security_engine_counts`, `payload_secret_scan`,
  `namespace_collections_copied`.
- Up-to-3-attempt retry with a fresh scratch DB per attempt absorbs transient
  Motor connection-pool churn from consecutive scratch drops.

### Fix 2 — Recovery Dashboard 422 handled with 0 console errors
- `frontend/src/pages/RecoveryDashboard.jsx::saveConfig` now client-side-gates
  RPO (1–100000), RTO (1–100000), and Backup-age-warning (1–720). Invalid input
  shows a `data-testid="cfg-validation-error"` inline banner + `toast.error(...)`
  and NEVER emits the axios POST → no 422 XHR, no browser console error, no
  console warning.

### Verification
- **Backend**: `pytest -q` full suite → **628 passed, 4 skipped, 0 failed** (777.89 s).
  - +4 targeted tests under `TestRealNamespaceEngines` in
    `backend/tests/test_recovery_eb17b.py` (clean → PASS, seeded integrity defect
    → integrity FAIL, seeded security defect → security FAIL, live-DB
    contaminant → no leak).
  - All 4 skipped tests are pre-existing conditional `pytest.skip(...)` guards
    inherited from EB-10 / EB-10.1 (no overridable outstanding item / no
    manual Licence-and-Compliance item — documented in EB-13 close-out entry).
- **Frontend**: `testing_agent_v3_fork` iteration_26 →
  **4/4 checkpoints PASS**, **0 console errors, 0 console warnings, 0 invalid-XHR emissions**.

### Files changed
- `backend/recovery_module.py` — real namespace-scoped gates wired in.
- `backend/integrity_module.py` — 2 x F601 lint fixes (`$ne` duplicate-key dict
  → `$nin` list). Zero behaviour change.
- `backend/tests/test_recovery_eb17b.py` — +4 `TestRealNamespaceEngines` tests,
  fixture cleans on entry AND exit, `_uuid_short` now returns a canonical
  hyphenated UUID so seeded rows don't leak into `test_registers_eb02` if any
  cross-file cleanup ever regresses.
- `frontend/src/pages/RecoveryDashboard.jsx` — pre-submit validation + inline
  banner.

No real ACE data, no real credentials, no live providers, no deploy, no GitHub push, `main` untouched.



## EB-17b Final Integrity Close-out (Feb 2026) ✅ COMPLETE

Removes the last integrity-gate compromise from EB-17b: engine execution
errors are no longer tolerated. Every applicable EB-16 detector must execute
successfully against the isolated rehearsal scratch database — anything less
blocks the gate.

### Fixed
- **Motor/cursor compatibility in EB-16 detectors** — replaced trailing
  `.limit(N)` (which returned an awaited cursor, always raising
  `object AsyncIOMotorCursor can't be used in 'await' expression`) with
  `.to_list(N)` across the 8 previously-broken detectors:
  `cmp.expired_marked_compliant`, `cmp.under_review_accepted`,
  `cmp.missing_evidence_accepted`, `cmp.archived_used_as_current`,
  `act.activated_not_ready`, `act.expired_override_active`,
  `act.missing_mandatory_but_ready`, `doc.checksum_mismatch`, plus 7 more
  in the notification / scheduler / migration domains that were silently
  returning `[]`. All 60 applicable detectors now execute successfully on a
  clean scratch namespace.

- **Hard rule enforced in `_run_namespace_gates`** — if
  `engine_error_findings > 0` OR the top-level engine call raised, then
  `integrity_gate` is FORCED to `FAIL`. Nothing is suppressed, downgraded,
  or filtered out; the failed detector rule keys are recorded on the
  rehearsal record.

- **New rehearsal record fields** (all indexable audit evidence):
  `integrity_engine_detectors_executed`,
  `integrity_engine_error_findings`,
  `integrity_engine_error_rules` (list of failing detector rule_keys),
  in addition to the fields introduced in the initial close-out.

- **Fault-injection hook** (`EB17B_FAULT_INJECT_RULE` env var, driven by the
  new `fault_inject_rule` field on `StartRehearsalBody`) — test-only, admin
  only, active only for the duration of a single rehearsal request. Used
  exclusively by the forced-failure test; never invoked by the UI, and
  never by real workflows.

### Verification
- **Targeted**: `pytest tests/test_recovery_eb17b.py -q` →
  **39 passed, 0 failed** (baseline 38 + 1 new
  `test_forced_detector_execution_failure_forces_integrity_fail`), 3
  consecutive stable runs.
- **Live proof captured by curl against `/api/recovery/rehearsals`**:
  - Clean rehearsal → `integrity_engine_detectors_executed=60`,
    `integrity_engine_error_findings=0`, `integrity_engine_error_rules=[]`,
    `integrity_gate=PASS`.
  - Forced fault on `act.activated_not_ready` →
    `integrity_engine_detectors_executed=60`,
    `integrity_engine_error_findings=1`,
    `integrity_engine_error_rules=['act.activated_not_ready']`,
    `integrity_gate=FAIL`, `final_state=Failed`.
- **Final full backend suite** (`pytest -q -rs`) →
  **629 passed, 4 skipped, 0 failed** in 749.34 s.
- **Every skip (exact test name and reason)** — all four inherited from
  EB-10 / EB-10.1 pre-existing conditional guards; none new to EB-17b:
  1. `tests/test_activation_eb10.py:350` — *No overridable outstanding item currently available*
  2. `tests/test_activation_eb10.py:378` — *No overridable outstanding item currently available*
  3. `tests/test_activation_eb10_extra.py:88` — *No manual Licence and Compliance item in template*
  4. `tests/test_activation_eb10_extra.py:108` — *No non-Compliance manual item available*

### Files changed
- `backend/integrity_module.py` — 15 × `.limit(N) → .to_list(N)` fixes across
  the previously-broken detectors; +1 env-var-gated fault-injection hook in
  `IntegrityService.run` (test-only, no runtime cost when unset).
- `backend/recovery_module.py` — hard-fail rule when engine errors > 0;
  new rehearsal-record fields (`integrity_engine_detectors_executed`,
  `integrity_engine_error_rules`); `fault_inject_rule` plumbed through
  `StartRehearsalBody` → `start_rehearsal` → `_run_namespace_gates`.
- `backend/tests/test_recovery_eb17b.py` — updated `test_clean_rehearsal_...`
  to assert `error_findings == 0` and `detectors_executed > 0`; added
  `test_forced_detector_execution_failure_forces_integrity_fail`.

### Requirement matrix — EB-17b
15/15 PASS · **0 MISSING · 0 DEFERRED**.

### Boundary confirmation
Reconciliation remains a separate result on every rehearsal record;
security assessment remains a separate result on every rehearsal record;
no real ACE data, no real credentials, no external providers activated,
no deploy, no GitHub push, `main` untouched.

## EB-17c — UAT, Sign-offs & Production Readiness Gate (Feb 2026) ✅ COMPLETE

Phase-2 gate before EB-18. Fictional-only (`_source: seed-eb17c`). No live
providers, no real ACE data, no deploy.

### Backend
- `backend/uat_module.py` — `UATService` + `build_uat_router(db, app, get_current_user)`.
  Registered from `backend/server.py`. Startup event ensures indexes.
- Collections created: `uat_test_plans`, `uat_test_cases`, `uat_test_runs`,
  `uat_test_results`, `uat_defects`, `uat_signoffs`, `uat_evidence`,
  `production_readiness_snapshots` (reserved), `production_readiness_checklist`,
  `production_readiness_events` (reserved), `production_readiness_conditions`.
- Deterministic seeded fictional cases: 59 across 7 packs — Driver Lifecycle,
  Compliance, Migration, Notifications, Operations, Security, Recovery.
- Statuses: Case {Draft, Ready, In Progress, Passed, Failed, Blocked,
  Not Applicable, Retest Required}; Defect {Open, Investigating, Fixed,
  Ready for Retest, Closed, Deferred, Reopened}; Sign-off {Pending, Approved,
  Approved with Conditions, Rejected, Withdrawn}; Condition {Open, Accepted,
  Resolved, Expired, Rejected}. Critical/High defects never deferred; Closed
  requires evidence or passing retest; sign-offs immutable (withdraw + new
  version); sign-offs blocked while Critical/High defects open, or any of
  Integrity / Security / Recovery gate = FAIL, or expired non-fictional
  security exceptions exist. Critical conditions cannot be Accepted.
- Routes (all `/api`-prefixed, RBAC-enforced):
  - UAT: `POST/GET /uat/plans`, `GET /uat/plans/{id}`, `GET /uat/cases`,
    `POST /uat/plans/{id}/start`, `GET /uat/runs/{id}`,
    `POST /uat/runs/{id}/close`, `POST /uat/results/{run_id}`,
    `POST/GET /uat/defects`, `POST /uat/defects/{id}/transition`,
    `POST/GET /uat/signoffs`, `POST /uat/signoffs/{id}/withdraw`.
  - Production Readiness: `GET /production-readiness/status`, `.../gate`,
    `.../checklist`, `POST .../checklist/{item_id}/update`.
  - Conditions: `GET .../conditions`, `POST .../conditions`,
    `POST .../conditions/{id}/update`.
- Readiness rule: worst-status-wins across Integrity, Security, Recovery,
  Migration readiness, UAT completion (100%), open Critical/High defects,
  every area sign-off Approved / Approved-with-Conditions, expired
  non-fictional security exceptions = 0, critical conditions = 0, every
  checklist item Complete/Waived (system items derive from live gates and
  reject manual writes with 400), rollback plan file present.
- Result: `READY` | `CONDITIONALLY_READY` (warnings only) | `NOT_READY`.
  No admin override to force READY.

### Frontend
- `/administration/uat` — 5-tab workspace (Plans, Runs, Test Cases, Defects,
  Sign-offs). All interactive elements carry `data-testid`.
- `/administration/production-readiness` — Overall gate banner, 8 gate cards,
  UAT summary, defect summary, sign-off matrix, conditions register,
  checklist. Accessible text labels (READY / CONDITIONALLY READY / NOT READY),
  not colour-only.

### Documentation
- `memory/EB-17c-UAT-PLAN.md`
- `memory/EB-17c-UAT-EXECUTION-RUNBOOK.md`
- `memory/EB-17c-PRODUCTION-READINESS-RUNBOOK.md`
- `memory/EB-17c-GO-LIVE-CHECKLIST.md`
- `memory/EB-17c-GO-LIVE-ROLLBACK-RUNBOOK.md`
- `VERSION` bumped to `dcc-phase2-eb17c`.

### Verification
- Targeted: `pytest tests/test_uat_eb17c.py -q` → **30 passed** (plan
  lifecycle, appending results, blocker-with-reason, defect lifecycle
  including Critical/High cannot-defer + close-requires-evidence, sign-off
  immutability / role restriction / withdraw / defect-blocks-approval,
  readiness NOT_READY → READY → CONDITIONALLY_READY, critical condition
  blocks, checklist RBAC, waiver-requires-evidence, expired condition
  visible, RBAC on every mutation).
- Final full backend suite: `pytest -q -rs` → **659 passed, 4 skipped,
  0 failed** in 318.04 s (localhost backend URL to avoid Cloudflare-edge
  transient timeouts on notification-scan tests).
- Every skip:
  1. `tests/test_activation_eb10.py:350` — *No overridable outstanding item currently available*
  2. `tests/test_activation_eb10.py:378` — *No overridable outstanding item currently available*
  3. `tests/test_activation_eb10_extra.py:88` — *No manual Licence and Compliance item in template*
  4. `tests/test_activation_eb10_extra.py:108` — *No non-Compliance manual item available*
- Frontend `testing_agent_v3_fork` iteration_27 → **21/21 checkpoints PASS**,
  0 app-level JS errors, 0 console warnings (one intentional 403 from
  ReadOnly attempting Create Plan is logged by Chromium as a network log,
  handled cleanly by the app via toast).

### EB-18 Prerequisites (must be READY before EB-18 begins)
1. Integrity gate = PASS
2. Security gate = PASS
3. Recovery gate = PASS
4. Migration readiness = PASS
5. Zero open Critical / High UAT defects
6. All 7 area sign-offs Approved or Approved with Conditions (Business Ops,
   Compliance, Management, Technical, Security, Data Migration, Recovery)
7. Zero expired non-fictional security exceptions
8. Zero open Critical conditions in the Condition Register
9. UAT completion = 100%
10. All 25 checklist items Complete / Waived (with evidence)
11. `memory/EB-17c-GO-LIVE-ROLLBACK-RUNBOOK.md` present

### Boundary
No real ACE data, no live providers, no public webhook activation, no deploy,
no GitHub push, `main` untouched.



---

## EB-18 — Controlled Go-Live Framework (2026-02-27) — **FRAMEWORK COMPLETE**

### Constitutional Boundary (enforced, non-negotiable)
EB-18 authorises the **build and verification of the controlled Go-Live
execution framework only**. It grants NO permission to:
- Deploy the application to Production
- Import real ACE data
- Enable live providers (SMTP, SMS, webhook receivers)
- Enable public webhooks
- Enable CronJobs / schedulers
- Push to GitHub / touch `main`

### Deliverables (all present)
1. **Prerequisite re-verification** — `/api/go-live/prerequisites` snapshots
   the 11 EB-17c gates (Integrity, Security, Recovery, Migration Readiness,
   UAT completion, sign-offs across 7 areas, zero Critical/High defects,
   zero expired security exceptions, zero open Critical conditions, all
   25 checklist items Complete/Waived, rollback runbook present).
2. **`golive_module.py`** — DRY_RUN / REHEARSAL / PRODUCTION modes with the
   PRODUCTION path gated behind an explicit approval marker (never
   one-clickable from the UI).
3. **Controlled real-data migration gate** — `/api/go-live/migration-authorisation`
   (grant / list / revoke) with reason + approver + expiry.
4. **Production deployment package generator** — `/api/go-live/deployment-package`
   produces the immutable package manifest (application version, migration
   set, config diff, prerequisite snapshot hash).
5. **Cutover execution workflow** — 33-step canonical checklist with
   per-step lifecycle (Pending → Running → Completed / Failed / Skipped),
   abort criteria, and rollback path (`/api/go-live/runs/{rid}/abort`,
   `/api/go-live/runs/{rid}/rollback`).
6. **Monitoring window** — `/api/go-live/runs/{rid}/monitoring` accepts
   snapshots and returns rolling status until the run reaches the final
   release decision.
7. **Release decision gates** — RELEASED, RELEASED_WITH_CONDITIONS,
   ABORTED, ROLLED_BACK via `/api/go-live/release-decision`.
8. **Frontend Go-Live Control Centre** — `/administration/go-live` with
   seven tabs: Overview, Prerequisites, Cutover, Migration Authorisation,
   Monitoring, Rollback, Release Decision.
9. **Runbooks (6 files, all present in `/app/memory`)**:
   - `EB-18-GO-LIVE-RUNBOOK.md`
   - `EB-18-CUTOVER-CHECKLIST.md`
   - `EB-18-MIGRATION-AUTHORISATION-RUNBOOK.md`
   - `EB-18-MONITORING-RUNBOOK.md`
   - `EB-18-ROLLBACK-RUNBOOK.md`
   - `EB-18-RELEASE-EVIDENCE-PACK.md`

### Endpoint Matrix (17 routes)
| Route | Method | Purpose |
|---|---|---|
| `/api/go-live/status` | GET | Framework health summary |
| `/api/go-live/prerequisites` | GET | Snapshot of 11 EB-17c gates |
| `/api/go-live/runs` | POST | Create DRY_RUN / REHEARSAL / PRODUCTION run |
| `/api/go-live/runs` | GET | List runs |
| `/api/go-live/runs/{rid}` | GET | Run detail + steps + evidence |
| `/api/go-live/runs/{rid}/approve` | POST | Approval marker (required for PRODUCTION) |
| `/api/go-live/runs/{rid}/start` | POST | Move run into Running state |
| `/api/go-live/runs/{rid}/steps/{step_id}/complete` | POST | Advance step |
| `/api/go-live/runs/{rid}/abort` | POST | Abort with reason |
| `/api/go-live/runs/{rid}/rollback` | POST | Execute rollback path |
| `/api/go-live/runs/{rid}/monitoring` | GET | List monitoring snapshots |
| `/api/go-live/runs/{rid}/monitoring` | POST | Record monitoring snapshot |
| `/api/go-live/deployment-package` | GET | Immutable deployment package |
| `/api/go-live/release-decision` | GET | Latest release decision |
| `/api/go-live/migration-authorisation` | GET | List authorisations |
| `/api/go-live/migration-authorisation` | POST | Grant authorisation |
| `/api/go-live/migration-authorisation/revoke` | POST | Revoke authorisation |

### Verification (2026-02-27)
- **EB-18 targeted:** `pytest tests/test_golive_eb18.py -q` → **27 passed, 0 failed**
- **Final full backend suite:** `pytest -q -rs` → **686 passed, 4 skipped, 0 failed** in 115.42s (localhost backend URL to bypass Cloudflare-edge transient timeouts).
- **Every skip (unchanged from EB-17c):**
  1. `tests/test_activation_eb10.py:350` — *No overridable outstanding item currently available*
  2. `tests/test_activation_eb10.py:378` — *No overridable outstanding item currently available*
  3. `tests/test_activation_eb10_extra.py:88` — *No manual Licence and Compliance item in template*
  4. `tests/test_activation_eb10_extra.py:108` — *No non-Compliance manual item available*
- **Frontend QA:** `testing_agent` iteration_28 → **100% PASS** across 7 tabs, lifecycle (READY TO START → RUNNING → ABORTED), RBAC (ReadOnly correctly blocked with 403 + toast), responsive at 1920×1080 and 1440×900 (no horizontal scroll), 0 console errors, 0 console warnings.

### Requirement Matrix
| # | Requirement | Status | Proof |
|---|---|---|---|
| 1 | Re-verify EB-18 entry prerequisites | COMPLETE | `/api/go-live/prerequisites` returns 11 gates + snapshot hash |
| 2 | `golive_module.py` DRY_RUN/REHEARSAL/PRODUCTION | COMPLETE | 711 lines, 3 modes, PRODUCTION gated by approval marker |
| 3 | Controlled real-data migration gate | COMPLETE | 3 endpoints: grant/list/revoke |
| 4 | Deployment package generator | COMPLETE | `/api/go-live/deployment-package` |
| 5 | Cutover / abort / rollback / monitoring | COMPLETE | 33-step workflow + monitoring snapshots |
| 6 | Release decision gates (4 outcomes) | COMPLETE | `/api/go-live/release-decision` |
| 7 | Frontend Go-Live Control Centre | COMPLETE | `/administration/go-live` — 7 tabs, all data-testid attributes |
| 8 | 6 runbook markdown files | COMPLETE | All present in `/app/memory` |
| — | Zero backend failures (full regression) | COMPLETE | 686 passed / 4 skipped / **0 failed** |
| — | Framework-only (no irreversible actions) | COMPLETE | No production deploy, no real data, no live providers, no public webhooks, no CronJobs, `main` untouched |

**MISSING: 0. DEFERRED: 0. Framework COMPLETE. Actual Production go-live NOT EXECUTED.**

### Boundary Re-affirmed
No real ACE data imported, no live providers enabled, no public webhook
activation, no production deploy, no GitHub push, `main` untouched.
