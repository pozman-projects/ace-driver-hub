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

## Prioritized Backlog

### P1 (next iteration)
- Edit/Update flow per row (dialog reusing field config)
- Driver ↔ Licences / Rego / Insurance / Equipment / Maintenance / Tilt Tray relationships (foreign key by driver id)
- Expiry alert badges (red/amber/green) on Licences, Insurance, Rego, Maintenance
- User management page (Admin only) — list users, create new user with role
- Onboarding multi-stage workflow (status board: Documents → Induction → Active)

### P2
- Document upload per record (S3-compatible object storage)
- Dashboard widgets: expiring-soon count, defects open, compliance score
- CSV export per module
- Audit log (who created/updated/deleted)
- Email alerts for expiring licences/rego/insurance

### P3
- Mobile responsive driver-facing portal
- Bulk import (CSV)
- Reports & analytics
