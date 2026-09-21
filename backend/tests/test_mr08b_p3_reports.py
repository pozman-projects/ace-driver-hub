"""MR-08B-P3 · Canonical Report Builder tests."""
from __future__ import annotations

import io
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
ADMIN = {"email": "admin@acedriverhub.com", "password": "Admin@123"}


def _tag(): return uuid.uuid4().hex[:8]


def _login(email, pw):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw}, timeout=15)
    r.raise_for_status()
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return s


def _register(admin, role):
    email = f"mr08p3-{role.lower()}-{_tag()}@acedriverhub.com"
    admin.post(f"{BASE_URL}/api/auth/register",
                json={"email": email, "password": "P@ssword1",
                      "full_name": f"MR08P3 {role}", "role": role}, timeout=15).raise_for_status()
    return _login(email, "P@ssword1")


@pytest.fixture(scope="module")
def admin(): return _login(ADMIN["email"], ADMIN["password"])
@pytest.fixture(scope="module")
def manager(admin): return _register(admin, "Manager")
@pytest.fixture(scope="module")
def compliance(admin): return _register(admin, "Compliance")
@pytest.fixture(scope="module")
def allocator(admin): return _register(admin, "Allocator")
@pytest.fixture(scope="module")
def readonly(admin): return _register(admin, "ReadOnly")


# ─── 1-3 Sources / unknown source + field ─────────────────────────────
class TestSources:
    def test_sources_allowlist(self, admin):
        r = admin.get(f"{BASE_URL}/api/reports/sources", timeout=15)
        r.raise_for_status()
        keys = {s["key"] for s in r.json()}
        expected = {"drivers", "owners", "vehicles", "equipment",
                    "driver-licences", "vehicle-registrations", "vehicle-insurance",
                    "vehicle-inspections", "vehicle-defects", "vehicle-maintenance",
                    "equipment-compliance", "activation-readiness", "documents"}
        assert expected.issubset(keys)

    def test_unknown_source_rejected(self, admin):
        r = admin.get(f"{BASE_URL}/api/reports/sources/nope/fields", timeout=15)
        assert r.status_code == 400

    def test_unknown_field_rejected_on_run(self, admin):
        r = admin.post(f"{BASE_URL}/api/reports/run",
                       json={"source": "drivers", "fields": ["not_a_field"]}, timeout=15)
        assert r.status_code == 400


# ─── 4-5 MR-07A sensitive driver fields ───────────────────────────────
class TestSensitiveDriverFields:
    def test_admin_sees_sensitive_fields(self, admin):
        r = admin.get(f"{BASE_URL}/api/reports/sources/drivers/fields", timeout=15)
        keys = {f["key"] for f in r.json()["fields"]}
        for f in ("business_name", "abn", "payroll_number", "payment_percentage"):
            assert f in keys, f"Admin missing {f}"

    def test_manager_sees_sensitive_fields(self, manager):
        r = manager.get(f"{BASE_URL}/api/reports/sources/drivers/fields", timeout=15)
        keys = {f["key"] for f in r.json()["fields"]}
        assert "business_name" in keys

    @pytest.mark.parametrize("role_name", ["compliance", "allocator", "readonly"])
    def test_non_privileged_hidden_sensitive_fields(self, request, role_name):
        sess = request.getfixturevalue(role_name)
        r = sess.get(f"{BASE_URL}/api/reports/sources/drivers/fields", timeout=15)
        keys = {f["key"] for f in r.json()["fields"]}
        for f in ("business_name", "abn", "payroll_number", "payment_percentage"):
            assert f not in keys, f"{role_name} sees {f}"

    @pytest.mark.parametrize("role_name", ["compliance", "allocator", "readonly"])
    def test_non_privileged_cannot_request_sensitive_field(self, request, role_name):
        sess = request.getfixturevalue(role_name)
        r = sess.post(f"{BASE_URL}/api/reports/run",
                       json={"source": "drivers", "fields": ["full_name", "business_name"]},
                       timeout=15)
        assert r.status_code == 403, r.text


