# EB-18 Migration Authorisation Runbook
Fields required (all 13): workbook_identified, workbook_checksum, workbook_owner, import_scope_approved, mapping_approved, dry_run_completed, issues_resolved, go_decision (GO|CONDITIONAL_GO), commit_pkg_checksum, rollback_pkg_generated, rollback_pkg_validated, operators_assigned, final_approval. Plus explicit_real_data_marker=true to move NOT_AUTHORISED → AUTHORISED. NO_GO forces NOT_AUTHORISED. Revoke via `/revoke`.
Real-data commit refuses unless status == AUTHORISED.
