# ACE Driver Command Centre — Product Requirements Document

## Original Problem Statement
Execute strict "NO-DRIFT" Remediation Packages to bring the application into
absolute alignment with Blueprint V1.
1. MR-04 · Single-Source Blueprint V1 Activation Cutover.
2. MR-05 · Owner/Carrier/Relationship Editing.
3. MR-06 · Compliance Alerts & Notification Lifecycle.
4. MR-07 · Role Matrix & Permission Consistency.
5. MR-08A · Driver Code & Dispatch Numbering.
6. MR-08B · Reporting & Administration (Company Manager, Default Company,
   Report Builder, **Theme scaffold**, **Global Skin**).

## Latest Increment · MR-08B-P4 (Feb 2026) · Theme scaffold + Global Skin
- **Theme (per-user)** persisted in `user_preferences` keyed by canonical
  `users.id`. Default = `light`. Dark preference persists but visual dark
  palette is intentionally NOT applied — deferred to `MR-08B-P4-DARK` per
  owner decision after STOP condition #2 was validly triggered
  (69 hardcoded-light-utility files would produce a "half-dark" application).
- **Skin (global)** persisted in `app_settings` under `key="skin"` with
  strictly hex accent and a logo stored via the canonical StorageAdapter
  (raw storage keys never exposed). Admin/Manager only for mutation; all
  authenticated roles may read.
- **PDF branding integration**: `driver_pdf_renderer` now accepts an
  optional `brand={"accent_colour", "logo_bytes"}` and applies to header
  band only. All PDF body content, MR-07A gating, versioning, checksum
  and storage paths unchanged. Skin/logo failure falls back silently to
  existing ACE text branding.
- **Appearance page** at `/administration/appearance` with clearly
  separated Theme and Skin sections. Section anchors `?section=theme` and
  `?section=skin` supported.
- **AdminUtilitiesCard** now exposes separate **Theme** and **Skin**
  shortcuts (both link to the Appearance surface). Final exact-five card
  ordering is deferred to `MR-08B-P5`.

## Prior Increment · MR-08B-P3-FIX (Feb 2026)
Report Builder canonical field alignment. Registry keys now match
canonical Pydantic models across all 13 sources. Structural regression
guard added to prevent recurrence.

## Test Coverage
- MR-04B: 32 · MR-05: 54 · MR-07A/07B/08B-P1/08B-P2/08B-P3: 238
- **MR-08B-P4: 32 (new)**
- Driver Exports (EB-11): 28 · Documents (EB-05): 28 · Compliance (EB-04): 34
- MR-08A: 45

## Deferred / Backlog
- **MR-08B-P4-DARK** — full application-wide visual dark palette across
  app shell, DCC cards, registers, Report Builder, Company Manager, forms,
  tables, badges, modals, auth, admin surfaces. Blocked here to prevent a
  half-dark application.
- **MR-08B-P5** — DCC Admin Card exact-five ordering + canonical Upload
  Licence shortcut + Import/Export mock-up conformance.
- Authoritative ACE data migration to Production.
- Email/SMS/Scheduler policy enablement.
- Cosmetic: duplicate `company_id` declaration in `DriverBase`.

## Guardrails Honoured This Package
staging only · main untouched · Production untouched · no real ACE data
migrated · StorageAdapter unchanged · MR-07A unchanged · MR-07B unchanged
· document sensitivity unchanged · no PDF body/content/permissions change
· no partial dark UI · no per-Company Skin · no arbitrary CSS · no raw
storage key exposure · Report Builder, Company Manager, Default Company,
Activation, Compliance, Notifications, Numbering all unchanged.
