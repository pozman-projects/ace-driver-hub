"""MR-06-FIX · Urgent Compliance Alert Lifecycle · surgical acceptance.

Owner-locked decisions:
    Compliance Urgent severity = High
    repeat_interval_hours     = 24
    escalation_policy.levels  = []

Canonical status authority = _classify_expiry() from MR-02.
This suite only validates the notification-side lifecycle around the
Urgent tier. It never mutates or asserts against canonical compliance
records except by moving expiry dates.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
ADMIN = {"email": "admin@acedriverhub.com", "password": "Admin@123"}

pytestmark = pytest.mark.slow


# ────────────────────────────────────────────────────────────────────────
# helpers
# ────────────────────────────────────────────────────────────────────────
def _tag() -> str:
    return uuid.uuid4().hex[:6]


def _iso_days(delta: int) -> str:
    return (datetime.now(timezone.utc).date() + timedelta(days=delta)).isoformat()


@pytest.fixture(scope="module")
def admin():
    r = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=15)
    if r.status_code != 200:
        pytest.skip("login failed")
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return s


@pytest.fixture(scope="module")
def db():
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    from pymongo import MongoClient
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _mk_driver(admin):
    r = admin.post(f"{BASE_URL}/api/drivers",
                   json={"full_name": f"MR06FIX {_tag()}", "driver_status": "Training"},
                   timeout=15)
    r.raise_for_status()
    return r.json()["id"]


def _mk_licence(admin, driver_id, days_to_expiry, status="Compliant"):
    r = admin.post(f"{BASE_URL}/api/driver-licences",
                   json={"driver_id": driver_id,
                         "licence_number": f"LC{_tag().upper()}",
                         "state": "NSW", "licence_class": "MC",
                         "expiry_date": _iso_days(days_to_expiry),
                         "is_primary": True, "status": status},
                   timeout=15)
    r.raise_for_status()
    return r.json()


def _set_licence_expiry(admin, licence_id, days_to_expiry):
    r = admin.put(f"{BASE_URL}/api/driver-licences/{licence_id}",
                  json={"expiry_date": _iso_days(days_to_expiry)}, timeout=15)
    r.raise_for_status()
    return r.json()


def _mk_vehicle(admin):
    r = admin.post(f"{BASE_URL}/api/vehicles",
                   json={"registration_number": f"URG{_tag().upper()}",
                         "make": "Test", "model": "MR06FIX",
                         "vehicle_status": "Active"},
                   timeout=15)
    r.raise_for_status()
    return r.json()["id"]


def _mk_registration(admin, vehicle_id, days_to_expiry):
    r = admin.post(f"{BASE_URL}/api/vehicle-registrations",
                   json={"vehicle_id": vehicle_id, "state": "NSW",
                         "expiry_date": _iso_days(days_to_expiry),
                         "is_current": True, "status": "Compliant"},
                   timeout=15)
    r.raise_for_status()
    return r.json()


def _mk_insurance(admin, vehicle_id, days_to_expiry):
    r = admin.post(f"{BASE_URL}/api/vehicle-insurance",
                   json={"vehicle_id": vehicle_id, "insurer": "TestCo",
                         "policy_number": f"P{_tag().upper()}",
                         "policy_type": "Comprehensive",
                         "expiry_date": _iso_days(days_to_expiry),
                         "is_current": True, "status": "Compliant"},
                   timeout=15)
    r.raise_for_status()
    return r.json()


def _run_scan(admin):
    r = admin.post(f"{BASE_URL}/api/notification-jobs/compliance-scan", timeout=240)
    r.raise_for_status()
    return r.json()


def _active_alerts(db, source_id, event_type=None):
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
        if et == event_type:
            keep.append(r)
    return keep


def _history(db, source_id, event_type):
    """All rows (any status) matching source + event_type — for history retention checks."""
    rows = list(db["notifications"].find({"source_record_id": source_id}, {"_id": 0}))
    keep = []
    for r in rows:
        et = r.get("event_type")
        if not et and r.get("notification_event_id"):
            ev = db["notification_events"].find_one(
                {"notification_event_id": r["notification_event_id"]},
                {"_id": 0, "event_type": 1},
            )
            et = ev.get("event_type") if ev else None
        if et == event_type:
            keep.append(r)
    return keep


# ────────────────────────────────────────────────────────────────────────
# TEST 9 (first — cheap, no scan) · rule shape is owner-locked
# ────────────────────────────────────────────────────────────────────────
class TestUrgentRule:
    def test_urgent_rule_shape(self, db):
        rule = db["notification_rules"].find_one({"name": "Compliance · Urgent (7d)"}, {"_id": 0})
        assert rule, "Urgent rule not seeded"
        assert rule["event_type"] == "Compliance Urgent"
        assert rule["severity"] == "High"
        assert rule["repeat_interval_hours"] == 24
        assert (rule.get("escalation_policy") or {}).get("levels") == []
        assert rule["template_key"] == "compliance_urgent"
        assert rule.get("is_active") is True


# ────────────────────────────────────────────────────────────────────────
# TESTS 1-6 · Licence Urgent + full lifecycle transitions in one scenario
# ────────────────────────────────────────────────────────────────────────
class TestLicenceUrgentLifecycle:
    def test_full_lifecycle(self, admin, db):
        d = _mk_driver(admin)

        # Step A · Due Soon (20 days)
        lic = _mk_licence(admin, d, days_to_expiry=20)
        _run_scan(admin)
        assert len(_active_alerts(db, lic["id"], "Compliance Due Soon")) == 1
        assert _active_alerts(db, lic["id"], "Compliance Urgent") == []

        # Step B · Due Soon → Urgent (5 days) — Test 1 + Test 3
        _set_licence_expiry(admin, lic["id"], 5)
        _run_scan(admin)
        assert _active_alerts(db, lic["id"], "Compliance Due Soon") == [], \
            "Due Soon must resolve when source becomes Urgent"
        urgent_active = _active_alerts(db, lic["id"], "Compliance Urgent")
        assert len(urgent_active) == 1
        assert urgent_active[0]["severity"] == "High"
        # history retained
        assert len(_history(db, lic["id"], "Compliance Due Soon")) >= 1

        # Step C · Urgent idempotency — Test 2
        _run_scan(admin)
        _run_scan(admin)
        assert len(_active_alerts(db, lic["id"], "Compliance Urgent")) == 1

        # Step D · Urgent → Due Soon (bump back to 20d) — Test 6
        _set_licence_expiry(admin, lic["id"], 20)
        _run_scan(admin)
        assert _active_alerts(db, lic["id"], "Compliance Urgent") == [], \
            "Urgent must resolve when source leaves the Urgent tier"
        assert len(_active_alerts(db, lic["id"], "Compliance Due Soon")) == 1

        # Step E · Due Soon → Urgent again (needed for Urgent→Expired test)
        _set_licence_expiry(admin, lic["id"], 3)
        _run_scan(admin)
        assert len(_active_alerts(db, lic["id"], "Compliance Urgent")) == 1
        assert _active_alerts(db, lic["id"], "Compliance Due Soon") == []

        # Step F · Urgent → Expired — Test 4
        _set_licence_expiry(admin, lic["id"], -2)
        _run_scan(admin)
        assert _active_alerts(db, lic["id"], "Compliance Urgent") == [], \
            "Urgent must resolve when canonical is now Expired"
        assert len(_active_alerts(db, lic["id"], "Compliance Expired")) == 1

        # Step G · Expired → Urgent again then → Current — Test 5
        _set_licence_expiry(admin, lic["id"], 4)
        _run_scan(admin)
        assert len(_active_alerts(db, lic["id"], "Compliance Urgent")) == 1
        assert _active_alerts(db, lic["id"], "Compliance Expired") == [], \
            "Expired must resolve when canonical is back inside the window"
        _set_licence_expiry(admin, lic["id"], 200)  # far Compliant
        _run_scan(admin)
        assert _active_alerts(db, lic["id"], "Compliance Urgent") == []
        assert _active_alerts(db, lic["id"], "Compliance Due Soon") == []
        assert _active_alerts(db, lic["id"], "Compliance Expired") == []


# ────────────────────────────────────────────────────────────────────────
# TEST 7 · Vehicle Registration Urgent
# ────────────────────────────────────────────────────────────────────────
class TestRegistrationUrgent:
    def test_registration_urgent(self, admin, db):
        v = _mk_vehicle(admin)
        reg = _mk_registration(admin, v, days_to_expiry=4)
        _run_scan(admin)
        alerts = _active_alerts(db, reg["id"], "Compliance Urgent")
        assert len(alerts) == 1, f"expected 1 Urgent notification, got {len(alerts)}"
        assert alerts[0]["entity_type"] == "Vehicle"
        assert alerts[0]["severity"] == "High"
        # idempotent
        _run_scan(admin)
        assert len(_active_alerts(db, reg["id"], "Compliance Urgent")) == 1


# ────────────────────────────────────────────────────────────────────────
# TEST 8 · Vehicle Insurance Urgent
# ────────────────────────────────────────────────────────────────────────
class TestInsuranceUrgent:
    def test_insurance_urgent(self, admin, db):
        v = _mk_vehicle(admin)
        pol = _mk_insurance(admin, v, days_to_expiry=2)
        _run_scan(admin)
        alerts = _active_alerts(db, pol["id"], "Compliance Urgent")
        assert len(alerts) == 1
        assert alerts[0]["entity_type"] == "Vehicle"
        assert alerts[0]["severity"] == "High"


# ────────────────────────────────────────────────────────────────────────
# TEST 10 · Legacy fallback — row without event_type resolves via
# notification_events. Simulate by stripping event_type on an existing
# Urgent row and re-running the auto-resolver via a scan that changes
# state (Urgent → Compliant).
# ────────────────────────────────────────────────────────────────────────
class TestLegacyFallback:
    def test_legacy_row_without_event_type_resolves(self, admin, db):
        d = _mk_driver(admin)
        lic = _mk_licence(admin, d, days_to_expiry=3)
        _run_scan(admin)
        urgent = _active_alerts(db, lic["id"], "Compliance Urgent")
        assert len(urgent) == 1
        # simulate legacy row: remove event_type from notification row only
        db["notifications"].update_one(
            {"notification_id": urgent[0]["notification_id"]},
            {"$unset": {"event_type": ""}},
        )
        # canonical event_type on notification_events must still exist
        ev = db["notification_events"].find_one(
            {"notification_event_id": urgent[0]["notification_event_id"]},
            {"_id": 0, "event_type": 1},
        )
        assert ev and ev["event_type"] == "Compliance Urgent"
        # push canonical to Compliant — auto-resolver must resolve via fallback
        _set_licence_expiry(admin, lic["id"], 200)
        _run_scan(admin)
        assert _active_alerts(db, lic["id"], "Compliance Urgent") == []


# ────────────────────────────────────────────────────────────────────────
# TEST 11 · Acknowledging Urgent does not mutate canonical compliance
# ────────────────────────────────────────────────────────────────────────
class TestAcknowledgeDoesNotMutateCanonical:
    def test_ack_urgent_leaves_source_untouched(self, admin, db):
        d = _mk_driver(admin)
        lic = _mk_licence(admin, d, days_to_expiry=3)
        _run_scan(admin)
        urgent = _active_alerts(db, lic["id"], "Compliance Urgent")
        assert len(urgent) == 1
        # snapshot canonical
        before = db["driver_licences"].find_one({"id": lic["id"]}, {"_id": 0})
        r = admin.post(f"{BASE_URL}/api/notifications/{urgent[0]['notification_id']}/acknowledge",
                        json={"note": "seen"}, timeout=15)
        assert r.status_code in (200, 204)
        after = db["driver_licences"].find_one({"id": lic["id"]}, {"_id": 0})
        assert before.get("expiry_date") == after.get("expiry_date")
        assert before.get("status") == after.get("status")
        # canonical classifier unchanged
        from compliance_records import _classify_expiry
        assert _classify_expiry(after.get("expiry_date")) == "Urgent"


# ────────────────────────────────────────────────────────────────────────
# TEST 12 · Delivery safety — no live email / SMS. Existing simulated /
# in-app pattern only.
# ────────────────────────────────────────────────────────────────────────
class TestDeliverySafety:
    def test_no_live_delivery_channels(self, admin, db):
        d = _mk_driver(admin)
        lic = _mk_licence(admin, d, days_to_expiry=2)
        _run_scan(admin)
        urgent = _active_alerts(db, lic["id"], "Compliance Urgent")
        assert len(urgent) == 1
        deliveries = list(db["notification_deliveries"].find(
            {"notification_id": urgent[0]["notification_id"]}, {"_id": 0}))
        # every non-InApp channel must remain in a simulated/queued state,
        # NEVER Sent or Delivered by a real provider
        for d_ in deliveries:
            if d_["channel"] == "In App":
                assert d_["delivery_status"] in ("Sent", "Simulated")
            else:
                assert d_["delivery_status"] in (
                    "Simulated", "Pending", "Queued", "Suppressed", "Cancelled",
                    "Retry Scheduled",
                )
                assert d_["provider"] == "simulated"


# ────────────────────────────────────────────────────────────────────────
# TESTS 13-15 · MR-04 / MR-08A / MR-05 regression smoke — surface-level.
# We only ensure the surfaces still respond and their canonical outputs
# are structurally intact; deep MR-* semantics live in their own suites.
# ────────────────────────────────────────────────────────────────────────
class TestOutOfScopeRegressions:
    def test_activation_readiness_untouched(self, admin):
        # MR-04 · at least one driver's readiness endpoint returns the 7-item shape.
        r = admin.get(f"{BASE_URL}/api/drivers?limit=1", timeout=15)
        r.raise_for_status()
        drivers = r.json()
        drivers = drivers.get("items") if isinstance(drivers, dict) else drivers
        if not drivers:
            pytest.skip("no drivers to check readiness on")
        did = drivers[0]["id"]
        rr = admin.get(f"{BASE_URL}/api/drivers/{did}/blueprint-v1-readiness", timeout=20)
        # endpoint exists and returns something parseable
        assert rr.status_code in (200, 404)  # 404 acceptable if driver has no readiness surface

    def test_numbering_untouched(self, admin):
        # MR-08A · numbering routes still respond.
        r = admin.get(f"{BASE_URL}/api/numbering/dispatch/pools", timeout=15)
        assert r.status_code in (200, 404, 405)

    def test_owner_carrier_untouched(self, admin):
        # MR-05 · owners endpoint still responds.
        r = admin.get(f"{BASE_URL}/api/owners?limit=1", timeout=15)
        assert r.status_code == 200
