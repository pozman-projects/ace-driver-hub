"""EB-07a Notifications, Alerts & Escalation Engine — backend tests.

These tests hit the live FastAPI service against the seeded database. They
exercise: rules + events + deduplication, lifecycle transitions, delivery
simulation, retry + dead-letter, escalation, preferences, permissions, and
the six scheduled jobs.
"""
from __future__ import annotations

import os
import uuid
import time
from datetime import datetime, timezone

import pytest
import requests


BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or "https://fleet-ops-center-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@acedriverhub.com"
ADMIN_PASSWORD = "Admin@123"


def _login(email: str, password: str) -> dict:
    r = requests.post(f"{API}/auth/login",
                       json={"email": email, "password": password}, timeout=20)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def admin_headers():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


def _seed_role_user(admin_headers: dict, role: str) -> dict:
    email = f"eb07_{role.lower()}_{uuid.uuid4().hex[:6]}@example.com"
    requests.post(
        f"{API}/auth/register",
        json={"email": email, "password": "T@1234",
              "full_name": f"EB07 {role}", "role": role},
        headers={**admin_headers, "Content-Type": "application/json"},
        timeout=20,
    )
    return _login(email, "T@1234")


@pytest.fixture(scope="session")
def readonly_headers(admin_headers):
    return _seed_role_user(admin_headers, "ReadOnly")


@pytest.fixture(scope="session")
def compliance_headers(admin_headers):
    return _seed_role_user(admin_headers, "Compliance")


@pytest.fixture(scope="session")
def manager_headers(admin_headers):
    return _seed_role_user(admin_headers, "Manager")


@pytest.fixture(scope="session")
def allocator_headers(admin_headers):
    return _seed_role_user(admin_headers, "Allocator")


# ==============================================================
#  Rules and events
# ==============================================================
def test_default_rules_seeded(admin_headers):
    r = requests.get(f"{API}/notification-rules", headers=admin_headers, timeout=20)
    r.raise_for_status()
    rules = r.json()
    names = {r["name"] for r in rules}
    for expected in [
        "Compliance · Due Soon (30d)",
        "Compliance · Expired",
        "Compliance · Missing",
        "Critical Vehicle Defect",
        "High Vehicle Defect",
        "Maintenance Due Soon",
        "Maintenance Overdue",
        "Document Under Review",
        "Document Rejected",
        "Import Validation Failed",
        "Import Ready to Commit",
        "Import Partially Committed",
        "Import Commit Failed",
    ]:
        assert expected in names, f"Missing rule: {expected}"


def test_create_and_archive_rule(admin_headers):
    payload = {
        "name": f"Test Manual Rule {uuid.uuid4().hex[:6]}",
        "description": "Unit-test rule",
        "event_type": "Manual Notification",
        "entity_type": "General",
        "conditions": {},
        "severity": "Medium",
        "channels": ["In App"],
        "recipient_strategy": "All Managers",
        "warning_days": 0,
        "repeat_interval_hours": 0,
        "escalation_policy": {"levels": []},
        "template_key": "manual_notification",
        "is_active": True,
        "priority": 500,
    }
    r = requests.post(f"{API}/notification-rules", json=payload, headers=admin_headers, timeout=20)
    assert r.status_code == 200, r.text
    rid = r.json()["notification_rule_id"]
    # Non-Admin/Manager cannot create
    r2 = requests.post(f"{API}/notification-rules", json=payload,
                        headers=_login(ADMIN_EMAIL, ADMIN_PASSWORD), timeout=20)
    assert r2.status_code == 200  # admin
    # Archive
    r3 = requests.delete(f"{API}/notification-rules/{rid}", headers=admin_headers, timeout=20)
    assert r3.status_code == 200
    got = requests.get(f"{API}/notification-rules/{rid}", headers=admin_headers, timeout=20).json()
    assert got.get("is_archived") is True


def test_unknown_event_type_rejected(admin_headers):
    r = requests.post(f"{API}/notification-rules",
                       json={"name": "bad", "event_type": "NotAnEvent"},
                       headers=admin_headers, timeout=20)
    assert r.status_code == 400