# ─── 6 Normal Driver report for legitimate roles ──────────────────────
class TestBasicRun:
    def test_admin_can_run_driver_report(self, admin):
        r = admin.post(f"{BASE_URL}/api/reports/run",
                        json={"source": "drivers", "fields": ["full_name", "driver_status"]},
                        timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["source"] == "drivers"
        assert isinstance(body["rows"], list)
        assert set(body["rows"][0].keys()) <= {"full_name", "driver_status"} if body["rows"] else True

    def test_readonly_can_run_basic_report(self, readonly):
        r = readonly.post(f"{BASE_URL}/api/reports/run",
                           json={"source": "drivers", "fields": ["full_name"]}, timeout=30)
        assert r.status_code == 200


# ─── 7-8 Document sensitivity ─────────────────────────────────────────
class TestDocumentSensitivity:
    def _seed(self, admin, sensitivity):
        did = admin.post(f"{BASE_URL}/api/drivers",
                         json={"full_name": f"DocSeed {_tag()}", "driver_status": "Training"},
                         timeout=15).json()["id"]
        files = {"file": (f"r-{_tag()}.csv", b"a,b,c", "text/csv")}
        data = {"entity_type": "Driver", "entity_id": did, "document_type": "Other",
                "sensitivity": sensitivity, "title": f"MR08P3 {sensitivity} {_tag()}"}
        admin.post(f"{BASE_URL}/api/documents/upload", files=files, data=data, timeout=30).raise_for_status()
        return sensitivity

    def test_restricted_filtered_out_for_non_privileged(self, admin, compliance, allocator, readonly):
        self._seed(admin, "Restricted")
        for sess, role in ((compliance, "Compliance"), (allocator, "Allocator"), (readonly, "ReadOnly")):
            r = sess.post(f"{BASE_URL}/api/reports/run",
                           json={"source": "documents",
                                 "fields": ["title", "sensitivity"],
                                 "limit": 1000},
                           timeout=45)
            assert r.status_code == 200
            leaks = [row for row in r.json()["rows"] if row.get("sensitivity") == "Restricted"]
            assert not leaks, f"{role} saw Restricted document rows"

    def test_confidential_visible_to_compliance_not_allocator(self, admin, compliance, allocator):
        self._seed(admin, "Confidential")
        r_c = compliance.post(f"{BASE_URL}/api/reports/run",
                              json={"source": "documents", "fields": ["title", "sensitivity"],
                                    "limit": 1000}, timeout=45).json()
        assert any(row.get("sensitivity") == "Confidential" for row in r_c["rows"])
        r_a = allocator.post(f"{BASE_URL}/api/reports/run",
                             json={"source": "documents", "fields": ["title", "sensitivity"],
                                   "limit": 1000}, timeout=45).json()
        assert not any(row.get("sensitivity") == "Confidential" for row in r_a["rows"])


# ─── 9-13 Filter / sort validation ────────────────────────────────────
class TestFilterSortValidation:
    def test_invalid_operator_for_type(self, admin):
        r = admin.post(f"{BASE_URL}/api/reports/run",
                        json={"source": "drivers", "fields": ["full_name"],
                              "filters": [{"field": "full_name", "operator": "greater_than", "value": "x"}]},
                        timeout=15)
        assert r.status_code == 400

    def test_raw_mongo_operator_rejected(self, admin):
        r = admin.post(f"{BASE_URL}/api/reports/run",
                        json={"source": "drivers", "fields": ["full_name"],
                              "filters": [{"field": "full_name", "operator": "$where", "value": "1"}]},
                        timeout=15)
        assert r.status_code == 400

    def test_max_two_sorts(self, admin):
        r = admin.post(f"{BASE_URL}/api/reports/run",
                        json={"source": "drivers", "fields": ["full_name"],
                              "sort": [{"field": "full_name"}, {"field": "driver_status"},
                                       {"field": "start_date"}]},
                        timeout=15)
        assert r.status_code == 400

    def test_unknown_sort_field(self, admin):
        r = admin.post(f"{BASE_URL}/api/reports/run",
                        json={"source": "drivers", "fields": ["full_name"],
                              "sort": [{"field": "nope"}]}, timeout=15)
        assert r.status_code == 400


# ─── 14-16 Archive / preview limit ────────────────────────────────────
class TestPreviewLimits:
    def test_default_excludes_archived_drivers(self, admin):
        r = admin.post(f"{BASE_URL}/api/reports/run",
                        json={"source": "drivers", "fields": ["full_name", "driver_status"],
                              "limit": 1000}, timeout=45).json()
        assert not any(row.get("driver_status") == "Archived" for row in r["rows"])

    def test_limit_enforced(self, admin):
        r = admin.post(f"{BASE_URL}/api/reports/run",
                        json={"source": "drivers", "fields": ["full_name"], "limit": 5},
                        timeout=15).json()
        assert len(r["rows"]) <= 5


# ─── 17-20 CSV / XLSX ────────────────────────────────────────────────
class TestCsvXlsx:
    def test_csv_export(self, admin):
        r = admin.post(f"{BASE_URL}/api/reports/export/csv",
                        json={"source": "drivers", "fields": ["full_name", "driver_status"]},
                        timeout=45)
        assert r.status_code == 200
        eid = r.json()["export"]["id"]
        d = admin.get(f"{BASE_URL}/api/reports/exports/{eid}/download", timeout=45)
        assert d.status_code == 200
        text = d.content.decode()
        header = text.splitlines()[0]
        assert header == "Full Name,Status", header

    def test_csv_formula_neutralised(self, admin):
        # Seed a driver whose name starts with `=` to trigger neutralisation.
        admin.post(f"{BASE_URL}/api/drivers",
                    json={"full_name": "=SUM(A1)", "driver_status": "Training"},
                    timeout=15).raise_for_status()
        r = admin.post(f"{BASE_URL}/api/reports/export/csv",
                        json={"source": "drivers", "fields": ["full_name"], "limit": 1000},
                        timeout=45)
        eid = r.json()["export"]["id"]
        d = admin.get(f"{BASE_URL}/api/reports/exports/{eid}/download", timeout=45).content.decode()
        assert "=SUM(A1)" not in d.replace("'=SUM(A1)", "")
        assert "'=SUM(A1)" in d

    def test_xlsx_export(self, admin):
        r = admin.post(f"{BASE_URL}/api/reports/export/xlsx",
                        json={"source": "drivers", "fields": ["full_name"]}, timeout=60)
        assert r.status_code == 200
        eid = r.json()["export"]["id"]
        d = admin.get(f"{BASE_URL}/api/reports/exports/{eid}/download", timeout=60)
        assert d.status_code == 200
        # basic XLSX signature
        assert d.content[:2] == b"PK", "XLSX must be a valid zip"
        # verify no formula cells
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(d.content))
        ws = wb.active
        for row in ws.iter_rows(values_only=True):
            for cell in row:
                if isinstance(cell, str):
                    assert not cell.startswith("="), f"formula cell in XLSX: {cell}"


