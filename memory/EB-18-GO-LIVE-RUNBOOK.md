# EB-18 Go-Live Runbook
Framework only. No irreversible Production action is performed by EB-18. Everything below is executed *in reverse order* against a DRY_RUN or REHEARSAL run first.
1. Verify EB-17c readiness gate = READY/CONDITIONAL via `GET /api/go-live/prerequisites`.
2. Create a run in DRY_RUN mode (`POST /api/go-live/runs`).
3. Collect four approval layers: Business, Technical, Security, Release (`POST /api/go-live/runs/{id}/approve`). PRODUCTION mode requires `production_mode_explicit_marker=true`.
4. Admin starts the run (`POST /api/go-live/runs/{id}/start`).
5. Execute cutover steps in order via `POST /api/go-live/runs/{id}/steps/{step_id}/complete`.
6. Record monitoring snapshots via `POST /api/go-live/runs/{id}/monitoring`.
7. Compute release decision via `GET /api/go-live/release-decision?rid={id}`.
8. Any hard trigger → immediate abort (`POST /api/go-live/runs/{id}/abort`).
9. Rollback via `POST /api/go-live/runs/{id}/rollback`.
No admin may manually force RELEASED.
