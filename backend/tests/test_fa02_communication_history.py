"""FA-02 · Communication multi-driver visibility + preference history + note author.

Backend behaviour tests plus small static frontend assertions.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
ADMIN = {"email": "admin@acedriverhub.com", "password": "Admin@123"}
FE = Path("/app/frontend/src/components/driver-cc")


def _tag(): return uuid.uuid4().hex[:8]


def _login(email, pw):
    r = requests.post(f"{BASE_URL}/api/auth/login",
                       json={"email": email, "password": pw}, timeout=15)
    r.raise_for_status()
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return s


def _register(admin, role):
    email = f"fa02-{role.lower()}-{_tag()}@acedriverhub.com"
    admin.post(f"{BASE_URL}/api/auth/register",
                json={"email": email, "password": "P@ssword1",
                      "full_name": f"FA02 {role}", "role": role},
                timeout=15).raise_for_status()
    return _login(email, "P@ssword1")


def _make_driver(admin, tag, **extras):
    payload = {"full_name": f"FA02 Driver {tag}", "driver_status": "Training", **extras}
    return admin.post(f"{BASE_URL}/api/drivers", json=payload, timeout=15).json()


def _make_owner(admin, tag):
    return admin.post(f"{BASE_URL}/api/owners",
                       json={"name": f"FA02 Owner {tag}", "owner_type": "Business"},
                       timeout=15).json()


def _link(admin, driver_id, owner_id):
    return admin.post(f"{BASE_URL}/api/driver-owner-relationships",
                       json={"driver_id": driver_id, "owner_id": owner_id,
                              "relationship_type": "Company Driver",
                              "start_date": "2026-01-01"},
                       timeout=15)


@pytest.fixture(scope="module")
def admin(): return _login(ADMIN["email"], ADMIN["password"])
@pytest.fixture(scope="module")
def allocator(admin): return _register(admin, "Allocator")
@pytest.fixture(scope="module")
def compliance(admin): return _register(admin, "Compliance")
@pytest.fixture(scope="module")
def readonly(admin): return _register(admin, "ReadOnly")


# ═══════════════════════════════════════════════════════════════════════
# 1 · Canonical communication model remains per-Driver
# ═══════════════════════════════════════════════════════════════════════
class TestPerDriverModel:
    def test_per_driver_preferences_isolated(self, admin):
        tag = _tag()
        d1 = _make_driver(admin, tag + "-A")["id"]
        d2 = _make_driver(admin, tag + "-B")["id"]
        admin.put(f"{BASE_URL}/api/drivers/{d1}/communication-preferences",
                   json={"display_on_dispatch": False}, timeout=15).raise_for_status()
        admin.put(f"{BASE_URL}/api/drivers/{d2}/communication-preferences",
                   json={"display_on_dispatch": True}, timeout=15).raise_for_status()
        p1 = admin.get(f"{BASE_URL}/api/drivers/{d1}/communication-preferences", timeout=10).json()
        p2 = admin.get(f"{BASE_URL}/api/drivers/{d2}/communication-preferences", timeout=10).json()
        assert p1["display_on_dispatch"] is False
        assert p2["display_on_dispatch"] is True


# ═══════════════════════════════════════════════════════════════════════
# 2 · Other Drivers for this Owner
# ═══════════════════════════════════════════════════════════════════════
class TestOtherDrivers:
    def test_same_owner_lists_peers_excluding_current(self, admin):
        tag = _tag()
        owner = _make_owner(admin, tag)
        d1 = _make_driver(admin, tag + "-A")["id"]
        d2 = _make_driver(admin, tag + "-B")["id"]
        d3 = _make_driver(admin, tag + "-C")["id"]
        for did in (d1, d2, d3):
            _link(admin, did, owner["id"]).raise_for_status()
        r = admin.get(f"{BASE_URL}/api/drivers/{d1}/command-centre-profile", timeout=15).json()
        peers = r.get("other_drivers_for_owner") or []
        peer_ids = {p["id"] for p in peers}
        assert d1 not in peer_ids
        assert d2 in peer_ids and d3 in peer_ids

    def test_no_owner_returns_empty(self, admin):
        tag = _tag()
        d = _make_driver(admin, tag)["id"]
        r = admin.get(f"{BASE_URL}/api/drivers/{d}/command-centre-profile", timeout=15).json()
        assert r.get("other_drivers_for_owner") == []

    def test_archived_peer_excluded(self, admin):
        tag = _tag()
        owner = _make_owner(admin, tag)
        current = _make_driver(admin, tag + "-cur")["id"]
        arch = _make_driver(admin, tag + "-arch")["id"]
        _link(admin, current, owner["id"]).raise_for_status()
        _link(admin, arch, owner["id"]).raise_for_status()
        # Archive the peer.
        admin.delete(f"{BASE_URL}/api/drivers/{arch}", timeout=15)
        r = admin.get(f"{BASE_URL}/api/drivers/{current}/command-centre-profile", timeout=15).json()
        peer_ids = {p["id"] for p in (r.get("other_drivers_for_owner") or [])}
        assert arch not in peer_ids

    def test_different_owner_peer_excluded(self, admin):
        tag = _tag()
        owner_a = _make_owner(admin, tag + "-A")
        owner_b = _make_owner(admin, tag + "-B")
        d_a = _make_driver(admin, tag + "-DA")["id"]
        d_b = _make_driver(admin, tag + "-DB")["id"]
        _link(admin, d_a, owner_a["id"]).raise_for_status()
        _link(admin, d_b, owner_b["id"]).raise_for_status()
        r = admin.get(f"{BASE_URL}/api/drivers/{d_a}/command-centre-profile", timeout=15).json()
        peer_ids = {p["id"] for p in (r.get("other_drivers_for_owner") or [])}
        assert d_b not in peer_ids

    def test_compact_payload_only(self, admin):
        tag = _tag()
        owner = _make_owner(admin, tag)
        d_a = _make_driver(admin, tag + "-A")["id"]
        d_b = _make_driver(admin, tag + "-B", business_name="SENSITIVE-Biz")["id"]
        _link(admin, d_a, owner["id"]).raise_for_status()
        _link(admin, d_b, owner["id"]).raise_for_status()
        r = admin.get(f"{BASE_URL}/api/drivers/{d_a}/command-centre-profile", timeout=15).json()
        peers = r.get("other_drivers_for_owner") or []
        for p in peers:
            # Compact set only; no full driver dump / no sensitive fields.
            assert set(p.keys()) <= {"id", "full_name", "driver_code",
                                      "dispatch_number", "driver_status"}


# ═══════════════════════════════════════════════════════════════════════
# 3 · Communication preference history
# ═══════════════════════════════════════════════════════════════════════
class TestCommHistory:
    def test_save_appends_event_with_actor_and_timestamp(self, admin):
        tag = _tag()
        d = _make_driver(admin, tag)["id"]
        admin.put(f"{BASE_URL}/api/drivers/{d}/communication-preferences",
                   json={"display_on_dispatch": False}, timeout=15).raise_for_status()
        r = admin.get(f"{BASE_URL}/api/drivers/{d}/communication-preferences/history",
                       timeout=10).json()
        assert len(r["events"]) == 1
        ev = r["events"][0]
        assert ev["driver_id"] == d
        assert ev["changed_by"] == ADMIN["email"]
        assert ev.get("changed_at")
        assert "display_on_dispatch" in ev["changed_fields"]
        assert ev["before"]["display_on_dispatch"] in (None, True)  # first save
        assert ev["after"]["display_on_dispatch"] is False

    def test_before_after_recorded(self, admin):
        tag = _tag()
        d = _make_driver(admin, tag)["id"]
        admin.put(f"{BASE_URL}/api/drivers/{d}/communication-preferences",
                   json={"send_daily_report_owner": True}, timeout=15).raise_for_status()
        admin.put(f"{BASE_URL}/api/drivers/{d}/communication-preferences",
                   json={"send_daily_report_owner": True,
                          "send_daily_report_driver": True}, timeout=15).raise_for_status()
        r = admin.get(f"{BASE_URL}/api/drivers/{d}/communication-preferences/history",
                       timeout=10).json()
        assert len(r["events"]) == 2  # both saves recorded
        last = r["events"][0]  # most recent first
        assert "send_daily_report_driver" in last["changed_fields"]
        assert last["before"]["send_daily_report_driver"] is False
        assert last["after"]["send_daily_report_driver"] is True

    def test_noop_save_does_not_create_event(self, admin):
        tag = _tag()
        d = _make_driver(admin, tag)["id"]
        admin.put(f"{BASE_URL}/api/drivers/{d}/communication-preferences",
                   json={"display_on_dispatch": True}, timeout=15).raise_for_status()
        before = admin.get(f"{BASE_URL}/api/drivers/{d}/communication-preferences/history",
                            timeout=10).json()
        # Same payload again ⇒ no new event
        admin.put(f"{BASE_URL}/api/drivers/{d}/communication-preferences",
                   json={"display_on_dispatch": True}, timeout=15).raise_for_status()
        after = admin.get(f"{BASE_URL}/api/drivers/{d}/communication-preferences/history",
                           timeout=10).json()
        assert len(after["events"]) == len(before["events"])

    @pytest.mark.parametrize("field,value", [
        ("owner_report_email_override", "own@ex.com"),
        ("driver_report_email_override", "drv@ex.com"),
        ("send_daily_report_owner", True),
        ("send_daily_report_driver", True),
        ("display_on_dispatch", False),
    ])
    def test_all_five_tracked_fields(self, admin, field, value):
        tag = _tag()
        d = _make_driver(admin, tag)["id"]
        admin.put(f"{BASE_URL}/api/drivers/{d}/communication-preferences",
                   json={field: value}, timeout=15).raise_for_status()
        r = admin.get(f"{BASE_URL}/api/drivers/{d}/communication-preferences/history",
                       timeout=10).json()
        assert field in r["events"][0]["changed_fields"]

    def test_history_endpoint_role_safe(self, readonly):
        # ReadOnly can READ but not mutate; endpoint should not 401/500 for auth roles.
        # Use any driver id — 404 is fine because it proves auth passed.
        r = readonly.get(f"{BASE_URL}/api/drivers/nonexistent/communication-preferences/history",
                          timeout=10)
        assert r.status_code == 404
        r = readonly.get(f"{BASE_URL}/api/drivers/nonexistent/communication-preferences",
                          timeout=10)
        assert r.status_code == 404

    def test_history_cannot_be_mutated_directly(self, admin):
        # No POST/PUT/DELETE routes exist for history; assert HTTP 405/404.
        tag = _tag()
        d = _make_driver(admin, tag)["id"]
        admin.put(f"{BASE_URL}/api/drivers/{d}/communication-preferences",
                   json={"display_on_dispatch": False}, timeout=15).raise_for_status()
        # Try a POST — must not succeed (405 or 404)
        r = admin.post(f"{BASE_URL}/api/drivers/{d}/communication-preferences/history",
                        json={}, timeout=10)
        assert r.status_code in (404, 405)

    def test_write_permissions_unchanged(self, compliance):
        # MR-07B: Compliance may NOT write communication preferences.
        tag = _tag()
        # Use admin to seed, then Compliance to attempt write.
        admin = _login(ADMIN["email"], ADMIN["password"])
        d = _make_driver(admin, tag)["id"]
        r = compliance.put(f"{BASE_URL}/api/drivers/{d}/communication-preferences",
                            json={"display_on_dispatch": False}, timeout=10)
        assert r.status_code == 403


# ═══════════════════════════════════════════════════════════════════════
# 4 · Aggregator surfaces last-5 history
# ═══════════════════════════════════════════════════════════════════════
class TestAggregatorSurface:
    def test_aggregator_includes_recent_history(self, admin):
        tag = _tag()
        d = _make_driver(admin, tag)["id"]
        # Alternate ⇒ 3 real changes (canonical default is display_on_dispatch=True)
        for v in (False, True, False):
            admin.put(f"{BASE_URL}/api/drivers/{d}/communication-preferences",
                       json={"display_on_dispatch": v}, timeout=15).raise_for_status()
        r = admin.get(f"{BASE_URL}/api/drivers/{d}/command-centre-profile", timeout=15).json()
        assert isinstance(r.get("communication_history"), list)
        assert len(r["communication_history"]) >= 3

    def test_aggregator_surface_limits_to_five(self, admin):
        tag = _tag()
        d = _make_driver(admin, tag)["id"]
        # 8 alternating saves
        v = True
        for _ in range(8):
            v = not v
            admin.put(f"{BASE_URL}/api/drivers/{d}/communication-preferences",
                       json={"display_on_dispatch": v}, timeout=15).raise_for_status()
        r = admin.get(f"{BASE_URL}/api/drivers/{d}/command-centre-profile", timeout=15).json()
        assert len(r["communication_history"]) == 5


# ═══════════════════════════════════════════════════════════════════════
# 5 · Simulated delivery footer + notes author (static checks)
# ═══════════════════════════════════════════════════════════════════════
class TestFrontendStatic:
    def test_communication_card_has_other_drivers_heading(self):
        src = (FE / "CommunicationCard.jsx").read_text(encoding="utf-8")
        assert "Other Drivers for this Owner" in src
        assert 'data-testid="comm-other-drivers"' in src

    def test_communication_card_has_empty_state(self):
        src = (FE / "CommunicationCard.jsx").read_text(encoding="utf-8")
        assert "No other current Drivers for this Owner" in src
        assert 'data-testid="comm-other-drivers-empty"' in src

    def test_communication_card_has_recent_changes_heading(self):
        src = (FE / "CommunicationCard.jsx").read_text(encoding="utf-8")
        assert "Recent changes" in src
        assert 'data-testid="comm-history"' in src
        assert 'data-testid="comm-history-empty"' in src

    def test_history_ui_does_not_expose_raw_json(self):
        # No JSON.stringify or {...ev} splatting into the DOM for history.
        src = (FE / "CommunicationCard.jsx").read_text(encoding="utf-8")
        assert "JSON.stringify(ev" not in src
        assert "JSON.stringify(history" not in src

    def test_simulated_footer_preserved(self):
        src = (FE / "CommunicationCard.jsx").read_text(encoding="utf-8")
        assert "simulated only" in src
        assert 'data-testid="comm-simulated-footer"' in src

    def test_notes_card_shows_author(self):
        src = (FE / "DriverNotesCard.jsx").read_text(encoding="utf-8")
        assert "note-author-" in src
        assert "n.updated_by" in src or "n.created_by" in src

    def test_notes_role_visibility_unchanged(self):
        src = (FE / "DriverNotesCard.jsx").read_text(encoding="utf-8")
        # Category filter helpers still present
        assert "Compliance" in src
        assert "Accounts" in src


# ═══════════════════════════════════════════════════════════════════════
# 6 · No messaging system introduced
# ═══════════════════════════════════════════════════════════════════════
class TestNoMessagingSystem:
    def test_no_message_endpoints(self, admin):
        # Verify no /messages, /chat, /threads routes were added.
        for path in ("/api/messages", "/api/chats", "/api/threads",
                      "/api/inbox", "/api/conversations"):
            r = admin.get(f"{BASE_URL}{path}", timeout=5)
            # Missing route must return 404 (not accidentally added)
            assert r.status_code == 404, f"unexpected route: {path}"