# ─── 21-22 Company display resolution (MR-08B-P3-FIX) ────────────────
class TestCompanyDisplay:
    def test_company_id_returns_raw_uuid_unmodified(self, admin):
        # Any driver row with a company_id must return the raw UUID, not a
        # resolved display name.
        r = admin.post(f"{BASE_URL}/api/reports/run",
                        json={"source": "drivers", "fields": ["full_name", "company_id"],
                              "limit": 1000}, timeout=45).json()
        import re as _re
        uuid_re = _re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
        for row in r["rows"]:
            cid = row.get("company_id")
            if cid:
                assert uuid_re.match(cid), f"company_id must be raw UUID, got: {cid!r}"

    def test_company_name_derived_field_present_in_metadata(self, admin):
        for source in ("drivers", "owners", "vehicles", "equipment"):
            fields = admin.get(f"{BASE_URL}/api/reports/sources/{source}/fields", timeout=15).json()["fields"]
            keys = {f["key"]: f for f in fields}
            assert "company_name" in keys, f"{source} missing company_name"
            assert keys["company_name"]["derived"] is True
            assert keys["company_name"]["sortable"] is False
            assert keys["company_name"]["filterable"] is False
            assert keys["company_name"]["label"] == "Company"

    def test_company_name_not_filterable(self, admin):
        r = admin.post(f"{BASE_URL}/api/reports/run",
                        json={"source": "drivers", "fields": ["full_name", "company_name"],
                              "filters": [{"field": "company_name", "operator": "equals", "value": "ACE"}]},
                        timeout=15)
        assert r.status_code == 400
        assert "not filterable" in r.text

    def test_company_name_not_sortable(self, admin):
        r = admin.post(f"{BASE_URL}/api/reports/run",
                        json={"source": "drivers", "fields": ["full_name", "company_name"],
                              "sort": [{"field": "company_name"}]},
                        timeout=15)
        assert r.status_code == 400
        assert "not sortable" in r.text


# ─── 25 Download security ────────────────────────────────────────────
class TestDownloadSecurity:
    def test_creator_can_download(self, admin):
        r = admin.post(f"{BASE_URL}/api/reports/export/csv",
                        json={"source": "drivers", "fields": ["full_name"]}, timeout=45)
        eid = r.json()["export"]["id"]
        assert admin.get(f"{BASE_URL}/api/reports/exports/{eid}/download", timeout=15).status_code == 200

    def test_non_creator_non_admin_denied(self, admin, allocator):
        r = admin.post(f"{BASE_URL}/api/reports/export/csv",
                        json={"source": "drivers", "fields": ["full_name"]}, timeout=45)
        eid = r.json()["export"]["id"]
        assert allocator.get(f"{BASE_URL}/api/reports/exports/{eid}/download", timeout=15).status_code == 403


# ─── 26 Revalidate at export time ────────────────────────────────────
class TestExportRevalidates:
    def test_compliance_cannot_export_sensitive(self, compliance):
        r = compliance.post(f"{BASE_URL}/api/reports/export/csv",
                             json={"source": "drivers", "fields": ["business_name"]},
                             timeout=15)
        assert r.status_code == 403


# ─── 29 Activation read-only ─────────────────────────────────────────
class TestActivationReadOnly:
    def test_activation_source_returns_readiness_rows(self, admin):
        r = admin.post(f"{BASE_URL}/api/reports/run",
                        json={"source": "activation-readiness",
                              "fields": ["driver_full_name", "readiness", "missing_count"],
                              "limit": 5}, timeout=45)
        assert r.status_code == 200, r.text
        for row in r.json()["rows"]:
            assert row.get("readiness") in (None, "Ready", "Not Ready", "Unknown")


# ─── 30 Existing driver PDF exports unchanged ────────────────────────
class TestDriverExportsUnchanged:
    def test_driver_start_sheet_still_works(self, admin):
        did = admin.post(f"{BASE_URL}/api/drivers",
                         json={"full_name": f"PdfSanity {_tag()}", "driver_status": "Training"},
                         timeout=15).json()["id"]
        r = admin.post(f"{BASE_URL}/api/drivers/{did}/exports/start-sheet",
                        json={"confirm": True}, timeout=60)
        # If MR-04 blocks the export we still expect a non-500 gate. 200 is
        # ideal; a policy 409 is acceptable — anything but 500.
        assert r.status_code < 500, r.text


# ═══════════════════════════════════════════════════════════════════════
# MR-08B-P3-FIX · Canonical Field Alignment · Real-fixture verification
# ═══════════════════════════════════════════════════════════════════════

def _find(rows, key, value):
    """Locate a single row in a report response by canonical key/value."""
    return next((r for r in rows if r.get(key) == value), None)


# ─── FIX-A · Owners real canonical fixture ─────────────────────────────
class TestFixOwnersCanonical:
    def test_owner_source_metadata_uses_canonical_keys(self, admin):
        fields = admin.get(f"{BASE_URL}/api/reports/sources/owners/fields", timeout=15).json()["fields"]
        keys = {f["key"] for f in fields}
        for canon in ("name", "owner_type", "abn", "primary_contact_name",
                      "mobile_number", "email", "business_address", "owner_status", "company_id", "company_name"):
            assert canon in keys, f"missing canonical Owner field: {canon}"
        # Invalid legacy names must be gone
        for gone in ("trading_name", "primary_email", "primary_phone"):
            assert gone not in keys, f"invalid legacy owner field remains: {gone}"

    def test_owner_report_returns_canonical_values(self, admin):
        tag = _tag()
        payload = {
            "name": f"Owner Alpha {tag}",
            "owner_type": "Business",
            "abn": "12345678901",
            "primary_contact_name": f"Contact {tag}",
            "mobile_number": "0400111222",
            "email": f"alpha-{tag}@ex.com",
            "business_address": "1 Alpha St, Sydney",
            "owner_status": "Active",
        }
        admin.post(f"{BASE_URL}/api/owners", json=payload, timeout=15).raise_for_status()
        r = admin.post(f"{BASE_URL}/api/reports/run",
                        json={"source": "owners",
                              "fields": ["name", "owner_type", "abn", "primary_contact_name",
                                          "mobile_number", "email", "business_address", "owner_status"],
                              "limit": 1000}, timeout=45).json()
        row = _find(r["rows"], "name", payload["name"])
        assert row is not None, f"seeded owner not found: {payload['name']}"
        for k, v in payload.items():
            assert row.get(k) == v, f"{k}: got {row.get(k)!r} expected {v!r}"

    def test_owner_abn_not_gated_by_mr07a(self, admin, compliance):
        # Owner ABN is master data, not the MR-07A Driver Account ABN. It
        # must be visible to Compliance role.
        fields = compliance.get(f"{BASE_URL}/api/reports/sources/owners/fields", timeout=15).json()["fields"]
        keys = {f["key"] for f in fields}
        assert "abn" in keys, "Owner ABN must not be MR-07A gated"


