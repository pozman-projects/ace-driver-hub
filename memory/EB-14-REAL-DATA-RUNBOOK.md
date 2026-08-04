# EB-14 — Real ACE Data Migration Runbook (Stage B)

**Stage B may begin ONLY after Paul provides an explicit written
instruction to commit real ACE data.** This runbook is the sequence to
follow when that instruction arrives. Do not import real data merely
because Stage A code passes tests.

## Pre-conditions
1. Real ACE workbook file(s) received from Paul through a private,
   authenticated channel.
2. Workbook stored on a personally controlled workstation until secure
   upload.
3. No copies on shared drives, chat platforms or personal email.

## Step-by-step sequence

### 1. Secure workbook receipt
- Verify the sender identity out-of-band (phone or Signal).
- Confirm the workbook is the authoritative source per Paul's
  instruction. Record the authority statement in `migration_approvals`
  `approval_note`.

### 2. Upload via EB-13 storage
- Log in as **Admin** in the target (staging or Production) environment.
- Navigate to `/migration-preparation/workbooks`.
- Upload the file. EB-13 will route bytes into the configured private
  object store and compute the SHA-256 checksum automatically.
- **Record the checksum externally**. It is the authoritative fingerprint
  of the source-of-truth workbook and will invalidate approval if it
  changes.

### 3. Authority confirmation
- On the workbook detail page, confirm the `source_system`,
  `business_owner`, `data_domain` and `authority_level` all match Paul's
  instruction.

### 4. Mapping profile
- Create or select an **Approved** mapping profile for each sheet.
- Do not use a Draft or In Review profile.
- Verify `profile_version` — this value is baked into the immutable
  migration package and any change invalidates the approval.

### 5. Dry run
- `/migration-preparation/dry-runs` → New dry run → tick the approved
  workbook + mapping profile.
- Execute the dry run. Wait for `status = "Preview Ready"`.
- Review every warning and every blocking issue.

### 6. Issue resolution
- Resolve every blocking issue before requesting Go/No-Go.
- Document each resolution in the issue notes.

### 7. Go / No-Go report
- Generate the Go/No-Go report at
  `/migration-preparation/dry-runs/{id}` → Go/No-Go.
- Confirm result is **GO** or **CONDITIONAL GO**. NO-GO cannot proceed.

### 8. Business review
- Send a printable summary of the Go/No-Go, all issues and all accepted
  risks to Paul.
- **Wait for written Go instruction from Paul** referencing that report
  by ID.

### 9. Migration approval
- Navigate to `/migration-commit`.
- Create a new commit job:
  - Mode: **Controlled Commit**
  - Name: Include a clear label including the workbook checksum prefix
- Request approval. Do NOT approve as the same user who requested it —
  the engine blocks self-approval for Controlled Commit.
- A second Admin approves with `risk_acceptance=true` if Go/No-Go is
  Conditional Go, plus a note capturing Paul's approval reference.

### 10. Preflight
- Run preflight and inspect every check on the UI.
- Every workbook checksum, every mapping profile version and every
  Go/No-Go result must be **Pass**.
- If preflight fails, DO NOT force execute — return to the failing step.

### 11. Rollback package verification
- Preflight will report `rollback_package_present`. Confirm on the
  detail panel that the rollback package status is `Building` and that
  the `commit-rollback-package` card is visible.

### 12. Rehearsal
- Do one final Rehearsal-mode job from the exact same dry run.
- Compare rehearsal totals (Created/Preserved/Skipped/Failed) against
  the Go/No-Go report. They must match.

### 13. Controlled commit
- Open the Controlled Commit job → Execute.
- Type the exact confirmation string `COMMIT ACE MIGRATION`.
- Watch the live event log. Do NOT close the tab. If the job pauses or
  partial-completes, do not restart it — call `resume`.

### 14. Post-commit reconciliation
- After completion, click **Reconcile**.
- Verify `result = "Reconciled"`. If `Reconciled with Warnings`, review
  each warning before declaring success.

### 15. Business sign-off
- Export the completion summary + reconciliation result and send it to
  Paul.
- Wait for written acknowledgement before archiving the job.

### 16. Rollback (contingency)
- If, at any point, Paul or business ops request rollback:
  1. Open the job in Migration Commit Hub.
  2. Click **Rollback request** → **Approve rollback** (Admin, another
     user).
  3. Type `ROLL BACK MIGRATION` to confirm.
- Later user edits after commit will block destructive rollback for
  those specific records. Those conflicts must be resolved manually
  with Paul's approval.

## Never
- Never commit a NO-GO dry run.
- Never approve or execute your own real commit request.
- Never edit `number_sequences` directly.
- Never delete legacy `_data` or filesystem originals as part of any
  EB-14 operation.
- Never publish real ACE data to a preview or staging environment.
- Never leave the browser tab or restart the container during a
  Controlled Commit — always use pause/resume through the UI.
