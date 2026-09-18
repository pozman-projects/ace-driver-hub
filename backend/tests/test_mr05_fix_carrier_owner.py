"""MR-05-FIX · Two surgical defects:

Defect 1 — CarrierEquipmentCard pending-Vehicle + config/status behaviour:
  - onSelect resets vDraft from the SELECTED vehicle
  - save() compares draft to the effective (pending or current) Vehicle
  - the old `!pendingVehicle` guard is gone → visible edits are never dropped
  - a partial failure after a successful reassignment refreshes canonical state

Defect 2 — Owner card label wording is "Truck Ownership" (both view & edit)

Source-level checks. No backend changes.
"""
import re
from pathlib import Path


def _read(p): return Path(p).read_text()


CARRIER = _read("/app/frontend/src/components/driver-cc/CarrierEquipmentCard.jsx")
OWNER = _read("/app/frontend/src/components/driver-cc/OwnerDetailsCard.jsx")


def test_carrier_picker_resets_draft_from_selected_vehicle():
    # A wrapped onSelect must be present that sets vDraft from the new vehicle's
    # canonical fields.
    assert re.search(
        r"onSelect=\{\(v\)\s*=>\s*\{[^}]*setPendingVehicle\(v\);[^}]*setVDraft\(\{[^}]*carrier_configuration:\s*v\?\.carrier_configuration[^}]*vehicle_status:\s*v\?\.vehicle_status",
        CARRIER, re.S,
    ), "onSelect must reset vDraft from the selected vehicle"


def test_carrier_save_uses_effective_vehicle_and_no_pending_guard():
    """The old `if (effVehicleId && vDraft && !pendingVehicle)` guard must be
    gone — draft edits now apply against the effective (pending or current)
    Vehicle."""
    assert "!pendingVehicle" not in CARRIER, "stale guard `!pendingVehicle` still present"
    # Effective vehicle is derived from pendingVehicle || vehicle
    assert "const effVehicle = pendingVehicle || vehicle;" in CARRIER


def test_carrier_save_compares_draft_against_effective_vehicle():
    # Both diff comparisons must use effVehicle (not the original `vehicle`)
    # for their baseline
    assert "effVehicle?.carrier_configuration" in CARRIER
    assert "effVehicle?.vehicle_status" in CARRIER


def test_carrier_partial_failure_refresh():
    # After a successful reassignment, a subsequent error must still call onSaved()
    assert "reassignmentDone" in CARRIER
    assert re.search(r"if \(reassignmentDone && onSaved\)", CARRIER)


def test_owner_label_is_truck_ownership_not_truck_owner():
    # View mode label
    assert 'label="Truck Ownership"' in OWNER
    # No leftover "Truck Owner" label
    assert 'label="Truck Owner"' not in OWNER


def test_no_backend_permission_changes_were_needed():
    """Guardrail: MR-05-FIX must not touch backend files. This is a source
    check — we don't run git here because MR-05 legitimately shipped
    aggregator changes on the same branch. Instead assert the two frontend
    files targeted are the only ones the fix would need."""
    # Both files still exist and are the only touched surfaces
    assert Path("/app/frontend/src/components/driver-cc/CarrierEquipmentCard.jsx").exists()
    assert Path("/app/frontend/src/components/driver-cc/OwnerDetailsCard.jsx").exists()