# ─── FIX-B · Equipment real canonical fixture ──────────────────────────
class TestFixEquipmentCanonical:
    def test_equipment_source_uses_equipment_status(self, admin):
        fields = admin.get(f"{BASE_URL}/api/reports/sources/equipment/fields", timeout=15).json()["fields"]
        keys = {f["key"] for f in fields}
        assert "equipment_status" in keys
        assert "status" not in keys, "invalid legacy 'status' key still exposed"

    def test_equipment_status_value_returned(self, admin):
        tag = _tag()
        oid = admin.post(f"{BASE_URL}/api/owners",
                         json={"name": f"EqOwner {tag}", "owner_type": "Business"},
                         timeout=15).json()["id"]
        num = f"EQ-{tag}"
        admin.post(f"{BASE_URL}/api/equipment",
                    json={"equipment_number": num, "equipment_type": "Trailer",
                          "equipment_status": "Available", "owner_id": oid},
                    timeout=15).raise_for_status()
        r = admin.post(f"{BASE_URL}/api/reports/run",
                        json={"source": "equipment",
                              "fields": ["equipment_number", "equipment_type", "equipment_status"],
                              "limit": 1000}, timeout=45).json()
        row = _find(r["rows"], "equipment_number", num)
        assert row is not None, f"seeded equipment not found: {num}"
        assert row["equipment_status"] == "Available"
        assert row["equipment_type"] == "Trailer"


# ─── FIX-C · Vehicle Insurance real canonical fixture ─────────────────
class TestFixVehicleInsuranceCanonical:
    def _seed_vehicle(self, admin, tag):
        return admin.post(f"{BASE_URL}/api/vehicles",
                            json={"registration_number": f"INS-{tag}",
                                  "make": "Volvo", "model": "FH", "vin": f"VIN-INS-{tag}"},
                            timeout=15).json()["id"]

    def test_insurance_source_uses_provider_cover_type(self, admin):
        fields = admin.get(f"{BASE_URL}/api/reports/sources/vehicle-insurance/fields", timeout=15).json()["fields"]
        keys = {f["key"] for f in fields}
        assert "provider" in keys and "cover_type" in keys
        assert "insurer" not in keys and "policy_type" not in keys

    def test_insurance_report_returns_provider_and_cover_type(self, admin):
        tag = _tag()
        vid = self._seed_vehicle(admin, tag)
        pol = f"POL-{tag}"
        admin.post(f"{BASE_URL}/api/vehicle-insurance",
                    json={"vehicle_id": vid, "policy_number": pol,
                          "provider": f"AlphaInsurer-{tag}",
                          "cover_type": "Comprehensive",
                          "expiry_date": "2099-01-01"},
                    timeout=15).raise_for_status()
        r = admin.post(f"{BASE_URL}/api/reports/run",
                        json={"source": "vehicle-insurance",
                              "fields": ["policy_number", "provider", "cover_type", "expiry_date"],
                              "filters": [{"field": "policy_number", "operator": "equals", "value": pol}],
                              "limit": 1000}, timeout=45).json()
        row = _find(r["rows"], "policy_number", pol)
        assert row is not None
        assert row["provider"] == f"AlphaInsurer-{tag}"
        assert row["cover_type"] == "Comprehensive"


# ─── FIX-D · Vehicle Inspections real canonical fixture ───────────────
class TestFixVehicleInspectionsCanonical:
    def test_inspection_source_uses_result_and_inspector_name(self, admin):
        fields = admin.get(f"{BASE_URL}/api/reports/sources/vehicle-inspections/fields", timeout=15).json()["fields"]
        keys = {f["key"] for f in fields}
        assert "result" in keys and "inspector_name" in keys
        assert "outcome" not in keys and "inspector" not in keys

    def test_inspection_report_returns_result_and_inspector(self, admin):
        tag = _tag()
        vid = admin.post(f"{BASE_URL}/api/vehicles",
                          json={"registration_number": f"INS2-{tag}",
                                "make": "Isuzu", "model": "NPR", "vin": f"VIN-INS2-{tag}"},
                          timeout=15).json()["id"]
        insp_id = admin.post(f"{BASE_URL}/api/vehicle-inspections",
                              json={"vehicle_id": vid,
                                    "inspection_type": "Scheduled Inspection",
                                    "inspection_date": "2026-01-15",
                                    "result": "Pass",
                                    "inspector_name": f"Insp-{tag}"},
                              timeout=15).json()["id"]
        assert insp_id
        r = admin.post(f"{BASE_URL}/api/reports/run",
                        json={"source": "vehicle-inspections",
                              "fields": ["inspection_type", "inspection_date", "result", "inspector_name"],
                              "limit": 1000}, timeout=45).json()
        row = next((rr for rr in r["rows"] if rr.get("inspector_name") == f"Insp-{tag}"), None)
        assert row is not None
        assert row["result"] == "Pass"
        assert row["inspection_type"] == "Scheduled Inspection"


