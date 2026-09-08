# EB-18 Release Evidence Pack
For each run, the release evidence pack aggregates:
- prerequisite_snapshot_id + snapshot
- migration_authorisation record (id, status, checksums, GO decision)
- deployment_package (`GET /api/go-live/deployment-package`) — no secret values
- ordered cutover step records with operator, evidence, timestamp, result
- monitoring snapshots (Healthy/Warning/Critical)
- abort events (if any)
- release_decision result: RELEASED | RELEASED_WITH_CONDITIONS | ABORTED | ROLLED_BACK
Nothing in this pack contains real ACE data, real credentials, or real messages.
