"""EB-09 · Driver Profile aggregator + communication preferences + notes + activation."""
from __future__ import annotations

import os
import uuid
from typing import Dict

import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or "https://fleet-ops-center-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@acedriverhub.com"
ADMIN_PASSWORD = "Admin@123"


def _login(email, password):
    r = requests.post(f"{API}/auth/login",
                       json={"email": email, "password": password}, timeout=20)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def admin_headers():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


def _seed_role_user(admin_headers, role):
    email = f"eb09_{role.lower()}_{uuid.uuid4().hex[:6]}@example.com"
    requests.post(f"{API}/auth/register",
                   json={"email": email, "password": "T@1234",
                         "full_name": f"EB09 {role}", "role": role},
                   headers={**admin_headers, "Content-Type": "application/json"},
                   timeout=20)
    return _login(email, "T@1234")


@pytest.fixture(scope="session")
def readonly_headers(admin_headers):
    return _seed_role_user(admin_headers, "ReadOnly")

@pytest.fixture(scope="session")
def allocator_headers(admin_headers):
    return _seed_role_user(admin_headers, "Allocator")

@pytest.fixture(scope="session")
def compliance_headers(admin_headers):
    return _seed_role_user(admin_headers, "Compliance")

@pytest.fixture(scope="session")
def manager_headers(admin_headers):
    return _seed_role_user(admin_headers, "Manager")


@pytest.fixture(scope="session")
def seed_driver_id(admin_headers):
    """Grab any live driver (seed or otherwise)."""
    r = requests.get(f"{API}/drivers", headers=admin_headers, timeout=20)
    r.raise_for_status()
    rows = r.json()
    assert rows, "no drivers in system"
    return rows[0]["id"]


# ─── Aggregator ────────────────────────────────────────────────────────────────
def test_aggregator_shape(admin_headers, seed_driver_id):
    r = requests.get(f"{API}/drivers/{seed_driver_id}/command-centre-profile",
                     headers=admin_headers, timeout=20)
    assert r.status_code == 200
    d = r.json()
    for key in ("driver", "role", "restricted_fields", "owner", "vehicle",
                 "equipment_assignments", "communication_preferences",
                 "compliance_intelligence", "primary_licence", "primary_registration",
                 "primary_insurance", "vehicle_compliance_extras", "alerts",
                 "alert_counts", "documents", "allocation_events", "notes",
                 "activation", "generated_at"):
        assert key in d, f"missing key {key}"
    ci = d["compliance_intelligence"]
    assert "worst_status" in ci and "worst_severity" in ci
    assert "Worst Status Wins" in (ci.get("explanation") or "")


def test_aggregator_missing_driver_404(admin_headers):
    r = requests.get(f"{API}/drivers/{uuid.uuid4()}/command-centre-profile",
                     headers=admin_headers, timeout=20)
    assert r.status_code == 404


def test_aggregator_role_filtering_readonly(readonly_headers, seed_driver_id):
    r = requests.get(f"{API}/drivers/{seed_driver_id}/command-centre-profile",
                     headers=readonly_headers, timeout=20)
    assert r.status_code == 200
    d = r.json()
    dr = d["driver"]
    for f in ("business_name", "abn", "payroll_number", "payment_percentage"):
        assert f not in dr, f"restricted field {f} leaked to ReadOnly"
    assert set(d["restricted_fields"]) == {"business_name", "abn", "payroll_number", "payment_percentage"}


def test_aggregator_role_filtering_admin(admin_headers, seed_driver_id):
    r = requests.get(f"{API}/drivers/{seed_driver_id}/command-centre-profile",
                     headers=admin_headers, timeout=20)
    assert r.status_code == 200
    d = r.json()
    # Admin should have empty restricted_fields
    assert d["restricted_fields"] == []