# ─── FIX-E · Vehicle Defects real canonical fixture ────────────────────
class TestFixVehicleDefectsCanonical:
    def test_defect_source_uses_reported_date_rectified_date(self, admin):
        fields = admin.get(f"{BASE_URL}/api/reports/sources/vehicle-defects/fields", timeout=15).json()["fields"]
        keys = {f["key"] for f in fields}
        assert "reported_date" in keys and "rectified_date" in keys
        assert "reported_at" not in keys and "resolved_at" not in keys

    def test_defect_report_returns_dates(self, admin):
        tag = _tag()
        vid = admin.post(f"{BASE_URL}/api/vehicles",
                          json={"registration_number": f"DEF-{tag}",
                                "make": "Mack", "model": "Trident", "vin": f"VIN-DEF-{tag}"},
                          timeout=15).json()["id"]
        desc = f"Defect {tag}"
        admin.post(f"{BASE_URL}/api/vehicle-defects",
                    json={"vehicle_id": vid,
                          "reported_date": "2026-02-01",
                          "rectified_date": "2026-02-05",
                          "severity": "Low", "status": "Rectified",
                          "description": desc},
                    timeout=15).raise_for_status()
        r = admin.post(f"{BASE_URL}/api/reports/run",
                        json={"source": "vehicle-defects",
                              "fields": ["reported_date", "rectified_date", "severity", "status", "description"],
                              "limit": 1000}, timeout=45).json()
        row = _find(r["rows"], "description", desc)
        assert row is not None
        assert row["reported_date"] == "2026-02-01"
        assert row["rectified_date"] == "2026-02-05"
        assert row["severity"] == "Low"
        assert row["status"] == "Rectified"


# ─── FIX-F · Equipment Compliance real canonical fixture ──────────────
class TestFixEquipmentComplianceCanonical:
    def test_ec_source_removes_invented_check_fields(self, admin):
        fields = admin.get(f"{BASE_URL}/api/reports/sources/equipment-compliance/fields", timeout=15).json()["fields"]
        keys = {f["key"] for f in fields}
        for canon in ("compliance_type", "reference_number", "effective_date", "expiry_date",
                       "status", "is_current", "is_mandatory", "verification_status"):
            assert canon in keys, f"missing canonical EC field: {canon}"
        for gone in ("check_type", "check_date", "outcome"):
            assert gone not in keys, f"invalid EC field remains: {gone}"

    def test_ec_report_returns_canonical_values(self, admin):
        tag = _tag()
        oid = admin.post(f"{BASE_URL}/api/owners",
                         json={"name": f"ECOwner {tag}", "owner_type": "Business"},
                         timeout=15).json()["id"]
        eid = admin.post(f"{BASE_URL}/api/equipment",
                         json={"equipment_number": f"EC-{tag}", "equipment_type": "Trailer",
                               "equipment_status": "Available", "owner_id": oid},
                         timeout=15).json()["id"]
        ref = f"REF-{tag}"
        admin.post(f"{BASE_URL}/api/equipment-compliance",
                    json={"equipment_id": eid,
                          "compliance_type": "Registration",
                          "reference_number": ref,
                          "effective_date": "2026-01-01",
                          "expiry_date": "2027-01-01",
                          "status": "Compliant",
                          "verification_status": "Verified"},
                    timeout=15).raise_for_status()
        r = admin.post(f"{BASE_URL}/api/reports/run",
                        json={"source": "equipment-compliance",
                              "fields": ["compliance_type", "reference_number", "effective_date",
                                          "expiry_date", "status", "verification_status"],
                              "limit": 1000}, timeout=45).json()
        row = _find(r["rows"], "reference_number", ref)
        assert row is not None
        assert row["compliance_type"] == "Registration"
        assert row["effective_date"] == "2026-01-01"
        assert row["expiry_date"] == "2027-01-01"
        assert row["status"] == "Compliant"
        assert row["verification_status"] == "Verified"


# ─── FIX-G · Vehicle Registration new canonical fixture ───────────────
class TestFixVehicleRegistrationCanonical:
    def test_registration_source_adds_snapshot_and_class(self, admin):
        fields = admin.get(f"{BASE_URL}/api/reports/sources/vehicle-registrations/fields", timeout=15).json()["fields"]
        keys = {f["key"] for f in fields}
        assert "registration_number_snapshot" in keys
        assert "registration_class" in keys

    def test_registration_report_returns_new_fields(self, admin):
        tag = _tag()
        vid = admin.post(f"{BASE_URL}/api/vehicles",
                          json={"registration_number": f"REG-{tag}",
                                "make": "Kenworth", "model": "T410", "vin": f"VIN-REG-{tag}"},
                          timeout=15).json()["id"]
        snap = f"SNAP-{tag}"
        admin.post(f"{BASE_URL}/api/vehicle-registrations",
                    json={"vehicle_id": vid,
                          "registration_number_snapshot": snap,
                          "registration_class": "Heavy Vehicle",
                          "state": "NSW",
                          "expiry_date": "2027-06-30"},
                    timeout=15).raise_for_status()
        r = admin.post(f"{BASE_URL}/api/reports/run",
                        json={"source": "vehicle-registrations",
                              "fields": ["registration_number_snapshot", "registration_class",
                                          "state", "expiry_date"],
                              "limit": 1000}, timeout=45).json()
        row = _find(r["rows"], "registration_number_snapshot", snap)
        assert row is not None
        assert row["registration_class"] == "Heavy Vehicle"
        assert row["state"] == "NSW"
        assert row["expiry_date"] == "2027-06-30"


# ─── FIX-H · Driver Licence new canonical fixture ─────────────────────
class TestFixDriverLicenceCanonical:
    def test_dl_source_adds_issue_date_verification_status(self, admin):
        fields = admin.get(f"{BASE_URL}/api/reports/sources/driver-licences/fields", timeout=15).json()["fields"]
        keys = {f["key"] for f in fields}
        assert "issue_date" in keys
        assert "verification_status" in keys

    def test_dl_report_returns_new_fields(self, admin):
        tag = _tag()
        did = admin.post(f"{BASE_URL}/api/drivers",
                          json={"full_name": f"DL Driver {tag}", "driver_status": "Training"},
                          timeout=15).json()["id"]
        num = f"DL-{tag}"
        admin.post(f"{BASE_URL}/api/driver-licences",
                    json={"driver_id": did, "licence_number": num,
                          "issue_date": "2020-05-05",
                          "expiry_date": "2028-05-05",
                          "verification_status": "Verified"},
                    timeout=15).raise_for_status()
        r = admin.post(f"{BASE_URL}/api/reports/run",
                        json={"source": "driver-licences",
                              "fields": ["licence_number", "issue_date", "expiry_date", "verification_status"],
                              "filters": [{"field": "licence_number", "operator": "equals", "value": num}],
                              "limit": 1000}, timeout=45).json()
        row = _find(r["rows"], "licence_number", num)
        assert row is not None
        assert row["issue_date"] == "2020-05-05"
        assert row["expiry_date"] == "2028-05-05"
        assert row["verification_status"] == "Verified"


