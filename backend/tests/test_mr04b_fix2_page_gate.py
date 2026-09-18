"""MR-04B-FIX2 · DriverActivationPage normal-Activate button gate cutover.

These tests inspect the DriverActivationPage.jsx source to prove:
  1. The normal Activate button `disabled=` expression uses ONLY
     `blueprint?.readiness !== "Ready"` — not the legacy record readiness
     and not "Ready with Override".
  2. The Activate confirmation dialog text references Blueprint readiness.
  3. The authoritative Blueprint V1 section is still present.
  4. Override / history controls are still present.

Backend files are NOT touched by this fix; a repo-level check asserts that.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

PAGE = Path("/app/frontend/src/pages/DriverActivationPage.jsx").read_text()


def test_normal_activate_button_uses_blueprint_readiness_only():
    # Locate the Activate Driver button block
    m = re.search(
        r'<button[^>]*onClick=\{activate\}[^>]*data-testid="activation-activate-btn"',
        PAGE, re.S,
    )
    assert m, "Activate Driver button not found"
    # Extract the surrounding element (up to the closing >)
    start = PAGE.rfind("<button", 0, m.end())
    end = PAGE.find(">", m.end())
    button_tag = PAGE[start:end + 1]
    assert 'blueprint?.readiness !== "Ready"' in button_tag, button_tag
    assert "Ready with Override" not in button_tag, button_tag
    assert "readiness_status" not in button_tag, button_tag


def test_confirmation_dialog_uses_blueprint_readiness():
    # Confirm the activate function's window.confirm text references Blueprint V1
    # readiness sourced from `blueprint?.readiness`.
    activate_fn_match = re.search(r"const activate = async \(\).*?\};", PAGE, re.S)
    assert activate_fn_match, "activate() function not located"
    body = activate_fn_match.group(0)
    assert "blueprint?.readiness" in body
    assert "Blueprint V1 readiness" in body
    # Must not present legacy readiness as the activation decision
    assert "Overrides active" not in body


def test_blueprint_v1_section_still_present():
    assert 'data-testid="blueprint-v1-section"' in PAGE
    assert 'data-testid="blueprint-v1-items"' in PAGE


def test_override_and_history_controls_preserved():
    # Override approve/reject/revoke and manual-complete flows remain intact.
    assert "override-approve-" in PAGE
    assert "override-reject-" in PAGE
    assert "override-request" in PAGE
    assert "manual-complete" in PAGE


def test_no_backend_files_changed_by_this_fix():
    """Guardrail: git diff against last commit must show only the
    DriverActivationPage.jsx and the two MR-04B-FIX2 test artefacts changed
    on the backend/frontend surface for this package.

    We do NOT fail the test if git is unavailable; this is a smoke check.
    """
    try:
        out = subprocess.check_output(
            ["git", "-C", "/app", "diff", "--name-only", "HEAD"],
            text=True, timeout=10,
        )
    except Exception:
        import pytest
        pytest.skip("git diff unavailable")
    changed = [ln for ln in out.splitlines() if ln.strip()]
    backend_changes = [c for c in changed if c.startswith("backend/") and "tests/" not in c]
    assert not backend_changes, f"Unexpected backend changes: {backend_changes}"
