# EB-17a — Security Foundation · Requirement Matrix

Generated: Feb 2026
Status: ✅ COMPLETE — 0 failed, 0 MISSING, 0 DEFERRED
Backend suite: **589 passed, 1 skipped, 0 failed** in 6m 18s
Frontend: 1 screenshot smoke-test with all tabs live

## Coverage (Parts 1–9)

| # | Part | Deliverable | Backend Artefact | Test Artefact | UI | Status |
|---|------|-------------|------------------|---------------|----|--------|
| 1 | Security Control Centre backing | 7 collections + control catalogue seeded idempotently | `security_module.py:CONTROLS`, `ensure_indexes()`, `SecurityService.seed_controls()` | `TestControlCatalogue::test_controls_seeded`, `test_seed_is_idempotent` | `/administration/security` — Controls tab | ✅ |
| 2 | Security assessment engine | Idempotent run + posture/findings/snapshot persistence | `SecurityService.run_assessment` (correlation_id keyed) | `TestAssessmentEngine` (5 tests) | Overview + Assessment Findings tabs | ✅ |
| 3 | Auth & session hardening | bcrypt cost, JWT secret strength/TTL/type-claim, admin default-password Warning | `_check_auth_session()` | `TestAuthSession` (3 tests) | Overview posture tile | ✅ |
| 4 | RBAC audit + Permission Matrix | Route-level role gate extraction (3-level delegation-aware); complete matrix per verb | `build_route_inventory`, `_check_rbac`, `_extract_role_gate_from_endpoint` | `TestRBACPermissionMatrix` (5 tests) | Permission Matrix tab (200+ routes × 5 roles) | ✅ |
| 5 | API security validation | auth-required coverage, CORS wildcard-in-prod, unsafe verb gating | `_check_api` + PUBLIC allowlist | `TestAPISecurity` (3 tests) | Findings tab | ✅ |
| 6 | Secrets / env validation | Required env keys, secret-shaped scrubber that ignores booleans/lengths | `_current_configuration_snapshot`, `_scrub_config_status` | `TestSecretsEnv` (4 tests) | Overview — Configuration Status card (Manager+) | ✅ |
| 7 | Privacy / sensitive-data audit | 13-field PII inventory, restricted-field gating check | `PII_INVENTORY`, `_check_privacy` | `TestPrivacy` (2 tests) | Data Classification tab | ✅ |
| 8 | Audit-log integrity | 13 append-only collections declared; tamper detection via `updated_at` sentinel | `APPEND_ONLY_COLLECTIONS`, `_check_audit`, `/security/audit-integrity` | `TestAuditIntegrity` (2 tests) | Audit Integrity tab | ✅ |
| 9 | Security exception workflow | Request → Approve/Reject → Expire/Revoke, requester ≠ approver, Critical→Admin | `ExceptionService`, `/security/exceptions/*` | `TestExceptionWorkflow` (11 tests) | Exceptions tab (approve/reject/revoke) | ✅ |

## Data Model (7 new collections, all indexed & append-only where required)

| Collection | Purpose | Immutable |
|-----------|---------|-----------|
| `security_control_definitions` | Catalogue of 19 controls | – |
| `security_assessment_runs` | Each assessment execution + overall_result | – |
| `security_assessment_findings` | Individual finding per run × control | – |
| `security_assessment_events` | Append-only run/event audit | ✅ |
| `security_configuration_snapshots` | Sanitised config at run time | ✅ |
| `security_exception_requests` | Exception state machine | – |
| `security_exception_approvals` | Append-only approval trail | ✅ |

## New API Surface (14 endpoints, all under `/api/security/*`)

| Method | Path | Min Role |
|--------|------|----------|
| GET | `/security/status` | ReadOnly |
| GET | `/security/controls` | ReadOnly |
| POST | `/security/assessments` | Manager |
| GET | `/security/assessments` | ReadOnly |
| GET | `/security/assessments/{run_id}` | ReadOnly |
| GET | `/security/assessments/{run_id}/findings` | ReadOnly |
| GET | `/security/configuration-status` | Manager |
| GET | `/security/permission-matrix` | Compliance |
| GET | `/security/data-classification` | Compliance |
| GET | `/security/audit-integrity` | Compliance |
| POST | `/security/exceptions` | Manager |
| GET | `/security/exceptions` | Compliance |
| GET | `/security/exceptions/{id}` | Compliance |
| POST | `/security/exceptions/{id}/approve` | Manager (Admin for Critical) |
| POST | `/security/exceptions/{id}/reject` | Manager |
| POST | `/security/exceptions/{id}/revoke` | Manager |
| POST | `/security/exceptions/expire-due` | Admin |

## Pre-existing gaps closed while hardening

| File | Endpoint | Change |
|------|----------|--------|
| `activation_module.py` | `POST /drivers/{driver_id}/activation/recalculate` | Now Allocator+ |
| `imports_module.py` | `POST /imports/{job_id}/inspect|mapping|validate` | Now Allocator+ |
| `notifications_module.py` | `PUT /notifications/{notification_id}/read` | ReadOnly denied |

## Frontend

- Route: `/administration/security` (protected)
- Component: `SecurityControlCentre.jsx` (7 tabs, role-gated actions, exception modal)
- Hub tile: `data-testid="security-hub-card"`

## Test Constraints Honoured

- ✅ Local test client only — `http://localhost:8001/api`. No preview URL in `test_security_eb17.py`.
- ✅ No conditional skips.
- ✅ Fictional/sanitised data only.
- ✅ No live cron, no real providers.
- ✅ `main` untouched; no deploy; no GitHub push.

## Final Backend Result

```
589 passed, 1 skipped, 0 failed
Duration: 6m 18s
Latest run log: /tmp/eb17a_FINAL4.log
```
