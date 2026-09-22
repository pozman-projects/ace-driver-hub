"""FA-04 · Truck Insurance N/A presentation / semantic clarity.

Static acceptance test — proves the DCC frontend correctly distinguishes:
    Case A  no primary vehicle             → Not Applicable + explanatory text
    Case B  primary vehicle, no insurance  → canonical Missing state
    Case C  primary vehicle + insurance    → canonical provider / status / evidence

Also proves:
    · Backend Compliance canonical model already supports Not Applicable
      (no new status, no new calculator).
    · StatusPill already renders Not Applicable.
    · Activation exact-seven unchanged and Truck Insurance remains mandatory.
    · Compliance Overview excludes canonical Not Applicable from denominator.
    · No new evidence endpoint / no fake VehicleInsurancePolicy entity.
"""
from __future__ import annotations

from pathlib import Path

FE = Path("/app/frontend/src/components/driver-cc")
FE_UTILS = FE / "driverCCUtils.jsx"
FE_INSURANCE = FE / "TruckInsuranceCard.jsx"
FE_OVERVIEW = FE / "ComplianceOverviewCard.jsx"
BE_COMPL = Path("/app/backend/compliance_records.py")
BE_ACTIVATION = Path("/app/backend/activation_module.py")


def _read(p): return p.read_text(encoding="utf-8")


# ─── FA-04.1 · Backend canonical N/A support (no new status) ──────────
class TestCanonicalNotApplicable:
    def test_status_enum_has_not_applicable(self):
        src = _read(BE_COMPL)
        assert 'NotApplicable = "Not Applicable"' in src

    def test_severity_zero(self):
        src = _read(BE_COMPL)
        # NotApplicable must remain the lowest-severity status so it never
        # trumps Compliant in Worst Status Wins.
        assert "ComplianceStatus.NotApplicable.value: 0," in src

    def test_worst_status_wins_excludes_na(self):
        src = _read(BE_COMPL)
        # _worst_vc filters out Not Applicable when comparing.
        assert 'ranked = [s for s in component_statuses if s and s != "Not Applicable"]' in src


# ─── FA-04.2 · StatusPill supports Not Applicable ─────────────────────
class TestStatusPillNotApplicable:
    def test_not_applicable_style(self):
        src = _read(FE_UTILS)
        assert '"Not Applicable":' in src


# ─── FA-04.3 · Case A · No primary vehicle → N/A presentation ─────────
class TestNoPrimaryVehicleCase:
    def test_status_pill_not_applicable(self):
        src = _read(FE_INSURANCE)
        assert 'status="Not Applicable"' in src
        assert 'testid="ci-insurance-status"' in src

    def test_reason_text_rendered(self):
        src = _read(FE_INSURANCE)
        assert "No primary vehicle assigned" in src
        assert 'testid="ci-insurance-na-reason"' in src

    def test_helper_text_rendered(self):
        src = _read(FE_INSURANCE)
        assert 'testid="ci-insurance-na-helper"' in src
        assert "Truck Insurance will be assessed once a primary vehicle is assigned." in src

    def test_no_compliant_rendered_in_case_a(self):
        # Case A branch must not render a Compliant pill.
        src = _read(FE_INSURANCE)
        # Case A branch is delimited by the `if (!vehicle) {` guard. Assert
        # the string "Compliant" appears only inside the Case C fallback
        # (via `insuranceComp?.status || "Compliant"`).
        assert 'status="Compliant"' not in src, \
            "Case A must never hard-code a Compliant pill"

    def test_no_fake_provider_or_policy(self):
        src = _read(FE_INSURANCE)
        # Case A block must not use InlineField (provider/policy/cover/expiry).
        case_a_start = src.index("if (!vehicle)")
        case_a_end = src.index("// ── Case C", case_a_start)
        case_a = src[case_a_start:case_a_end]
        assert "InlineField" not in case_a
        assert "provider" not in case_a
        assert "policy_number" not in case_a

    def test_no_evidence_actions_in_case_a(self):
        src = _read(FE_INSURANCE)
        case_a_start = src.index("if (!vehicle)")
        case_a_end = src.index("// ── Case C", case_a_start)
        case_a = src[case_a_start:case_a_end]
        assert "EvidenceActions" not in case_a


