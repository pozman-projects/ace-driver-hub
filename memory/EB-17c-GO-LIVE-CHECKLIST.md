# EB-17c — Go-Live Checklist

Version: `dcc-phase2-eb17c`.

Each row is seeded into `production_readiness_checklist` with a `kind`:
- `human` — an operator or approver must click Complete (or Waive with
  evidence) via the dashboard.
- `system` — computed from live gate state; never manually mutable.

| # | ID | Item | Kind | Owner (default) |
| - | -- | ---- | ---- | -- |
| 1  | `pe.env`          | Production environment created                       | human  | Platform |
| 2  | `pe.secrets`      | Secrets loaded via approved mechanism                | human  | Security |
| 3  | `pe.db_backup`    | Database backup verified                             | human  | Recovery |
| 4  | `pe.storage`      | Object storage verified                              | human  | Platform |
| 5  | `pe.prod_cfg`     | Production configuration validated                   | human  | Platform |
| 6  | `pe.cors`         | CORS validated                                       | human  | Platform |
| 7  | `pe.tls`          | TLS validated                                        | human  | Platform |
| 8  | `pe.sched_token`  | Scheduler token loaded                               | human  | Platform |
| 9  | `pe.provider_off` | Provider credentials loaded but disabled             | human  | Security |
| 10 | `pe.webhook_off`  | Webhook secrets loaded but callbacks disabled        | human  | Security |
| 11 | `pe.outbox`       | Development Outbox confirmed                         | human  | Ops      |
| 12 | `pe.mig_pkg`      | Migration package approved                           | human  | Migration (Admin) |
| 13 | `pe.rollback_pkg` | Rollback package verified                            | human  | Recovery |
| 14 | `pe.mig_ops`      | Migration operators assigned                         | human  | Migration (Admin) |
| 15 | `pe.support`      | Support contacts recorded                            | human  | Ops      |
| 16 | `pe.escalation`   | Escalation contacts recorded                         | human  | Ops      |
| 17 | `pe.monitor`      | Monitoring enabled                                   | human  | Platform |
| 18 | `pe.audit_log`    | Audit logging enabled                                | human  | Security |
| 19 | `pe.backup_sched` | Backup schedule configured                           | human  | Recovery |
| 20 | `pe.first_reh`    | First restore rehearsal scheduled                    | human  | Recovery |
| 21 | `pe.uat_ok`       | UAT approvals complete                               | system | *derived* |
| 22 | `pe.int_gate`     | Integrity gate PASS                                  | system | *derived* |
| 23 | `pe.sec_gate`     | Security gate PASS                                   | system | *derived* |
| 24 | `pe.rec_gate`     | Recovery gate PASS                                   | system | *derived* |
| 25 | `pe.final_change` | Final change approval recorded                       | human  | Admin    |

Rules:
- Waivers require evidence.
- History is preserved on every update.
- System-derived items never accept manual writes (`400`).
- Manager+ may update all human items except `pe.final_change`, `pe.mig_pkg`
  and `pe.mig_ops` — which require Admin.