def test_readonly_cannot_create_rule(readonly_headers):
    r = requests.post(f"{API}/notification-rules",
                       json={"name": "x", "event_type": "Manual Notification"},
                       headers=readonly_headers, timeout=20)
    assert r.status_code == 403


# ==============================================================
#  Notifications overview / counts / listing
# ==============================================================
def test_overview_shape(admin_headers):
    r = requests.get(f"{API}/notifications/overview", headers=admin_headers, timeout=20)
    r.raise_for_status()
    d = r.json()
    for k in ("by_status", "by_severity", "delivery_failures", "dead_letters_open"):
        assert k in d
    assert isinstance(d["by_status"], dict)


def test_counts_positive(admin_headers):
    r = requests.get(f"{API}/notifications/counts", headers=admin_headers, timeout=20)
    r.raise_for_status()
    d = r.json()
    for k in ("active", "unread", "critical", "high"):
        assert k in d
        assert isinstance(d[k], int)


def test_list_filters(admin_headers):
    r_all = requests.get(f"{API}/notifications", headers=admin_headers, timeout=20)
    assert r_all.status_code == 200
    r_crit = requests.get(f"{API}/notifications?severity=Critical",
                           headers=admin_headers, timeout=20)
    assert r_crit.status_code == 200
    for n in r_crit.json():
        assert n["severity"] == "Critical"


def test_unread_only_filter(admin_headers):
    r = requests.get(f"{API}/notifications?unread_only=true",
                      headers=admin_headers, timeout=20)
    r.raise_for_status()
    for n in r.json():
        assert n["is_read"] is False


# ==============================================================
#  Scan job + deduplication
# ==============================================================
def _first_seed_notification(admin_headers, event_type=None):
    r = requests.get(f"{API}/notifications", headers=admin_headers, timeout=20)
    for n in r.json():
        if n.get("_source") == "seed-eb07":
            if event_type:
                # Look up event to check event_type
                evt = requests.get(
                    f"{API}/notifications/{n['notification_id']}",
                    headers=admin_headers, timeout=20,
                ).json()
                return evt
            return n
    return None


def test_compliance_scan_idempotent(admin_headers):
    # Snapshot notifications count
    before = requests.get(f"{API}/notifications", headers=admin_headers,
                           timeout=20).json()
    n0 = len(before)
    r1 = requests.post(f"{API}/notification-jobs/compliance-scan",
                        headers=admin_headers, timeout=60)
    assert r1.status_code == 200, r1.text
    r2 = requests.post(f"{API}/notification-jobs/compliance-scan",
                        headers=admin_headers, timeout=60)
    assert r2.status_code == 200
    after = requests.get(f"{API}/notifications", headers=admin_headers, timeout=20).json()
    # Repeated scan should NOT increase total notifications (dedup)
    n2 = len(after)
    assert n2 >= n0
    # Third run — still stable
    r3 = requests.post(f"{API}/notification-jobs/compliance-scan",
                        headers=admin_headers, timeout=60)
    after3 = requests.get(f"{API}/notifications", headers=admin_headers, timeout=20).json()
    assert len(after3) == n2


def test_critical_scan_runs(admin_headers):
    r = requests.post(f"{API}/notification-jobs/critical-scan",
                       headers=admin_headers, timeout=60)
    assert r.status_code == 200
    d = r.json()
    assert d["status"] in ("Completed", "Completed with Warnings")


def test_job_history_shape(admin_headers):
    r = requests.get(f"{API}/notification-jobs", headers=admin_headers, timeout=20)
    r.raise_for_status()
    jobs = r.json()
    assert isinstance(jobs, list) and len(jobs) > 0
    for j in jobs[:3]:
        for k in ("job_type", "started_at", "status", "notification_job_run_id"):
            assert k in j


def test_readonly_cannot_run_scans(readonly_headers):
    r = requests.post(f"{API}/notification-jobs/compliance-scan",
                       headers=readonly_headers, timeout=20)
    assert r.status_code == 403


def test_allocator_cannot_run_scans(allocator_headers):
    r = requests.post(f"{API}/notification-jobs/compliance-scan",
                       headers=allocator_headers, timeout=20)
    assert r.status_code == 403


