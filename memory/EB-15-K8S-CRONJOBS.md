## EB-15 · Kubernetes CronJob Manifests (Reference)

These manifests are **reference examples** demonstrating how the DCC scheduler
should be triggered externally in a production cluster. They are **not
applied** by this repository — the DCC pod does not, and must not, run a
permanent in-process cron loop.

The pattern used is:

1. A tiny `curl`-only container (`curlimages/curl`) issues an authenticated
   POST to `/api/internal/scheduler/{job_key}`.
2. The container reads the shared secret from a Kubernetes `Secret` mounted as
   an environment variable.
3. Concurrency is disabled via `concurrencyPolicy: Forbid` and additional
   database-level `scheduled_job_locks` enforcement.

---

### `scheduler-service-token` Secret

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: dcc-scheduler-service-token
  namespace: dcc
type: Opaque
stringData:
  SCHEDULER_SERVICE_TOKEN: "REPLACE-ME-IN-DEPLOYMENT"  # rotate quarterly
```

---

### CronJob template

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: dcc-{{JOB_KEY_SLUG}}
  namespace: dcc
  labels: { app: dcc-scheduler, job_key: "{{JOB_KEY}}" }
spec:
  schedule: "{{CRON}}"           # See table below
  timeZone: "Australia/Melbourne"
  concurrencyPolicy: Forbid
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 5
  startingDeadlineSeconds: 120
  jobTemplate:
    spec:
      backoffLimit: 0
      ttlSecondsAfterFinished: 3600
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: trigger
              image: curlimages/curl:8.4.0
              env:
                - name: SCHEDULER_SERVICE_TOKEN
                  valueFrom:
                    secretKeyRef:
                      name: dcc-scheduler-service-token
                      key: SCHEDULER_SERVICE_TOKEN
              command: ["/bin/sh", "-c"]
              args:
                - |
                  curl -sS --fail --show-error --max-time 60 \
                    -H "X-Scheduler-Token: $SCHEDULER_SERVICE_TOKEN" \
                    -X POST https://dcc.internal/api/internal/scheduler/{{JOB_KEY}} \
                  || (echo "trigger failed" >&2; exit 1)
```

---

### Job schedule reference (must match `scheduled_job_definitions`)

| Job key                              | Cron        | Notes                             |
|--------------------------------------|-------------|-----------------------------------|
| notifications.dispatch               | */5 * * * * | Push pending deliveries           |
| notifications.retry                  | */10 * * * *| Reactivate expired retry windows  |
| notifications.dead_letter            | 0 * * * *   | Dead-letter reconciliation        |
| notifications.escalation             | */15 * * * *| Escalation scan (deduped)         |
| numbering.reservation_expiry         | */5 * * * * | Expire numbering reservations     |
| numbering.reconciliation             | 0 1 * * *   | Daily numbering reconciliation    |
| activation.recalculation             | 0 * * * *   | Hourly activation recalc          |
| activation.override_expiry           | 0 * * * *   | Override expiry sweep             |
| storage.reconciliation               | 0 2 * * *   | Daily storage reconciliation      |
| storage.checksum_verification        | 0 3 * * *   | Checksum verification             |
| storage.retention_review             | 0 4 * * *   | Report-only retention review      |
| migration.status_reconciliation      | 0 * * * *   | Migration status                  |
| migration.backfill_reconciliation    | 0 2 * * *   | Backfill reconciliation           |
| migration.stale_approval_expiry      | */30 * * * *| Expire stale approvals            |
| documents.review_reminders           | 0 9 * * *   | Daily Under-Review reminders      |
| compliance.scan                      | 0 * * * *   | Hourly compliance scan            |

---

### Rollout notes

- `SCHEDULER_ENABLED=true` must be set on the API pod.
- Restrict callers with `SCHEDULER_ALLOWED_IPS` (comma-separated).
- Rotate `SCHEDULER_SERVICE_TOKEN` quarterly. All CronJobs remount on rotation.
- Alerts should fire when any CronJob's last `Succeeded` timestamp is older
  than 2× its schedule interval (Prometheus + `kube_cronjob_status_last_successful_time`).
