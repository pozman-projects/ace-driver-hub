# ACE Driver Command Centre — Product Requirements Document

## Original Problem Statement
Execute strict "NO-DRIFT" Remediation Packages to bring the application into
absolute alignment with Blueprint V1. Product Requirements:
1. Complete Single-Source Blueprint V1 Activation Cutover (MR-04).
2. Owner/Carrier/Relationship Editing (MR-05).
3. Driver Code & Dispatch Numbering (MR-08A).
4. Compliance Alerts & Notification Lifecycle (MR-06).
5. Role Matrix & Permission Consistency (MR-07B).
6. Reporting & Administration (MR-08B): Company Manager, Default Company,
   Report Builder, Theme, Skin.

## Latest Increment · MR-08B-P3-FIX (Feb 2026)
Canonical field alignment of the Report Builder registry. All invalid
stored-field aliases (Owners `trading_name/primary_email/primary_phone`,
Equipment `status`, Vehicle Insurance `insurer/policy_type`, Vehicle
Inspections `outcome/inspector`, Vehicle Defects `reported_at/resolved_at`,
Equipment Compliance `check_type/check_date/outcome`, Documents
`entity_type/entity_id`) removed or replaced with canonical Pydantic keys.
Introduced explicit derived `company_name` field (display only, non
filterable, non sortable). Canonical `company_id` now returns raw UUID.
Vehicle Registration & Driver Licence gained additional canonical fields
(`registration_number_snapshot`, `registration_class`, `issue_date`,
`verification_status`).

### Field capability model additions
- `filterable: bool = True` on Field_.
- `derived: bool = False` on Field_.
- `_validate_request` rejects filters/sorts on non-filterable / non-sortable
  fields with 400 (e.g. `company_name`).

### Structural regression guard
`TestFixStructuralRegistryAlignment` imports canonical Pydantic models and
asserts every non-derived REPORT_SOURCES key exists on the canonical model.
Prevents recurrence of invented stored-field keys.

## Test Coverage
- MR-04B: 32
- MR-05: 54
- MR-06 urgent + notifications: 17 (test_mr06 slow — DB scan volume unrelated to P3-FIX)
- MR-07A / MR-07B / MR-08B-P1 / MR-08B-P2: 135
- MR-08A: 45
- **MR-08B-P3 (incl. FIX): 71 (was 30)**
- Documents (EB-05): 28
- Compliance (EB-04): 34

Total curated regression: ~430 tests passing.

## Deferred / Backlog
- `DriverBase.company_id` duplicate field declaration (cosmetic; no runtime
  defect). Do NOT touch under MR-08B-P3-FIX scope.
- `document_links` join for Documents source (V1 excludes joins).
- MR-08B-P4: Theme / Skin. Awaiting owner decision.
- MR-08B-P5: DCC Admin Card exact-five ordering.
- Authoritative ACE data migration to Production.
- Email / SMS / Scheduler policy enablement.

## Guardrails Honoured This Package
staging only · main untouched · Production untouched · no real ACE data
migrated · StorageAdapter unchanged · MR-07A unchanged · MR-07B unchanged
· document sensitivity unchanged · no PDF reports · no saved reports · no
Theme/Skin · no MR-08B-P4 · no domain schema mutation · no cross-source joins.