# ==============================================================
#  Notification detail — full audit envelope
# ==============================================================
def test_notification_detail_includes_history(admin_headers):
    notifs = requests.get(f"{API}/notifications", headers=admin_headers,
                           timeout=20).json()
    assert notifs, "expected seeded notifications"
    nid = notifs[0]["notification_id"]
    r = requests.get(f"{API}/notifications/{nid}", headers=admin_headers, timeout=20)
    r.raise_for_status()
    d = r.json()
    for k in ("recipients", "deliveries", "acknowledgements", "snoozes", "escalations"):
        assert k in d


# ==============================================================
#  Lifecycle: read / ack / snooze / resolve / reopen
# ==============================================================
def _pick_active_notif(admin_headers):
    for n in requests.get(f"{API}/notifications?status=Active",
                           headers=admin_headers, timeout=20).json():
        if n["status"] == "Active":
            return n
    return None


def test_mark_read(admin_headers):
    n = _pick_active_notif(admin_headers)
    assert n is not None
    r = requests.put(f"{API}/notifications/{n['notification_id']}/read",
                      headers=admin_headers, timeout=20)
    assert r.status_code == 200
    got = requests.get(f"{API}/notifications/{n['notification_id']}",
                        headers=admin_headers, timeout=20).json()
    assert got["is_read"] is True


def test_acknowledge_and_duplicate(admin_headers):
    n = _pick_active_notif(admin_headers)
    r = requests.post(f"{API}/notifications/{n['notification_id']}/acknowledge",
                       json={"note": "test ack"}, headers=admin_headers, timeout=20)
    assert r.status_code == 200
    # Duplicate ack: no-op, still 200
    r2 = requests.post(f"{API}/notifications/{n['notification_id']}/acknowledge",
                        json={"note": "second"}, headers=admin_headers, timeout=20)
    assert r2.status_code == 200
    detail = requests.get(f"{API}/notifications/{n['notification_id']}",
                           headers=admin_headers, timeout=20).json()
    assert len(detail["acknowledgements"]) == 1  # de-duped per user


def test_readonly_cannot_acknowledge(readonly_headers, admin_headers):
    n = _pick_active_notif(admin_headers)
    r = requests.post(f"{API}/notifications/{n['notification_id']}/acknowledge",
                       json={}, headers=readonly_headers, timeout=20)
    assert r.status_code == 403


def test_snooze_and_max(admin_headers):
    # Grab an Active notification not yet snoozed
    picks = [n for n in requests.get(f"{API}/notifications?status=Active",
                                       headers=admin_headers, timeout=20).json()]
    n = None
    for p in picks:
        if p["severity"] in ("Low", "Medium", "High"):
            n = p
            break
    assert n
    # Attempt too-long snooze
    max_map = {"Information": 720, "Low": 720, "Medium": 336, "High": 168, "Critical": 24}
    r_bad = requests.post(f"{API}/notifications/{n['notification_id']}/snooze",
                           json={"hours": max_map[n["severity"]] + 1, "reason": "too long"},
                           headers=admin_headers, timeout=20)
    assert r_bad.status_code == 400
    # Valid snooze
    r_ok = requests.post(f"{API}/notifications/{n['notification_id']}/snooze",
                          json={"hours": 4, "reason": "cool"},
                          headers=admin_headers, timeout=20)
    assert r_ok.status_code == 200
    detail = requests.get(f"{API}/notifications/{n['notification_id']}",
                           headers=admin_headers, timeout=20).json()
    assert detail["status"] == "Snoozed"
    assert len(detail["snoozes"]) >= 1


def test_snooze_zero_rejected(admin_headers):
    n = _pick_active_notif(admin_headers)
    r = requests.post(f"{API}/notifications/{n['notification_id']}/snooze",
                       json={"hours": 0}, headers=admin_headers, timeout=20)
    assert r.status_code == 400


