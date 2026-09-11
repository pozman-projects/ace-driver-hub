"""EB-R02 · targeted acceptance tests for canonical compliance
intelligence reconciliation. Backend-only, no external services."""
import os, sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compliance_records import (  # noqa: E402
    _classify_expiry,
    _days_remaining,
    _to_vc_component,
    _worst_vc,
    ComplianceStatus,
    WARNING_WINDOW_DAYS,
    URGENT_WINDOW_DAYS,
    STATUS_SEVERITY,
)


def _iso_days(delta_days: int) -> str:
    return (datetime.now(timezone.utc).date() + timedelta(days=delta_days)).isoformat()


class TestExpiryBoundaries:
    def test_31_days_current(self):
        assert _classify_expiry(_iso_days(31)) == ComplianceStatus.Compliant.value

    def test_30_days_due_soon(self):
        assert _classify_expiry(_iso_days(30)) == ComplianceStatus.DueSoon.value

    def test_8_days_due_soon(self):
        assert _classify_expiry(_iso_days(8)) == ComplianceStatus.DueSoon.value

    def test_7_days_urgent(self):
        assert _classify_expiry(_iso_days(7)) == ComplianceStatus.Urgent.value

    def test_1_day_urgent(self):
        assert _classify_expiry(_iso_days(1)) == ComplianceStatus.Urgent.value

    def test_0_days_urgent(self):
        assert _classify_expiry(_iso_days(0)) == ComplianceStatus.Urgent.value

    def test_minus_1_day_expired(self):
        assert _classify_expiry(_iso_days(-1)) == ComplianceStatus.Expired.value


class TestMissingInvalidExpiry:
    def test_none_is_incomplete_not_compliant(self):
        s = _classify_expiry(None)
        assert s == ComplianceStatus.Incomplete.value
        assert s != ComplianceStatus.Compliant.value

    def test_empty_is_incomplete(self):
        assert _classify_expiry("") == ComplianceStatus.Incomplete.value

    def test_garbage_is_incomplete(self):
        assert _classify_expiry("not-a-date") == ComplianceStatus.Incomplete.value

    def test_days_remaining_none_on_bad_date(self):
        assert _days_remaining("not-a-date") is None
        assert _days_remaining(None) is None


class TestThresholds:
    def test_warning_window_days_is_central(self):
        assert WARNING_WINDOW_DAYS == 30

    def test_urgent_window_days_is_central(self):
        assert URGENT_WINDOW_DAYS == 7

    def test_urgent_lower_than_warning(self):
        assert URGENT_WINDOW_DAYS < WARNING_WINDOW_DAYS


class TestVCComponentMap:
    def test_compliant_maps_compliant(self):
        assert _to_vc_component("Compliant") == "Compliant"

    def test_under_review_maps_compliant(self):
        assert _to_vc_component("Under Review") == "Compliant"

    def test_due_soon_maps_conditions(self):
        assert _to_vc_component("Due Soon") == "Conditions"

    def test_urgent_maps_conditions(self):
        assert _to_vc_component("Urgent") == "Conditions"

    def test_expired_maps_non_compliant(self):
        assert _to_vc_component("Expired") == "Non-Compliant"

    def test_missing_maps_non_compliant(self):
        assert _to_vc_component("Missing") == "Non-Compliant"

    def test_incomplete_maps_non_compliant(self):
        assert _to_vc_component("Incomplete") == "Non-Compliant"

    def test_not_applicable_stays(self):
        assert _to_vc_component("Not Applicable") == "Not Applicable"


class TestWorstVC:
    def test_compliant_plus_conditions_equals_conditions(self):
        assert _worst_vc(["Compliant", "Conditions"]) == "Conditions"

    def test_conditions_plus_non_compliant_equals_non_compliant(self):
        assert _worst_vc(["Conditions", "Non-Compliant"]) == "Non-Compliant"

    def test_compliant_plus_na_equals_compliant(self):
        assert _worst_vc(["Compliant", "Not Applicable"]) == "Compliant"

    def test_all_na_equals_na(self):
        assert _worst_vc(["Not Applicable", "Not Applicable"]) == "Not Applicable"

    def test_empty_equals_na(self):
        assert _worst_vc([]) == "Not Applicable"


class TestStatusSeverityIncludesUrgent:
    def test_urgent_is_between_due_soon_and_missing(self):
        assert STATUS_SEVERITY[ComplianceStatus.DueSoon.value] < STATUS_SEVERITY[ComplianceStatus.Urgent.value]
        assert STATUS_SEVERITY[ComplianceStatus.Urgent.value] < STATUS_SEVERITY[ComplianceStatus.Expired.value]