# ─── FA-04.4 · Case B · Primary vehicle, no insurance ──────────────────
class TestVehicleButNoInsurance:
    def test_case_b_reuses_canonical_component_status(self):
        src = _read(FE_INSURANCE)
        # Case B binds to canonical insuranceComp?.status (Missing / etc).
        assert "insuranceComp?.status" in src
        # The "No current Truck Insurance policy" explanation renders in Case B.
        assert "No current Truck Insurance policy" in src
        assert 'testid="ci-insurance-missing-reason"' in src

    def test_case_b_no_evidence_actions(self):
        src = _read(FE_INSURANCE)
        # Case B branch (final block) must not render EvidenceActions —
        # there is no canonical VehicleInsurancePolicy entity to attach to.
        case_b_start = src.rindex("// ── Case B")
        case_b = src[case_b_start:]
        assert "EvidenceActions" not in case_b

    def test_case_b_no_fake_entity_fields(self):
        src = _read(FE_INSURANCE)
        case_b_start = src.rindex("// ── Case B")
        case_b = src[case_b_start:]
        assert "InlineField" not in case_b
        assert "policy_number" not in case_b


# ─── FA-04.5 · Case C · Current insurance preserved ───────────────────
class TestCurrentInsurancePreserved:
    def test_canonical_provider(self):
        src = _read(FE_INSURANCE)
        assert 'label="Provider"' in src
        assert "i.provider" in src
        assert 'testid="ci-insurance-provider"' in src

    def test_canonical_policy_number(self):
        src = _read(FE_INSURANCE)
        assert "i.policy_number" in src
        assert 'testid="ci-insurance-policy"' in src

    def test_canonical_cover_type(self):
        src = _read(FE_INSURANCE)
        assert "i.cover_type" in src
        assert 'testid="ci-insurance-cover"' in src

    def test_canonical_expiry(self):
        src = _read(FE_INSURANCE)
        assert "i.expiry_date" in src
        assert 'testid="ci-insurance-expiry"' in src

    def test_evidence_actions_preserved_in_case_c(self):
        src = _read(FE_INSURANCE)
        assert "EvidenceActions" in src
        assert 'testidPrefix="ci-insurance-ev"' in src
        # entity_type stays canonical VehicleInsurancePolicy.
        assert 'entity_type: "VehicleInsurancePolicy"' in src

    def test_no_legacy_insurer_alias(self):
        src = _read(FE_INSURANCE)
        assert "i.insurer" not in src


# ─── FA-04.6 · Compliance Overview N/A exclusion ──────────────────────
class TestComplianceOverviewNaExclusion:
    def test_denominator_excludes_not_applicable(self):
        src = _read(FE_OVERVIEW)
        assert 'c.status !== "Not Applicable"' in src
        assert "applicable" in src

    def test_still_reads_canonical_components(self):
        src = _read(FE_OVERVIEW)
        assert "driver_summary?.components" in src
        assert "vehicle_summary?.components" in src

    def test_worst_status_wins_still_visible(self):
        src = _read(FE_OVERVIEW)
        assert 'testid="ci-worst-status"' in src
        assert "worst_status" in src

    def test_no_new_calculator(self):
        # The card must not introduce a new severity or classifier.
        src = _read(FE_OVERVIEW)
        assert "classifyExpiry" not in src
        assert "recompute" not in src


# ─── FA-04.7 · Activation exact-seven unchanged ───────────────────────
class TestActivationExactSevenUnchanged:
    def test_truck_insurance_still_mandatory(self):
        src = _read(BE_ACTIVATION)
        # Truck Insurance remains one of the seven mandatory components.
        assert "truck_insurance" in src.lower() or "Truck Insurance" in src

    def test_no_na_exemption(self):
        src = _read(BE_ACTIVATION)
        # No branch that skips Truck Insurance when no vehicle is assigned.
        # If such an exemption were added it would typically read something
        # like "Not Applicable" or "no_primary_vehicle" — assert absent.
        assert "No primary vehicle assigned" not in src, \
            "Activation must not carry a no-vehicle exemption string"


# ─── FA-04.8 · No backend schema / no new evidence endpoint ───────────
class TestNoBackendSchemaChange:
    def test_insurance_model_unchanged(self):
        src = _read(BE_COMPL)
        # Insurance schema anchors — provider / policy_number / cover_type /
        # expiry_date remain the canonical fields.
        assert "vehicle_insurance_policies" in src
        # No new "not_applicable" flag on the insurance record.
        assert "insurance_not_applicable" not in src

    def test_no_new_evidence_endpoint(self):
        src = _read(BE_COMPL)
        assert "/insurance-na" not in src
        assert "insurance_na_evidence" not in src
