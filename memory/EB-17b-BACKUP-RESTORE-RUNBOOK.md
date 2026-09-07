# EB-17b · Backup & Restore Runbook (Fictional / Dev-Test Only)

**Not production-approved.** No real ACE data, no real credentials, no live providers.

## Backup

- Provider-neutral snapshot of `_source: seed-eb17b` fictional rows across every EB-17b backup domain (canonical registers, relationships, compliance, activation, numbering, documents, storage inventory, notifications, audit events, migration state, integrity findings, security findings, configuration).
- Each snapshot emits per-artifact SHA-256 checksums, a manifest with per-domain counts + per-domain checksum + manifest checksum, schema_version `eb17b-v1`, `fictional_test_marker: true`, `source_system: "DCC-EB17b-Rehearsal"`.
- Idempotent per `correlation_id`.
- Secret-shaped keys are refused at snapshot time — a scan finds any `secret|password|api_key|token|credential|private_key|access_key|session|bearer` string value >8 chars and fails the run.

### Backup states
Queued · Running · Completed · Completed with Warnings · Failed · Cancelled

## Backup validation checks
- manifest_present, schema_version, manifest_checksum, no_missing_artifact,
  no_duplicate_artifact, artifact_checksum, record_count_match,
  no_secret_leak, not_cancelled, not_failed, complete_or_warn, stale (warning-only)

## Restore (rehearsal-only, isolated namespace)
- Restores solely into `restore_namespace_data` scoped by `restore_rehearsal_id`.
- Never writes into live application collections.
- Reconciles counts, identifiers, relationships, documents↔storage, audit continuity.
- Cleanup runs the delete pass and verifies zero residue.

## Routes
`POST /api/backups` · `GET /api/backups` · `GET /api/backups/{id}` · `POST /api/backups/{id}/validate` · `POST /api/recovery/rehearsals` · `GET /api/recovery/rehearsals` · `GET /api/recovery/rehearsals/{id}`

## Permissions
Admin only for create-backup and rehearsal execution. Manager may validate. Compliance may read backups/rehearsals. ReadOnly is limited to `/api/recovery/status` + `/api/recovery/gate`.
