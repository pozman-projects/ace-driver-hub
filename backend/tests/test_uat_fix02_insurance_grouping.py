"""UAT-FIX-02 · Truck Insurance evidence visual grouping.

Locks in the P2 polish from UAT-02:
    · Case C now visually separates the canonical policy status pill
      from the evidence workflow via a subtle top divider + muted
      "Evidence" section label.
    · Case A and Case B are untouched.
    · No new status vocabulary. No modal / tooltip / banner.
    · No backend / activation / compliance / evidence-workflow change.
"""
from __future__ import annotations

from pathlib import Path

FE_INSURANCE = Path("/app/frontend/src/components/driver-cc/TruckInsuranceCard.jsx")


def _read(p): return p.read_text(encoding="utf-8")


# ─── UAT-FIX-02.1 · Evidence grouping present in Case C ───────────────
class TestEvidenceGroupingCaseC:
    def test_evidence_group_container_present(self):
        src = _read(FE_INSURANCE)
        assert 'data-testid="ci-insurance-evidence-group"' in src

    def test_evidence_group_has_divider(self):
        src = _read(FE_INSURANCE)
        # Top border + spacing proves the visual separator.
        assert 'border-t border-slate-200' in src
        assert 'mt-3 pt-3' in src

    def test_evidence_label_present_and_muted(self):
        src = _read(FE_INSURANCE)
        assert 'data-testid="ci-insurance-evidence-label"' in src
        # Muted uppercase treatment (small tracked text, slate-400).
        assert 'text-[10px] uppercase tracking-wide text-slate-400' in src
        # Contains the literal word "Evidence" between the label divs.
        assert '>\n            Evidence\n          <' in src

    def test_evidence_actions_still_wired(self):
        src = _read(FE_INSURANCE)
        assert 'EvidenceActions' in src
        assert 'testidPrefix="ci-insurance-ev"' in src
        # Upload payload targets canonical VehicleInsurancePolicy entity.
        assert 'entity_type: "VehicleInsurancePolicy"' in src
        assert 'document_type: "Vehicle Insurance"' in src
        assert 'relationship_type: "Evidence"' in src


# ─── UAT-FIX-02.2 · Policy status pill unchanged in Case C ────────────
class TestPolicyStatusUnchanged:
    def test_status_pill_still_reads_canonical_component(self):
        src = _read(FE_INSURANCE)
        assert 'status={insuranceComp?.status || "Compliant"}' in src
        assert 'testid="ci-insurance-status"' in src

    def test_provider_policy_cover_expiry_preserved(self):
        src = _read(FE_INSURANCE)
        assert 'label="Provider"' in src and 'i.provider' in src
        assert 'i.policy_number' in src
        assert 'i.cover_type' in src
        assert 'i.expiry_date' in src


# ─── UAT-FIX-02.3 · Case A untouched ──────────────────────────────────
class TestCaseAUntouched:
    def test_case_a_not_applicable_preserved(self):
        src = _read(FE_INSURANCE)
        assert 'status="Not Applicable"' in src
        assert 'testid="ci-insurance-na-reason"' in src
        assert 'testid="ci-insurance-na-helper"' in src
        assert "Truck Insurance will be assessed once a primary vehicle is assigned." in src

    def test_case_a_still_no_evidence_actions(self):
        src = _read(FE_INSURANCE)
        case_a_start = src.index("if (!vehicle)")
        case_a_end = src.index("// ── Case C", case_a_start)
        case_a = src[case_a_start:case_a_end]
        assert 'EvidenceActions' not in case_a
        assert 'ci-insurance-evidence-group' not in case_a


# ─── UAT-FIX-02.4 · Case B untouched ──────────────────────────────────
class TestCaseBUntouched:
    def test_case_b_missing_reason_preserved(self):
        src = _read(FE_INSURANCE)
        assert 'testid="ci-insurance-missing-reason"' in src
        assert "No current Truck Insurance policy" in src

    def test_case_b_still_no_evidence_actions(self):
        src = _read(FE_INSURANCE)
        case_b_start = src.rindex("// ── Case B")
        case_b = src[case_b_start:]
        assert 'EvidenceActions' not in case_b
        assert 'ci-insurance-evidence-group' not in case_b


# ─── UAT-FIX-02.5 · No new status vocabulary / no modal / no banner ───
class TestNoNewSemantics:
    def test_no_new_status_string(self):
        src = _read(FE_INSURANCE)
        # Only the canonical statuses may appear as StatusPill status props.
        # Assert no new invented labels.
        forbidden = ["Awaiting Evidence", "Evidence Missing", "Pending Upload", "No Document"]
        for f in forbidden:
            assert f not in src

    def test_no_modal_or_tooltip(self):
        src = _read(FE_INSURANCE)
        assert "Dialog" not in src
        assert "Modal" not in src
        assert "Tooltip" not in src

    def test_no_extra_warning_banner(self):
        src = _read(FE_INSURANCE)
        # Prevent accidental addition of a full-width warning banner.
        assert 'bg-amber' not in src
        assert 'bg-red-50' not in src
