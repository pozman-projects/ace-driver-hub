# EB-17b · Disaster Recovery Rehearsal Runbook (Fictional / Dev-Test Only)

**Not production-approved.** All data is `_source: seed-eb17b` fictional and lives in the shared MongoDB rehearsal namespace only.

## Deterministic DR sequence
1. Seed clean fictional baseline (drivers, owners, relationships, documents, storage inventory, activation, audit).
2. `POST /api/backups` → produces manifest + artifacts (idempotent per `correlation_id`).
3. `POST /api/backups/{id}/validate` → confirms manifest + artifact integrity.
4. `POST /api/recovery/rehearsals { backup_run_id, approved: true }` — Admin-only.
5. Isolated namespace restore into `restore_namespace_data` scoped by `restore_rehearsal_id`.
6. Reconciliation: counts, identifiers, relationships (no orphans), documents↔storage, audit-continuity.
7. Integrity gate (namespace-scoped reconciliation subset) + Security gate (no secret-shaped values in restored payload).
8. Result computed → cleanup deletes the entire namespace → residue check confirms zero rows remain.
9. Source system untouched — every live collection row created outside `_source: seed-eb17b` is unchanged.

## Deterministic assertions
Backup checksum valid · Counts match · Identifiers match · Relationships match · Documents↔storage match · Numbering matches · Activation matches · Audit continuity preserved · Integrity gate PASS · Security gate PASS · Source system unchanged · Isolated namespace removed · No secrets captured · No real messages sent · No real ACE data used.

## Failure scenarios directly tested
Checksum mismatch · Missing artifact · Malformed manifest · Failed backup not recoverable · Cancelled backup rejected · Record-count mismatch · Orphan relationship · Documents↔storage mismatch · Reconciliation FAIL · Restore without approval · Stale backup · RPO breach · RTO breach.
