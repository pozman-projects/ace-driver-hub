# ACE Driver Command Centre — Product Requirements Document

## Original Problem Statement
Execute strict "NO-DRIFT" Remediation Packages to bring the application into
absolute alignment with Blueprint V1 and the approved Dan Murgo mock-up.

## Latest Increment · FA-04 (Feb 2026) · Truck Insurance N/A presentation
- **Truck Insurance card** now distinguishes three canonical states:
  - Case A · no primary vehicle → `Not Applicable` pill + reason
    "No primary vehicle assigned" + helper "Truck Insurance will be
    assessed once a primary vehicle is assigned." No provider/policy
    fields, no evidence controls, no fabricated entity.
  - Case B · primary vehicle, no current insurance → canonical `Missing`
    (or whatever vehicle_summary insurance component reports) + reason
    "No current Truck Insurance policy". Still no evidence controls
    because no `VehicleInsurancePolicy` entity exists.
  - Case C · primary vehicle + insurance → unchanged canonical provider,
    policy_number, cover_type, expiry_date, calculated status, and
    Upload / Replace / Open evidence workflow.
- **Compliance Overview** denominator now excludes canonically
  `Not Applicable` components — "2 of 2 Compliant" instead of
  "2 of 3 Compliant" when the third item is canonically N/A. Reuses
  backend canonical status; no new frontend calculator.
- **StatusPill** already carried "Not Applicable" (slate style). No new
  status vocabulary, no severity-ranking change.
- **Activation exact-seven** UNTOUCHED — Truck Insurance remains one of
  the seven mandatory items. No exemption added. Canonical readiness
  engine remains the authority.
- **No backend schema change · no new evidence endpoint · no fake
  insurance entity · no role permission change.**

## Prior Increments
- **FA-03** — Driver residential address autocomplete via Google Places.
- **FA-02** — Communication multi-driver visibility + preference history + note author.
- **FA-01** — DCC compliance presentation + canonical field alignment.
- **MR-08B-P5** — DCC Admin card exact-five mock-up conformance.
- **MR-08B-P4** — Theme scaffold + Global Skin.
- **MR-08B-P3-FIX** — Report Builder canonical field alignment.
- MR-08B-P1/P2/P3 · MR-08A · MR-07A/B · MR-06 · MR-05 · MR-04.

## Test Coverage
- **FA-04**: 27 / 27 green (canonical N/A status support, StatusPill
  N/A, Case A/B/C presentation, no fake entity, no legacy insurer alias,
  Compliance Overview denominator, activation mandatory unchanged, no
  new evidence endpoint).
- FA-01 + FA-02 + FA-03 + FA-04 combined: **95 / 95 passing**.
- Full activation / compliance / MR-04B / MR-07B regression: **210 passing,
  1 skipped, 0 new failures**.
- Pre-existing baseline in `test_driver_profile_eb09.py`: 2 failures
  (`test_activation_summary_shape*`) — unchanged from prior sessions.

## Remaining Acceptance Punch List
_(none — FA-01, FA-02, FA-03, FA-04 close the audit's DCC punch list.)_

## Deferred / Backlog
- **MR-08B-P4-DARK** — full application dark palette.
- Additional Pass canonical expiry/status model.
- Live outbound Email/SMS/Scheduler activation.
- Authoritative ACE data migration to Production.
- DriverBase.company_id duplicate declaration cleanup.
- Baseline `activation-summary` shape fix (2 pre-existing eb09 failures).

## Guardrails Honoured This Package
staging only · main untouched · Production untouched · no backend
schema change · no activation rule change · Truck Insurance remains
mandatory · no activation exemption · no new compliance calculator ·
no new evidence endpoint · no fake VehicleInsurancePolicy · no role
permission change · no out-of-scope changes.

