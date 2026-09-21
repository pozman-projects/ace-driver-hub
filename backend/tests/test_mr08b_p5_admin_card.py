"""MR-08B-P5 · DCC Admin card exact-five mock-up conformance.

Static acceptance test — reads the JSX source to prove that the approved
Dan Murgo primary five (Company, Import / Export, Upload Licence, Theme,
Skin) are:
    · declared with the exact visible labels,
    · placed in the ``admin-primary-five`` block before the
      ``admin-primary-divider`` divider,
    · wired to the canonical destinations without a new engine.

This is a low-cost recurrence guard against future card refactors.
"""
from __future__ import annotations

import re
from pathlib import Path

ADMIN_CARD = Path("/app/frontend/src/components/driver-cc/AdminUtilitiesCard.jsx")
LICENCE_CARD = Path("/app/frontend/src/components/driver-cc/DriverLicenceCard.jsx")
APP_JS = Path("/app/frontend/src/App.js")


def _src():
    return ADMIN_CARD.read_text(encoding="utf-8")


# ─── Exact primary five ────────────────────────────────────────────────
def test_primary_block_exists():
    assert 'data-testid="admin-primary-five"' in _src(), "primary five block missing"

def test_divider_exists():
    assert 'data-testid="admin-primary-divider"' in _src(), "divider missing"

def test_secondary_heading_exists():
    assert 'data-testid="admin-secondary-heading"' in _src()

def test_primary_five_before_divider():
    src = _src()
    assert src.index('admin-primary-five') < src.index('admin-primary-divider')

def test_primary_five_appears_before_secondary_utilities():
    src = _src()
    assert src.index('admin-primary-five') < src.index('admin-secondary-utilities')


# ─── Exact visible labels (Dan Murgo mock-up) ─────────────────────────
def test_label_company_visible():
    assert re.search(r'>\s*Company\s*<', _src())

def test_label_import_export_visible():
    assert re.search(r'>\s*Import / Export\s*<', _src())

def test_label_upload_licence_visible():
    assert re.search(r'>\s*Upload Licence\s*<', _src())

def test_label_theme_visible():
    assert re.search(r'>\s*Theme\s*<', _src())

def test_label_skin_visible():
    assert re.search(r'>\s*Skin\s*<', _src())


# ─── Canonical destinations (no new engine, reuse MR-08B-P1..P4) ──────
def test_company_reuses_p2_company_manager():
    assert 'to="/administration/companies"' in _src()

def test_import_reuses_canonical_import_centre():
    # Compact Import action inside the Import/Export row
    src = _src()
    assert 'admin-primary-import' in src
    assert 'to="/imports"' in src

def test_export_reuses_p3_report_builder():
    src = _src()
    assert 'admin-primary-export' in src
    assert 'to="/administration/reports"' in src

def test_theme_reuses_p4_appearance_section_theme():
    assert '/administration/appearance?section=theme' in _src()

def test_skin_reuses_p4_appearance_section_skin():
    assert '/administration/appearance?section=skin' in _src()


# ─── Upload Licence reuses canonical evidence workflow ────────────────
def test_upload_licence_targets_canonical_licence_upload_button():
    src = _src()
    # The Upload Licence shortcut must click the canonical EvidenceActions
    # button on the DriverLicenceCard — proving no duplicate uploader.
    assert 'ci-licence-ev-upload' in src, "Upload Licence must click canonical licence upload button"
    assert 'ci-licence-ev-replace' in src, "Upload Licence must also handle the 'replace' variant"

def test_upload_licence_does_not_post_to_new_endpoint():
    src = _src()
    # Contract: no new POST route is introduced for licence upload. The
    # canonical uploader (EvidenceActions → /api/documents/upload +
    # /api/documents/{id}/versions) is invoked via a DOM click.
    assert '/api/documents' not in src, "Admin card must not call documents endpoint directly"
    assert '/api/driver-licences' not in src, "Admin card must not touch licence records directly"
    # Ensure the canonical EvidenceActions is still wired on the Licence card
    lc = LICENCE_CARD.read_text(encoding="utf-8")
    assert 'EvidenceActions' in lc


# ─── Data-testids for automated e2e (kept minimal) ────────────────────
def test_primary_five_have_data_testids():
    src = _src()
    for testid in (
        'admin-primary-company', 'admin-primary-import-export',
        'admin-primary-import', 'admin-primary-export',
        'admin-primary-upload-licence',
        'admin-primary-theme', 'admin-primary-skin',
    ):
        assert testid in src, f"missing data-testid: {testid}"


# ─── Regression / no-drift guards ─────────────────────────────────────
def test_report_builder_secondary_shortcut_preserved():
    assert 'util-reports' in _src(), "Report Builder secondary link removed"

def test_document_library_secondary_shortcut_preserved():
    assert 'util-open-docs' in _src()

def test_supporting_document_upload_secondary_preserved():
    assert 'util-upload' in _src()

def test_numbering_admin_secondary_preserved():
    assert 'util-numbering' in _src()

def test_driver_alerts_secondary_preserved():
    assert 'util-notifications' in _src()

def test_existing_pdf_generation_controls_preserved():
    src = _src()
    assert 'btn-generate-start-sheet' in src
    assert 'btn-generate-profile-pdf' in src

def test_existing_export_history_preserved():
    assert 'btn-open-export-history' in _src()


# ─── No duplication across primary and secondary sections ────────────
def test_no_duplicate_company_utility_in_secondary():
    src = _src()
    # Utility array must not still hold the old Company Manager entry.
    utilities_block_start = src.index("const utilities = [")
    utilities_block_end = src.index("];", utilities_block_start)
    utilities_block = src[utilities_block_start:utilities_block_end]
    assert '"company"' not in utilities_block, "Company must not appear in secondary utilities"
    assert '"imports"' not in utilities_block, "Import must not appear in secondary utilities"
    assert '"theme"' not in utilities_block, "Theme must not appear in secondary utilities"
    assert '"skin"' not in utilities_block, "Skin must not appear in secondary utilities"


# ─── No Dark visual mode introduced ───────────────────────────────────
def test_no_dark_mode_introduced_in_admin_card():
    src = _src()
    # Do not add dark: variants or a dark toggle in this package.
    assert re.search(r'\bdark:', src) is None, "no dark: variants may be added in P5"
    assert "html.classList" not in src, "no dark class toggling introduced"

def test_appearance_route_still_wired():
    assert "/administration/appearance" in APP_JS.read_text(encoding="utf-8")
