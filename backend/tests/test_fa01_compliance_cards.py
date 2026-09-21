"""FA-01 · DCC Compliance presentation + canonical field alignment.

Static acceptance test — inspects the DCC card sources to prove:
    · Truck Insurance reads canonical `provider` (not legacy `insurer`).
    · Truck Registration reads canonical `registration_number_snapshot`
      (not the denormalised `registration_number` alias).
    · Registration Class rendered.
    · Driver Licence verification triple rendered.
    · Compliance Overview shows "n of n Compliant" primary summary while
      preserving Worst Status Wins.
    · Vehicle Compliance shows explicit Prime / Tray / Trailer rows.
    · No new compliance calculator introduced.
    · OwnershipModel canonical enum untouched (Owned / Leased /
      Sub-Contracted / Other).
"""
from __future__ import annotations

import re
from pathlib import Path

FE = Path("/app/frontend/src/components/driver-cc")
BE_REGISTERS = Path("/app/backend/registers.py")
BE_COMPL = Path("/app/backend/compliance_records.py")


def _read(p): return p.read_text(encoding="utf-8")


# ─── FA-01.1 · Truck Insurance canonical `provider` ───────────────────
class TestInsuranceProvider:
    def test_provider_field_used(self):
        src = _read(FE / "TruckInsuranceCard.jsx")
        assert "i.provider" in src, "Insurance must read canonical `provider`"
        assert 'label="Provider"' in src
        assert 'testid="ci-insurance-provider"' in src

    def test_legacy_insurer_alias_removed(self):
        src = _read(FE / "TruckInsuranceCard.jsx")
        assert "i.insurer" not in src, "legacy `insurer` alias must be gone"
        assert 'testid="ci-insurance-insurer"' not in src

    def test_evidence_actions_preserved(self):
        src = _read(FE / "TruckInsuranceCard.jsx")
        assert "EvidenceActions" in src
        assert 'testidPrefix="ci-insurance-ev"' in src


# ─── FA-01.2 · Truck Registration canonical snapshot ───────────────────
class TestRegistrationSnapshot:
    def test_snapshot_field_used(self):
        src = _read(FE / "TruckRegistrationCard.jsx")
        assert "r.registration_number_snapshot" in src

    def test_legacy_registration_number_alias_absent(self):
        src = _read(FE / "TruckRegistrationCard.jsx")
        # The card must not read the denormalised Vehicle field alias.
        # We allow the string 'registration_number_snapshot' but reject any
        # bare 'r.registration_number' access.
        assert not re.search(r"r\.registration_number(?!_snapshot)", src), \
            "Registration card must NOT read legacy `r.registration_number`"

    def test_registration_class_rendered(self):
        src = _read(FE / "TruckRegistrationCard.jsx")
        assert 'label="Class"' in src
        assert "r.registration_class" in src
        assert 'testid="ci-registration-class"' in src

    def test_evidence_actions_preserved(self):
        src = _read(FE / "TruckRegistrationCard.jsx")
        assert "EvidenceActions" in src
        assert 'testidPrefix="ci-registration-ev"' in src


# ─── FA-01.3 · Driver Licence verification triple ─────────────────────
class TestLicenceVerification:
    def test_verification_status_rendered(self):
        src = _read(FE / "DriverLicenceCard.jsx")
        assert "l.verification_status" in src
        assert 'testid="ci-licence-verification-status"' in src

    def test_verified_by_rendered(self):
        src = _read(FE / "DriverLicenceCard.jsx")
        assert "l.verified_by" in src
        assert 'testid="ci-licence-verified-by"' in src

    def test_verified_at_rendered(self):
        src = _read(FE / "DriverLicenceCard.jsx")
        assert "l.verified_at" in src
        assert 'testid="ci-licence-verified-at"' in src

    def test_evidence_actions_preserved(self):
        src = _read(FE / "DriverLicenceCard.jsx")
        assert "EvidenceActions" in src
        assert 'testidPrefix="ci-licence-ev"' in src


