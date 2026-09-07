"""EB-17a · Security Foundation tests.

Deterministic. Local-only — hits the supervisor-managed uvicorn on
http://localhost:8001/api directly, NOT the external preview URL. No
Cloudflare in the path.

No conditional skips.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict

from dotenv import load_dotenv

# Load backend/.env so JWT_SECRET / MONGO_URL / DB_NAME are available
# to the test process without requiring pytest env inheritance.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import pytest
import requests
from pymongo import MongoClient


# Local uvicorn — never the external Cloudflare-fronted preview URL.
API = "http://localhost:8001/api"


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════
def _login(email: str, password: str) -> Dict[str, str]:
    r = requests.post(f"{API}/auth/login",
                      json={"email": email, "password": password}, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════
@pytest.fixture(scope="module")
def admin_headers():
    return _login("admin@acedriverhub.com", "Admin@123")


@pytest.fixture(scope="module")
def readonly_headers():
    return _login("readonly.qa@acedriverhub.com", "ReadOnly@123")


@pytest.fixture(scope="module")
def manager_headers(admin_headers):
    email = f"eb17a.manager.{uuid.uuid4().hex[:8]}@acedriverhub.com"
    r = requests.post(f"{API}/auth/register", headers=admin_headers, json={
        "email": email, "password": "Manager@123",
        "full_name": "EB17a Manager", "role": "Manager"}, timeout=30)
    r.raise_for_status()
    return _login(email, "Manager@123")


@pytest.fixture(scope="module")
def compliance_headers(admin_headers):
    email = f"eb17a.comp.{uuid.uuid4().hex[:8]}@acedriverhub.com"
    r = requests.post(f"{API}/auth/register", headers=admin_headers, json={
        "email": email, "password": "Compliance@123",
        "full_name": "EB17a Compliance", "role": "Compliance"}, timeout=30)
    r.raise_for_status()
    return _login(email, "Compliance@123")


# ═══════════════════════════════════════════════════════════════════════
# 1. Control catalogue seeded idempotently (Part 1)
# ═══════════════════════════════════════════════════════════════════════
class TestControlCatalogue:
    def test_controls_seeded(self, admin_headers):
        r = requests.get(f"{API}/security/controls", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        controls = r.json()
        keys = {c["control_key"] for c in controls}
        for k in ("auth.bcrypt_cost_min", "auth.jwt_expiry_bounded",
                  "auth.jwt_secret_strength", "auth.jwt_type_check",
                  "auth.admin_password_not_default", "auth.password_hash_present",
                  "rbac.role_gate_present", "rbac.readonly_not_writable",
                  "rbac.permission_matrix_complete",
                  "api.auth_required_coverage",
                  "api.cors_not_wildcard_in_prod",
                  "api.unsafe_verb_role_gated",
                  "env.required_keys_present",
                  "env.secret_leak_in_config_endpoint",
                  "env.storage_backend_declared",
                  "data.pii_inventory_present",
                  "data.restricted_field_gated",
                  "audit.append_only_collections_declared",
                  "audit.security_events_immutable"):
            assert k in keys, f"missing control: {k}"

    def test_seed_is_idempotent(self, admin_headers):
        from security_module import CONTROLS
        r = requests.get(f"{API}/security/controls", headers=admin_headers, timeout=30)
        assert len(r.json()) == len(CONTROLS)


# ═══════════════════════════════════════════════════════════════════════
# 2. Assessment engine (Part 2)
# ═══════════════════════════════════════════════════════════════════════
class TestAssessmentEngine:
    def test_run_assessment_authorised(self, admin_headers):
        r = requests.post(f"{API}/security/assessments", headers=admin_headers,
                          json={}, timeout=60)
        assert r.status_code == 200
        body = r.json()
        assert body["overall_result"] in ("PASS", "PASS_WITH_WARNINGS", "FAIL")
        assert "findings_by_severity" in body
        assert body["route_count"] > 100
        assert body["_source"] == "seed-eb17a"

    def test_readonly_cannot_run(self, readonly_headers):
        r = requests.post(f"{API}/security/assessments", headers=readonly_headers,
                          json={}, timeout=30)
        assert r.status_code == 403

    def test_idempotent_by_correlation_id(self, admin_headers):
        corr = f"eb17a-test-{uuid.uuid4()}"
        r1 = requests.post(f"{API}/security/assessments", headers=admin_headers,
                           json={"correlation_id": corr}, timeout=60)
        r2 = requests.post(f"{API}/security/assessments", headers=admin_headers,
                           json={"correlation_id": corr}, timeout=60)
        assert r1.status_code == r2.status_code == 200
        assert r1.json()["security_assessment_run_id"] == r2.json()["security_assessment_run_id"]

    def test_findings_endpoint(self, admin_headers):
        run = requests.post(f"{API}/security/assessments", headers=admin_headers,
                            json={}, timeout=60).json()
        rid = run["security_assessment_run_id"]
        r = requests.get(f"{API}/security/assessments/{rid}/findings",
                         headers=admin_headers, timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_status_summary(self, admin_headers):
        r = requests.get(f"{API}/security/status", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert "last_assessment" in body
        assert body["controls_count"] >= 19


# ═══════════════════════════════════════════════════════════════════════
# 3. Authentication + Session hardening checks (Part 3)
# ═══════════════════════════════════════════════════════════════════════
class TestAuthSession:
    def test_jwt_secret_strong(self):
        assert len(os.environ["JWT_SECRET"]) >= 32

    def test_no_critical_auth_findings(self, admin_headers):
        run = requests.post(f"{API}/security/assessments", headers=admin_headers,
                            json={}, timeout=60).json()
        rid = run["security_assessment_run_id"]
        r = requests.get(f"{API}/security/assessments/{rid}/findings",
                         headers=admin_headers,
                         params={"severity": "Critical"}, timeout=30)
        for f in r.json():
            assert not f["control_key"].startswith("auth."), \
                f"unexpected Critical auth finding: {f}"

    def test_bcrypt_cost_control_defined(self, admin_headers):
        r = requests.get(f"{API}/security/controls", headers=admin_headers, timeout=30)
        keys = {c["control_key"] for c in r.json()}
        assert "auth.bcrypt_cost_min" in keys


# ═══════════════════════════════════════════════════════════════════════
# 4. RBAC audit + complete permission matrix (Part 4)
# ═══════════════════════════════════════════════════════════════════════
class TestRBACPermissionMatrix:
    def test_permission_matrix_generated(self, admin_headers):
        r = requests.get(f"{API}/security/permission-matrix",
                         headers=admin_headers, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert set(body["roles"]) == {"ReadOnly", "Allocator", "Compliance",
                                       "Manager", "Admin"}
        assert len(body["routes"]) > 100
        for row in body["routes"]:
            assert row["path"].startswith("/api")

    def test_no_write_route_grants_readonly(self, admin_headers):
        run = requests.post(f"{API}/security/assessments", headers=admin_headers,
                            json={}, timeout=60).json()
        rid = run["security_assessment_run_id"]
        r = requests.get(f"{API}/security/assessments/{rid}/findings",
                         headers=admin_headers,
                         params={"control_key": "rbac.readonly_not_writable"},
                         timeout=30)
        assert r.json() == [], f"ReadOnly-accepted write routes: {r.json()}"

    def test_all_write_routes_gated(self, admin_headers):
        run = requests.post(f"{API}/security/assessments", headers=admin_headers,
                            json={}, timeout=60).json()
        rid = run["security_assessment_run_id"]
        r = requests.get(f"{API}/security/assessments/{rid}/findings",
                         headers=admin_headers,
                         params={"control_key": "rbac.role_gate_present"},
                         timeout=30)
        assert r.json() == [], f"Ungated write routes: {r.json()}"

    def test_compliance_can_read_matrix(self, compliance_headers):
        r = requests.get(f"{API}/security/permission-matrix",
                         headers=compliance_headers, timeout=30)
        assert r.status_code == 200

    def test_allocator_cannot_read_matrix(self, admin_headers):
        email = f"eb17a.alloc.{uuid.uuid4().hex[:8]}@acedriverhub.com"
        requests.post(f"{API}/auth/register", headers=admin_headers, json={
            "email": email, "password": "Allocator@123",
            "full_name": "EB17a Allocator", "role": "Allocator"}, timeout=30).raise_for_status()
        alloc = _login(email, "Allocator@123")
        r = requests.get(f"{API}/security/permission-matrix", headers=alloc, timeout=30)
        assert r.status_code == 403


# ═══════════════════════════════════════════════════════════════════════
# 5. API security (Part 5)
# ═══════════════════════════════════════════════════════════════════════
class TestAPISecurity:
    def test_no_unauth_write_route(self, admin_headers):
        run = requests.post(f"{API}/security/assessments", headers=admin_headers,
                            json={}, timeout=60).json()
        rid = run["security_assessment_run_id"]
        r = requests.get(f"{API}/security/assessments/{rid}/findings",
                         headers=admin_headers,
                         params={"control_key": "api.auth_required_coverage"},
                         timeout=30)
        assert r.json() == [], f"Unauthenticated routes: {r.json()}"

    def test_no_unsafe_verb_gap(self, admin_headers):
        run = requests.post(f"{API}/security/assessments", headers=admin_headers,
                            json={}, timeout=60).json()
        rid = run["security_assessment_run_id"]
        r = requests.get(f"{API}/security/assessments/{rid}/findings",
                         headers=admin_headers,
                         params={"control_key": "api.unsafe_verb_role_gated"},
                         timeout=30)
        assert r.json() == [], f"Unsafe verb without gate: {r.json()}"

    def test_login_is_public(self):
        r = requests.post(f"{API}/auth/login",
                          json={"email": "nobody@example.com", "password": "wrong"},
                          timeout=30)
        assert r.status_code in (401, 400)


# ═══════════════════════════════════════════════════════════════════════
# 6. Secrets / environment validation (Part 6)
# ═══════════════════════════════════════════════════════════════════════
class TestSecretsEnv:
    def test_configuration_status_never_leaks_values(self, admin_headers):
        r = requests.get(f"{API}/security/configuration-status",
                         headers=admin_headers, timeout=30)
        assert r.status_code == 200
        body = r.json()
        cfg = body["configuration"]
        assert cfg["jwt_secret_configured"] in (True, False)
        assert isinstance(cfg["jwt_secret_length"], int)
        assert "JWT_SECRET" not in cfg
        assert body["leaked_keys"] == []

    def test_configuration_status_manager_only(self, compliance_headers):
        r = requests.get(f"{API}/security/configuration-status",
                         headers=compliance_headers, timeout=30)
        assert r.status_code == 403

    def test_scrubber_redacts_secret_shaped_string(self):
        from security_module import _scrub_config_status
        safe, leaked = _scrub_config_status({"api_key": "abcdef123456789",
                                             "safe_flag": True})
        assert "api_key" in leaked
        assert safe["api_key"] == "[REDACTED]"
        assert safe["safe_flag"] is True

    def test_scrubber_ignores_booleans_and_ints(self):
        from security_module import _scrub_config_status
        _, leaked = _scrub_config_status({"jwt_secret_configured": True,
                                          "jwt_secret_length": 64,
                                          "webhooks_enabled": False})
        assert leaked == []


# ═══════════════════════════════════════════════════════════════════════
# 7. Privacy / sensitive-data audit (Part 7)
# ═══════════════════════════════════════════════════════════════════════
class TestPrivacy:
    def test_pii_inventory_returned(self, compliance_headers):
        r = requests.get(f"{API}/security/data-classification",
                         headers=compliance_headers, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body["fields"], list)
        assert len(body["fields"]) >= 10
        collections = {f["collection"] for f in body["fields"]}
        for c in ("drivers", "owners", "users", "documents"):
            assert c in collections

    def test_restricted_field_gating_still_intact(self, admin_headers):
        run = requests.post(f"{API}/security/assessments", headers=admin_headers,
                            json={}, timeout=60).json()
        rid = run["security_assessment_run_id"]
        r = requests.get(f"{API}/security/assessments/{rid}/findings",
                         headers=admin_headers,
                         params={"control_key": "data.restricted_field_gated"},
                         timeout=30)
        assert r.json() == []


# ═══════════════════════════════════════════════════════════════════════
# 8. Audit-log integrity (Part 8)
# ═══════════════════════════════════════════════════════════════════════
class TestAuditIntegrity:
    def test_audit_integrity_endpoint(self, compliance_headers):
        r = requests.get(f"{API}/security/audit-integrity",
                         headers=compliance_headers, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body["worst_status"] in ("OK", "TAMPERED")
        assert len(body["collections"]) >= 5

    def test_security_events_immutable(self, admin_headers):
        db_ = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        before = list(db_["security_assessment_events"].find({}, {"_id": 0}))
        requests.post(f"{API}/security/assessments", headers=admin_headers,
                      json={}, timeout=60).raise_for_status()
        after = list(db_["security_assessment_events"].find({}, {"_id": 0}))
        assert len(after) >= len(before)
        for row in after:
            assert "updated_at" not in row


# ═══════════════════════════════════════════════════════════════════════
# 9. Security exception workflow (Part 9)
# ═══════════════════════════════════════════════════════════════════════
class TestExceptionWorkflow:
    def _make_request(self, headers, control_key="auth.admin_password_not_default"):
        r = requests.post(f"{API}/security/exceptions", headers=headers, json={
            "control_key": control_key,
            "reason": "Documented dev-preview finding — kept intentionally.",
            "risk_acknowledgement": "Risk understood, isolated to preview only.",
            "requested_days": 7,
        }, timeout=30)
        r.raise_for_status()
        return r.json()

    def test_manager_can_request(self, manager_headers):
        exc = self._make_request(manager_headers)
        assert exc["status"] == "Pending"
        assert exc["control_key"] == "auth.admin_password_not_default"

    def test_readonly_cannot_request(self, readonly_headers):
        r = requests.post(f"{API}/security/exceptions", headers=readonly_headers,
                          json={"control_key": "auth.admin_password_not_default",
                                "reason": "abc" * 5,
                                "risk_acknowledgement": "xyz" * 5,
                                "requested_days": 1}, timeout=30)
        assert r.status_code == 403

    def test_unknown_control_rejected(self, manager_headers):
        r = requests.post(f"{API}/security/exceptions", headers=manager_headers,
                          json={"control_key": "not.a.real.control",
                                "reason": "abc" * 5,
                                "risk_acknowledgement": "xyz" * 5,
                                "requested_days": 1}, timeout=30)
        assert r.status_code == 400

    def test_requester_cannot_self_approve(self, manager_headers):
        exc = self._make_request(manager_headers)
        r = requests.post(
            f"{API}/security/exceptions/{exc['security_exception_request_id']}/approve",
            headers=manager_headers, json={}, timeout=30)
        assert r.status_code == 403

    def test_admin_can_approve(self, manager_headers, admin_headers):
        exc = self._make_request(manager_headers)
        r = requests.post(
            f"{API}/security/exceptions/{exc['security_exception_request_id']}/approve",
            headers=admin_headers, json={"note": "approved for preview"}, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "Approved"
        assert body["approved_by"] == "admin@acedriverhub.com"
        assert body["expires_at"] is not None

    def test_approve_then_revoke(self, manager_headers, admin_headers):
        exc = self._make_request(manager_headers)
        eid = exc["security_exception_request_id"]
        requests.post(f"{API}/security/exceptions/{eid}/approve",
                      headers=admin_headers, json={}, timeout=30).raise_for_status()
        r = requests.post(f"{API}/security/exceptions/{eid}/revoke",
                          headers=admin_headers, json={"note": "reversal"}, timeout=30)
        assert r.status_code == 200
        assert r.json()["status"] == "Revoked"

    def test_approve_from_wrong_state_rejected(self, manager_headers, admin_headers):
        exc = self._make_request(manager_headers)
        eid = exc["security_exception_request_id"]
        requests.post(f"{API}/security/exceptions/{eid}/approve",
                      headers=admin_headers, json={}, timeout=30).raise_for_status()
        r = requests.post(f"{API}/security/exceptions/{eid}/approve",
                          headers=admin_headers, json={}, timeout=30)
        assert r.status_code == 400

    def test_reject_flow(self, manager_headers, admin_headers):
        exc = self._make_request(manager_headers)
        eid = exc["security_exception_request_id"]
        r = requests.post(f"{API}/security/exceptions/{eid}/reject",
                          headers=admin_headers, json={"note": "declined"}, timeout=30)
        assert r.status_code == 200
        assert r.json()["status"] == "Rejected"

    def test_critical_control_requires_admin_approver(self, manager_headers, admin_headers):
        r = requests.post(f"{API}/security/exceptions", headers=manager_headers,
                          json={"control_key": "auth.jwt_secret_strength",
                                "reason": "Documented risk under review.",
                                "risk_acknowledgement": "Ack — dev preview only.",
                                "requested_days": 3}, timeout=30)
        r.raise_for_status()
        eid = r.json()["security_exception_request_id"]
        # Create a second Manager to attempt approval (requester ≠ approver).
        email = f"eb17a.mgr2.{uuid.uuid4().hex[:8]}@acedriverhub.com"
        requests.post(f"{API}/auth/register", headers=admin_headers, json={
            "email": email, "password": "Manager@123",
            "full_name": "EB17a Mgr2", "role": "Manager"}, timeout=30).raise_for_status()
        mgr2 = _login(email, "Manager@123")
        deny = requests.post(f"{API}/security/exceptions/{eid}/approve",
                             headers=mgr2, json={}, timeout=30)
        assert deny.status_code == 403

    def test_expire_due_is_admin_only(self, manager_headers):
        r = requests.post(f"{API}/security/exceptions/expire-due",
                          headers=manager_headers, timeout=30)
        assert r.status_code == 403

    def test_expire_due_admin_ok(self, admin_headers):
        r = requests.post(f"{API}/security/exceptions/expire-due",
                          headers=admin_headers, timeout=30)
        assert r.status_code == 200
        assert "expired" in r.json()

    def test_get_exception_returns_approvals(self, manager_headers, admin_headers):
        exc = self._make_request(manager_headers)
        eid = exc["security_exception_request_id"]
        requests.post(f"{API}/security/exceptions/{eid}/approve",
                      headers=admin_headers, json={"note": "audit trail"},
                      timeout=30).raise_for_status()
        r = requests.get(f"{API}/security/exceptions/{eid}",
                         headers=admin_headers, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "Approved"
        actions = [a["action"] for a in body["approvals"]]
        assert "Requested" in actions
        assert "Approved" in actions


# ═══════════════════════════════════════════════════════════════════════
# EB-17a expiry lifecycle — deterministic direct evidence
# (Fictional local fixtures only; no external network; no conditional skips.)
# ═══════════════════════════════════════════════════════════════════════
class TestExceptionExpiryLifecycle:
    """Proves the exception expiry contract end-to-end:
      1. approved exception with elapsed TTL → status "Expired"
      2. linked blocker/finding reactivates (control_key not suppressed)
      3. expired exception no longer affects the security assessment result
      4. requester self-approval remains denied
    """

    CONTROL_KEY = "auth.admin_password_not_default"

    @pytest.fixture(autouse=True)
    def _purge_prior_approvals(self):
        """Ensure no leftover Approved/Pending exception from earlier test
        classes suppresses our control during the lifecycle baseline."""
        db_ = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        db_["security_exception_requests"].delete_many(
            {"control_key": self.CONTROL_KEY,
             "status": {"$in": ["Approved", "Pending"]}})
        yield

    def _db(self):
        return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

    def _create_and_approve(self, manager_headers, admin_headers):
        r = requests.post(f"{API}/security/exceptions", headers=manager_headers, json={
            "control_key": self.CONTROL_KEY,
            "reason": "Deterministic expiry-lifecycle fixture (fictional).",
            "risk_acknowledgement": "Ack: fictional test-only exception.",
            "requested_days": 7,
        }, timeout=30)
        r.raise_for_status()
        eid = r.json()["security_exception_request_id"]
        requests.post(f"{API}/security/exceptions/{eid}/approve",
                      headers=admin_headers, json={},
                      timeout=30).raise_for_status()
        return eid

    def _back_date_expiry(self, eid: str):
        """Set expires_at to one day in the past — the ONLY mutation the
        test performs directly on Mongo, to simulate wall-clock elapse
        without a sleep."""
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        self._db()["security_exception_requests"].update_one(
            {"security_exception_request_id": eid},
            {"$set": {"expires_at": past}},
        )

    # 4. Requester self-approval denied (re-asserted at the top of the
    # lifecycle so failure surfaces here if a regression flips it).
    def test_requester_self_approval_denied(self, manager_headers):
        r = requests.post(f"{API}/security/exceptions", headers=manager_headers, json={
            "control_key": self.CONTROL_KEY,
            "reason": "Same-actor approval attempt (fictional).",
            "risk_acknowledgement": "Ack fictional.",
            "requested_days": 3,
        }, timeout=30)
        r.raise_for_status()
        eid = r.json()["security_exception_request_id"]
        deny = requests.post(f"{API}/security/exceptions/{eid}/approve",
                             headers=manager_headers, json={}, timeout=30)
        assert deny.status_code == 403

    # 1. Approved + elapsed TTL → "Expired"
    def test_approved_with_elapsed_ttl_becomes_expired(self,
                                                        manager_headers, admin_headers):
        eid = self._create_and_approve(manager_headers, admin_headers)
        self._back_date_expiry(eid)
        # invoke sweep
        r = requests.post(f"{API}/security/exceptions/expire-due",
                          headers=admin_headers, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert eid in body["expired"]
        # verify persisted state
        db_ = self._db()
        row = db_["security_exception_requests"].find_one(
            {"security_exception_request_id": eid}, {"_id": 0})
        assert row["status"] == "Expired"
        assert row.get("expired_at") is not None
        # append-only audit row exists
        actions = list(db_["security_exception_approvals"].find(
            {"security_exception_request_id": eid}, {"_id": 0, "action": 1}))
        assert any(a["action"] == "Expired" for a in actions)

    # 2. Expiry reactivates the linked blocker/finding
    #    (control_key is no longer suppressed in the next assessment)
    def test_expiry_reactivates_linked_blocker(self,
                                                 manager_headers, admin_headers):
        # Baseline assessment
        run0 = requests.post(f"{API}/security/assessments", headers=admin_headers,
                             json={}, timeout=60).json()
        finds0 = requests.get(
            f"{API}/security/assessments/{run0['security_assessment_run_id']}/findings",
            headers=admin_headers,
            params={"control_key": self.CONTROL_KEY}, timeout=30).json()
        baseline_open = [f for f in finds0 if f["status"] == "Open"]
        assert baseline_open, \
            f"Fixture control {self.CONTROL_KEY} must currently produce a finding"

        # Approve exception; new assessment → finding suppressed
        eid = self._create_and_approve(manager_headers, admin_headers)
        run1 = requests.post(f"{API}/security/assessments", headers=admin_headers,
                             json={}, timeout=60).json()
        finds1 = requests.get(
            f"{API}/security/assessments/{run1['security_assessment_run_id']}/findings",
            headers=admin_headers,
            params={"control_key": self.CONTROL_KEY}, timeout=30).json()
        suppressed = [f for f in finds1 if f["status"] == "Suppressed"]
        assert suppressed, "Approved exception must suppress the linked finding"
        assert suppressed[0]["suppressed_by_exception_id"] == eid

        # Expire the exception; new assessment → finding OPEN again
        self._back_date_expiry(eid)
        requests.post(f"{API}/security/exceptions/expire-due",
                      headers=admin_headers, timeout=30).raise_for_status()
        run2 = requests.post(f"{API}/security/assessments", headers=admin_headers,
                             json={}, timeout=60).json()
        finds2 = requests.get(
            f"{API}/security/assessments/{run2['security_assessment_run_id']}/findings",
            headers=admin_headers,
            params={"control_key": self.CONTROL_KEY}, timeout=30).json()
        reactivated = [f for f in finds2 if f["status"] == "Open"]
        assert reactivated, "Expired exception must reactivate the blocker/finding"

    # 3. Expired exception no longer affects assessment overall_result
    def test_expired_exception_no_longer_affects_result(self,
                                                          manager_headers, admin_headers):
        # Baseline (no active exception on our control)
        base = requests.post(f"{API}/security/assessments", headers=admin_headers,
                             json={}, timeout=60).json()
        base_counts = base["findings_by_severity"]
        base_result = base["overall_result"]

        # Approve exception → suppresses control → non-zero suppressed count
        eid = self._create_and_approve(manager_headers, admin_headers)
        active = requests.post(f"{API}/security/assessments", headers=admin_headers,
                               json={}, timeout=60).json()
        assert active["suppressed_count"] >= 1

        # Expire → next run must match baseline severity distribution
        self._back_date_expiry(eid)
        requests.post(f"{API}/security/exceptions/expire-due",
                      headers=admin_headers, timeout=30).raise_for_status()
        after = requests.post(f"{API}/security/assessments", headers=admin_headers,
                              json={}, timeout=60).json()
        assert after["overall_result"] == base_result
        assert after["findings_by_severity"] == base_counts
        assert after["suppressed_count"] == 0
