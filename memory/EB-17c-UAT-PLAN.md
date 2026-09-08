# EB-17c — UAT Plan

Version: `dcc-phase2-eb17c` · Fictional dataset (`_source: seed-eb17c`).

## Scope
User Acceptance Testing for Phase 2 EB-01 through EB-17b, prior to EB-18.

## Responsibilities
- **UAT Coordinator** — owns the plan, run lifecycle, evidence journal.
- **Tester** — executes cases, records results and evidence.
- **Business Approver** — signs Business Ops, Compliance, Management, Data Migration.
- **Technical Approver** — signs Technical, Security, Recovery.

## Statuses
- Case: Draft, Ready, In Progress, Passed, Failed, Blocked, Not Applicable, Retest Required.
- Defect: Open, Investigating, Fixed, Ready for Retest, Closed, Deferred, Reopened.
- Sign-off: Pending, Approved, Approved with Conditions, Rejected, Withdrawn.

## Packs
Driver Lifecycle · Compliance · Migration · Notifications · Operations · Security · Recovery.

## Deferral rules
- **Critical** defects: never deferred.
- **High** defects: never deferred into EB-18.
- **Medium/Low**: deferrable with a documented reason.

## Evidence
Every recorded result is append-only. Retest preserves prior attempts.
Every UAT evidence attachment is journalled in `uat_evidence`.

## Exit criteria for EB-17c → EB-18
- All required sign-offs Approved (or Approved with Conditions + Condition Register complete).
- Zero open Critical defects.
- Zero open High defects.
- Integrity, Security, Recovery gates = PASS.
- Migration readiness = PASS.
- Go-Live Checklist complete.
- No expired security exceptions (real, non-fictional).
