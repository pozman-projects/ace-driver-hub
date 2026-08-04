# EB-16 · Operations Runbook

Operations dashboards live at `/operations` and cover four surfaces:

1. **Command Dashboard** — top-level KPIs, Worst-Status-Wins overall
   health, migration + storage state.
2. **Driver Readiness Workload** — one row per activation record with
   completion %, outstanding mandatory, active overrides, vehicle
   assignment. Filterable by Ready / Ready with Override / Incomplete /
   Blocked / No Vehicle.
3. **Compliance Workload** — all equipment compliance rows with
   verification status, evidence flag and expiry days.
4. **Migration Readiness** — latest dry run, commit job status,
   Go/No-Go, storage + scheduler readiness. Read-only (no commit
   button).

## Escalation Incidents
`/administration/automation/incidents`. Manager+ can acknowledge,
resolve or reopen incidents; View shows full incident JSON including
escalations trail.

## Automation Health History
Snapshots via `POST /api/automation/health-snapshots` (Manager+).
`GET /api/automation/health-snapshots` returns the 50 most recent.
Rendered as a simple accessible bar chart plus a table on the
Automation Hub.

## RBAC recap
- ReadOnly → Operations summary only.
- Allocator → Driver Readiness, Operations summary.
- Compliance → Compliance Workload + integrity acknowledge (non-Critical).
- Manager → All dashboards, run non-release integrity, resolve,
  reopen, accept non-Critical risk.
- Admin → Full integrity, Pre-Release Gate, accept Critical risk.
