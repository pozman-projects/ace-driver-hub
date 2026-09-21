# ACE Driver Command Centre — Product Requirements Document

## Original Problem Statement
Execute strict "NO-DRIFT" Remediation Packages to bring the application into
absolute alignment with Blueprint V1 and the approved Dan Murgo mock-up.

## Latest Increment · FA-02 (Feb 2026) · Communication multi-driver visibility + preference history + note author
- **Communication card — Other Drivers for this Owner**: read-only,
  compact peer list resolved from canonical `driver_owner_relationships`
  (excludes current driver, archived drivers, non-current DORs, and drivers
  linked to a different Owner). Peer rows optionally link to that driver's
  DCC. No shared preference record — canonical per-Driver preference model
  preserved.
- **Communication preference history (append-only)**: new
  `driver_communication_preference_events` collection. Every meaningful
  change to the five tracked fields (owner_report_email_override,
  driver_report_email_override, send_daily_report_owner,
  send_daily_report_driver, display_on_dispatch) records one event with
  driver_id, changed_at, changed_by, before, after, changed_fields. No-op
  saves append no event. History cannot be directly mutated (no
  POST/PUT/DELETE). Aggregator surfaces the latest 5 events.
- **Communication card — Recent Changes** panel renders history compactly
  as `<date> · <actor> · <field>: <before> → <after>`. No raw JSON.
- **Notes card** now displays the note author (updated_by → created_by →
  "System") alongside category, pinned marker and timestamp. Role
  visibility, categories and note history unchanged.
- **Delivery remains simulated only** — the footer contract stays truthful.

## Prior Increments
- **FA-01** — DCC compliance presentation + canonical field alignment
  (Insurance `provider`, Registration `registration_number_snapshot`,
  Registration class, Licence verification triple, "n of n Compliant"
  primary summary, explicit Prime / Tray / Trailer rows).
- **MR-08B-P5** — DCC Admin card exact-five mock-up conformance.
- **MR-08B-P4** — Theme scaffold + Global Skin.
- **MR-08B-P3-FIX** — Report Builder canonical field alignment.
- MR-08B-P1/P2/P3 · MR-08A · MR-07A/B · MR-06 · MR-05 · MR-04.

## Test Coverage
- **FA-02**: 27 / 27 green (per-driver isolation, other-drivers scoping,
  history append/diff, tracked-field parametrised coverage, aggregator
  surface, ReadOnly/Compliance role safety, no messaging endpoints).
- **FA-01**: 25 / 25 green.
- Full targeted regression MR-05 + MR-07B + FA-01 + FA-02 + driver profile:
  **157 passing, 0 new failures** (2 pre-existing `test_activation_summary_shape*`
  baseline failures independent of FA-02).

## Remaining Acceptance Punch List
- **FA-03** · CE-03 OwnershipModel enum audit — already closed (canonical
  values include `Owned / Leased / Sub-Contracted / Other`).
- **FA-04** · Driver Details residential address autocomplete (P2, provider TBD).

## Deferred / Backlog
- **MR-08B-P4-DARK** — full application dark palette.
- Additional Pass canonical expiry/status model.
- Live outbound Email/SMS/Scheduler activation.
- Authoritative ACE data migration to Production.
- DriverBase.company_id duplicate declaration cleanup.

## Guardrails Honoured This Package
staging only · main untouched · Production untouched · no real ACE data
migrated · communication remains per-Driver · no shared Owner preferences
· no message/chat/thread endpoints · no live email/SMS · display_on_dispatch
canonical authority preserved · history append-only · no destructive history
overwrite · current Driver excluded · archived Drivers excluded · Notes
permissions unchanged · MR-07B unchanged · Report Builder / Company /
Theme / Skin / Activation / Compliance rules untouched.
