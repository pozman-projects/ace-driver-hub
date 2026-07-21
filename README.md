# Driver Command Centre — ACE Car Freighters

> **Status:** Phase 2 Foundation Build (EB-03) — staging branch · `dcc-phase2-eb03`
> **Baseline release:** Phase 1 · `v0.1-phase1-baseline` (unchanged, on `main`)
> **Previous builds:** EB-01 shell / branding · `dcc-phase2-eb01` · EB-02 registers · `dcc-phase2-eb02`

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
| **EB-02** — Foundation Registers (Drivers, Owners, Vehicles, Equipment) | ✅ Complete |
| **EB-03** — Assignment & Relationship Layer | ✅ **This build** |
| ACE spreadsheet import               | ⏳ Not performed |
| Compliance Intelligence changes      | ⏳ Deferred |
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
