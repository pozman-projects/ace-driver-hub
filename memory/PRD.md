# ACE Driver Command Centre — Product Requirements Document

## Original Problem Statement
Execute strict "NO-DRIFT" Remediation Packages to bring the application into
absolute alignment with Blueprint V1 and the approved Dan Murgo mock-up.

## Latest Increment · MR-08B-P5 (Feb 2026) · Final DCC Admin card mock-up conformance
- The Administration & Utilities card now presents the approved primary five
  in exact visible order **BEFORE** a divider, followed by "Other utilities":
  1. **Company** → `/administration/companies` (MR-08B-P2)
  2. **Import / Export** → single row exposing two compact actions
     · **Import** → `/imports` (canonical Import Centre)
     · **Export** → `/administration/reports` (MR-08B-P3 Report Builder)
  3. **Upload Licence** → focuses `[data-section="licence"]` and invokes
     the existing canonical `EvidenceActions` upload/replace control on
     `DriverLicenceCard`. No duplicate uploader created. No new endpoint.
  4. **Theme** → `/administration/appearance?section=theme` (MR-08B-P4)
  5. **Skin** → `/administration/appearance?section=skin` (MR-08B-P4)
- Retained "Other utilities" below the divider: Report Builder shortcut,
  Document Library, Upload supporting document, Numbering admin, Driver
  alerts. Existing PDF generation buttons and Export History unchanged.
- Duplicates removed from the secondary utilities list: Company (now
  primary), Import Centre (now primary), Theme (now primary), Skin (now
  primary). Report Builder shortcut deliberately retained per locked owner
  decision.

## Prior Increments
- **MR-08B-P4** — Theme scaffold (per-user light/dark persisted; dark
  visual application deferred to MR-08B-P4-DARK) + Global Skin (accent
  colour, StorageAdapter-backed PNG/JPEG logo, PDF branding integration
  with graceful fallback).
- **MR-08B-P3-FIX** — Report Builder canonical field alignment + structural
  recurrence guard.
- MR-08B-P1/P2/P3 base packages: Import commit lock, Company Manager +
  Default Company, canonical Report Builder.
- MR-04B, MR-05, MR-06, MR-07A/B, MR-08A.

## Test Coverage
- MR-07B / MR-08B-P1..P5 combined: **266 / 266 green**
- Driver Exports (EB-11): **28 / 28 green** — branding hook non-regressive.
- Compliance (EB-04): **34 / 34 green** — licence evidence workflow untouched.
- Cumulative recent-suite pytest run (P3/P4/P5 + supporting): **301 / 301 green**.

## Deferred / Backlog
- **MR-08B-P4-DARK** — full application-wide visual dark palette across
  ~69 files. Explicitly deferred; NOT started here.
- Authoritative ACE data migration to Production.
- Email/SMS/Scheduler policy enablement.
- Cosmetic: duplicate `company_id` declaration in `DriverBase`.

## Guardrails Honoured This Package
staging only · main untouched · Production untouched · no real ACE data
migrated · MR-07A unchanged · MR-07B unchanged · MR-08B-P1..P4 locks
unchanged · Report Builder unchanged · Company Manager unchanged · Theme
persistence unchanged · Skin storage unchanged · no duplicate uploader ·
no duplicate import/export engine · no new backend routes · no dark
visual mode · no MR-08B-P4-DARK · DCC macro layout unchanged.
