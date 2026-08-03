# EB-11 — Driver Start Sheet & Profile PDF: Technical Note

## Purpose
Turn the currently unavailable *Generate Start Sheet* / *Export Profile* actions
in the Driver Command Centre into a secure, auditable, role-gated PDF
generation workflow. Every generated PDF is an immutable historical snapshot
resolved from canonical DCC state at the moment of generation.

## Module layout
```
backend/
├── driver_pdf_renderer.py    ← Layout-only PDF renderer (ReportLab Platypus)
├── driver_export_module.py   ← ExportService + FastAPI router
└── tests/
    └── test_driver_exports_eb11.py

frontend/
├── src/pages/
│   ├── DriverExportsPage.jsx        ← /drivers/:driverId/exports
│   └── ExportVerificationPage.jsx   ← /exports/verify/:reference
└── src/components/driver-cc/
    └── AdminUtilitiesCard.jsx       ← DCC card with generate + history buttons
```

## Snapshot generation
`ExportService._resolve_snapshot(driver_id, role, actor_email, export_type)`
pulls, in one method, from:

- `drivers`, `driver_owner_relationships`, `driver_vehicle_assignments`,
  `driver_equipment_assignments`, `owners`, `vehicles`, `equipment`,
  `driver_communication_preferences`
- `driver_licences`, `vehicle_registrations`, `vehicle_insurance_policies`,
  `vehicle_inspections`, `vehicle_defects`, `vehicle_maintenance_tasks`
- `notifications` (Driver alerts)
- `documents` + `document_links` (Driver-linked evidence, `storage_key` and
  `storage_provider` explicitly projected out)
- `driver_activation_records`, `driver_activation_items`,
  `driver_activation_overrides`, `driver_activation_events`,
  `activation_templates`
- `driver_notes` — filtered by the requester's role
- `number_allocation_events`

The compliance service (`compliance_records._ComplianceService`) is used to
compute the Worst-Status-Wins overall figure across Driver, assigned Vehicle
and assigned Equipment.

The returned dict is the **snapshot payload**. It is:
1. Permission-filtered *before* it is stored.
2. Fed directly to the renderer.
3. Persisted verbatim in `driver_export_versions.snapshot_payload` so that
   later audits and verification calls can reason about exactly what the file
   contained without re-reading canonical records.

### Permission filtering rules
| Field / section                             | Roles allowed to include                 |
| ------------------------------------------- | ----------------------------------------- |
| Business Name, ABN, Payroll, Payment %      | Manager, Admin                            |
| Accounts notes                              | Manager, Admin                            |
| Compliance notes                            | Compliance, Manager, Admin                |
| Management notes                            | Manager, Admin                            |
| Operations notes                            | Allocator, Compliance, Manager, Admin     |
| General notes                               | Everyone (incl. ReadOnly)                 |

If a role is not permitted, the field is either **removed from the snapshot
payload** (business fields) or the note is filtered out **before storage** —
the PDF renderer never sees restricted content for that role.

## Rendering pipeline
`driver_pdf_renderer.py` is layout-only. It never calls the DB and never
reasons about permissions — that lives in the service. It exports:

- `render_start_sheet(snapshot) -> bytes` — 2–3 page A4 portrait.
- `render_profile_pdf(snapshot) -> bytes` — 4–8 page A4 portrait.

Styling uses ReportLab's built-in Helvetica family (no bundled font files),
dark-navy header band with cyan accent, brand palette in CSS-like hex values,
KeepTogether flowables for sign-off block, and label/value grids sized so
narrow columns (~2cm) never wrap common labels like "DRIVER CODE".

### Automatic PDF validation (per generation)
Every produced PDF is fed through:

- `%PDF` signature check
- `PdfReader(...)` (pypdf) — must parse; page count > 0
- File-size > 500 bytes
- Extractable title metadata (`Driver Start Sheet` / `Driver Command Centre
  Profile`)
- SHA-256 recorded

If any check fails the job transitions to `Failed` and writes a
`Generation Failed` event with the reason; no version is created.

## Storage integration (EB-05)
On successful render the service creates:

- A `documents` row (`document_type = "Driver Start Sheet"` or `"Driver Profile Export"`, `sensitivity = "Confidential"`, `category = "Generated Export"`)
- A `document_versions` row referencing the storage key on disk under
  `${DOCUMENT_STORAGE_PATH}/exports/{driver_id[:2]}/{driver_id}/{doc_id}_{ver_id}.pdf`
- A `document_links` row linking the document to the Driver entity via
  `link_relationship = "Generated Export"`
- A `driver_export_versions` row that ties `driver_id`, `export_type`,
  `version_number`, the two document ids, `snapshot_payload`, `sha256`,
  `page_count`, `file_size`, `verification_reference`, and the generator's
  role

`storage_key` and `storage_provider` are stripped from every documents-related
API response by the existing EB-05 router. The EB-11 routes never return
these fields either.

## Verification reference
A 15-character human-friendly code (`ACE-XXXX-XXXX-XXXX`) drawn from a
34-character crockford-style alphabet (no ambiguous 0/O/1/I). Enforced unique
via a sparse Mongo index. Contains no personal data.

The `GET /api/driver-exports/verify/{ref}` endpoint requires an
authenticated user, then:

1. Emits a `Verification Viewed` event.
2. Returns metadata (`export_type`, `version_number`, `generated_at/by`,
   `is_archived`, `sha256`) plus a role-filtered driver summary.
3. Re-computes the checksum from the on-disk file and returns
   `checksum_ok = true` iff it matches the stored `sha256`.
4. Sets `can_open = false` when the stored snapshot contains account fields
   (i.e. a Manager/Admin generated it) but the current requester is not
   Manager/Admin. In that case `driver_export_version_id` is omitted from the
   response so the client cannot even attempt a download.

No public QR route exists — QR was intentionally scoped out to avoid leaking
verification codes.

## Access control (dual gate)
Two layers of role checks protect every version:

- **Generation:** the initiator must be role-permitted for the requested
  export type. Snapshot-time role is captured on the version.
- **Download / Preview / Verification opening:** the *current* requester's
  role is also checked — a Manager-generated Profile PDF with account fields
  is 403 for a later Compliance requester, even though Compliance can
  generate their own Profile PDFs (which omit the account section).

Archive is Manager/Admin only. Regenerate is Allocator+ (Start Sheet
regenerate for Allocator; Profile PDF regenerate implicitly restricted by
the generation route it delegates to). ReadOnly can view history but cannot
generate.

## Event log
Every state change writes an append-only row into `driver_export_events`
with `driver_export_job_id`, `driver_export_version_id` (if any),
`driver_id`, `event_type`, `previous_status`, `new_status`, `performed_by`,
`performed_at`, `correlation_id`, and a free-form `payload` (e.g. page count
or failure reason). Preview and download additionally write
`document_access_events` rows through the EB-05 access log, so file
retrieval is auditable through the existing document-access reporting tools.

## Known limitations
- **Local development storage.** Files sit on disk under `DOCUMENT_STORAGE_PATH`.
  Production object storage (S3/GCS) will replace this with the same interface
  in a later milestone.
- **No real ACE data** has been imported.
- **No real email/SMS/Blink** delivery of generated exports.
- **No malware scan** on export files (the exports are locally-generated, so
  no external content path exists — but the same scanning integration used
  for uploaded documents will be layered on later).
- **No public QR.** Verification reference is displayed in the PDF footer and
  the authenticated `/exports/verify/:reference` route resolves it. Public
  QR remains a later enhancement.
- **Notes cap.** The Profile PDF caps included notes at 15 for readability
  and appends a "more notes exist" note. The exact cap is a layout constant
  in the renderer.

## Production requirements to lift EB-11 out of "local development"
- Replace `documents_module.STORAGE_ROOT` with an object storage adapter
  (S3-compatible signed URLs, or GCS). No changes needed in
  `driver_export_module`; the write path is contained in one method.
- Enable production ClamAV or equivalent malware scanning on all uploaded
  documents (independent of EB-11).
- Turn on real email/SMS delivery for the export-completion notification if
  we choose to add that later.
- Optional: rotate the verification-reference alphabet or increase length if
  the collision-birthday probability at scale becomes a concern (currently
  `34^12 ≈ 2.4e18` combinations).
