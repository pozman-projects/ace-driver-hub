# DCC Scheduler Deployment

**Status:** Reference — **NOT applied**. These files describe how to trigger
the DCC scheduler in a production Kubernetes cluster. Applying is
out-of-scope for this repository; no deploy has been executed and `main`
remains untouched.

Contents:
- `/app/deploy/kubernetes/cronjobs.yaml` — All 16 CronJob manifests plus the
  supporting `ConfigMap`. Uses `secretKeyRef` to read
  `SCHEDULER_SERVICE_TOKEN` from a Kubernetes `Secret`. No secret values
  are inlined.
- (This file) — Rollout, rotation, and DST guidance.

## Why external cron?

The DCC API pod is stateless and does NOT run a permanent in-process cron
loop. Periodicity comes entirely from Kubernetes CronJobs, giving us:

- HA safety (multi-replica API pods without duplicate execution).
- Full audit of each trigger via K8s job history.
- Independent scaling — the API stays lean, cron pods spin up on demand.
- Strong isolation from application errors — a crashed API pod does not
  silently drop scheduled work.

Concurrency is defended twice:

1. `concurrencyPolicy: Forbid` in every CronJob.
2. Database `scheduled_job_locks` unique index on `job_key` (10-minute TTL
   via `SCHEDULER_LOCK_TTL_SECONDS`).

## Prerequisites

- Kubernetes ≥ 1.25 (needed for `spec.timeZone`).
- Namespace `dcc` (adjust to match your cluster).
- API service reachable at the URL configured in the
  `dcc-scheduler-endpoint` ConfigMap.
- A `dcc-scheduler-service-token` Secret containing
  `SCHEDULER_SERVICE_TOKEN` (≥ 32 random bytes, base64).

Sample secret (do NOT commit real values):

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: dcc-scheduler-service-token
  namespace: dcc
type: Opaque
stringData:
  SCHEDULER_SERVICE_TOKEN: "PLACEHOLDER-ROTATE-QUARTERLY"
```

## Rollout (whenever you decide to apply)

1. Create the namespace and secret out-of-band (`kubectl create -n dcc …`).
2. Confirm the API pod has:
   - `SCHEDULER_ENABLED=true`
   - `SCHEDULER_SERVICE_TOKEN=<matches the secret>`
   - (Optional) `SCHEDULER_ALLOWED_IPS` with the cluster egress CIDRs.
3. `kubectl apply -f /app/deploy/kubernetes/cronjobs.yaml`.
4. Verify: `kubectl get cronjob -n dcc` — 16 CronJobs, all `SUSPEND=false`.
5. Wait one cycle; check `kubectl get jobs -n dcc` — recent Jobs
   `Succeeded`, none pending.
6. Verify inside DCC: log in as Admin → `/administration/automation` →
   Recent Runs should show `Scheduler`-triggered runs with `Completed`
   status.

## Token rotation (quarterly)

1. Generate a new token: `openssl rand -base64 48`.
2. Patch the secret in-place: `kubectl create secret generic
   dcc-scheduler-service-token --from-literal=SCHEDULER_SERVICE_TOKEN=… -n
   dcc -o yaml --dry-run=client | kubectl apply -f -`.
3. Update the API pod env (rolling restart).
4. Confirm at least one CronJob triggers successfully after rotation.

## Timezone & DST handling

- The manifests use `spec.timeZone: "Australia/Melbourne"`. On DST
  transitions this preserves local business time (e.g. `0 9 * * *` remains
  9 a.m. Melbourne local).
- On Kubernetes < 1.25 (no `spec.timeZone` support) OR clusters that
  centralise TZ in UTC:
  1. Remove the `timeZone:` key from every CronJob.
  2. Convert each schedule to UTC (Melbourne is UTC+10 in AEST, UTC+11 in
     AEDT — pick one, be explicit).
  3. Document the DST-drift in your on-call runbook. Alerts on
     `kube_cronjob_status_last_successful_time` older than 2× interval
     will still catch missed runs; local time will drift 1h twice a year.
- The `notifications.escalation` quiet-hours logic is enforced INSIDE the
  API using `zoneinfo("Australia/Melbourne")` and is independent of the
  cron schedule's timezone — no double-DST hazard.

## Monitoring

Recommended Prometheus alerts:

- `kube_cronjob_status_last_successful_time` older than 2× the schedule
  interval → warning.
- Any Job with `status.failed >= 1` → warning.
- API side (via `/api/automation/status`):
  - `deliveries_dead_letter > 20` → warning.
  - `recent_failed_runs > 10` → warning.

## Do-not-do

- ❌ Never inline the scheduler token into a CronJob env value.
- ❌ Never point CronJobs at the internet-facing URL; use the cluster-local
  service (`http://dcc-api.dcc.svc.cluster.local` if possible).
- ❌ Never disable `concurrencyPolicy: Forbid` — even with DB locks, doubled
  triggers waste connections and create noise.
- ❌ Never remove the `activeDeadlineSeconds` — a wedged curl process would
  eat pod slots.