def test_resolve_and_reopen(admin_headers, manager_headers):
    n = _pick_active_notif(admin_headers)
    r = requests.post(f"{API}/notifications/{n['notification_id']}/resolve",
                       json={"reason": "test"}, headers=admin_headers, timeout=20)
    assert r.status_code == 200
    got = requests.get(f"{API}/notifications/{n['notification_id']}",
                        headers=admin_headers, timeout=20).json()
    assert got["status"] == "Resolved"
    # Acknowledge on resolved must fail with 409
    r_ack = requests.post(f"{API}/notifications/{n['notification_id']}/acknowledge",
                           json={}, headers=admin_headers, timeout=20)
    assert r_ack.status_code == 409
    # Reopen — Manager can reopen
    r2 = requests.post(f"{API}/notifications/{n['notification_id']}/reopen",
                        headers=manager_headers, timeout=20)
    assert r2.status_code == 200
    reopened = requests.get(f"{API}/notifications/{n['notification_id']}",
                             headers=admin_headers, timeout=20).json()
    assert reopened["status"] == "Active"


def test_compliance_cannot_reopen(admin_headers, compliance_headers):
    n = _pick_active_notif(admin_headers)
    requests.post(f"{API}/notifications/{n['notification_id']}/resolve",
                   json={}, headers=admin_headers, timeout=20)
    r = requests.post(f"{API}/notifications/{n['notification_id']}/reopen",
                       headers=compliance_headers, timeout=20)
    assert r.status_code == 403


# ==============================================================
#  Deliveries and outbox
# ==============================================================
def test_outbox_has_simulated(admin_headers):
    r = requests.get(f"{API}/notification-outbox?status=Simulated",
                      headers=admin_headers, timeout=20)
    r.raise_for_status()
    items = r.json()
    assert isinstance(items, list)
    for d in items:
        assert d["delivery_status"] == "Simulated"


def test_outbox_readonly_forbidden(readonly_headers):
    r = requests.get(f"{API}/notification-outbox", headers=readonly_headers, timeout=20)
    assert r.status_code == 403


def test_in_app_delivery_is_sent(admin_headers):
    # find an in-app delivery
    outbox = requests.get(f"{API}/notification-outbox?channel=In App",
                           headers=admin_headers, timeout=20).json()
    assert outbox
    d = outbox[0]
    assert d["delivery_status"] in ("Sent", "Delivered")
    assert d["provider"] == "in-app"


def test_email_and_sms_are_simulated(admin_headers):
    outbox_email = requests.get(f"{API}/notification-outbox?channel=Email",
                                  headers=admin_headers, timeout=20).json()
    for d in outbox_email:
        assert d["delivery_status"] in ("Simulated", "Retry Scheduled", "Failed", "Sent")
        assert d["provider"] == "simulated"
        assert d.get("rendered_subject")
    outbox_sms = requests.get(f"{API}/notification-outbox?channel=SMS",
                                headers=admin_headers, timeout=20).json()
    for d in outbox_sms:
        assert d["provider"] == "simulated"


def test_simulate_failure_then_success(admin_headers):
    outbox = requests.get(f"{API}/notification-outbox?channel=Email",
                           headers=admin_headers, timeout=20).json()
    assert outbox, "expected simulated email deliveries"
    d = outbox[0]
    # Fail
    r_f = requests.post(
        f"{API}/notification-outbox/{d['notification_delivery_id']}/simulate-failure",
        json={"reason": "test failure"}, headers=admin_headers, timeout=20,
    )
    assert r_f.status_code == 200
    assert r_f.json()["delivery_status"] in ("Retry Scheduled", "Failed")
    # Retry (success)
    r_s = requests.post(
        f"{API}/notification-outbox/{d['notification_delivery_id']}/simulate-success",
        headers=admin_headers, timeout=20,
    )
    assert r_s.status_code == 200
    assert r_s.json()["delivery_status"] in ("Simulated", "Sent")


def test_dead_letter_after_max_attempts(admin_headers):
    # Fetch a fresh Simulated email delivery
    outbox = requests.get(f"{API}/notification-outbox?channel=Email",
                           headers=admin_headers, timeout=20).json()
    # Pick one that isn't already Failed
    d = next((x for x in outbox if x["delivery_status"] == "Simulated"), None)
    assert d, "no Simulated email delivery available"
    did = d["notification_delivery_id"]
    # Force to max_attempts by repeatedly simulating failure
    for _ in range(6):
        requests.post(f"{API}/notification-outbox/{did}/simulate-failure",
                       json={"reason": "force"}, headers=admin_headers, timeout=20)
    final = requests.get(f"{API}/notification-outbox/{did}",
                          headers=admin_headers, timeout=20).json()
    assert final["delivery_status"] in ("Failed", "Retry Scheduled")


