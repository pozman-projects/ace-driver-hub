## EB-15 · Automation Operations Runbook

Applies to: DCC Automation & Delivery module (scheduler + notification pipeline).
Audience: Operations, on-call, and delivery managers.

---

### 1. Default posture

- **Scheduler enabled** but no in-process cron; jobs are triggered externally
  (see `EB-15-K8S-CRONJOBS.md`).
- **Delivery disabled** by default — `NOTIFICATION_DELIVERY_ENABLED=false`.
  All sends go to the **Development Outbox** (no external network).
- **Test mode on** — subject lines are prefixed `[TEST MODE]`, SMS bodies with
  `[TEST]`, and recipients are rewritten to `NOTIFICATION_ALLOWLIST` values
  when configured.
- **Providers**: `EMAIL_PROVIDER=development`, `SMS_PROVIDER=development`.

### 2. Health signals

| Signal                                | UI location                       | Threshold        |
|---------------------------------------|-----------------------------------|------------------|
| Overall health                        | `/administration/automation`      | Healthy          |
| Dead-letter count                     | Metrics card                      | 0 (Warning >0)   |
| Failed runs (last 24h)                | Metrics card                      | 0 (Warning >0)   |
| Circuit-breaker state (per provider)  | Providers page                    | `closed`         |
| Provider `configured`                 | Providers page                    | true             |

Escalate to **Critical** when `Dead Letter > 20` or `Failed Runs > 10`.

### 3. Common tasks

**Retry a failed delivery**
1. Navigate to Deliveries → filter `Failed` / `Dead Letter`.
2. Click **Retry** (Manager or Admin).
3. Confirm status → `Pending`. Next run of `notifications.dispatch` will pick
   it up. Manual dispatch: Jobs → `notifications.dispatch` → **Run**.

**Cancel a delivery**
- Deliveries → Row → **Cancel**. Allowed for anything except `Sent` and
  `Cancelled`.

**Resolve a dead-letter (paperwork only)**
- Deliveries → Row (Dead Letter) → **Resolve**. This records human resolution
  without a further attempt.

**Reset an open circuit breaker (Admin only)**
- Providers → Row → **Reset Circuit** after root cause is confirmed. This
  clears `consecutive_failures` and sets `state=closed`.

**Enable / disable a job**
- Jobs → Row → **Enable / Disable**. Disabled jobs still respond to manual
  runs by Manager+ but are skipped when triggered by the scheduler.

**Rotate `SCHEDULER_SERVICE_TOKEN`**
1. Generate a new token (≥ 32 random bytes, base64).
2. Update `dcc-scheduler-service-token` Secret in K8s.
3. Update `SCHEDULER_SERVICE_TOKEN` in the API pod env and restart.
4. Confirm at least one job triggers successfully.

### 4. Provider switch (Development → Production)

1. Set env vars in the API pod (rolling restart):
   - `EMAIL_PROVIDER=smtp` **or** `sendgrid`
   - `SMS_PROVIDER=twilio`
   - SMTP: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`,
     `SMTP_USE_TLS`.
   - SendGrid: `SENDGRID_API_KEY`.
   - Twilio: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`.
2. Verify at `/administration/automation/providers` → each row shows
   `configured: true`.
3. Trigger a health probe from the UI.
4. Enable actual delivery: `NOTIFICATION_DELIVERY_ENABLED=true`.
5. Keep `NOTIFICATION_TEST_MODE=true` until acceptance sign-off.
6. Retire test-mode: set `NOTIFICATION_TEST_MODE=false`. Suppression allow-list
   should remain for at least the first 72 hours to catch drift.

### 5. Escalation

- **Dead-letter surge (>50 in 1h)**: page the delivery on-call. Suspect
  provider outage. Verify circuit-breaker state and provider health-check.
- **All runs Failed for 15 min**: page platform on-call. Check scheduler
  ingress and API pod logs; verify Mongo is reachable.
- **Circuit stuck open >30 min**: page Admin; investigate provider status
  page; reset only after upstream is confirmed healthy.

### 6. Do-not-do

- ❌ Never bypass the retry pipeline by editing `notification_deliveries` in
  Mongo directly.
- ❌ Never set `NOTIFICATION_DELIVERY_ENABLED=true` in dev/preview clusters.
- ❌ Never commit real API keys to the repository or `.env` files.