# ─── FIX-I · Documents · entity_type/entity_id removal ────────────────
class TestFixDocumentsCanonical:
    def test_documents_source_removes_entity_fields(self, admin):
        fields = admin.get(f"{BASE_URL}/api/reports/sources/documents/fields", timeout=15).json()["fields"]
        keys = {f["key"] for f in fields}
        assert "entity_type" not in keys, "entity_type must not be on documents source (lives on document_links)"
        assert "entity_id" not in keys, "entity_id must not be on documents source (lives on document_links)"
        for canon in ("title", "document_type", "sensitivity", "status", "created_at"):
            assert canon in keys


# ─── FIX-J · Company canonical fixture · id vs name behaviour ─────────
class TestFixCompanyIdVsName:
    def _make_company(self, admin, tag):
        r = admin.post(f"{BASE_URL}/api/companies",
                        json={"name": f"ACE Test Co {tag}"}, timeout=15)
        r.raise_for_status()
        return r.json()

    def test_company_id_returns_uuid_and_company_name_returns_name(self, admin):
        tag = _tag()
        comp = self._make_company(admin, tag)
        comp_id, comp_name = comp["id"], comp["name"]
        full_name = f"CompDriver {tag}"
        did = admin.post(f"{BASE_URL}/api/drivers",
                          json={"full_name": full_name,
                                "driver_status": "Training",
                                "company_id": comp_id,
                                "company_ref": comp_name},
                          timeout=15).json()["id"]
        assert did
        r = admin.post(f"{BASE_URL}/api/reports/run",
                        json={"source": "drivers",
                              "fields": ["full_name", "company_id", "company_name"],
                              "filters": [{"field": "full_name", "operator": "equals", "value": full_name}],
                              "limit": 1000}, timeout=45).json()
        row = _find(r["rows"], "full_name", full_name)
        assert row is not None
        assert row["company_id"] == comp_id, f"raw UUID expected, got {row['company_id']!r}"
        assert row["company_name"] == comp_name

    def test_legacy_company_ref_fallback_populates_company_name(self, admin):
        tag = _tag()
        legacy = f"Legacy ACE {tag}"
        full_name = f"LegacyDriver {tag}"
        did = admin.post(f"{BASE_URL}/api/drivers",
                          json={"full_name": full_name,
                                "driver_status": "Training",
                                "company_ref": legacy},
                          timeout=15).json()["id"]
        # Company Manager may auto-inject a default company_id; overwrite it
        # to None so the legacy fallback path is exercised.
        admin.put(f"{BASE_URL}/api/drivers/{did}",
                    json={"company_id": None}, timeout=15).raise_for_status()
        r = admin.post(f"{BASE_URL}/api/reports/run",
                        json={"source": "drivers",
                              "fields": ["full_name", "company_id", "company_name"],
                              "filters": [{"field": "full_name", "operator": "equals", "value": full_name}],
                              "limit": 1000}, timeout=45).json()
        row = _find(r["rows"], "full_name", full_name)
        assert row is not None
        assert row["company_id"] in (None, "")
        assert row["company_name"] == legacy