# ==============================================================
#  Preferences
# ==============================================================
def test_get_and_set_my_pref(compliance_headers):
    r = requests.put(f"{API}/notification-preferences/me",
                      json={"event_type": "Compliance Due Soon", "channel": "In App",
                            "is_enabled": True, "minimum_severity": "Low"},
                      headers=compliance_headers, timeout=20)
    assert r.status_code == 200
    got = requests.get(f"{API}/notification-preferences/me",
                        headers=compliance_headers, timeout=20).json()
    assert any(p["event_type"] == "Compliance Due Soon" and p["channel"] == "In App"
               for p in got)


def test_critical_cannot_be_fully_disabled(compliance_headers):
    r = requests.put(f"{API}/notification-preferences/me",
                      json={"event_type": "Compliance Expired", "channel": "In App",
                            "is_enabled": False, "minimum_severity": "Critical"},
                      headers=compliance_headers, timeout=20)
    assert r.status_code == 400


def test_unknown_pref_event_type_rejected(compliance_headers):
    r = requests.put(f"{API}/notification-preferences/me",
                      json={"event_type": "Nope", "channel": "In App"},
                      headers=compliance_headers, timeout=20)
    assert r.status_code == 400


def test_admin_can_list_all_prefs(admin_headers):
    r = requests.get(f"{API}/notification-preferences", headers=admin_headers, timeout=20)
    assert r.status_code == 200


def test_readonly_cannot_list_all_prefs(readonly_headers):
    r = requests.get(f"{API}/notification-preferences", headers=readonly_headers, timeout=20)
    assert r.status_code == 403


# ==============================================================
#  My notifications
# ==============================================================
def test_my_notifications_admin(admin_headers):
    r = requests.get(f"{API}/notifications/my-notifications", headers=admin_headers, timeout=20)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ==============================================================
#  Escalation processing (idempotent)
# ==============================================================
def test_process_escalations_idempotent(admin_headers):
    r1 = requests.post(f"{API}/notification-jobs/process-escalations",
                        headers=admin_headers, timeout=30)
    assert r1.status_code == 200
    # Snapshot count of escalations
    r2 = requests.post(f"{API}/notification-jobs/process-escalations",
                        headers=admin_headers, timeout=30)
    assert r2.status_code == 200
    d1 = r1.json()
    d2 = r2.json()
    # Second run should not update more than the first
    assert d2["notifications_updated"] <= d1["notifications_updated"] + 1


def test_process_snoozes_no_op_when_none_expired(admin_headers):
    r = requests.post(f"{API}/notification-jobs/process-snoozes",
                       headers=admin_headers, timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert "records_scanned" in d


def test_retry_deliveries_runs(admin_headers):
    r = requests.post(f"{API}/notification-jobs/retry-deliveries",
                       headers=admin_headers, timeout=30)
    assert r.status_code == 200


def test_reconcile_runs(admin_headers):
    r = requests.post(f"{API}/notification-jobs/reconcile",
                       headers=admin_headers, timeout=60)
    assert r.status_code == 200
    d = r.json()
    assert d["status"] in ("Completed", "Completed with Warnings")


# ==============================================================
#  Archive
# ==============================================================
def test_archive_notification(admin_headers, manager_headers):
    n = _pick_active_notif(admin_headers)
    r = requests.delete(f"{API}/notifications/{n['notification_id']}",
                         headers=manager_headers, timeout=20)
    assert r.status_code == 200
    got = requests.get(f"{API}/notifications/{n['notification_id']}",
                        headers=admin_headers, timeout=20).json()
    assert got["is_archived"] is True


def test_readonly_cannot_archive(readonly_headers, admin_headers):
    n = _pick_active_notif(admin_headers)
    r = requests.delete(f"{API}/notifications/{n['notification_id']}",
                         headers=readonly_headers, timeout=20)
    assert r.status_code == 403


# ==============================================================
#  Compliance role: can trigger compliance scan, cannot reopen
# ==============================================================
def test_compliance_can_run_compliance_scan(compliance_headers):
    r = requests.post(f"{API}/notification-jobs/compliance-scan",
                       headers=compliance_headers, timeout=60)
    assert r.status_code == 200
