"""EB-10.1 · Template item editor + reorder + duplicate + restore + usage tests."""
from __future__ import annotations
import os
import uuid
import pytest
import requests

BASE = (os.environ.get("REACT_APP_BACKEND_URL")
        or "https://fleet-ops-center-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=25)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _seed_user(admin_headers, role):
    email = f"eb101_{role.lower()}_{uuid.uuid4().hex[:6]}@acedriverhub.com"
    requests.post(f"{API}/auth/register",
                   json={"email": email, "password": "T@1234",
                         "full_name": f"EB101 {role}", "role": role},
                   headers={**admin_headers, "Content-Type": "application/json"}, timeout=20)
    return _login(email, "T@1234")


@pytest.fixture(scope="session")
def admin_headers():
    return _login("admin@acedriverhub.com", "Admin@123")

@pytest.fixture(scope="session")
def readonly_headers(admin_headers):
    return _seed_user(admin_headers, "ReadOnly")

@pytest.fixture(scope="session")
def allocator_headers(admin_headers):
    return _seed_user(admin_headers, "Allocator")


@pytest.fixture(scope="session")
def draft_template(admin_headers):
    """A brand-new unlocked template so structural edits are allowed."""
    r = requests.post(f"{API}/activation/templates",
                       json={"name": f"eb10.1-draft-{uuid.uuid4().hex[:6]}",
                             "driver_type": "Other", "company_ref": f"QA-{uuid.uuid4().hex[:4]}",
                             "is_default": False},
                       headers=admin_headers, timeout=15)
    assert r.status_code == 200
    return r.json()["activation_template_id"]


# ─── Item CRUD ────────────────────────────────────────────────────────────────
def test_item_create_unique_key(admin_headers, draft_template):
    payload = {"item_key": "qa.one", "label": "QA One", "category": "Other",
               "completion_type": "Manual", "mandatory": True, "display_order": 0,
               "evidence_required": False, "override_allowed": False, "override_max_days": 30}
    r = requests.post(f"{API}/activation/templates/{draft_template}/items",
                       json=payload, headers=admin_headers, timeout=15)
    assert r.status_code == 200
    # Duplicate key rejected
    r2 = requests.post(f"{API}/activation/templates/{draft_template}/items",
                        json=payload, headers=admin_headers, timeout=15)
    assert r2.status_code == 400 and "already exists" in r2.json()["detail"]


def test_item_conditional_requires_condition_rule(admin_headers, draft_template):
    r = requests.post(f"{API}/activation/templates/{draft_template}/items",
                       json={"item_key": "qa.cond", "label": "Cond", "category": "Other",
                             "completion_type": "Conditional Manual", "mandatory": False,
                             "display_order": 5, "conditional": True},
                       headers=admin_headers, timeout=15)
    assert r.status_code == 400 and "condition_rule" in r.json()["detail"]


def test_item_override_requires_positive_days(admin_headers, draft_template):
    r = requests.post(f"{API}/activation/templates/{draft_template}/items",
                       json={"item_key": "qa.ovr0", "label": "Ovr0", "category": "Other",
                             "completion_type": "Manual", "mandatory": False,
                             "display_order": 6, "override_allowed": True, "override_max_days": 0},
                       headers=admin_headers, timeout=15)
    assert r.status_code == 400


def test_item_critical_defect_cannot_be_overrideable(admin_headers, draft_template):
    # Create then attempt to update override_allowed=True on a vehicle_defect item
    create = requests.post(f"{API}/activation/templates/{draft_template}/items",
                            json={"item_key": "qa.crit", "label": "Crit", "category": "Other",
                                  "completion_type": "Automatic",
                                  "source_entity_type": "vehicle_defect", "source_field": "none_critical",
                                  "mandatory": True, "display_order": 7},
                            headers=admin_headers, timeout=15)
    assert create.status_code == 200
    iid = create.json()["activation_template_item_id"]
    upd = requests.put(f"{API}/activation/template-items/{iid}",
                        json={"item_key": "qa.crit", "label": "Crit", "category": "Other",
                              "completion_type": "Automatic",
                              "source_entity_type": "vehicle_defect", "source_field": "none_critical",
                              "mandatory": True, "display_order": 7,
                              "override_allowed": True, "override_max_days": 5},
                        headers=admin_headers, timeout=15)
    assert upd.status_code == 400 and "Critical-defect" in upd.json()["detail"]


def test_item_readonly_cannot_edit(readonly_headers, draft_template):
    r = requests.post(f"{API}/activation/templates/{draft_template}/items",
                       json={"item_key": "qa.readonly", "label": "no", "category": "Other",
                             "completion_type": "Manual"},
                       headers=readonly_headers, timeout=15)
    assert r.status_code == 403


def test_item_allocator_cannot_edit(allocator_headers, draft_template):
    r = requests.post(f"{API}/activation/templates/{draft_template}/items",
                       json={"item_key": "qa.alloc", "label": "no", "category": "Other",
                             "completion_type": "Manual"},
                       headers=allocator_headers, timeout=15)
    assert r.status_code == 403


# ─── Duplicate ────────────────────────────────────────────────────────────────
def test_item_duplicate(admin_headers, draft_template):
    src = requests.post(f"{API}/activation/templates/{draft_template}/items",
                        json={"item_key": "qa.dup.src", "label": "Dup Src", "category": "Other",
                              "completion_type": "Manual", "mandatory": True, "display_order": 20},
                        headers=admin_headers, timeout=15).json()
    dup = requests.post(f"{API}/activation/template-items/{src['activation_template_item_id']}/duplicate",
                        headers=admin_headers, timeout=15)
    assert dup.status_code == 200
    d = dup.json()
    assert d["activation_template_item_id"] != src["activation_template_item_id"]
    assert d["item_key"].startswith("qa.dup.src.copy")
    assert d["label"].endswith("(Copy)")


# ─── Restore ──────────────────────────────────────────────────────────────────
def test_item_archive_then_restore(admin_headers, draft_template):
    src = requests.post(f"{API}/activation/templates/{draft_template}/items",
                        json={"item_key": "qa.arch", "label": "Arch", "category": "Other",
                              "completion_type": "Manual", "mandatory": False, "display_order": 30},
                        headers=admin_headers, timeout=15).json()
    iid = src["activation_template_item_id"]
    a = requests.delete(f"{API}/activation/template-items/{iid}", headers=admin_headers, timeout=15)
    assert a.status_code == 200
    r = requests.post(f"{API}/activation/template-items/{iid}/restore", headers=admin_headers, timeout=15)
    assert r.status_code == 200
    assert r.json()["is_archived"] is False
    assert r.json()["is_active"] is True


# ─── Reorder ──────────────────────────────────────────────────────────────────
def test_item_reorder(admin_headers, draft_template):
    # Ensure ≥ 2 items
    ids = []
    for i, k in enumerate(["qa.re1", "qa.re2", "qa.re3"]):
        r = requests.post(f"{API}/activation/templates/{draft_template}/items",
                           json={"item_key": k, "label": k, "category": "Other",
                                 "completion_type": "Manual", "display_order": 100 + i},
                           headers=admin_headers, timeout=15)
        assert r.status_code == 200
        ids.append(r.json()["activation_template_item_id"])
    reversed_ids = list(reversed(ids))
    r = requests.post(f"{API}/activation/templates/{draft_template}/items/reorder",
                       json={"order": reversed_ids}, headers=admin_headers, timeout=15)
    assert r.status_code == 200
    # Verify each got a new order
    items = requests.get(f"{API}/activation/templates/{draft_template}/items",
                          headers=admin_headers, timeout=15).json()
    by_id = {i["activation_template_item_id"]: i for i in items}
    orders = [by_id[i]["display_order"] for i in reversed_ids]
    assert orders == sorted(orders)  # ascending in the reordered order


def test_reorder_unknown_id_rejected(admin_headers, draft_template):
    r = requests.post(f"{API}/activation/templates/{draft_template}/items/reorder",
                       json={"order": [str(uuid.uuid4())]},
                       headers=admin_headers, timeout=15)
    assert r.status_code == 400


def _template_in_use(admin_headers):
    """Return a template that has at least one driver_activation_record referencing it.
    Prefer the seeded ACE template; fall back to any template with activations."""
    tpls = requests.get(f"{API}/activation/templates", headers=admin_headers, timeout=15).json()
    # Prefer seeded
    ordered = sorted(tpls, key=lambda t: (0 if t.get("_source") == "seed-eb10" else 1, -t.get("version", 0)))
    for t in ordered:
        usage = requests.get(f"{API}/activation/templates/{t['activation_template_id']}/usage",
                              headers=admin_headers, timeout=15).json()
        if usage.get("used_by_activation_records", 0) >= 1:
            return t
    return None


# ─── Template lock ────────────────────────────────────────────────────────────
def test_template_usage_and_lock(admin_headers):
    """At least one template must be in use by driver activations after
    reconcile has been run (which the earlier EB-10 job tests do)."""
    t = _template_in_use(admin_headers)
    assert t, "no template found with driver activations attached"
    usage = requests.get(f"{API}/activation/templates/{t['activation_template_id']}/usage",
                          headers=admin_headers, timeout=15).json()
    assert usage["used_by_activation_records"] >= 1
    assert usage["locked"] is True


def test_locked_template_item_key_rename_rejected(admin_headers):
    t = _template_in_use(admin_headers)
    if not t:
        pytest.skip("no locked template present")
    items = requests.get(f"{API}/activation/templates/{t['activation_template_id']}/items",
                          headers=admin_headers, timeout=15).json()
    assert items
    item = items[0]
    body = {**{k: item.get(k) for k in ("label", "description", "category", "completion_type",
                                          "source_entity_type", "source_field", "source_rule",
                                          "mandatory", "conditional", "condition_rule",
                                          "display_order", "evidence_required", "override_allowed",
                                          "override_max_days")}, "item_key": f"renamed.{uuid.uuid4().hex[:5]}"}
    r = requests.put(f"{API}/activation/template-items/{item['activation_template_item_id']}",
                      json=body, headers=admin_headers, timeout=15)
    assert r.status_code == 400 and "locked" in r.json()["detail"].lower()


def test_locked_template_non_structural_edit_permitted(admin_headers):
    """Label edits on a locked template are allowed."""
    t = _template_in_use(admin_headers)
    if not t:
        pytest.skip("no locked template present")
    items = requests.get(f"{API}/activation/templates/{t['activation_template_id']}/items",
                          headers=admin_headers, timeout=15).json()
    item = items[0]
    original_label = item["label"]
    body = {**{k: item.get(k) for k in ("item_key", "description", "category", "completion_type",
                                          "source_entity_type", "source_field", "source_rule",
                                          "mandatory", "conditional", "condition_rule",
                                          "display_order", "evidence_required", "override_allowed",
                                          "override_max_days")}, "label": f"{original_label} — QA touch"}
    r = requests.put(f"{API}/activation/template-items/{item['activation_template_item_id']}",
                      json=body, headers=admin_headers, timeout=15)
    assert r.status_code == 200
    # Restore original label
    body["label"] = original_label
    requests.put(f"{API}/activation/template-items/{item['activation_template_item_id']}",
                  json=body, headers=admin_headers, timeout=15)


def test_clone_as_new_version_uses_max_plus_one(admin_headers):
    t = _template_in_use(admin_headers)
    if not t:
        pytest.skip("no locked template present")
    prev = t["version"]
    r = requests.post(f"{API}/activation/templates/{t['activation_template_id']}/clone",
                       headers=admin_headers, timeout=15)
    assert r.status_code == 200
    cloned = r.json()
    assert cloned["version"] > prev
    assert cloned["is_default"] is False  # Clone never becomes default automatically


def test_historical_activation_unaffected_by_edits(admin_headers):
    """After a non-structural edit of a locked template, driver activation
    label snapshots remain the same as when the checklist was instantiated.
    """
    t = _template_in_use(admin_headers)
    if not t:
        pytest.skip("no locked template present")
    tpl_id = t["activation_template_id"]
    # Find any driver whose activation uses this template
    all_drivers = requests.get(f"{API}/drivers", headers=admin_headers, timeout=15).json()
    did = None
    for d in all_drivers[:20]:
        rec = requests.get(f"{API}/drivers/{d['id']}/activation",
                            headers=admin_headers, timeout=15).json()
        r = rec.get("record") or {}
        if r.get("activation_template_id") == tpl_id:
            did = d["id"]
            before = rec
            break
    if not did:
        pytest.skip("no driver activation on the locked template")
    snapshot_labels = {i["item_key"]: i["label_snapshot"] for i in before["items"]}

    items = requests.get(f"{API}/activation/templates/{tpl_id}/items",
                          headers=admin_headers, timeout=15).json()
    item = items[0]
    key = item["item_key"]
    original_label = item["label"]
    body = {**{k: item.get(k) for k in ("item_key", "description", "category", "completion_type",
                                          "source_entity_type", "source_field", "source_rule",
                                          "mandatory", "conditional", "condition_rule",
                                          "display_order", "evidence_required", "override_allowed",
                                          "override_max_days")},
             "label": "temporary QA edit"}
    requests.put(f"{API}/activation/template-items/{item['activation_template_item_id']}",
                  json=body, headers=admin_headers, timeout=15)
    after = requests.get(f"{API}/drivers/{did}/activation",
                          headers=admin_headers, timeout=15).json()
    after_label = next((i["label_snapshot"] for i in after["items"] if i["item_key"] == key), None)
    assert after_label == snapshot_labels[key], "instantiated snapshot label should NOT have changed"
    body["label"] = original_label
    requests.put(f"{API}/activation/template-items/{item['activation_template_item_id']}",
                  json=body, headers=admin_headers, timeout=15)
