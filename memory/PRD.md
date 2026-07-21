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

## Prioritized Backlog

### P1 (next iteration)
- **Document / File storage** — attach documents (licence scans, rego papers, insurance certs, inspection sheets, defect photos) to canonical compliance records via the `evidence_document_id` placeholder already reserved by EB-04; playbook-driven object storage.
- **Spreadsheet imports** — ACE-supplied driver / owner / vehicle / equipment / compliance spreadsheets → canonical registers with dry-run and validation report, using the `legacy_record_id` bridge added in EB-04.
- **Notifications / Alerts** — email/SMS alerts for canonical Due Soon and Expired records, using the summary engine as source of truth.

### P2
- Automated numbering (auto Driver Code allocation, auto Dispatch Number allocation with reserved-number guard)
- Final three-row DCC Driver profile interface mock-up (canonical widgets present but layout still compact)
- Compliance record edit dialogs already present on CompliancePage — add bulk actions and CSV export
- Audit log surface (who created/updated/archived) across canonical collections

### P3
- Mobile responsive driver-facing portal
- Bulk import (CSV)
- Reports & analytics
