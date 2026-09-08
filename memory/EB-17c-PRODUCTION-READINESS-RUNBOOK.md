# EB-17c — Production Readiness Runbook

Version: `dcc-phase2-eb17c`.

## Purpose
Determine, deterministically, whether the fictional Phase 2 platform is
`READY`, `CONDITIONALLY_READY`, or `NOT_READY` for the EB-18 controlled
go-live. Worst-status-wins across every input.

## Composition
The gate at `GET /api/production-readiness/gate` aggregates:

1. **Integrity gate** — latest `integrity_gate_results.result` (PASS,
   PASS_WITH_WARNINGS, or FAIL).
2. **Security gate** — latest `security_assessment_runs.overall_result`
   for a Completed run.
3. **Recovery gate + Migration readiness** — latest `restore_rehearsals`
   record. Requires `final_state = Passed`, `integrity_gate = PASS`,
   `security_gate = PASS`.
4. **UAT completion** — latest terminal result per case must reach 100%.
5. **Open defects** — Critical and High must be zero.
6. **Sign-offs** — every area in Approved / Approved with Conditions.
7. **Expired security exceptions** — must be zero (non-fictional only).
8. **Conditions register** — zero open Critical conditions.
9. **Checklist** — every human item Complete or Waived (with evidence),
   every system-derived item Complete.
10. **Rollback plan** — `memory/EB-17c-GO-LIVE-ROLLBACK-RUNBOOK.md` present.

## Result rules
- `NOT_READY` — any blocker in the list above.
- `CONDITIONALLY_READY` — no blockers but at least one warning:
  Integrity `PASS_WITH_WARNINGS`, or Approved with Conditions sign-off,
  or Conditions register non-empty.
- `READY` — everything clean.

## Route inventory
- `GET /api/production-readiness/status`
- `GET /api/production-readiness/gate`
- `GET /api/production-readiness/checklist`
- `POST /api/production-readiness/checklist/{item_id}/update`
- `GET /api/production-readiness/conditions`
- `POST /api/production-readiness/conditions`
- `POST /api/production-readiness/conditions/{id}/update`

## Forbidden operations
- No admin, no signer, and no operator may override to `READY`.
- No manual mutation of `integrity_gate`, `security_gate`, `recovery_gate`,
  `pe.int_gate`, `pe.sec_gate`, `pe.rec_gate`, `pe.uat_ok` — these are
  system-derived only and rejected with `400`.

## Data safety
No real ACE data is loaded, generated, or transmitted. All rows carry
`_source: seed-eb17c`.
