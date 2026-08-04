# EB-16 · Migration Rehearsal Runbook

Fictional migration rehearsal. **No real ACE data.**

## Prerequisites
- Admin session (`admin@acedriverhub.com` / `Admin@123`)
- Backend running; scheduler enabled (`SCHEDULER_ENABLED=true`)
- Delivery in Development Outbox (`NOTIFICATION_DELIVERY_ENABLED=false`)

## One-command seed
```
POST /api/rehearsal/eb16/seed  (Admin only)
```
Produces:
- 3 Drivers (`eb16-drv-clean`, `-cond`, `-nogo`)
- 3 Activation records (Ready / Incomplete / Blocked)
- 2 Owners, 2 Vehicles (one with Critical defect), 2 Equipment
- 1 primary Vehicle assignment, 1 expired compliance record
- 1 Notification + 1 Development-Outbox delivery + 1 attempt

All rows tagged `_source="seed-eb16"` for deterministic teardown.

## Scenarios covered (bulk-seeded)
- Clean GO — driver `eb16-drv-clean`, Ready.
- CONDITIONAL GO — driver `eb16-drv-cond`, Incomplete with outstanding=1.
- NO-GO — driver `eb16-drv-nogo`, Blocked with outstanding=3.
- Critical defect vehicle — `eb16-veh-2`.
- Expired compliance — record `eb16-cmp-expired`.
- Activation Ready / Incomplete / Blocked.

## Extended scenarios (run integrity to reveal)
Additional scenarios (duplicate Driver Code, reserved dispatch, missing
FK, overlapping assignment etc.) are seeded per-test in
`tests/test_integrity_eb16.py`. Each test seeds a specific scenario,
runs integrity, and asserts the finding.

## Sequence
1. Preflight — Admin logs in.
2. Seed — `POST /api/rehearsal/eb16/seed`.
3. Verify — `/operations` dashboard shows 3 Ready+1 counts derived
   from the seed.
4. Integrity — `POST /api/integrity/runs {run_type: "FullSystem"}`.
5. Findings — `GET /api/integrity/runs/{id}/findings`.
6. Release gate — `GET /api/integrity/release-gate`.
7. Snapshot — `POST /api/automation/health-snapshots`.

## Rollback rehearsal
The seed is fully idempotent. To "rollback" simply re-run the seed —
all previous rehearsal rows are dropped. Repeat integrity + release
gate — counts return to zero for rehearsal-sourced findings.
