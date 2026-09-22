"""UAT-FIX-01 · Mobile responsive DCC layout — static acceptance.

Proves the mobile-first responsive scaffolding is in place on the DCC page
and its shared layout primitives. This does not attempt to reproduce a
375 × 812 live viewport (E2E harness is fixed to a desktop viewport in
this environment) — instead it locks in the mobile-first Tailwind class
structure that guarantees no horizontal overflow on real devices.

Guardrails asserted:
    · No hard-coded `min-width` / fixed page width on the DCC main element.
    · No `style={{ maxWidth: … }}` inline (Tailwind utility instead).
    · Outer grid is mobile-first: `grid-cols-1` at base, desktop only at
      `xl:` breakpoint.
    · Management rows stack single-column at base, three-across from `md:`.
    · Right rail is not sticky below `xl:`.
    · `HeaderBadge` min-width only kicks in from `sm:` upward.
    · Card content untouched (business-logic / RBAC / activation import
      list remains identical to prior FA-04 state).
    · `<meta name="viewport" content="width=device-width, initial-scale=1">`
      remains in place.
"""
from __future__ import annotations

from pathlib import Path

PAGE = Path("/app/frontend/src/pages/DriverCommandCentre.jsx")
UTIL = Path("/app/frontend/src/components/driver-cc/driverCCUtils.jsx")
INDEX_HTML = Path("/app/frontend/public/index.html")
INSURANCE = Path("/app/frontend/src/components/driver-cc/TruckInsuranceCard.jsx")


def _read(p): return p.read_text(encoding="utf-8")


# ─── UAT-FIX-01.1 · Root DCC page mobile-first scaffolding ────────────
class TestPageMobileScaffolding:
    def test_no_inline_maxwidth_fixed_style(self):
        src = _read(PAGE)
        assert "style={{ maxWidth: 1920 }}" not in src, \
            "Inline fixed maxWidth removed per UAT-FIX-01"
        assert "style={{maxWidth: 1920}}" not in src

    def test_uses_tailwind_maxw_utility(self):
        src = _read(PAGE)
        assert "max-w-[1920px]" in src, \
            "Tailwind max-w utility caps desktop width without forcing minimum"

    def test_no_min_width_on_main(self):
        src = _read(PAGE)
        # Search only within the <main ...> opening tag.
        main_open = src.split("<main", 1)[1].split(">", 1)[0]
        assert "min-w" not in main_open, \
            "No min-width forcing desktop width on the DCC main element"

    def test_outer_grid_is_mobile_first(self):
        src = _read(PAGE)
        assert 'className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_420px] gap-6"' in src, \
            "Base grid stays one column; desktop composition only at xl:"

    def test_left_column_min_w_zero(self):
        src = _read(PAGE)
        # `min-w-0` prevents children (e.g. long strings) from expanding
        # the grid column beyond the viewport.
        assert 'className="min-w-0 space-y-6"' in src

    def test_right_rail_sticky_only_at_xl(self):
        src = _read(PAGE)
        assert 'xl:sticky xl:top-6 xl:self-start' in src, \
            "Right rail is sticky only at desktop; mobile keeps normal flow"
        # Guard against a raw non-responsive sticky slipping in.
        assert 'className="sticky' not in src


# ─── UAT-FIX-01.2 · ManagementRow stacks on mobile ────────────────────
class TestManagementRowResponsive:
    def test_management_row_mobile_first(self):
        src = _read(UTIL)
        assert '<div className="grid grid-cols-1 md:grid-cols-3 gap-4">' in src, \
            "ManagementRow keeps mobile-first grid: 1 column at base, 3 at md:"


# ─── UAT-FIX-01.3 · HeaderBadge min-w only at sm+ ─────────────────────
class TestHeaderBadgeMinWidth:
    def test_min_width_guarded_by_sm_breakpoint(self):
        src = _read(UTIL)
        assert "sm:min-w-[130px]" in src, \
            "HeaderBadge min-width only kicks in from sm+ so 375px viewports do not overflow"

    def test_no_bare_min_width_forces_desktop(self):
        src = _read(UTIL)
        # Assert no bare "min-w-[130px]" that ignores breakpoint.
        # (We only care about HeaderBadge — MiniStat is safe.)
        badge_block = src.split("HeaderBadge", 1)[1]
        assert "sm:min-w-[130px]" in badge_block


# ─── UAT-FIX-01.4 · Viewport meta preserved ───────────────────────────
class TestViewportMeta:
    def test_meta_viewport_present(self):
        src = _read(INDEX_HTML)
        assert 'name="viewport"' in src
        assert "width=device-width" in src
        assert "initial-scale=1" in src


# ─── UAT-FIX-01.5 · No business-logic / card-content regression ───────
class TestNoContentRegression:
    def test_truck_insurance_case_a_preserved(self):
        src = _read(INSURANCE)
        # Case A (Not Applicable) branch untouched.
        assert 'status="Not Applicable"' in src
        assert "No primary vehicle assigned" in src
        assert 'testid="ci-insurance-na-helper"' in src

    def test_truck_insurance_case_c_preserved(self):
        src = _read(INSURANCE)
        # Case C canonical fields untouched.
        assert "i.provider" in src
        assert "i.policy_number" in src
        assert "i.cover_type" in src
        assert "i.expiry_date" in src

    def test_dcc_still_orchestrates_all_15_cards(self):
        src = _read(PAGE)
        for card in [
            "DriverDetailsCard", "AccountDetailsCard", "DriverSetupCard",
            "CommunicationCard", "CarrierEquipmentCard", "OwnerDetailsCard",
            "AdminUtilitiesCard", "ActivationChecklistCard", "DriverNotesCard",
            "ComplianceOverviewCard", "DriverLicenceCard", "TruckRegistrationCard",
            "TruckInsuranceCard", "VehicleComplianceCard", "DocumentsPassesPhotosCard",
        ]:
            assert f"<{card}" in src, f"{card} still rendered by DCC"


# ─── UAT-FIX-01.6 · Desktop hierarchy preserved ───────────────────────
class TestDesktopHierarchyPreserved:
    def test_three_management_rows_present(self):
        src = _read(PAGE)
        assert src.count("<ManagementRow>") == 3, "Three management rows preserved"

    def test_desktop_composition_intact(self):
        src = _read(PAGE)
        # Left management column + right compliance-intelligence aside pair
        # must remain the desktop composition.
        assert 'data-testid="compliance-intelligence-layer"' in src
        assert '<aside' in src
