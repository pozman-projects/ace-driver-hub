## EB-15 · Technical Note

**Scope**: Production-capable scheduling, notification providers, and delivery
pipeline for DCC. Everything in this document was implemented in
`/app/backend/scheduler_module.py` and its accompanying tests in
`/app/backend/tests/test_scheduler_eb15.py`.

### Architecture

1. **Scheduler triggers are external**. The API exposes:
   - `POST /api/internal/scheduler/{job_key}` — HMAC-compared service token
     via `X-Scheduler-Token` header, optional IP allow-list.
   - `POST /api/automation/jobs/{job_key}/run` — human trigger (Manager+).
   No in-process cron loop exists. All periodicity is enforced by an external
   scheduler (see `EB-15-K8S-CRONJOBS.md`).

2. **Locking**. `scheduled_job_locks` uses a unique index on `job_key` to
   enforce `Forbid` concurrency. Stale locks (`expires_at` in the past) are
   reaped on acquire. TTL is 10 min by default.

3. **Runs & events**. Every trigger writes a `scheduled_job_runs` row and one
   or more `scheduled_job_events` rows (Started, Completed, Failed). Runs are
   linked to a `correlation_id` that propagates into all attempts.

4. **Providers**. Adapters live in the same module and expose a common
   `send()` protocol with typed `ProviderResult`. All four are production-
   capable but adhere to constraints:
   - `DevelopmentEmailProvider` / `DevelopmentSmsProvider`: no network,
     circuit-immune, default.
   - `SMTPEmailProvider`: uses stdlib `smtplib`. `send()` uses
     `run_in_executor` so the async pipeline is never blocked.
   - `SendGridEmailProvider`: uses `httpx.AsyncClient` against
     `https://api.sendgrid.com/v3/mail/send`. No SDK.
   - `TwilioSmsProvider`: uses `httpx.AsyncClient` against Twilio's REST API
     with basic auth. No SDK.
   Provider is chosen at construction time from `EMAIL_PROVIDER` /
   `SMS_PROVIDER` env vars.

5. **Delivery pipeline**. `DeliveryService.dispatch_pending()`:
   - Walks `notification_deliveries` where `delivery_status` ∈ `{Pending,
     Queued, Retry Scheduled}`.
   - Enforces quiet-hours (Australia/Melbourne, configurable), with a
     `Critical`-priority override that never overrides SMS.
   - Consults the circuit-breaker; if `open`, marks delivery
     `Retry Scheduled` with `suppression_reason=circuit_open`.
   - Sends via the chosen provider **or**, when
     `NOTIFICATION_DELIVERY_ENABLED=false`, produces a synthetic
     Development-outbox result without touching the real adapter.
   - Writes a `notification_delivery_attempts` row per attempt with the
     masked recipient (see below).
   - On transient failure and `attempts_made < max_attempts`: schedules a
     retry with exponential backoff (`[0, 300, 900, 3600, 14400]` seconds by
     default), stored in `next_retry_at`.
   - On terminal failure or exhausted attempts: moves the delivery to
     `Dead Letter`.
   - Updates circuit-breaker state (`on_success` / `on_failure`).

6. **Circuit breaker**. Stored per `provider_key` in
   `notification_provider_health`. Opens after
   `NOTIFICATION_CIRCUIT_THRESHOLD` (default 5) **consecutive transient**
   failures. Half-opens after `NOTIFICATION_CIRCUIT_HALFOPEN_SECONDS`
   (default 300). Admins can reset via
   `POST /api/automation/providers/{key}/reset-circuit`.

7. **Templates**. `notification_templates` is versioned and immutable when
   `status=Approved`. Approvals cannot be edited; a clone bumps `version` and
   returns to `Draft`. The rendering helper `render_template()` uses
   `{{var}}` substitution with `[missing:var]` masking on unknown keys, and a
   conservative HTML sanitiser strips `<script>`, `<iframe>` and event
   handlers.

8. **PII masking**. `_mask_email("bob@x.io")` → `bo***@x.io`. Non-Admins do
   not receive raw recipient fields; the API strips them and returns the
   masked equivalent in `email_address_masked` / `mobile_number_masked`.

### Collections added

- `scheduled_job_definitions`, `scheduled_job_runs`, `scheduled_job_events`,
  `scheduled_job_locks`
- `automation_health_snapshots` (indexed, unused today; reserved)
- `notification_delivery_attempts`, `notification_provider_events`,
  `notification_suppression_events`, `notification_templates`,
  `notification_provider_health`

All ID columns are UUID strings. All timestamps are ISO 8601 UTC.

### Test strategy

- **48 tests** in `test_scheduler_eb15.py` cover: registry, RBAC, manual run,
  service-token auth, all four providers (Dev + SMTP + SendGrid + Twilio) via
  `smtplib` mocks and `httpx.MockTransport`, delivery pipeline with the
  Development provider, templates (create/approve/clone/edit-lock, variable
  extraction, HTML sanitiser), circuit-breaker open/close, provider listing
  without credential leaks, job integrations, and locking (stale recovery +
  duplicate block).
- Full backend regression: **499 passed, 4 skipped** (baseline was
  451 passed + 4 skipped; +48 EB-15 tests, 0 regressions).

### Constraints honoured

- ❌ No SendGrid or Twilio Python SDKs — HTTP only via `httpx`.
- ❌ No permanent in-process cron loop.
- ❌ No live network calls in tests (verified by `httpx.MockTransport` and
  `unittest.mock.patch("scheduler_module.smtplib.SMTP")`).
- ❌ No real provider credentials (all env-driven; `.env` contains dev tokens
  only).
- ✅ Development Outbox is the default; delivery must be opted-in explicitly.
- ✅ Test mode allow-list rewrites recipients when set.

### Known limitations

- Escalation deduplication endpoint returns `{escalations_created: 0,
  deduped: 0}` — placeholder; will be filled by EB-16 when real business
  drivers land.
- No webhook receivers yet for SendGrid/Twilio delivery-status callbacks; the
  provider reply from the send call is the source of truth.
- Automation health snapshots collection is indexed but not yet materialised
  by any job — reserved for the future health-history endpoint.
