# EB-16 · Release Gate Runbook

## What is the release gate?
A deterministic **PreReleaseGate** integrity run whose outcome is
mapped to one of three release results:

| Result | Condition |
|---|---|
| **PASS** | Zero open Critical, zero open Error findings across all domains. |
| **PASS_WITH_WARNINGS** | Warnings present but no Critical or Error. |
| **FAIL** | Any open Critical or Error finding. |

## How to run
```
GET /api/integrity/release-gate    (Manager+)
```
Returns:
```
{
  integrity_check_run_id: <uuid>,
  gate_result: "PASS" | "PASS_WITH_WARNINGS" | "FAIL",
  findings_by_severity: { Critical, Error, Warning, Info },
  rules_evaluated: <n>
}
```

## UI
`/administration/integrity` shows the latest gate banner with a colour-
coded status plus a severity breakdown. Manager+ may re-run the full
system check; Admin only may re-run the Pre-Release Gate.

## Blockers for EB-17
EB-17 **must not begin** unless the release gate returns PASS or
explicitly approved PASS_WITH_WARNINGS with a documented risk-acceptance
paper trail.

## Auto-repair boundary
Critical findings never auto-repair. Accept-Risk on Critical requires
Admin. Errors can be Accepted by Manager+; Warnings by Compliance+.

## Baselines
Each run writes a row to `integrity_baselines` for historical
comparison. The most recent gate result is stamped onto the same
baseline row for the sanity check.
