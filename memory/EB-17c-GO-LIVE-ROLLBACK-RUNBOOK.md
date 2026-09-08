# EB-17c — Go-Live Rollback Runbook

Version: `dcc-phase2-eb17c` · Status: **PLANNING ONLY** · Not for execution.

## Stop-Decision Authority
- **Primary**: Head of Fleet Ops (Business Approver).
- **Secondary**: Head of Engineering (Technical Approver).
- **Emergency**: Head of Security may halt for security breaches without
  Business consensus.

## Rollback Triggers
- Integrity gate transitions to `FAIL` post cut-over.
- Security gate transitions to `FAIL` post cut-over.
- Recovery / DR rehearsal not verifiable within 60 minutes of cut-over.
- More than 3 High incidents open in the first hour.
- Any Critical defect surfaced in Production and not fixable in-flight.
- Manual authorisation violation detected in Production.
- Any real-provider unsafe state (webhook 5xx / provider rejection) that
  cannot be quarantined via feature-flag.

## Migration Stop Points
1. Pre-cutover: last chance before touching prod DB.
2. Post-schema: after Alembic-equivalent schema apply.
3. Post-data-migration: after data load but before UI cut-over.
4. Post-cut-over: soak window, first 60 min.

## Application Rollback
- Revert deployment to prior tagged image `dcc-phase2-eb17b`.
- Confirm `/api/health`, `/api/production-readiness/gate` return prior state.
- Retain rollback build image ≥ 30 days.

## Database Rollback
- Restore from verified backup captured at Stop Point 1.
- Run reconciliation via `POST /api/backups/{id}/validate`.
- Do NOT reuse partially migrated collections.

## Document / Storage Rollback
- Freeze uploads by disabling `documents/upload` (webhook flag).
- Rehydrate storage-object index from `storage_objects` snapshot.
- Verify checksum reconciliation clean before re-enabling uploads.

## Provider Disablement
- Provider credentials remain loaded but **disabled**.
- Set `PROVIDER_MODE=disabled` in secrets.
- Confirm no webhook callbacks fire against real numbers/addresses.

## Scheduler Disablement
- Revoke scheduler JWT.
- Confirm no scheduled jobs run against Production.

## Webhook Disablement
- Rotate webhook signing secrets to a decoy value.
- Publish empty allow-list.
- Confirm 401 on every legacy inbound webhook.

## Notification Suppression
- Set `NOTIFICATIONS_OUTBOX_ONLY=true`.
- Confirm no email / SMS goes to real recipients.

## Reconciliation After Rollback
- Run integrity, security, and recovery gates.
- Compare counts against Stop Point 1 snapshot.
- Any drift ≥ 0 records that were not part of the aborted change requires
  Manager+ investigation before re-attempt.

## Stakeholder Notification
- Business Ops: within 15 min.
- Engineering + Security: within 5 min.
- End-users: only after Business consensus.

## Incident Logging
- Create an incident in `security_assessment_events` with `event_type =
  rollback.executed`.
- Attach evidence bundle: Integrity, Security, Recovery gate snapshots.

## Recovery Verification
- Confirm scratch-DB rehearsal completes green **twice** consecutively.
- Confirm no residue rows left in `restore_namespace_data`.

## Retry / Abandon Decision
- **Retry** only when the underlying blocker has a fix approved by the same
  authority that ordered the rollback and re-verified via UAT retest.
- **Abandon** rolls back the EB-18 go-live approval; any new attempt requires
  a fresh sign-off round in EB-17c.

## Boundary
Production execution is **not** performed by this runbook. This document is
the plan of record. Execution requires EB-18 authorisation and a real
Production environment — neither of which is provisioned in EB-17c.
