# EB-17c — UAT Execution Runbook

Version: `dcc-phase2-eb17c`.

## 1. Prepare
- Log in as Admin, Manager, Compliance or Allocator depending on the pack.
- Navigate to `/administration/uat`.
- Confirm cases are seeded (all 7 packs visible on the Cases tab).

## 2. Create and start a plan
- On the Plans tab enter a name and click **Create Plan** (Manager+).
- Click **Start** to spawn a `uat_test_runs` record and move state → `In Progress`.

## 3. Execute cases
- Switch to the Runs tab, review each pack, click **Passed** / **Failed** /
  **Blocked** / **Retest Required** per case.
- **Blocked** requires a reason (prompt).
- Every result is stored append-only — retest simply adds a new attempt.

## 4. Raise defects (Failed / Blocked)
- On the Defects tab enter severity, title, click **Raise**.
- Transition using the pill buttons: `Open → Investigating → Fixed →
  Ready for Retest → Closed`.
- **Deferred** allowed only for Medium/Low.
- **Reopened** allowed from `Ready for Retest` if regression seen.

## 5. Sign off
- Sign-offs available on the Sign-offs tab. Only signers with a mapped role
  for that area may sign (see `SIGNOFF_ROLE_MAP` in `uat_module.py`).
- Approved sign-off is **immutable**. Use Withdraw + create a new sign-off
  (bumped `version`) to record a revision.

## 6. Close
- On the Runs tab click **Close Run**; both the run and its plan move to
  `Closed`.

## Boundaries
- No real customer data is loaded.
- No real messages, phone numbers or emails are used.
- No live provider is enabled.
- No deployment happens as part of UAT execution.