# ─── FIX-K · Filter tests on real canonical keys ──────────────────────
class TestFixFiltersOnCanonicalKeys:
    def test_filter_owner_email(self, admin):
        tag = _tag()
        email = f"filt-{tag}@ex.com"
        admin.post(f"{BASE_URL}/api/owners",
                    json={"name": f"FilterOwner {tag}", "owner_type": "Business", "email": email},
                    timeout=15).raise_for_status()
        r = admin.post(f"{BASE_URL}/api/reports/run",
                        json={"source": "owners",
                              "fields": ["name", "email"],
                              "filters": [{"field": "email", "operator": "equals", "value": email}],
                              "limit": 500}, timeout=30).json()
        assert len(r["rows"]) == 1
        assert r["rows"][0]["email"] == email

    def test_filter_equipment_status(self, admin):
        tag = _tag()
        oid = admin.post(f"{BASE_URL}/api/owners",
                         json={"name": f"FS Owner {tag}", "owner_type": "Business"},
                         timeout=15).json()["id"]
        admin.post(f"{BASE_URL}/api/equipment",
                    json={"equipment_number": f"FS-{tag}-A", "equipment_type": "Trailer",
                          "equipment_status": "Maintenance", "owner_id": oid},
                    timeout=15).raise_for_status()
        r = admin.post(f"{BASE_URL}/api/reports/run",
                        json={"source": "equipment",
                              "fields": ["equipment_number", "equipment_status"],
                              "filters": [{"field": "equipment_status", "operator": "equals", "value": "Maintenance"}],
                              "limit": 500}, timeout=30).json()
        for row in r["rows"]:
            assert row["equipment_status"] == "Maintenance"

    def test_filter_insurance_provider(self, admin):
        tag = _tag()
        vid = admin.post(f"{BASE_URL}/api/vehicles",
                          json={"registration_number": f"FIP-{tag}",
                                "make": "Isuzu", "model": "F", "vin": f"VIN-FIP-{tag}"},
                          timeout=15).json()["id"]
        prov = f"ProvFilt-{tag}"
        admin.post(f"{BASE_URL}/api/vehicle-insurance",
                    json={"vehicle_id": vid, "policy_number": f"POLFIP-{tag}",
                          "provider": prov, "cover_type": "Third Party"},
                    timeout=15).raise_for_status()
        r = admin.post(f"{BASE_URL}/api/reports/run",
                        json={"source": "vehicle-insurance",
                              "fields": ["policy_number", "provider"],
                              "filters": [{"field": "provider", "operator": "equals", "value": prov}],
                              "limit": 500}, timeout=30).json()
        assert len(r["rows"]) >= 1
        for row in r["rows"]:
            assert row["provider"] == prov

    def test_filter_inspection_result(self, admin):
        tag = _tag()
        vid = admin.post(f"{BASE_URL}/api/vehicles",
                          json={"registration_number": f"FIR-{tag}",
                                "make": "Ford", "model": "F150", "vin": f"VIN-FIR-{tag}"},
                          timeout=15).json()["id"]
        admin.post(f"{BASE_URL}/api/vehicle-inspections",
                    json={"vehicle_id": vid, "inspection_type": "Scheduled Inspection",
                          "inspection_date": "2026-03-01", "result": "Fail",
                          "inspector_name": f"InsFilt-{tag}"},
                    timeout=15).raise_for_status()
        r = admin.post(f"{BASE_URL}/api/reports/run",
                        json={"source": "vehicle-inspections",
                              "fields": ["inspection_date", "result", "inspector_name"],
                              "filters": [{"field": "result", "operator": "equals", "value": "Fail"}],
                              "limit": 500}, timeout=30).json()
        assert len(r["rows"]) >= 1
        for row in r["rows"]:
            assert row["result"] == "Fail"

    def test_filter_defect_reported_date(self, admin):
        tag = _tag()
        vid = admin.post(f"{BASE_URL}/api/vehicles",
                          json={"registration_number": f"FDF-{tag}",
                                "make": "Volvo", "model": "F", "vin": f"VIN-FDF-{tag}"},
                          timeout=15).json()["id"]
        admin.post(f"{BASE_URL}/api/vehicle-defects",
                    json={"vehicle_id": vid, "severity": "High", "status": "Open",
                          "reported_date": "2026-04-10",
                          "description": f"FiltDefect-{tag}"},
                    timeout=15).raise_for_status()
        r = admin.post(f"{BASE_URL}/api/reports/run",
                        json={"source": "vehicle-defects",
                              "fields": ["description", "reported_date"],
                              "filters": [{"field": "reported_date", "operator": "equals", "value": "2026-04-10"}],
                              "limit": 500}, timeout=30).json()
        assert any(r0["description"] == f"FiltDefect-{tag}" for r0 in r["rows"])

    def test_filter_equipment_compliance_type(self, admin):
        tag = _tag()
        oid = admin.post(f"{BASE_URL}/api/owners",
                         json={"name": f"ECT Owner {tag}", "owner_type": "Business"},
                         timeout=15).json()["id"]
        eid = admin.post(f"{BASE_URL}/api/equipment",
                         json={"equipment_number": f"ECT-{tag}", "equipment_type": "Trailer",
                               "equipment_status": "Available", "owner_id": oid},
                         timeout=15).json()["id"]
        admin.post(f"{BASE_URL}/api/equipment-compliance",
                    json={"equipment_id": eid,
                          "compliance_type": "Certification",
                          "reference_number": f"ECREF-{tag}",
                          "effective_date": "2026-01-01",
                          "expiry_date": "2027-01-01",
                          "status": "Compliant"},
                    timeout=15).raise_for_status()
        r = admin.post(f"{BASE_URL}/api/reports/run",
                        json={"source": "equipment-compliance",
                              "fields": ["compliance_type", "reference_number"],
                              "filters": [{"field": "compliance_type", "operator": "equals", "value": "Certification"}],
                              "limit": 500}, timeout=30).json()
        assert any(r0["reference_number"] == f"ECREF-{tag}" for r0 in r["rows"])


# ─── FIX-L · Sort tests on real canonical keys ────────────────────────
class TestFixSortsOnCanonicalKeys:
    def test_sort_owner_name(self, admin):
        r = admin.post(f"{BASE_URL}/api/reports/run",
                        json={"source": "owners",
                              "fields": ["name"], "sort": [{"field": "name", "direction": "asc"}],
                              "limit": 500}, timeout=30).json()
        names = [r0.get("name") for r0 in r["rows"] if r0.get("name")]
        assert names == sorted(names)

    def test_sort_equipment_status(self, admin):
        r = admin.post(f"{BASE_URL}/api/reports/run",
                        json={"source": "equipment",
                              "fields": ["equipment_number", "equipment_status"],
                              "sort": [{"field": "equipment_status", "direction": "asc"}],
                              "limit": 500}, timeout=30).json()
        statuses = [r0.get("equipment_status") for r0 in r["rows"] if r0.get("equipment_status")]
        assert statuses == sorted(statuses)

    def test_sort_insurance_provider(self, admin):
        r = admin.post(f"{BASE_URL}/api/reports/run",
                        json={"source": "vehicle-insurance",
                              "fields": ["policy_number", "provider"],
                              "sort": [{"field": "provider", "direction": "desc"}],
                              "limit": 500}, timeout=30).json()
        provs = [r0.get("provider") for r0 in r["rows"] if r0.get("provider")]
        assert provs == sorted(provs, reverse=True)

    def test_sort_inspection_date(self, admin):
        r = admin.post(f"{BASE_URL}/api/reports/run",
                        json={"source": "vehicle-inspections",
                              "fields": ["inspection_date", "result"],
                              "sort": [{"field": "inspection_date", "direction": "asc"}],
                              "limit": 500}, timeout=30).json()
        dates = [r0.get("inspection_date") for r0 in r["rows"] if r0.get("inspection_date")]
        assert dates == sorted(dates)


