"""MR-05 · DCC frontend smoke — source-level checks that Owner Details and
Carrier Details cards render the required Blueprint fields and testids.
"""
from pathlib import Path


def _read(p): return Path(p).read_text()


def test_owner_card_has_required_fields():
    src = _read("/app/frontend/src/components/driver-cc/OwnerDetailsCard.jsx")
    for testid in [
        "card-owner-details", "owner-driving-for", "owner-truck-ownership",
        "owner-mobile", "owner-email",
        "owner-picker", "owner-picker-toggle", "owner-picker-input",
        "owner-create-open", "owner-create-modal", "owner-create-submit",
        "owner-shared-warning",
    ]:
        assert testid in src, f"missing testid {testid}"


def test_carrier_card_has_required_fields():
    src = _read("/app/frontend/src/components/driver-cc/CarrierEquipmentCard.jsx")
    for testid in [
        "card-car-carrier", "field-vehicle-rego", "field-vehicle-config",
        "field-vehicle-status",
        "field-tray-number", "field-tray-ownership",
        "field-trailer-number", "field-trailer-ownership",
        "vehicle-picker", "${testidPrefix}-picker",
        "edit-carrier-config", "edit-vehicle-status",
        "carrier-pending-banner",
    ]:
        assert testid in src, f"missing testid {testid}"


def test_no_non_canonical_ownership_translation_in_carrier():
    src = _read("/app/frontend/src/components/driver-cc/CarrierEquipmentCard.jsx")
    # Deferred terminology: NOT allowed in MR-05
    for term in ("ACE", "Contractor", "Hire", "Loan"):
        # These strings must not appear as ownership-translation display values.
        # A conservative check: they must not appear as a bare literal string.
        assert f'"{term}"' not in src, f"non-canonical ownership label leaked: {term}"


def test_carrier_uses_only_canonical_lifecycle_values():
    src = _read("/app/frontend/src/components/driver-cc/CarrierEquipmentCard.jsx")
    # Deprecated lifecycle values must never appear
    for banned in ("Inactive", "Maintenance"):
        assert f'"{banned}"' not in src, f"deprecated vehicle status present: {banned}"


def test_dcc_wires_role_and_refresh():
    src = _read("/app/frontend/src/pages/DriverCommandCentre.jsx")
    assert "<CarrierEquipmentCard data={data} role={role} driverId={driverId} onSaved={refresh} />" in src
    assert "<OwnerDetailsCard data={data} role={role} driverId={driverId} onSaved={refresh} />" in src
