"""EB-16 · Cross-module Integrity, Operations, Webhooks tests.

Deterministic. No conditional skips. Uses fictional _source='seed-eb16'
fixtures only. No real ACE data.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

BASE = (os.environ.get("REACT_APP_BACKEND_URL")
        or "https://fleet-ops-center-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")


def _login(email, password):
    r = requests.post(f"{API}/auth/login",
                       json={"email": email, "password": password}, timeout=25)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def admin_headers():
    return _login("admin@acedriverhub.com", "Admin@123")


@pytest.fixture(scope="module")
def readonly_headers():
    return _login("readonly.qa@acedriverhub.com", "ReadOnly@123")


def _mongo():
    return AsyncIOMotorClient(MONGO_URL)["ace_driver_hub"]


async def _clear_seed(tag="seed-eb16"):
    db = _mongo()
    try:
        for c in ("drivers", "owners", "vehicles", "equipment_register",
                    "driver_vehicle_assignments",
                    "driver_owner_relationships",
                    "driver_equipment_assignments",
                    "equipment_compliance_records",
                    "driver_activation_records",
                    "driver_activation_overrides",
                    "notification_deliveries", "notifications",
                    "notification_delivery_attempts",
                    "integrity_check_findings", "integrity_check_runs",
                    "scheduled_job_locks", "scheduled_job_runs"):
            try:
                await db[c].delete_many({"_source": tag})
            except Exception: pass
    finally: db.client.close()


@pytest.fixture(autouse=True)
def clean():
    asyncio.run(_clear_seed())
    yield
    asyncio.run(_clear_seed())


# ─────────────────────────────────────────────────────────────────────
# 1. Rehearsal seed
# ─────────────────────────────────────────────────────────────────────
class TestRehearsal:
    def test_seed_creates_all_scenarios(self, admin_headers):
        r = requests.post(f"{API}/rehearsal/eb16/seed", headers=admin_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["drivers"] == 3
        assert body["activations"] == 3
        assert "clean_go" in body["scenarios"]
        assert "conditional_go" in body["scenarios"]
        assert "no_go" in body["scenarios"]
        # Idempotent — running again yields same counts
        r2 = requests.post(f"{API}/rehearsal/eb16/seed", headers=admin_headers)
        assert r2.status_code == 200
        assert r2.json()["drivers"] == 3


# ─────────────────────────────────────────────────────────────────────
# 2. Integrity — targeted rules
# ─────────────────────────────────────────────────────────────────────
def _seed_driver(row):
    async def _do():
        db = _mongo()
        try:
            await db["drivers"].insert_one({**row, "is_archived": False,
                                              "_source": "seed-eb16"})
        finally: db.client.close()
    asyncio.run(_do())


def _seed_activation(row):
    async def _do():
        db = _mongo()
        try:
            await db["driver_activation_records"].insert_one(
                {**row, "is_archived": False, "_source": "seed-eb16"})
        finally: db.client.close()
    asyncio.run(_do())


def _run_integrity(admin_headers, run_type="FullSystem"):
    r = requests.post(f"{API}/integrity/runs",
                       json={"run_type": run_type},
                       headers=admin_headers, timeout=60)
    assert r.status_code == 200, r.text
    return r.json()


class TestIntegrityRegisters:
    def test_duplicate_driver_code(self, admin_headers):
        _seed_driver({"id": "eb16-a1", "driver_code": "DUP-01",
                          "dispatch_number": 501, "status": "Active"})
        _seed_driver({"id": "eb16-a2", "driver_code": "DUP-01",
                          "dispatch_number": 502, "status": "Active"})
        run = _run_integrity(admin_headers, "Registers")
        f = requests.get(f"{API}/integrity/runs/{run['integrity_check_run_id']}/findings",
                          headers=admin_headers).json()
        assert any(x["rule_key"] == "reg.duplicate_driver_code" for x in f)

    def test_duplicate_dispatch(self, admin_headers):
        _seed_driver({"id": "eb16-b1", "driver_code": "X1",
                          "dispatch_number": 777, "status": "Active"})
        _seed_driver({"id": "eb16-b2", "driver_code": "X2",
                          "dispatch_number": 777, "status": "Active"})
        run = _run_integrity(admin_headers, "Registers")
        f = requests.get(f"{API}/integrity/runs/{run['integrity_check_run_id']}/findings",
                          headers=admin_headers).json()
        assert any(x["rule_key"] == "reg.duplicate_dispatch" for x in f)

    def test_reserved_dispatch(self, admin_headers):
        _seed_driver({"id": "eb16-c1", "driver_code": "R0",
                          "dispatch_number": 13, "status": "Active"})
        run = _run_integrity(admin_headers, "Registers")
        f = requests.get(f"{API}/integrity/runs/{run['integrity_check_run_id']}/findings",
                          headers=admin_headers).json()
        assert any(x["rule_key"] == "reg.reserved_dispatch" for x in f)


class TestIntegrityActivation:
    def test_activated_not_ready(self, admin_headers):
        _seed_activation({"driver_activation_id": "eb16-act-x",
                              "driver_id": "eb16-drv-x",
                              "status": "Activated",
                              "readiness_status": "Incomplete"})
        run = _run_integrity(admin_headers, "Activation")
        f = requests.get(f"{API}/integrity/runs/{run['integrity_check_run_id']}/findings",
                          headers=admin_headers).json()
        assert any(x["rule_key"] == "act.activated_not_ready" for x in f)

    def test_missing_mandatory_but_ready(self, admin_headers):
        _seed_activation({"driver_activation_id": "eb16-act-y",
                              "driver_id": "eb16-drv-y",
                              "readiness_status": "Ready",
                              "outstanding_mandatory_count": 2})
        run = _run_integrity(admin_headers, "Activation")
        f = requests.get(f"{API}/integrity/runs/{run['integrity_check_run_id']}/findings",
                          headers=admin_headers).json()
        assert any(x["rule_key"] == "act.missing_mandatory_but_ready" for x in f)

    def test_counts_not_reconciling(self, admin_headers):
        _seed_activation({"driver_activation_id": "eb16-act-z",
                              "driver_id": "eb16-drv-z",
                              "readiness_status": "Incomplete",
                              "applicable_item_count": 5, "completed_item_count": 3,
                              "mandatory_item_count": 3, "mandatory_completed_count": 1,
                              "outstanding_mandatory_count": 5})  # should be 2
        run = _run_integrity(admin_headers, "Activation")
        f = requests.get(f"{API}/integrity/runs/{run['integrity_check_run_id']}/findings",
                          headers=admin_headers).json()
        assert any(x["rule_key"] == "act.counts_not_reconciling" for x in f)


class TestIntegrityRunLifecycle:
    def test_run_creates_findings_and_baseline(self, admin_headers):
        run = _run_integrity(admin_headers, "FullSystem")
        assert run["status"] == "Completed"
        assert run["rules_evaluated"] >= 40
        assert set(run["findings_by_severity"].keys()) == {"Info", "Warning", "Error", "Critical"}

    def test_finding_acknowledge_and_resolve(self, admin_headers):
        _seed_driver({"id": "eb16-lc-1", "driver_code": "LC1",
                          "dispatch_number": 601, "status": "Active"})
        _seed_driver({"id": "eb16-lc-2", "driver_code": "LC1",
                          "dispatch_number": 602, "status": "Active"})
        run = _run_integrity(admin_headers, "Registers")
        findings = requests.get(f"{API}/integrity/runs/{run['integrity_check_run_id']}/findings",
                                   headers=admin_headers).json()
        f = next(x for x in findings if x["rule_key"] == "reg.duplicate_driver_code")
        fid = f["integrity_check_finding_id"]
        # Acknowledge
        r = requests.post(f"{API}/integrity/findings/{fid}/acknowledge",
                           json={"note": "triage"}, headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["status"] == "Acknowledged"
        # Resolve
        r2 = requests.post(f"{API}/integrity/findings/{fid}/resolve",
                            json={"note": "fixed"}, headers=admin_headers)
        assert r2.status_code == 200
        assert r2.json()["status"] == "Resolved"
        # Reopen
        r3 = requests.post(f"{API}/integrity/findings/{fid}/reopen",
                            headers=admin_headers)
        assert r3.status_code == 200


# ─────────────────────────────────────────────────────────────────────
# 3. Operations dashboards
# ─────────────────────────────────────────────────────────────────────
class TestOperations:
    def test_summary_no_sensitive(self, admin_headers):
        requests.post(f"{API}/rehearsal/eb16/seed", headers=admin_headers)
        r = requests.get(f"{API}/operations/summary", headers=admin_headers).json()
        for k in ("active_drivers", "ready_drivers", "blocked_drivers",
                    "overall_health", "migration_state"):
            assert k in r
        # No financial-sounding keys
        for k in r.keys():
            assert "salary" not in k.lower()
            assert "wage" not in k.lower()
            assert "rate" not in k.lower()

    def test_driver_readiness(self, admin_headers):
        requests.post(f"{API}/rehearsal/eb16/seed", headers=admin_headers)
        r = requests.get(f"{API}/operations/driver-readiness",
                          headers=admin_headers).json()
        assert isinstance(r, list)
        assert any(x.get("readiness_status") == "Ready" for x in r)

    def test_compliance_workload(self, admin_headers):
        requests.post(f"{API}/rehearsal/eb16/seed", headers=admin_headers)
        r = requests.get(f"{API}/operations/compliance-workload",
                          headers=admin_headers).json()
        assert any(x.get("status") == "Expired" for x in r)

    def test_migration_readiness(self, admin_headers):
        r = requests.get(f"{API}/operations/migration-readiness",
                          headers=admin_headers).json()
        assert "go_no_go_recommendation" in r


# ─────────────────────────────────────────────────────────────────────
# 4. Release gate
# ─────────────────────────────────────────────────────────────────────
class TestReleaseGate:
    def test_release_gate_returns_result(self, admin_headers):
        # Clean rehearsal
        requests.post(f"{API}/rehearsal/eb16/seed", headers=admin_headers)
        r = requests.get(f"{API}/integrity/release-gate",
                          headers=admin_headers).json()
        assert r["gate_result"] in ("PASS", "PASS_WITH_WARNINGS", "FAIL")

    def test_release_gate_fails_on_critical(self, admin_headers):
        # Seed a Critical finding source
        _seed_driver({"id": "eb16-crit-1", "driver_code": "RG1",
                          "dispatch_number": 13, "status": "Active"})
        r = requests.get(f"{API}/integrity/release-gate",
                          headers=admin_headers).json()
        # Reserved 13 is Critical → gate must FAIL
        assert r["gate_result"] == "FAIL"


# ─────────────────────────────────────────────────────────────────────
# 5. Health snapshots
# ─────────────────────────────────────────────────────────────────────
class TestHealthSnapshots:
    def test_create_and_list(self, admin_headers):
        r = requests.post(f"{API}/automation/health-snapshots",
                           headers=admin_headers).json()
        assert "overall_health" in r
        assert "captured_at" in r
        r2 = requests.get(f"{API}/automation/health-snapshots",
                           headers=admin_headers).json()
        assert isinstance(r2, list)
        assert len(r2) >= 1


# ─────────────────────────────────────────────────────────────────────
# 6. Webhook signatures & idempotency
# ─────────────────────────────────────────────────────────────────────
class TestWebhooks:
    def test_disabled_by_default(self):
        # WEBHOOKS_ENABLED is not "true" — should return 503
        r = requests.post(f"{API}/webhooks/sendgrid", json=[])
        assert r.status_code == 503
        r2 = requests.post(f"{API}/webhooks/twilio", data={})
        assert r2.status_code == 503

    def test_enabled_invalid_signature_rejected(self, admin_headers):
        # Toggle WEBHOOKS_ENABLED at runtime is not supported; we test the
        # signature verification helpers directly.
        from importlib import import_module
        m = import_module("integrity_module")
        assert m._verify_twilio_signature("http://x", {"a": "1"}, "bad") is False
        assert m._verify_sendgrid_signature(b"", "1", "bad", "") is False

    def test_twilio_signature_verification_positive(self):
        os.environ["TWILIO_AUTH_TOKEN"] = "test-token-eb16"
        from importlib import import_module
        m = import_module("integrity_module")
        url = "https://x.test/webhook"
        params = {"MessageSid": "SM123", "MessageStatus": "delivered"}
        payload = url + "".join(f"{k}{v}" for k, v in sorted(params.items()))
        sig = base64.b64encode(hmac.new(b"test-token-eb16", payload.encode(),
                                              hashlib.sha1).digest()).decode()
        assert m._verify_twilio_signature(url, params, sig) is True


# ─────────────────────────────────────────────────────────────────────
# 7. Escalation incident actions (reopen)
# ─────────────────────────────────────────────────────────────────────
class TestEscalationReopen:
    def test_reopen_endpoint(self, admin_headers):
        # Seed an incident row
        async def _do():
            db = _mongo()
            try:
                await db["notification_escalation_incidents"].insert_one({
                    "notification_escalation_incident_id": "eb16-inc-1",
                    "rule_key": "compliance_expired",
                    "source_entity": "equipment_compliance",
                    "source_id": "eb16-src-1",
                    "active": False, "resolved_at": "2026-01-01T00:00:00+00:00",
                    "current_level": 1, "_source": "seed-eb16",
                })
            finally: db.client.close()
        asyncio.run(_do())
        r = requests.post(
            f"{API}/automation/escalation-incidents/eb16-inc-1/reopen",
            headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["reopened"] is True


# ─────────────────────────────────────────────────────────────────────
# 8. Permissions
# ─────────────────────────────────────────────────────────────────────
class TestPermissions:
    def test_readonly_can_view_summary(self, readonly_headers):
        r = requests.get(f"{API}/operations/summary",
                          headers=readonly_headers)
        assert r.status_code == 200

    def test_readonly_cannot_run_integrity(self, readonly_headers):
        r = requests.post(f"{API}/integrity/runs",
                           json={"run_type": "FullSystem"},
                           headers=readonly_headers)
        assert r.status_code == 403

    def test_readonly_cannot_seed_rehearsal(self, readonly_headers):
        r = requests.post(f"{API}/rehearsal/eb16/seed",
                           headers=readonly_headers)
        assert r.status_code == 403