# ─── FIX-M · CSV / XLSX with real canonical data ──────────────────────
class TestFixCsvXlsxCanonical:
    def test_owner_csv_has_canonical_values(self, admin):
        tag = _tag()
        payload = {"name": f"CSV Owner {tag}", "owner_type": "Business",
                    "primary_contact_name": f"CP-{tag}",
                    "mobile_number": "0400999888",
                    "email": f"csv-{tag}@ex.com",
                    "owner_status": "Active"}
        admin.post(f"{BASE_URL}/api/owners", json=payload, timeout=15).raise_for_status()
        r = admin.post(f"{BASE_URL}/api/reports/export/csv",
                        json={"source": "owners",
                              "fields": ["name", "primary_contact_name", "mobile_number", "email", "owner_status"],
                              "limit": 1000},
                        timeout=60)
        assert r.status_code == 200
        eid = r.json()["export"]["id"]
        d = admin.get(f"{BASE_URL}/api/reports/exports/{eid}/download", timeout=45).content.decode()
        header = d.splitlines()[0]
        assert header == "Owner Name,Primary Contact,Mobile,Email,Status"
        assert f"CSV Owner {tag}" in d
        assert f"csv-{tag}@ex.com" in d
        assert f"CP-{tag}" in d
        # No blank-column indicator (5 columns per row after neutralisation)
        for line in d.splitlines()[1:]:
            if line.startswith(f"CSV Owner {tag},"):
                assert line.count(",") == 4

    def test_company_id_and_company_name_both_export(self, admin):
        tag = _tag()
        comp = admin.post(f"{BASE_URL}/api/companies",
                            json={"name": f"CSV Co {tag}"}, timeout=15).json()
        admin.post(f"{BASE_URL}/api/drivers",
                    json={"full_name": f"CSVCompDriver {tag}", "driver_status": "Training",
                          "company_id": comp["id"], "company_ref": comp["name"]},
                    timeout=15).raise_for_status()
        r = admin.post(f"{BASE_URL}/api/reports/export/csv",
                        json={"source": "drivers",
                              "fields": ["full_name", "company_id", "company_name"],
                              "limit": 1000}, timeout=60)
        eid = r.json()["export"]["id"]
        d = admin.get(f"{BASE_URL}/api/reports/exports/{eid}/download", timeout=45).content.decode()
        target = [ln for ln in d.splitlines() if ln.startswith(f"CSVCompDriver {tag},")]
        assert target, "seeded driver not in CSV"
        # header order preserved: Full Name,Company ID,Company
        assert d.splitlines()[0] == "Full Name,Company ID,Company"
        assert comp["id"] in target[0]
        assert comp["name"] in target[0]

    def test_xlsx_no_formulas_on_canonical_data(self, admin):
        r = admin.post(f"{BASE_URL}/api/reports/export/xlsx",
                        json={"source": "owners",
                              "fields": ["name", "owner_status"], "limit": 200}, timeout=60)
        eid = r.json()["export"]["id"]
        d = admin.get(f"{BASE_URL}/api/reports/exports/{eid}/download", timeout=45).content
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(d))
        ws = wb.active
        for row in ws.iter_rows(values_only=True):
            for cell in row:
                if isinstance(cell, str):
                    assert not cell.startswith("="), f"formula in xlsx: {cell}"


# ─── FIX-N · Structural registry alignment (recurrence guard) ─────────
class TestFixStructuralRegistryAlignment:
    """MR-08B-P3-FIX · This test intentionally imports canonical Pydantic
    models directly and verifies every non-derived REPORT_SOURCES field
    key exists in the canonical source model. It is designed to catch
    invented stored-field keys before they ship."""

    def test_every_non_derived_field_key_matches_canonical_schema(self):
        import sys, os
        sys.path.insert(0, "/app/backend")
        from report_builder_module import REPORT_SOURCES
        from registers import DriverBase, OwnerBase, VehicleBase, EquipmentBase
        from compliance_records import (
            DriverLicenceBase, VehicleRegistrationBase, VehicleInsuranceBase,
            VehicleInspectionBase, VehicleDefectBase, MaintenanceTaskBase,
            EquipmentComplianceBase,
        )

        def fields_of(model):
            return set(model.model_fields.keys())

        # Canonical schema fields per source. company_ref / company_id are
        # optional stored fields on register models — both remain valid.
        SCHEMAS = {
            "drivers": fields_of(DriverBase),
            "owners": fields_of(OwnerBase),
            "vehicles": fields_of(VehicleBase),
            "equipment": fields_of(EquipmentBase),
            "driver-licences": fields_of(DriverLicenceBase),
            "vehicle-registrations": fields_of(VehicleRegistrationBase),
            "vehicle-insurance": fields_of(VehicleInsuranceBase),
            "vehicle-inspections": fields_of(VehicleInspectionBase),
            "vehicle-defects": fields_of(VehicleDefectBase),
            "vehicle-maintenance": fields_of(MaintenanceTaskBase),
            "equipment-compliance": fields_of(EquipmentComplianceBase),
        }
        # Documents source is verified separately because it reads the
        # `documents` collection (not a single Pydantic base).
        DOC_ALLOWED = {"title", "document_type", "sensitivity", "status", "created_at"}

        for src_key, source in REPORT_SOURCES.items():
            if src_key == "activation-readiness":
                # Every field must be marked derived on the virtual source.
                for f in source.fields:
                    assert f.derived, f"activation-readiness · {f.key} must be derived"
                continue
            if src_key == "documents":
                for f in source.fields:
                    assert f.key in DOC_ALLOWED, f"documents · unexpected field {f.key}"
                continue
            allowed = SCHEMAS[src_key]
            for f in source.fields:
                if f.derived:
                    continue
                assert f.key in allowed, (
                    f"{src_key}: report field '{f.key}' is not on the canonical "
                    f"model (canonical keys: {sorted(allowed)})")


# ─── FIX-O · MR-07A regression (unchanged) ────────────────────────────
class TestFixMr07aRegression:
    @pytest.mark.parametrize("field", ["business_name", "abn", "payroll_number", "payment_percentage"])
    def test_sensitive_driver_field_still_gated(self, compliance, field):
        r = compliance.post(f"{BASE_URL}/api/reports/run",
                             json={"source": "drivers",
                                   "fields": ["full_name", field]}, timeout=15)
        assert r.status_code == 403
