"""MR-06 · Compliance Alerts + Notification lifecycle · surgical acceptance.

The canonical compliance scan iterates the full register (~1k+ records) and
takes tens of seconds per invocation. To respect that cost these tests
consolidate related assertions into fewer scan invocations and mark the
suite as slow.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
ADMIN = {"email": "admin@acedriverhub.com", "password": "Admin@123"}

pytestmark = pytest.mark.slow


def _tag(): return uuid.uuid4().hex[:6]
def _iso_days(delta):
    return (datetime.now(timezone.utc).date() + timedelta(days=delta)).isoformat()


@pytest.fixture(scope="module")
def admin():
    r = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=15)
    if r.status_code != 200: pytest.skip("login failed")
    s = requests.Session(); s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return s


@pytest.fixture(scope="module")
def db():
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    from pymongo import MongoClient
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _mk_driver(admin):
    r = admin.post(f"{BASE_URL}/api/drivers",
                   json={"full_name": f"MR06 {_tag()}", "driver_status": "Training"},
                   timeout=15)
    r.raise_for_status(); return r.json()["id"]


def _mk_licence(admin, driver_id, days_to_expiry, status):
    r = admin.post(f"{BASE_URL}/api/driver-licences",
                    json={"driver_id": driver_id,
                          "licence_number": f"LC{_tag().upper()}",
                          "state": "NSW", "licence_class": "MC",
                          "expiry_date": _iso_days(days_to_expiry),
                          "is_primary": True, "status": status},
                    timeout=15)
    r.raise_for_status(); return r.json()


def _run_scan(admin):
    r = admin.post(f"{BASE_URL}/api/notification-jobs/compliance-scan", timeout=180)
    r.raise_for_status(); return r.json()


def _active_alerts(db, source_id, event_type=None):
    """Return currently-open notifications for a source. `event_type` is
    stored on new rows but legacy rows may only have it on the linked event;
    we resolve either way."""
    open_states = ["Active", "Snoozed", "Acknowledged"]
    q = {"source_record_id": source_id, "status": {"$in": open_states}}
    rows = list(db["notifications"].find(q, {"_id": 0}))
    if event_type is None:
        return rows
    keep = []
    for r in rows:
        et = r.get("event_type")
        if not et and r.get("notification_event_id"):
            ev = db["notification_events"].find_one(
                {"notification_event_id": r["notification_event_id"]},
                {"_id": 0, "event_type": 1},
            )
            et = ev.get("event_type") if ev else None
        if et == event_type: keep.append(r)
    return keep


# ────────────────────────────────────────────────────────────────────────
# TEST 1 · full licence lifecycle in ONE scenario with minimum scan calls
# Missing → present → DueSoon → Expired → renewed. Each step verifies
# auto-resolution semantics.
# ────────────────────────────────────────────────────────────────────────
class TestLicenceFullLifecycle:
    def test_missing_to_present_to_expired_to_renewed(self, admin, db):
        d = _mk_driver(admin)
        # 1) Missing state
        _run_scan(admin)
        missing = _active_alerts(db, d, "Compliance Missing")
        assert len(missing) == 1

        # 2) Add a DueSoon licence → Missing resolves, DueSoon appears
        lic = _mk_licence(admin, d, days_to_expiry=20, status="Compliant")
        _run_scan(admin)
        assert len(_active_alerts(db, d, "Compliance Missing")) == 0
        assert len(_active_alerts(db, lic["id"], "Compliance Due Soon")) == 1
        # Idempotency: 2nd scan does not duplicate DueSoon
        _run_scan(admin)
        assert len(_active_alerts(db, lic["id"], "Compliance Due Soon")) == 1

        # 3) Escalate to Expired → DueSoon auto-resolves, Expired active
        db["driver_licences"].update_one({"id": lic["id"]},
                                          {"$set": {"expiry_date": _iso_days(-3)}})
        _run_scan(admin)
        assert len(_active_alerts(db, lic["id"], "Compliance Due Soon")) == 0
        assert len(_active_alerts(db, lic["id"], "Compliance Expired")) == 1
        # Resolved history retained with auto-resolve reason
        old = db["notifications"].find_one(
            {"source_record_id": lic["id"], "event_type": "Compliance Due Soon",
             "status": "Resolved"})
        assert old and "auto-resolve" in (old.get("resolution_reason") or "").lower()

        # 4) Renew → Expired auto-resolves, no active alerts
        db["driver_licences"].update_one({"id": lic["id"]},
                                          {"$set": {"expiry_date": _iso_days(400)}})
        _run_scan(admin)
        assert len(_active_alerts(db, lic["id"])) == 0
        # Resolved Expired retained
        assert db["notifications"].count_documents(
            {"source_record_id": lic["id"], "event_type": "Compliance Expired",
             "status": "Resolved"}) == 1


# ────────────────────────────────────────────────────────────────────────
# TEST 2 · Insurance missing → present resolves
# ────────────────────────────────────────────────────────────────────────
class TestInsuranceLifecycle:
    def test_missing_insurance_resolves_on_create(self, admin, db):
        v = admin.post(f"{BASE_URL}/api/vehicles",
                        json={"registration_number": f"MR06I-{_tag().upper()}",
                              "vehicle_type": "Prime Mover",
                              "vehicle_status": "Active",
                              "ownership_model": "Owned"}, timeout=15).json()
        _run_scan(admin)
        assert len(_active_alerts(db, v["id"], "Compliance Missing")) == 1
        admin.post(f"{BASE_URL}/api/vehicle-insurance",
                    json={"vehicle_id": v["id"], "insurer": "X",
                          "policy_number": f"P{_tag()}",
                          "cover_type": "Comprehensive",
                          "expiry_date": _iso_days(400),
                          "is_primary": True, "status": "Compliant"},
                    timeout=15).raise_for_status()
        _run_scan(admin)
        assert len(_active_alerts(db, v["id"])) == 0


# ────────────────────────────────────────────────────────────────────────
# TEST 3 · Static safety guards — no HTTP, fast
# ────────────────────────────────────────────────────────────────────────
class TestSafetyGuards:
    def test_notification_delivery_disabled(self):
        env = Path("/app/backend/.env").read_text()
        assert 'NOTIFICATION_DELIVERY_ENABLED="false"' in env
        assert 'EMAIL_PROVIDER="development"' in env
        assert 'SMS_PROVIDER="development"' in env

    def test_scan_uses_canonical_classifier_only(self):
        src = Path("/app/backend/notifications_module.py").read_text()
        assert "_classify_expiry" in src
        # No re-implemented 30/7 day thresholds inside notifications
        assert "days=30" not in src
        assert "days=7" not in src

    def test_activation_untouched_by_notifications(self):
        src = Path("/app/backend/activation_module.py").read_text()
        assert "notifications_module" not in src.replace(
            "# notifications_module", "# ok"
        ), "activation must not depend on notifications"


# ────────────────────────────────────────────────────────────────────────
# TEST 4 · Acknowledge does not touch canonical Compliance
# ────────────────────────────────────────────────────────────────────────
class TestAckSemantics:
    def test_ack_does_not_change_canonical(self, admin, db):
        d = _mk_driver(admin)
        lic = _mk_licence(admin, d, days_to_expiry=-2, status="Expired")
        _run_scan(admin)
        alert = _active_alerts(db, lic["id"], "Compliance Expired")[0]
        r = admin.post(f"{BASE_URL}/api/notifications/{alert['notification_id']}/acknowledge",
                       json={"reason": "seen"}, timeout=15)
        assert r.status_code in (200, 204), r.text
        # Canonical Compliance status unchanged (expiry still in the past)
        row = db["driver_licences"].find_one({"id": lic["id"]})
        assert row["expiry_date"] == _iso_days(-2)


# ────────────────────────────────────────────────────────────────────────
# TEST 5 · Regression — Activation V1 gate unaffected
# ────────────────────────────────────────────────────────────────────────
class TestRegressions:
    def test_activation_gate_seven_items_only(self, admin):
        d = _mk_driver(admin)
        rd = admin.get(f"{BASE_URL}/api/drivers/{d}/blueprint-readiness").json()
        assert len(rd["items"]) == 7
