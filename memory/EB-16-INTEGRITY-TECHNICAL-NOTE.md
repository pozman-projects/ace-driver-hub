# EB-16 · Integrity Engine — Technical Note

## Overview
Cross-module integrity engine implemented as a compact single module
`/app/backend/integrity_module.py`. Provides deterministic detection of
data-quality issues across 8 domains, plus operations aggregations,
provider webhook foundations, rehearsal fixtures, and the release gate.

## Domains & rule catalogue
Full rule catalogue is in `RULES` (`integrity_module.py`). Domains:
Registers, Relationships, Compliance, Numbering, Activation,
DocumentsStorage, NotificationsAutomation, Migration.

Each rule specifies `rule_key`, `severity` (Info / Warning / Error /
Critical), and an async detector method that returns a list of
context dicts.

## Findings model
`integrity_check_findings` has a `signature` (sha256 of rule_key +
sorted context items). On subsequent runs the engine looks up the same
`(rule_key, signature)` open finding and updates its `last_seen_at`
and `occurrences` rather than creating a duplicate. Statuses: Open,
Acknowledged, Resolved, Accepted Risk, False Positive, Archived.

## Run types
FullSystem, Registers, Relationships, Compliance, Numbering, Activation,
DocumentsStorage, NotificationsAutomation, Migration, PreReleaseGate.
All runs are durable (persisted), auditable (events collection),
repeatable, idempotent, and correlation-ID based (`correlation_id`
column on the run).

## Release gate
`GET /api/integrity/release-gate` triggers a `PreReleaseGate` run and
computes:
- FAIL: any Critical open OR any Error open.
- PASS_WITH_WARNINGS: only Warnings open.
- PASS: zero open findings above Info.

## Auto-repair boundary
Critical findings are never auto-repaired. `accept-risk` on Critical
requires Admin role.

## Idempotency
- All runs are safe to re-execute; findings with the same signature are
  updated in place.
- Rehearsal seed is idempotent — clears `_source="seed-eb16"` rows and
  re-inserts fresh.
