# EB-18 Monitoring Runbook
Record monitoring snapshots via `POST /api/go-live/runs/{id}/monitoring`.
Overall state is derived:
- **Critical**: application_health=Critical OR provider_circuits=Critical OR integrity_findings>0 OR security_findings>0 OR uat_defects_post_cutover>0 OR migration_failures>0.
- **Warning**: api_error_rate>1% OR auth_failures>0 OR failed_jobs>0 OR notification_failures>0 OR dead_letters>0 OR webhook_failures>0.
- **Healthy**: none of the above.
Monitoring window duration is *fictional/test* only in EB-18.
