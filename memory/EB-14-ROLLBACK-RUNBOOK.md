# EB-14 — Rollback Runbook

Rollback is a **separate, Admin-authorised operation**. It exists to
reverse a controlled commit when business or data authority calls for
it. It is not a routine action and it does **not** delete audit trails.

## When rollback is appropriate
- Immediately after a Controlled Commit that Paul or business ops
  determine was executed against a superseded workbook or mapping.
- After post-commit reconciliation reports `Failed Reconciliation` and
  the root cause requires a full re-migration.

## When rollback is NOT appropriate
- Fixing an individual bad record. Prefer canonical edit via the normal
  UI, which preserves history correctly.
- After users have edited canonical records that were created by
  migration. Destructive rollback of those specific records is blocked
  by the conflict detector.

## Sequence

### 1. Open the commit job
Navigate to `/migration-commit` and open the target job. Confirm
`status ∈ {Completed, Partially Completed, Rolling Back}` and that the
rollback package `status` is `Sealed`.

### 2. Rollback request
Click **Rollback request**. The engine:
- Creates a `migration_approval` of type `Rollback Approval`
- Sets job status to `Rollback Pending`
- Records the requesting user in the approval + event trail

### 3. Rollback approval (Admin, another user)
A second Admin approves. Approval note MUST reference:
- The business reason for rollback
- Paul's authorisation (or explicit escalation)

Self-approval is blocked for Controlled Commit jobs.

### 4. Preview the rollback package
Open the **Rollback package** panel:
- `actions_count` = number of reverse steps
- `pending / reverted / failed` counters
- Each action shows entity type, canonical ID, reverse action and
  expected current value

### 5. Execute
Click **Execute rollback** → type `ROLL BACK MIGRATION` → confirm.

The engine walks actions in reverse dependency order:
1. Cross-sheet relationships (assignments, driver-owner) — closed
2. Drivers created by migration — deleted
3. Equipment created by migration — deleted
4. Vehicles created by migration — deleted
5. Owners created by migration — deleted
6. Identifier allocations — marked reusable where safe (never blindly
   decrements sequences)

### 6. Conflict handling
For every action, the engine checks the current canonical record's
`updated_at` and `_source`. If either has changed since commit:
- The action is marked `Failed / conflict`
- The record is left in place (destructive rollback is refused)
- The job transitions to `Partially Completed` if any action is
  reverted, or `Rollback Failed` if none succeed

Conflicts must be resolved manually with Paul's authorisation before
another rollback attempt.

### 7. Post-rollback verification
- Run **Reconcile** again — it should now show missing records for the
  rolled-back scope (which is expected).
- Confirm `driver_export_versions` and other downstream artefacts are
  in the expected state.
- If storage backfill was linked to the rolled-back scope, the storage
  objects **remain** — deleting evidence is not part of rollback.

## Never
- Never mass-delete rollback actions or audit events. Rollback state is
  append-only for compliance.
- Never rewind `number_sequences.next_value` blindly — reuse of freed
  numbers is safer.
- Never rollback in Production without Paul's explicit written
  authorisation and a second Admin approval.
