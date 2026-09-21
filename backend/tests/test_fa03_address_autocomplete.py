"""FA-03 · Driver Residential Address autocomplete (Google Places).

Static acceptance tests. Verifies:
    · No hard-coded API key.
    · Env-var name follows CRA convention.
    · Loader is a singleton, safe-fallback, no map/geocoder/coords stored.
    · Driver Details wires the autocomplete only on residential_address in
      edit mode; plain typing still works; no schema change.
    · No place_id / lat / lng persisted.
    · Backend Driver update path unchanged.
"""
from __future__ import annotations

import re
from pathlib import Path

DDC = Path("/app/frontend/src/components/driver-cc/DriverDetailsCard.jsx")
LOADER = Path("/app/frontend/src/lib/googlePlaces.js")
BACKEND_REG = Path("/app/backend/registers.py")


def _read(p): return p.read_text(encoding="utf-8")


class TestLoader:
    def test_env_var_name(self):
        src = _read(LOADER)
        assert "REACT_APP_GOOGLE_MAPS_API_KEY" in src

    def test_no_hardcoded_key(self):
        src = _read(LOADER)
        # No literal Google API key in source (starts with AIza in production).
        assert re.search(r"AIza[0-9A-Za-z_\-]{20,}", src) is None
        # Address bar-visible URL param must interpolate from env only.
        assert 'key=${encodeURIComponent(key)}' in src or 'key=" + encodeURIComponent(key)' in src

    def test_loader_singleton_promise(self):
        src = _read(LOADER)
        assert "let _promise = null" in src
        assert "if (_promise) return _promise" in src

    def test_loader_no_map_or_geocoder_requested(self):
        raw = _read(LOADER)
        # Strip block comments (JSDoc-style) but keep URL slashes intact.
        src = re.sub(r"/\*.*?\*/", "", raw, flags=re.S)
        assert "libraries=places" in src
        # No geocoder / geometry references in executable code.
        assert "geocoder" not in src.lower()
        assert "geometry" not in src

    def test_loader_never_logs_key(self):
        src = _read(LOADER)
        assert "console.log" not in src
        assert "console.error(key" not in src

    def test_loader_never_stores_place_id_or_coordinates(self):
        src = _read(LOADER)
        assert "place_id" not in src
        assert "lat" not in src.lower() or "latency" in src.lower()  # tolerate 'latency' word if present
        assert "lng" not in src


class TestDriverDetailsIntegration:
    def test_autocomplete_component_present(self):
        src = _read(DDC)
        assert "AddressAutocompleteInput" in src

    def test_autocomplete_only_on_residential_address(self):
        src = _read(DDC)
        # Only the residential address input uses the new component.
        assert src.count("<AddressAutocompleteInput") == 1
        # Other four fields remain plain EditInputs.
        for f in ("mobile_number", "email", "emergency_contact_name",
                  "emergency_contact_phone"):
            assert f"form.{f}" in src

    def test_residential_address_still_canonical_string(self):
        src = _read(DDC)
        # Save payload still uses the plain string field.
        assert "form.residential_address" in src
        # No structured address destructure introduced.
        assert "street" not in src.lower() or "streets" in src.lower()  # tolerate any incidental token
        assert "postcode" not in src
        assert "suburb" not in src

    def test_australia_bias(self):
        src = _read(DDC)
        assert 'country: ["au"]' in src

    def test_only_formatted_address_persisted(self):
        # Strip JS block comments before scanning so descriptive prose does
        # not trip the guard.
        src = re.sub(r"/\*.*?\*/", "", _read(DDC), flags=re.S)
        assert "formatted_address" in src
        # Do not read/store place_id / geometry / coordinates in code.
        assert "place_id" not in src
        assert "geometry" not in src

    def test_manual_typing_preserved(self):
        src = _read(DDC)
        # Manual onChange still writes the raw input value into the form.
        assert 'onChange={(e) => onChange(e.target.value)}' in src

    def test_missing_key_fallback(self):
        # Loader returns null when the env var is unset. Component reflects
        # that with an unavailable helper line.
        src = _read(DDC)
        assert "Address suggestions unavailable" in src
        assert 'data-testid="address-autocomplete-unavailable"' in src

    def test_api_failure_fallback(self):
        src = _read(LOADER)
        # onerror path resolves to null (no crash, no console loop).
        assert "s.onerror" in src
        assert "resolve(null)" in src

    def test_no_map_ui(self):
        src = _read(DDC)
        # No map component, no coordinates rendering.
        assert "<GoogleMap" not in src
        assert "Marker" not in src
        assert "Street View" not in src


class TestBackendUntouched:
    def test_driver_model_unchanged(self):
        src = _read(BACKEND_REG)
        # residential_address remains a single-string canonical field on
        # the Driver model.
        assert "residential_address" in src
        assert "residential_address_line1" not in src
        assert "residential_address_line2" not in src
        assert "residential_postcode" not in src
