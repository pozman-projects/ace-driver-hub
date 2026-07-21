# Driver Command Centre — ACE Car Freighters

> **Status:** Phase 2 Foundation Build (EB-01) — staging branch · `dcc-phase2-eb01`
> **Baseline release:** Phase 1 · `v0.1-phase1-baseline` (unchanged, on `main`)

The **Driver Command Centre (DCC)** is ACE Car Freighters' operational control
surface — a single command hub for drivers, licences, vehicles, equipment,
maintenance and compliance. Built for transport operations staff who need
fast, clean, practical access to the data that keeps the fleet moving.

The DCC is the evolution of the Phase 1 **ACE Driver Hub** prototype. The
same React + FastAPI + MongoDB stack, the same tested APIs, database
collections and authentication behaviour — with an updated identity and
visual frame in preparation for Phase 2 business features.

## Phase 2 status

| Milestone                            | State       |
| ------------------------------------ | ----------- |
| Business Blueprint                   | ✅ Complete |
| Technical Architecture               | ✅ Complete |
| Phase 2 Foundation Build             | 🟡 Commenced |
| **EB-01** — App shell / branding / visual frame | ✅ This build |
| Business logic / DB changes          | ⏳ Not in EB-01 |

### EB-01 scope (this build)
- Visible branding renamed **ACE Driver Hub → Driver Command Centre / DCC**
- New visual frame: dark navy navigation, light-grey page background,
  white workspace surfaces, teal/cyan operational accents
- Version stamp `DCC · Phase 2 Foundation · EB-01` on the landing hub
- `VERSION` file → `dcc-phase2-eb01`
- **No business logic, API, database schema, route, role or auth changes**
- Staging branch only — `main` untouched

Phase 1 Baseline features (all preserved unchanged from `v0.1-phase1-baseline`)
are listed below.

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
