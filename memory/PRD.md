# ACE Driver Command Centre — Product Requirements Document

## Original Problem Statement
Execute strict "NO-DRIFT" Remediation Packages to bring the application into
absolute alignment with Blueprint V1 and the approved Dan Murgo mock-up.

## Latest Increment · FA-01 (Feb 2026) · DCC compliance presentation + canonical field alignment
- **Truck Insurance card** now reads canonical `provider` (retiring the
  legacy `insurer` alias); label preserved as "Provider".
- **Truck Registration card** now reads canonical
  `registration_number_snapshot`; adds visible `Registration Class`.
- **Driver Licence card** now displays canonical verification triple:
  `verification_status`, `verified_at`, `verified_by`.
- **Compliance Overview card** — primary summary now shows the canonical
  "n of n Compliant" count across driver + vehicle canonical components
  while preserving Worst Status Wins and alert-count triplet.
- **Vehicle Compliance card** — explicit Prime / Tray / Trailer rows with
  uncoupled handling; consumes `vehicle_summary + tray_equipment +
  trailer_equipment` from the existing aggregator; no new calculator.
- All fixes are frontend-only. No backend schema, no data migration, no
  denormalisation change, no OwnershipModel change (canonical enum values
  are already `Owned / Leased / Sub-Contracted / Other`).
- 25 static FA-01 acceptance tests + full targeted regression across
  MR-04B, MR-07B, EB-04 compliance, EB-09 driver profile, EB-11 driver
  exports, EBR02/EBR03B intelligence/inline evidence → **236/236 green**
  (2 pre-existing failures in `test_activation_summary_shape` and
  `test_activation_no_false_completion_without_licence` predate FA-01 and
  are unaffected by these changes).

## Prior Increments
- **MR-08B-P5** — DCC Admin card exact-five mock-up conformance.
- **MR-08B-P4** — Theme scaffold + Global Skin (dark visual deferred to
  MR-08B-P4-DARK).
- **MR-08B-P3-FIX** — Report Builder canonical field alignment.
- MR-08B-P1/P2/P3 base packages · MR-08A · MR-07A/B · MR-06 · MR-05 · MR-04.

## Test Coverage (curated regression, latest)
- FA-01 static acceptance: **25 / 25**
- MR-04B + MR-07B + DCC compliance/intelligence + evidence + exports: **236 / 236 green** (+ 2 pre-existing failures untouched)
- Previous MR-08B suite (P1..P5): **266 / 266** (established in P5)

## Remaining Acceptance Punch List (after FA-01)
- **FA-02** · Communication multi-driver awareness + note author display
  (P1 + P2 mix).
- **FA-03** · Confirm/close CE-03 OwnershipModel enum audit line (already
  no defect — canonical values include Other).
- **FA-04** · Driver Details address autocomplete (P2, provider TBD).

## Deferred / Backlog
- **MR-08B-P4-DARK** — full application dark palette.
- Additional Pass canonical expiry/status model.
- Live outbound Email/SMS/Scheduler activation.
- Authoritative ACE data migration to Production.
- DriverBase.company_id duplicate declaration cleanup.

## Guardrails Honoured This Package
staging only · main untouched · Production untouched · no real ACE data
migrated · no data migration · no denormalised backend write path change ·
canonical `provider` used · canonical `registration_number_snapshot` used
· no new aliases · no business-rule changes · MR-04 activation semantics
unchanged · MR-07A / MR-07B unchanged · OwnershipModel unchanged · Report
Builder unchanged · Company Manager unchanged · Theme / Skin unchanged ·
EvidenceActions unchanged.