# ─── FA-01.4 · Compliance Overview "n of n Compliant" ─────────────────
class TestComplianceOverview:
    def test_primary_compliant_count(self):
        src = _read(FE / "ComplianceOverviewCard.jsx")
        assert 'testid="ci-compliant-count"' in src
        # Must aggregate canonical components — no new calculator.
        assert "driver_summary?.components" in src
        assert "vehicle_summary?.components" in src

    def test_worst_status_preserved(self):
        src = _read(FE / "ComplianceOverviewCard.jsx")
        assert 'testid="ci-worst-status"' in src, "Worst Status Wins must remain visible"
        assert "worst_status" in src

    def test_alert_counts_secondary(self):
        # Alert triplet may remain — it is secondary now, not primary.
        src = _read(FE / "ComplianceOverviewCard.jsx")
        assert "ci-count-active" in src
        assert "ci-count-ack" in src
        assert "ci-count-snoozed" in src


# ─── FA-01.5 · Vehicle Compliance component rows ──────────────────────
class TestVehicleComplianceComponents:
    def test_prime_row_visible(self):
        src = _read(FE / "VehicleComplianceCard.jsx")
        assert 'testid="ci-vc-prime-row"' in src
        assert 'testid="ci-vc-prime-status"' in src
        assert 'testid="ci-vc-prime-identity"' in src

    def test_tray_row_visible(self):
        src = _read(FE / "VehicleComplianceCard.jsx")
        assert 'testid="ci-vc-tray-row"' in src

    def test_trailer_row_visible(self):
        src = _read(FE / "VehicleComplianceCard.jsx")
        assert 'testid="ci-vc-trailer-row"' in src

    def test_uncoupled_states_handled(self):
        src = _read(FE / "VehicleComplianceCard.jsx")
        assert 'testid="ci-vc-tray-uncoupled"' in src
        assert 'testid="ci-vc-trailer-uncoupled"' in src

    def test_worst_status_preserved(self):
        src = _read(FE / "VehicleComplianceCard.jsx")
        assert "Worst Status Wins" in src
        assert 'testid="ci-vehicle-worst-status"' in src

    def test_no_new_calculator_introduced(self):
        # The card must consume existing canonical fields — vehicle_summary,
        # tray_equipment, trailer_equipment — and must NOT compute a new
        # component status from raw records.
        src = _read(FE / "VehicleComplianceCard.jsx")
        assert "compliance_intelligence?.vehicle_summary" in src
        assert "tray_equipment" in src
        assert "trailer_equipment" in src
        # No forbidden re-classification helpers snuck in
        assert "classifyExpiry" not in src
        assert "recompute" not in src

    def test_inspection_prime_details_preserved(self):
        src = _read(FE / "VehicleComplianceCard.jsx")
        assert 'testid="ci-inspection-date"' in src
        assert 'testid="ci-inspection-result"' in src
        assert 'testid="ci-defects-count"' in src
        assert 'testid="ci-maintenance-count"' in src


# ─── FA-01.6 · OwnershipModel enum non-regression ─────────────────────
class TestOwnershipEnumUnchanged:
    def test_enum_owned(self):
        src = _read(BE_REGISTERS)
        assert 'Owned = "Owned"' in src

    def test_enum_leased(self):
        src = _read(BE_REGISTERS)
        assert 'Leased = "Leased"' in src

    def test_enum_sub_contracted(self):
        src = _read(BE_REGISTERS)
        assert 'SubContracted = "Sub-Contracted"' in src


# ─── FA-01.7 · Confirm no data migration / denormalised write change ──
class TestNoBackendDenormalisationChange:
    def test_compliance_records_registration_write_unchanged(self):
        # We are NOT changing the backend denormalisation path in FA-01 —
        # only DCC display now uses canonical snapshot. Assert the file
        # still contains its existing behaviour reference to prove no drift.
        src = _read(BE_COMPL)
        assert "registration_number_snapshot" in src
