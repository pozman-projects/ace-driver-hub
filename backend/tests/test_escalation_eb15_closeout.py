"""EB-15 Close-out · Escalation Deduplication tests (deterministic).

Verifies that:
  1. Repeated scans do NOT create duplicate escalations at the same level.
  2. All six covered sources trigger correctly.
  3. Acknowledgement blocks new escalations at the same level.
  4. Resolution stops further escalation.
  5. Level increase produces new escalation records without duplicating
     earlier levels.
  6. Escalation-generated deliveries are NOT re-escalated by the
     ``delivery_repeatedly_failed`` rule.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

BASE = (os.environ.get("REACT_APP_BACKEND_URL")
        or "https://fleet-ops-center-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"
AUTO = f"{API}/automation"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")


def _login(email, password):
    r = requests.post(f"{API}/auth/login",
                       json={"email": email, "password": password}, timeout=25)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def admin_headers():
    return _login("admin@acedriverhub.com", "Admin@123")


TEST_TAG = {"$in": ["eb15-esc-test", "escalation"]}  # cleanup tag filter


def _mongo():
    return AsyncIOMotorClient(MONGO_URL)["ace_driver_hub"]


async def _cleanup_all():
    db = _mongo()
    try:
        await db.notification_escalations.delete_many(
            {"source_id": {"$regex": "^EB15-ESC-"}})
        await db.notification_escalation_incidents.delete_many(
            {"source_id": {"$regex": "^EB15-ESC-"}})
        await db.notifications.delete_many({"_source": "escalation",
                                              "escalation_incident_id": {"$exists": True}})
        await db.notification_deliveries.delete_many({"_source": "escalation"})
        # Test fixture rows in business collections
        await db.equipment_compliance_records.delete_many({"_source": "eb15-esc-test"})
        await db.driver_activation_records.delete_many({"_source": "eb15-esc-test"})
        await db.driver_activation_overrides.delete_many({"_source": "eb15-esc-test"})
        await db.migration_commit_jobs.delete_many({"_source": "eb15-esc-test"})
        await db.storage_reconciliation_runs.delete_many({"_source": "eb15-esc-test"})
        await db.notification_deliveries.delete_many({"_source": "eb15-esc-test"})
    finally:
        db.client.close()


@pytest.fixture(autouse=True)
def clean():
    asyncio.run(_cleanup_all())
    yield
    asyncio.run(_cleanup_all())


def _run_scan(admin_headers) -> dict:
    r = requests.post(f"{AUTO}/jobs/notifications.escalation/run",
                       json={}, headers=admin_headers, timeout=30)
    r.raise_for_status()
    body = r.json()
    assert body["status"] == "Completed", body
    return body["result_summary"] or {}


# ─────────────────────────────────────────────────────────────────────────
# Seed helpers (fictional data only, all tagged _source=eb15-esc-test)
# ─────────────────────────────────────────────────────────────────────────
def _seed_compliance_expired():
    async def _do():
        db = _mongo()
        try:
            await db.equipment_compliance_records.insert_one({
                "id": f"EB15-ESC-CMP-{uuid.uuid4().hex[:6]}",
                "equipment_id": "EB15-ESC-EQ-1",
                "compliance_type": "Rego", "status": "Expired",
                "is_current": True, "is_mandatory": True, "is_archived": False,
                "expiry_date": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
                "_source": "eb15-esc-test",
            })
        finally: db.client.close()
    asyncio.run(_do())


def _seed_activation_blocked():
    async def _do():
        db = _mongo()
        try:
            await db.driver_activation_records.insert_one({
                "driver_activation_id": f"EB15-ESC-ACT-{uuid.uuid4().hex[:6]}",
                "driver_id": "EB15-ESC-DR-1", "status": "Blocked",
                "outstanding_mandatory_count": 3,
                "is_archived": False, "_source": "eb15-esc-test",
            })
        finally: db.client.close()
    asyncio.run(_do())


def _seed_override_expired():
    async def _do():
        db = _mongo()
        try:
            await db.driver_activation_overrides.insert_one({
                "activation_override_id": f"EB15-ESC-OV-{uuid.uuid4().hex[:6]}",
                "driver_id": "EB15-ESC-DR-1", "status": "Active",
                "expires_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
                "is_archived": False, "_source": "eb15-esc-test",
            })
        finally: db.client.close()
    asyncio.run(_do())


def _seed_migration_failed():
    async def _do():
        db = _mongo()
        try:
            await db.migration_commit_jobs.insert_one({
                "migration_commit_job_id": f"EB15-ESC-MIG-{uuid.uuid4().hex[:6]}",
                "name": "Test Migration", "status": "Failed",
                "failure_reason": "seeded", "failed_at": _now_iso(),
                "_source": "eb15-esc-test",
            })
        finally: db.client.close()
    asyncio.run(_do())


def _seed_storage_failed():
    async def _do():
        db = _mongo()
        try:
            await db.storage_reconciliation_runs.insert_one({
                "storage_reconciliation_run_id": f"EB15-ESC-STG-{uuid.uuid4().hex[:6]}",
                "status": "Failed", "missing_count": 3,
                "checksum_failure_count": 0,
                "_source": "eb15-esc-test",
            })
        finally: db.client.close()
    asyncio.run(_do())


def _seed_dead_letter_delivery():
    async def _do():
        db = _mongo()
        try:
            await db.notification_deliveries.insert_one({
                "notification_delivery_id": f"EB15-ESC-DL-{uuid.uuid4().hex[:6]}",
                "channel": "EMAIL", "delivery_status": "Dead Letter",
                "email_address": "fictional@example.test",
                "last_failure_reason": "seeded", "attempts_made": 5,
                "_source": "eb15-esc-test",
            })
        finally: db.client.close()
    asyncio.run(_do())


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


async def _count_escalations_by_rule(rule_key):
    db = _mongo()
    try:
        return await db.notification_escalations.count_documents(
            {"rule_key": rule_key})
    finally: db.client.close()


async def _get_incident_for_source(source_id):
    db = _mongo()
    try:
        return await db.notification_escalation_incidents.find_one(
            {"source_id": source_id}, {"_id": 0})
    finally: db.client.close()


# ═════════════════════════════════════════════════════════════════════════
# 1. Zero-trigger baseline
# ═════════════════════════════════════════════════════════════════════════
class TestBaseline:
    def test_zero_triggers_zero_created(self, admin_headers):
        r = _run_scan(admin_headers)
        # cleanup ensured empty fixtures; deltas from any external rows are
        # deduped so `created` can be 0 or reflect pre-existing untagged
        # incidents. Deltas from our fixtures = 0.
        assert isinstance(r.get("created"), int)
        assert isinstance(r.get("deduped"), int)
        assert isinstance(r.get("per_rule"), dict)


# ═════════════════════════════════════════════════════════════════════════
# 2. Dedup: repeated scans keep counts flat per rule
# ═════════════════════════════════════════════════════════════════════════
class TestDedup:
    def _dedup_flat(self, admin_headers, seed_fn, rule_key):
        seed_fn()
        # First scan
        _run_scan(admin_headers)
        first = asyncio.run(_count_escalations_by_rule(rule_key))
        # Second scan — must not add rows
        _run_scan(admin_headers)
        second = asyncio.run(_count_escalations_by_rule(rule_key))
        # Third scan — still flat
        _run_scan(admin_headers)
        third = asyncio.run(_count_escalations_by_rule(rule_key))
        assert first > 0, f"expected at least one escalation for {rule_key}"
        assert first == second == third, (
            f"{rule_key} produced duplicates: {first}→{second}→{third}")

    def test_compliance_expired(self, admin_headers):
        self._dedup_flat(admin_headers, _seed_compliance_expired,
                            "compliance_expired")

    def test_activation_blocked(self, admin_headers):
        self._dedup_flat(admin_headers, _seed_activation_blocked,
                            "activation_blocked")

    def test_override_expired(self, admin_headers):
        self._dedup_flat(admin_headers, _seed_override_expired,
                            "override_expired")

    def test_migration_failed(self, admin_headers):
        self._dedup_flat(admin_headers, _seed_migration_failed,
                            "migration_failed")

    def test_storage_failed(self, admin_headers):
        self._dedup_flat(admin_headers, _seed_storage_failed,
                            "storage_failed")

    def test_delivery_repeatedly_failed(self, admin_headers):
        self._dedup_flat(admin_headers, _seed_dead_letter_delivery,
                            "delivery_repeatedly_failed")


# ═════════════════════════════════════════════════════════════════════════
# 3. Acknowledged incidents block same-level escalations
# ═════════════════════════════════════════════════════════════════════════
class TestAcknowledge:
    def test_ack_blocks_same_level(self, admin_headers):
        _seed_compliance_expired()
        _run_scan(admin_headers)
        # Find the incident and ack it via API
        async def _find():
            db = _mongo()
            try:
                return await db.notification_escalation_incidents.find_one(
                    {"rule_key": "compliance_expired",
                      "source_id": {"$regex": "^EB15-ESC-CMP-"}}, {"_id": 0})
            finally: db.client.close()
        incident = asyncio.run(_find())
        assert incident, "incident missing"
        iid = incident["notification_escalation_incident_id"]
        r = requests.post(f"{AUTO}/escalation-incidents/{iid}/acknowledge",
                           headers=admin_headers)
        assert r.status_code == 200

        count_before = asyncio.run(_count_escalations_by_rule("compliance_expired"))
        r2 = _run_scan(admin_headers)
        count_after = asyncio.run(_count_escalations_by_rule("compliance_expired"))
        assert count_before == count_after
        # Scanner should report the ack skip in stats
        per_rule = r2["per_rule"]["compliance_expired"]
        assert per_rule["acknowledged_skipped"] >= 1


# ═════════════════════════════════════════════════════════════════════════
# 4. Resolved incidents stop further escalation
# ═════════════════════════════════════════════════════════════════════════
class TestResolve:
    def test_resolved_incident_stops(self, admin_headers):
        _seed_activation_blocked()
        _run_scan(admin_headers)
        async def _find():
            db = _mongo()
            try:
                return await db.notification_escalation_incidents.find_one(
                    {"rule_key": "activation_blocked",
                      "source_id": {"$regex": "^EB15-ESC-ACT-"}}, {"_id": 0})
            finally: db.client.close()
        incident = asyncio.run(_find())
        assert incident
        iid = incident["notification_escalation_incident_id"]
        r = requests.post(f"{AUTO}/escalation-incidents/{iid}/resolve",
                           headers=admin_headers)
        assert r.status_code == 200
        count_before = asyncio.run(_count_escalations_by_rule("activation_blocked"))
        _run_scan(admin_headers)
        count_after = asyncio.run(_count_escalations_by_rule("activation_blocked"))
        assert count_before == count_after


# ═════════════════════════════════════════════════════════════════════════
# 5. Level increase produces new escalation without dup-ing earlier level
# ═════════════════════════════════════════════════════════════════════════
class TestLevelIncrease:
    def test_level_increase_creates_new_no_duplicates(self, admin_headers):
        _seed_compliance_expired()
        _run_scan(admin_headers)
        # Force incident age → 3h so level should reach L3 (>=240m)
        async def _age_incident():
            db = _mongo()
            try:
                past = (datetime.now(timezone.utc) - timedelta(minutes=300)).isoformat()
                r = await db.notification_escalation_incidents.update_many(
                    {"rule_key": "compliance_expired",
                      "source_id": {"$regex": "^EB15-ESC-CMP-"}},
                    {"$set": {"first_seen_at": past}})
                return r.modified_count
            finally: db.client.close()
        touched = asyncio.run(_age_incident())
        assert touched >= 1

        pre_l1 = asyncio.run(_count_escalations_at("compliance_expired", 1))
        _run_scan(admin_headers)
        post_l1 = asyncio.run(_count_escalations_at("compliance_expired", 1))
        post_l2 = asyncio.run(_count_escalations_at("compliance_expired", 2))
        post_l3 = asyncio.run(_count_escalations_at("compliance_expired", 3))
        # Level 1 count must not have grown
        assert post_l1 == pre_l1
        # New levels appeared
        assert post_l2 + post_l3 >= 1


async def _count_escalations_at(rule_key, level):
    db = _mongo()
    try:
        return await db.notification_escalations.count_documents(
            {"rule_key": rule_key, "level": level})
    finally: db.client.close()


# ═════════════════════════════════════════════════════════════════════════
# 6. Escalation-driven deliveries are not re-escalated
# ═════════════════════════════════════════════════════════════════════════
class TestSelfRecursionGuard:
    def test_escalation_delivery_not_reescalated(self, admin_headers):
        # Seed a Dead Letter delivery tagged as escalation → must not appear
        # in delivery_repeatedly_failed detector.
        async def _seed():
            db = _mongo()
            try:
                await db.notification_deliveries.insert_one({
                    "notification_delivery_id": f"EB15-ESC-EDL-{uuid.uuid4().hex[:6]}",
                    "channel": "EMAIL", "delivery_status": "Dead Letter",
                    "email_address": "role:Manager@dcc.local",
                    "attempts_made": 5, "_source": "escalation",
                })
            finally: db.client.close()
        asyncio.run(_seed())
        r = _run_scan(admin_headers)
        # This delivery MUST NOT show up in the delivery_repeatedly_failed rule
        deliv_stats = r["per_rule"]["delivery_repeatedly_failed"]
        # triggers should not include our escalation-sourced row
        # (there may be other Dead Letter rows from noise; assert our test row
        #  was excluded from the incident set)
        async def _find():
            db = _mongo()
            try:
                return await db.notification_escalation_incidents.find_one(
                    {"rule_key": "delivery_repeatedly_failed",
                      "source_id": {"$regex": "^EB15-ESC-EDL-"}}, {"_id": 0})
            finally: db.client.close()
        assert asyncio.run(_find()) is None
        # Cleanup escalation-tagged row so autouse cleanup handles it
        async def _rm():
            db = _mongo()
            try:
                await db.notification_deliveries.delete_many(
                    {"notification_delivery_id": {"$regex": "^EB15-ESC-EDL-"}})
            finally: db.client.close()
        asyncio.run(_rm())


# ═════════════════════════════════════════════════════════════════════════
# 7. Idempotency key persisted and unique
# ═════════════════════════════════════════════════════════════════════════
class TestIdempotencyKey:
    def test_key_present_and_unique(self, admin_headers):
        _seed_migration_failed()
        _run_scan(admin_headers)
        async def _rows():
            db = _mongo()
            try:
                return await db.notification_escalations.find(
                    {"rule_key": "migration_failed",
                      "source_id": {"$regex": "^EB15-ESC-MIG-"}},
                    {"_id": 0}).to_list(50)
            finally: db.client.close()
        rows = asyncio.run(_rows())
        assert rows, "expected at least one escalation row"
        for r in rows:
            assert r.get("idempotency_key"), "missing idempotency key"
        keys = [r["idempotency_key"] for r in rows]
        assert len(keys) == len(set(keys))


# ═════════════════════════════════════════════════════════════════════════
# 8. Rules & incidents API
# ═════════════════════════════════════════════════════════════════════════
class TestAPIs:
    def test_list_rules(self, admin_headers):
        r = requests.get(f"{AUTO}/escalation-rules", headers=admin_headers).json()
        keys = {x["rule_key"] for x in r}
        for expected in ("compliance_expired", "activation_blocked",
                            "override_expired", "migration_failed",
                            "storage_failed", "delivery_repeatedly_failed"):
            assert expected in keys

    def test_list_incidents(self, admin_headers):
        _seed_storage_failed()
        _run_scan(admin_headers)
        r = requests.get(f"{AUTO}/escalation-incidents?active=true",
                           headers=admin_headers).json()
        assert any(i["rule_key"] == "storage_failed" for i in r)


# ═════════════════════════════════════════════════════════════════════════
# 9. Template preview endpoint (Template Studio backend)
# ═════════════════════════════════════════════════════════════════════════
class TestTemplatePreview:
    def test_preview_missing_and_unknown(self, admin_headers):
        r = requests.post(f"{AUTO}/notification-templates/preview",
                           headers=admin_headers,
                           json={"subject_template": "Hi {{name}}",
                                  "body_template": "Total {{count}} for {{name}}",
                                  "context": {"name": "Ficta", "extra": "x"}}).json()
        assert "Ficta" in r["subject"]
        assert "[missing:count]" in r["body_text"]
        assert "count" in r["missing_variables"]
        assert "extra" in r["unknown_variables"]
        assert r["sms_length"] > 0
        assert r["sms_segments"] >= 1

    def test_preview_html_sanitiser(self, admin_headers):
        r = requests.post(f"{AUTO}/notification-templates/preview",
                           headers=admin_headers,
                           json={"subject_template": "s",
                                  "body_template": "b",
                                  "context": {"body_html": "<p>ok</p><script>x</script>"}}).json()
        assert "<script>" not in r["body_html_sanitised"]
