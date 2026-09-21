# ACE Driver Command Centre — Product Requirements Document

## Original Problem Statement
Execute strict "NO-DRIFT" Remediation Packages to bring the application into
absolute alignment with Blueprint V1 and the approved Dan Murgo mock-up.

## Latest Increment · FA-03 (Feb 2026) · Driver residential address autocomplete (Google Places)
- **Google Places JavaScript API** integrated on Driver Details residential
  address edit input. Australian country bias. Only the canonical
  `residential_address` string is persisted — no `place_id`, no
  coordinates, no `geometry`, no raw Places response.
- **Loader** at `/app/frontend/src/lib/googlePlaces.js`: singleton
  in-flight promise, deduplicated script tag, `libraries=places` only,
  `loading=async&v=weekly`. Reads the key from
  `REACT_APP_GOOGLE_MAPS_API_KEY`. Missing key or `onerror` resolve to
  `null` so the field silently falls back to a plain text input with the
  helper line **"Address suggestions unavailable"** (`data-testid`
  `address-autocomplete-unavailable`).
- **No hard-coded API keys**; no key echoed in logs; no backend endpoint
  returns the key.
- **Driver Details edit mode** wires `AddressAutocompleteInput` only on
  the residential address input. All four other fields remain plain
  `EditInput`s. Manual typing, Save, Cancel, dirty-state protection
  unchanged. `ROLE_CAN_EDIT` gating and backend `PUT /api/drivers/{id}`
  unchanged.
- **No map, no marker, no street view, no coordinates, no geocoder, no
  distance matrix.** Places-only autocomplete UX.
- **Backend Driver schema unchanged** — `residential_address` remains a
  single canonical string.

## Prior Increments
- **FA-02** — Communication multi-driver visibility + preference history + note author.
- **FA-01** — DCC compliance presentation + canonical field alignment.
- **MR-08B-P5** — DCC Admin card exact-five mock-up conformance.
- **MR-08B-P4** — Theme scaffold + Global Skin.
- **MR-08B-P3-FIX** — Report Builder canonical field alignment.
- MR-08B-P1/P2/P3 · MR-08A · MR-07A/B · MR-06 · MR-05 · MR-04.

## Test Coverage
- **FA-03**: 16 / 16 green (loader singleton, no hardcoded key, no map/geocoder,
  no place_id/lat/lng persisted, Australian bias, formatted_address handling,
  missing-key + API-failure fallback, backend schema unchanged).
- Full targeted regression FA-01 + FA-02 + FA-03 + MR-07B + Driver profile:
  **151 passing, 0 new failures** (2 pre-existing `test_activation_summary_shape*`
  baseline failures untouched, verified via `git stash` in FA-01).

## Remaining Acceptance Punch List
_(none — FA-01, FA-02, FA-03 close the audit's DCC punch list.)_

## Deferred / Backlog
- **MR-08B-P4-DARK** — full application dark palette.
- Additional Pass canonical expiry/status model.
- Live outbound Email/SMS/Scheduler activation.
- Authoritative ACE data migration to Production.
- DriverBase.company_id duplicate declaration cleanup.

## Guardrails Honoured This Package
staging only · main untouched · Production untouched · no backend schema
change · no structured-address model · no `place_id` stored · no
coordinates stored · no map · no hard-coded API key · `residential_address`
remains canonical single string · no role changes · MR-07B unchanged ·
no out-of-scope changes.
