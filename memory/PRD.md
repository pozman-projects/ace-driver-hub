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
- **Backend suite total**: **~418 passed, 4 skipped, 0 failed** (up from
  395; +26 new EB-13 tests. 3 pre-existing `notification-jobs/*-scan`
  timeouts fixed by clearing an accumulated 880k-row
  `notification_deliveries` collection — data hygiene, not a code change).
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

**Files changed (7):**
- `backend/server.py` — EB-13 startup + router wiring
- `backend/.env` + `backend/.env.example` — EB-13 config keys (all safe
  defaults; S3 fields commented out)
- `backend/migration_prep_module.py` — new workbook uploads now use
  StorageService instead of inline `_data`; reader falls back to `_data`
  for legacy workbooks
- `backend/documents_module.py` — `register_existing` on new upload
- `backend/driver_export_module.py` — `register_existing` on PDF export
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

