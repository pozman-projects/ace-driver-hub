# EB-17b · Recovery Technical Note

## Collections
`backup_definitions` · `backup_runs` · `backup_artifacts` · `backup_manifests` · `restore_rehearsals` · `restore_reconciliation_results` · `recovery_events` · `recovery_configuration` · `restore_namespace_data` (isolated restore target).

## Namespaces
Every rehearsal writes exclusively into `restore_namespace_data` records keyed by `restore_rehearsal_id` + `namespace`. No writes are ever performed on live application collections.

## Manifest
`schema_version = "eb17b-v1"` · `manifest_version = 1` · per-domain `domain_checksum` and per-artifact `checksum` (SHA-256 over canonical-JSON of the payload) · `fictional_test_marker: true` · `source_system: "DCC-EB17b-Rehearsal"`.

## RPO / RTO
Development/Test defaults labelled `DEVELOPMENT DEFAULT — NOT PRODUCTION APPROVED`. `production_approved: false` is enforced at the API layer: any attempt to set `environment=Production` returns HTTP 403.

## Recovery Gate result taxonomy
- **PASS** — every blocking check green.
- **PASS_WITH_WARNINGS** — every blocking check green, only advisory (backup age) warnings present.
- **FAIL** — one or more blocking checks red.

Blocking checks: latest_valid_backup · backup_integrity · backup_checksum · restore_rehearsal · reconciliation · integrity_gate · security_gate · no_residue · rpo_target_met · rto_target_met · no_unreconciled_diffs · no_secret_leak.

## RBAC (backend-enforced)
- ReadOnly · `GET /api/recovery/status`, `GET /api/recovery/gate` only.
- Compliance · adds read on backups/rehearsals/configuration.
- Manager · adds `POST /api/backups/{id}/validate`; cannot mutate config or execute rehearsals.
- Admin · full CRUD; cannot set `environment=Production`; cannot force PASS.
