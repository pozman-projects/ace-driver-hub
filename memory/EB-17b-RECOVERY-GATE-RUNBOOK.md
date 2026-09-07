# EB-17b · Recovery Gate Runbook

## Endpoint
`GET /api/recovery/gate` — accessible to every authenticated role (ReadOnly+).

## Result contract
```
{
  "result": "PASS" | "PASS_WITH_WARNINGS" | "FAIL",
  "checks": { "<check_key>": "PASS" | "FAIL" | "WARN", ... },
  "errors":   [ "<blocking reason>", ... ],
  "warnings": [ "<advisory reason>", ... ],
  "status":   { latest_backup, latest_rehearsal, achieved_rpo_minutes,
                achieved_rto_minutes, configuration,
                outstanding_reconciliation_differences },
  "generated_at": "<ISO-8601>"
}
```

## PASS requires ALL of
- `latest_valid_backup` — a Completed/Completed-with-Warnings backup exists.
- `backup_integrity` — validation is not FAIL.
- `backup_checksum` — manifest checksum matches.
- `no_secret_leak` — no secret-shaped payload values.
- `restore_rehearsal` — most recent rehearsal `final_state == "Passed"`.
- `reconciliation` — reconciliation `result == "PASS"`.
- `integrity_gate` — namespace-scoped integrity PASS.
- `security_gate` — namespace-scoped security PASS.
- `no_residue` — post-cleanup residue count is zero.
- `rpo_target_met` — achieved RPO ≤ configured target.
- `rto_target_met` — achieved RTO ≤ configured target.
- `no_unreconciled_diffs` — reconciliation differences list is empty.

## PASS_WITH_WARNINGS
All blocking checks green, but one or more advisories present (typically `backup_age` above the configured `backup_age_warning_hours`). Warnings are enumerated in `warnings[]`.

## FAIL
Any blocking check red. Warnings are still enumerated. The gate never forces PASS regardless of role.