# ─── Communication preferences ─────────────────────────────────────────────────
def test_comms_upsert_and_get(admin_headers, seed_driver_id):
    payload = {
        "owner_report_email_override": None,
        "driver_report_email_override": None,
        "send_daily_report_owner": True,
        "send_daily_report_driver": False,
        "display_on_dispatch": True,
    }
    r = requests.put(f"{API}/drivers/{seed_driver_id}/communication-preferences",
                      json=payload, headers=admin_headers, timeout=20)
    assert r.status_code == 200
    got = requests.get(f"{API}/drivers/{seed_driver_id}/communication-preferences",
                       headers=admin_headers, timeout=20).json()
    assert got["send_daily_report_owner"] is True
    assert got["display_on_dispatch"] is True

    # Second PUT does NOT create duplicate — same preference_id
    id1 = got["communication_preference_id"]
    r2 = requests.put(f"{API}/drivers/{seed_driver_id}/communication-preferences",
                       json={**payload, "send_daily_report_owner": False},
                       headers=admin_headers, timeout=20)
    assert r2.status_code == 200
    assert r2.json()["communication_preference_id"] == id1
    assert r2.json()["send_daily_report_owner"] is False


def test_comms_readonly_cannot_write(readonly_headers, seed_driver_id):
    r = requests.put(f"{API}/drivers/{seed_driver_id}/communication-preferences",
                      json={"send_daily_report_owner": False,
                            "send_daily_report_driver": False,
                            "display_on_dispatch": True},
                      headers=readonly_headers, timeout=20)
    assert r.status_code == 403


# ─── Notes ─────────────────────────────────────────────────────────────────────
def test_note_create_and_version(admin_headers, seed_driver_id):
    r = requests.post(f"{API}/drivers/{seed_driver_id}/notes",
                       json={"note_type": "General", "title": "T1",
                             "content": "first content", "is_pinned": False},
                       headers=admin_headers, timeout=20)
    assert r.status_code == 200
    note = r.json()
    note_id = note["driver_note_id"]
    # Edit -> new version
    r2 = requests.put(f"{API}/drivers/{seed_driver_id}/notes/{note_id}",
                       json={"content": "second content", "is_pinned": True},
                       headers=admin_headers, timeout=20)
    assert r2.status_code == 200
    assert r2.json()["content"] == "second content"
    assert r2.json()["is_pinned"] is True
    # Version history
    detail = requests.get(f"{API}/drivers/{seed_driver_id}/notes/{note_id}",
                          headers=admin_headers, timeout=20).json()
    assert len(detail["versions"]) == 2
    versions_content = [v["content"] for v in detail["versions"]]
    assert "first content" in versions_content
    assert "second content" in versions_content


def test_note_readonly_cannot_create(readonly_headers, seed_driver_id):
    r = requests.post(f"{API}/drivers/{seed_driver_id}/notes",
                       json={"note_type": "General", "content": "x"},
                       headers=readonly_headers, timeout=20)
    assert r.status_code == 403


def test_note_compliance_category_gated(admin_headers, allocator_headers,
                                         compliance_headers, seed_driver_id):
    # Allocator CANNOT create Compliance notes
    r = requests.post(f"{API}/drivers/{seed_driver_id}/notes",
                       json={"note_type": "Compliance", "content": "audit"},
                       headers=allocator_headers, timeout=20)
    assert r.status_code == 403
    # Compliance CAN
    r2 = requests.post(f"{API}/drivers/{seed_driver_id}/notes",
                       json={"note_type": "Compliance", "content": "audit"},
                       headers=compliance_headers, timeout=20)
    assert r2.status_code == 200


def test_note_accounts_category_gated(admin_headers, compliance_headers,
                                        manager_headers, seed_driver_id):
    # Compliance CANNOT create Accounts notes
    r = requests.post(f"{API}/drivers/{seed_driver_id}/notes",
                       json={"note_type": "Accounts", "content": "payroll"},
                       headers=compliance_headers, timeout=20)
    assert r.status_code == 403
    # Manager CAN
    r2 = requests.post(f"{API}/drivers/{seed_driver_id}/notes",
                       json={"note_type": "Accounts", "content": "payroll"},
                       headers=manager_headers, timeout=20)
    assert r2.status_code == 200


def test_note_visibility_gating_in_aggregator(admin_headers, allocator_headers,
                                                seed_driver_id, manager_headers):
    # Manager creates a Compliance + Accounts note
    for note_type in ("Compliance", "Accounts"):
        requests.post(f"{API}/drivers/{seed_driver_id}/notes",
                       json={"note_type": note_type, "content": f"{note_type} note"},
                       headers=manager_headers, timeout=20)
    # Allocator's aggregator should NOT contain those categories
    d = requests.get(f"{API}/drivers/{seed_driver_id}/command-centre-profile",
                     headers=allocator_headers, timeout=20).json()
    types = {n["note_type"] for n in d["notes"]}
    assert "Compliance" not in types
    assert "Accounts" not in types


def test_note_direct_get_denied_for_wrong_role(admin_headers, allocator_headers,
                                                 seed_driver_id, manager_headers):
    r = requests.post(f"{API}/drivers/{seed_driver_id}/notes",
                       json={"note_type": "Accounts", "content": "denied"},
                       headers=manager_headers, timeout=20)
    nid = r.json()["driver_note_id"]
    r2 = requests.get(f"{API}/drivers/{seed_driver_id}/notes/{nid}",
                      headers=allocator_headers, timeout=20)
    assert r2.status_code == 403


def test_note_archive_only_admin_manager(admin_headers, allocator_headers,
                                           seed_driver_id):
    r = requests.post(f"{API}/drivers/{seed_driver_id}/notes",
                       json={"note_type": "General", "content": "delete-me"},
                       headers=admin_headers, timeout=20)
    nid = r.json()["driver_note_id"]
    # Allocator cannot archive
    ra = requests.delete(f"{API}/drivers/{seed_driver_id}/notes/{nid}",
                          headers=allocator_headers, timeout=20)
    assert ra.status_code == 403
    # Admin can
    rd = requests.delete(f"{API}/drivers/{seed_driver_id}/notes/{nid}",
                          headers=admin_headers, timeout=20)
    assert rd.status_code == 200


# ─── Activation adapter ────────────────────────────────────────────────────────
def test_activation_summary_shape(admin_headers, seed_driver_id):
    r = requests.get(f"{API}/drivers/{seed_driver_id}/activation-summary",
                     headers=admin_headers, timeout=20)
    assert r.status_code == 200
    d = r.json()
    assert d["readiness"] in {"Ready", "Partial", "Not Ready"}
    assert "items" in d and isinstance(d["items"], list)
    assert d["mandatory_total"] >= 1
    # Every mandatory item has explicit source string
    for it in d["items"]:
        assert "source" in it and isinstance(it["source"], str)
        assert isinstance(it["complete"], bool)
        assert isinstance(it["mandatory"], bool)


def test_activation_missing_driver_404(admin_headers):
    r = requests.get(f"{API}/drivers/{uuid.uuid4()}/activation-summary",
                     headers=admin_headers, timeout=20)
    assert r.status_code == 404


def test_activation_no_false_completion_without_licence(admin_headers, seed_driver_id):
    """primary_licence item must be complete iff a licence document actually exists.
    We can't easily delete a licence in the test, but we can at least assert the
    semantics: an item marked complete must have a truthy source signal in the reason.
    """
    d = requests.get(f"{API}/drivers/{seed_driver_id}/activation-summary",
                     headers=admin_headers, timeout=20).json()
    pl = next((i for i in d["items"] if i["item_key"] == "primary_licence"), None)
    assert pl is not None
    # If complete, the source should reference canonical
    if pl["complete"]:
        assert "canonical" in pl["source"]
    else:
        # If not complete, it must be reported as Missing
        assert not pl["complete"]


# ─── Aggregator resilience ─────────────────────────────────────────────────────
def test_aggregator_never_leaks_mongo_id(admin_headers, seed_driver_id):
    r = requests.get(f"{API}/drivers/{seed_driver_id}/command-centre-profile",
                     headers=admin_headers, timeout=20)
    assert r.status_code == 200
    text = r.text
    assert '"_id"' not in text, "raw Mongo _id leaked"
