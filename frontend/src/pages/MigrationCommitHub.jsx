import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import AppHeader from "../components/app/AppHeader";
import api, { formatApiErrorDetail } from "../lib/api";
import { toast } from "sonner";
import { useAuth } from "../context/AuthContext";
import {
  ShieldWarning, Play, Pause, ArrowClockwise, Warning,
  CheckCircle, XCircle, ArrowUpRight, Database, ArrowsCounterClockwise,
  Cube, ArrowCounterClockwise,
} from "@phosphor-icons/react";
import { formatDateTime } from "../lib/notifications";

/**
 * EB-14 — Migration Commit Hub + Preflight + Execution + Rollback + Backfill.
 *
 * Single-page control surface for the controlled migration commit engine.
 * All actions are role-gated by the backend; frontend mirrors visibility.
 * Displays truthful staged-idempotent commit banner (transactions off in
 * this environment).
 */
export default function MigrationCommitHub() {
  const { user } = useAuth();
  const [env, setEnv] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [dryRuns, setDryRuns] = useState([]);
  const [backfills, setBackfills] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedJob, setSelectedJob] = useState(null);
  const [detail, setDetail] = useState(null);
  const [preflight, setPreflight] = useState(null);
  const [rollback, setRollback] = useState(null);
  const [recon, setRecon] = useState(null);
  const [events, setEvents] = useState([]);
  const [busy, setBusy] = useState(null);
  const [newJob, setNewJob] = useState(null);
  const [confirmCommit, setConfirmCommit] = useState(null);
  const [confirmRollback, setConfirmRollback] = useState(null);

  const canManage = user?.role === "Manager" || user?.role === "Admin";
  const canAdmin = user?.role === "Admin";

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [e, j, dr, bf] = await Promise.all([
        api.get("/migration-commit/environment"),
        api.get("/migration-commit/jobs"),
        api.get("/migration-prep/dry-runs"),
        canManage ? api.get("/storage/backfill") : Promise.resolve({ data: [] }),
      ]);
      setEnv(e.data);
      setJobs(j.data || []);
      setDryRuns(dr.data || []);
      setBackfills(bf.data || []);
    } catch (err) {
      toast.error(formatApiErrorDetail(err?.response?.data?.detail) || "Load failed");
    } finally { setLoading(false); }
  }, [canManage]);

  useEffect(() => { refresh(); }, [refresh]);

  const openJob = async (id) => {
    setSelectedJob(id);
    setBusy("open");
    try {
      const [d, pf, rb, rc, ev] = await Promise.all([
        api.get(`/migration-commit/jobs/${id}`),
        Promise.resolve({ data: null }),
        api.get(`/migration-commit/jobs/${id}/rollback-package`).catch(() => ({ data: null })),
        api.get(`/migration-commit/jobs/${id}/reconciliation`).catch(() => ({ data: [] })),
        api.get(`/migration-commit/jobs/${id}/events`),
      ]);
      setDetail(d.data);
      setPreflight(d.data?.preflight_result || null);
      setRollback(rb.data);
      setRecon(rc.data || []);
      setEvents(ev.data || []);
    } catch (err) {
      toast.error(formatApiErrorDetail(err?.response?.data?.detail));
    } finally { setBusy(null); }
  };

  const runAction = async (label, path, body = null, opts = {}) => {
    setBusy(label);
    try {
      const { data } = body ? await api.post(path, body) : await api.post(path);
      toast.success(`${label} · ${data?.status || "OK"}`);
      if (opts.reloadJob && selectedJob) await openJob(selectedJob);
      await refresh();
      return data;
    } catch (err) {
      toast.error(formatApiErrorDetail(err?.response?.data?.detail) || label + " failed");
      return null;
    } finally { setBusy(null); }
  };

  const createJob = async () => {
    if (!newJob?.migration_dry_run_id || !newJob?.name) {
      toast.error("Select a dry run and enter a name");
      return;
    }
    const created = await runAction("Create job",
      "/migration-commit/jobs", newJob);
    if (created?.migration_commit_job_id) {
      setNewJob(null);
      openJob(created.migration_commit_job_id);
    }
  };

  const runPreflight = () => selectedJob && runAction("Preflight",
    `/migration-commit/jobs/${selectedJob}/preflight`, null, { reloadJob: true });

  const requestApproval = () => selectedJob && runAction("Request approval",
    `/migration-commit/jobs/${selectedJob}/request-approval`, null, { reloadJob: true });

  const approve = (risk_acceptance = false) => selectedJob && runAction("Approve",
    `/migration-commit/jobs/${selectedJob}/approve`,
    { risk_acceptance, note: "" }, { reloadJob: true });

  const execute = async (typedConfirmation) => {
    if (!selectedJob) return;
    if (detail?.mode === "Controlled Commit" && typedConfirmation !== "COMMIT ACE MIGRATION") {
      toast.error("Type the exact confirmation string");
      return;
    }
    await runAction("Execute", `/migration-commit/jobs/${selectedJob}/execute`, null, { reloadJob: true });
    setConfirmCommit(null);
  };

  const reconcile = () => selectedJob && runAction("Reconcile",
    `/migration-commit/jobs/${selectedJob}/reconcile`, null, { reloadJob: true });

  const requestRollback = () => selectedJob && runAction("Rollback request",
    `/migration-commit/jobs/${selectedJob}/rollback/request`, null, { reloadJob: true });

  const approveRollback = () => selectedJob && runAction("Rollback approve",
    `/migration-commit/jobs/${selectedJob}/rollback/approve`, null, { reloadJob: true });

  const executeRollback = async (typedConfirmation) => {
    if (!selectedJob) return;
    if (typedConfirmation !== "ROLL BACK MIGRATION") {
      toast.error("Type ROLL BACK MIGRATION to confirm");
      return;
    }
    await runAction("Rollback", `/migration-commit/jobs/${selectedJob}/rollback/execute`,
      null, { reloadJob: true });
    setConfirmRollback(null);
  };

  const startBackfill = async (scope) => {
    const created = await runAction("Backfill queued",
      "/storage/backfill", { scope });
    if (created?.storage_backfill_job_id) {
      await runAction("Backfill execute",
        `/storage/backfill/${created.storage_backfill_job_id}/execute`);
    }
  };

  const eligibleDryRuns = useMemo(
    () => (dryRuns || []).filter(d => d.status === "Preview Ready" || d.status === "Complete"),
    [dryRuns]);

  const statusColor = (s) => (
    s === "Completed" ? "bg-emerald-50 text-emerald-700" :
    s === "Partially Completed" ? "bg-amber-50 text-amber-700" :
    s === "Rolled Back" ? "bg-neutral-100 text-neutral-600" :
    s === "Failed" || s === "Preflight Failed" || s === "Rollback Failed" ? "bg-rose-50 text-rose-700" :
    s === "Committing" || s === "Rolling Back" ? "bg-indigo-50 text-indigo-700" :
    s === "Paused" ? "bg-amber-50 text-amber-700" :
    "bg-neutral-100 text-neutral-600"
  );

  return (
    <div className="min-h-screen bg-neutral-50">
      <AppHeader />
      <div className="max-w-[1600px] mx-auto px-6 py-8" data-testid="migration-commit-hub">
        {/* Header */}
        <div className="flex items-start justify-between gap-4 mb-3">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight text-neutral-900 flex items-center gap-2">
              <ShieldWarning weight="duotone" className="text-indigo-600" />
              Migration Commit Hub
            </h1>
            <p className="text-neutral-500 mt-1 text-sm">
              EB-14 · Controlled migration commit, rollback and legacy storage backfill.
            </p>
          </div>
          <button
            data-testid="commit-refresh"
            onClick={refresh}
            className="px-3 py-2 rounded-lg text-sm border border-neutral-200 bg-white hover:bg-neutral-100 flex items-center gap-2"
          >
            <ArrowClockwise weight="bold" /> Refresh
          </button>
        </div>

        {/* Environment banner */}
        {env && (
          <div className="mb-6 p-4 rounded-xl border border-amber-200 bg-amber-50" data-testid="commit-env-banner">
            <div className="flex items-start gap-3">
              <Warning weight="fill" className="text-amber-600 mt-0.5" />
              <div>
                <div className="font-semibold text-amber-900">
                  Commit mode: {env.commit_mode}
                </div>
                <div className="text-sm text-amber-800 mt-0.5">{env.banner}</div>
                <div className="text-xs text-amber-700 mt-1">
                  Multi-document transactions are {env.transactions_enabled ? "ENABLED" : "NOT enabled"} in this environment.
                  Real ACE data commit requires a separate explicit Admin instruction (Stage B).
                </div>
              </div>
            </div>
          </div>
        )}

        <div className="mb-6 p-4 rounded-xl border border-rose-200 bg-rose-50 text-rose-900 text-sm">
          <b>Migration commit writes canonical DCC records.</b> It requires an approved
          EB-12 report and explicit authorised confirmation. Do NOT execute in Production
          without deployment controls and explicit sign-off.
        </div>

        {/* Jobs table + New job */}
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-neutral-900">Commit Jobs</h2>
          {canManage && (
            <button
              data-testid="commit-new-job-btn"
              onClick={() => setNewJob({ migration_dry_run_id: "", name: "", description: "", mode: "Rehearsal" })}
              className="px-3 py-2 rounded-lg text-sm bg-indigo-600 text-white hover:bg-indigo-700"
            >+ New commit job</button>
          )}
        </div>
        <div className="rounded-xl border border-neutral-200 bg-white overflow-hidden mb-8">
          <table className="w-full text-sm">
            <thead className="bg-neutral-50 text-neutral-500 text-xs uppercase">
              <tr>
                <th className="text-left px-3 py-2">Name</th>
                <th className="text-left px-3 py-2">Mode</th>
                <th className="text-left px-3 py-2">Status</th>
                <th className="text-left px-3 py-2">Rows</th>
                <th className="text-left px-3 py-2">Requested</th>
                <th className="text-right px-3 py-2">Open</th>
              </tr>
            </thead>
            <tbody>
              {loading && <tr><td colSpan={6} className="px-3 py-4 text-center text-neutral-500">Loading…</td></tr>}
              {!loading && jobs.length === 0 && <tr><td colSpan={6} className="px-3 py-4 text-center text-neutral-500">No commit jobs yet.</td></tr>}
              {jobs.map(j => (
                <tr key={j.migration_commit_job_id}
                     className={`border-t border-neutral-100 ${selectedJob === j.migration_commit_job_id ? "bg-indigo-50/40" : ""}`}
                     data-testid={`commit-job-row-${j.migration_commit_job_id}`}>
                  <td className="px-3 py-2 font-medium">{j.name}</td>
                  <td className="px-3 py-2 text-neutral-600">{j.mode}</td>
                  <td className="px-3 py-2">
                    <span className={`px-2 py-0.5 rounded-full text-xs ${statusColor(j.status)}`}>{j.status}</span>
                  </td>
                  <td className="px-3 py-2 text-neutral-600">
                    {j.processed_rows || 0}/{j.total_rows || 0}
                    {j.failed_rows > 0 && <span className="ml-1 text-rose-600">· {j.failed_rows} failed</span>}
                  </td>
                  <td className="px-3 py-2 text-neutral-500 text-xs">{formatDateTime(j.requested_at)}</td>
                  <td className="px-3 py-2 text-right">
                    <button
                      data-testid={`commit-job-open-${j.migration_commit_job_id}`}
                      onClick={() => openJob(j.migration_commit_job_id)}
                      className="px-2 py-1 rounded text-xs border border-neutral-200 hover:bg-neutral-100"
                    >Open →</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Job detail panel */}
        {detail && (
          <div className="mb-8 rounded-xl border border-neutral-200 bg-white p-6" data-testid="commit-job-detail">
            <div className="flex items-start justify-between gap-3 mb-4">
              <div>
                <div className="text-lg font-semibold">{detail.name}</div>
                <div className="text-xs text-neutral-500">
                  {detail.mode} · Job {detail.migration_commit_job_id.slice(0, 8)} ·
                  {" "}Dry-run <Link className="underline" to={`/migration-preparation/dry-runs/${detail.migration_dry_run_id}`}>
                    {detail.migration_dry_run_id.slice(0, 8)}
                  </Link>
                </div>
              </div>
              <span className={`px-3 py-1 rounded-full text-xs ${statusColor(detail.status)}`} data-testid="commit-job-status">{detail.status}</span>
            </div>

            {/* Package summary */}
            {detail.immutable_package && (
              <div className="mb-4 p-3 rounded-lg bg-neutral-50 border border-neutral-200" data-testid="commit-package">
                <div className="text-xs uppercase text-neutral-500 mb-1">Immutable migration package</div>
                <div className="text-xs text-neutral-700 grid grid-cols-2 gap-x-4">
                  <div>Package SHA-256: <span className="font-mono">{detail.immutable_package.package_sha256?.slice(0, 16)}…</span></div>
                  <div>Go/No-Go: <b>{detail.immutable_package.go_no_go_result}</b></div>
                  <div>Rows: {detail.immutable_package.row_count}</div>
                  <div>Creates: {detail.immutable_package.proposed_create_count} · Updates: {detail.immutable_package.proposed_update_count}</div>
                  <div>Workbooks: {detail.immutable_package.workbooks?.length}</div>
                  <div>Mapping profiles: {detail.immutable_package.mapping_profiles?.length}</div>
                </div>
              </div>
            )}

            {/* Actions */}
            <div className="flex flex-wrap items-center gap-2 mb-4">
              {canManage && (
                <>
                  <button data-testid="commit-preflight" onClick={runPreflight} disabled={busy === "Preflight"}
                          className="px-3 py-2 rounded-lg text-sm border border-neutral-200 hover:bg-neutral-100 disabled:opacity-50">
                    Preflight
                  </button>
                  <button data-testid="commit-request-approval" onClick={requestApproval} disabled={busy === "Request approval"}
                          className="px-3 py-2 rounded-lg text-sm border border-neutral-200 hover:bg-neutral-100 disabled:opacity-50">
                    Request approval
                  </button>
                  <button data-testid="commit-approve" onClick={() => approve(true)} disabled={busy === "Approve"}
                          className="px-3 py-2 rounded-lg text-sm border border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100 disabled:opacity-50">
                    Approve (with risk)
                  </button>
                  {detail.mode === "Rehearsal" && (
                    <button data-testid="commit-execute-rehearsal" onClick={() => execute()} disabled={busy === "Execute"}
                            className="px-3 py-2 rounded-lg text-sm border border-indigo-200 bg-indigo-50 text-indigo-700 hover:bg-indigo-100 disabled:opacity-50">
                      <Play weight="fill" className="inline mr-1" /> Execute rehearsal
                    </button>
                  )}
                  {detail.mode === "Controlled Commit" && canAdmin && (
                    <button data-testid="commit-execute-controlled" onClick={() => setConfirmCommit("")} disabled={busy === "Execute"}
                            className="px-3 py-2 rounded-lg text-sm border border-rose-200 bg-rose-50 text-rose-700 hover:bg-rose-100 disabled:opacity-50">
                      <Warning weight="fill" className="inline mr-1" /> Execute Controlled Commit
                    </button>
                  )}
                  <button data-testid="commit-reconcile" onClick={reconcile} disabled={busy === "Reconcile"}
                          className="px-3 py-2 rounded-lg text-sm border border-neutral-200 hover:bg-neutral-100 disabled:opacity-50">
                    Reconcile
                  </button>
                  {["Committing", "Committed", "Completed", "Partially Completed"].includes(detail.status) && (
                    <button data-testid="commit-rollback-request" onClick={requestRollback}
                            className="px-3 py-2 rounded-lg text-sm border border-amber-200 bg-amber-50 text-amber-700 hover:bg-amber-100">
                      Rollback request
                    </button>
                  )}
                  {detail.status === "Rollback Pending" && canAdmin && (
                    <button data-testid="commit-rollback-approve" onClick={approveRollback}
                            className="px-3 py-2 rounded-lg text-sm border border-amber-200 bg-amber-100 hover:bg-amber-200">
                      Approve rollback
                    </button>
                  )}
                  {["Rollback Pending"].includes(detail.status) && canAdmin && (
                    <button data-testid="commit-rollback-execute" onClick={() => setConfirmRollback("")}
                            className="px-3 py-2 rounded-lg text-sm border border-rose-200 bg-rose-50 text-rose-700 hover:bg-rose-100">
                      <ArrowCounterClockwise weight="fill" className="inline mr-1" /> Execute rollback
                    </button>
                  )}
                </>
              )}
            </div>

            {/* Preflight results */}
            {preflight && (
              <div className="mb-4" data-testid="commit-preflight-results">
                <div className="text-sm font-semibold mb-2 flex items-center gap-2">
                  {preflight.passed ? <CheckCircle weight="fill" className="text-emerald-600" /> :
                    <XCircle weight="fill" className="text-rose-600" />}
                  Preflight {preflight.passed ? "PASSED" : "FAILED"}
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-1 text-xs">
                  {preflight.checks.map((c, i) => (
                    <div key={i} data-testid={`preflight-check-${c.check}`}
                          className={`px-2 py-1 rounded ${c.ok ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"}`}>
                      {c.ok ? "✓" : "✗"} {c.check}{c.message ? ` — ${c.message}` : ""}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Progress */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
              {[
                ["Processed", detail.processed_rows, "text-neutral-900"],
                ["Created", detail.created_records, "text-emerald-700"],
                ["Preserved", detail.preserved_records, "text-neutral-600"],
                ["Skipped", detail.skipped_records, "text-amber-700"],
                ["Failed", detail.failed_rows, "text-rose-700"],
              ].map(([lbl, val, cls]) => (
                <div key={lbl} className="p-3 rounded-lg border border-neutral-200 bg-white">
                  <div className="text-xs uppercase text-neutral-500">{lbl}</div>
                  <div className={`text-2xl font-semibold ${cls}`}>{val || 0}</div>
                </div>
              ))}
            </div>

            {/* Reconciliation */}
            {recon.length > 0 && (
              <div className="mb-4" data-testid="commit-reconciliation">
                <div className="text-sm font-semibold mb-1">Reconciliation history</div>
                {recon.slice(0, 3).map(r => (
                  <div key={r.migration_post_commit_reconciliation_id} className="text-xs p-2 rounded bg-neutral-50 border border-neutral-200 mb-1">
                    <span className={`font-semibold ${r.result === "Reconciled" ? "text-emerald-700" :
                      r.result === "Failed Reconciliation" ? "text-rose-700" : "text-amber-700"}`}>
                      {r.result}
                    </span> · missing: {r.missing_count} · mismatch: {r.mismatch_count}
                    <span className="text-neutral-500 ml-2">{formatDateTime(r.completed_at)}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Rollback package */}
            {rollback && (
              <div className="mb-4" data-testid="commit-rollback-package">
                <div className="text-sm font-semibold mb-1">Rollback package</div>
                <div className="text-xs text-neutral-600">
                  Status: <b>{rollback.package?.status}</b> · Actions: {rollback.actions_count} ·
                  Reverted: {rollback.reverted} · Pending: {rollback.pending} · Failed: {rollback.failed}
                </div>
              </div>
            )}

            {/* Events */}
            <div>
              <div className="text-sm font-semibold mb-1">Recent events</div>
              <div className="max-h-56 overflow-auto rounded border border-neutral-200">
                {events.length === 0 ? (
                  <div className="p-3 text-center text-neutral-500 text-xs">No events yet.</div>
                ) : events.map(e => (
                  <div key={e.migration_commit_event_id}
                        className="px-3 py-1.5 border-b border-neutral-100 text-xs flex justify-between">
                    <span><b>{e.event_type}</b> · {e.actor}</span>
                    <span className="text-neutral-500">{formatDateTime(e.created_at)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Legacy Storage Backfill */}
        {canManage && (
          <section className="mb-8" data-testid="commit-backfill-section">
            <h2 className="text-lg font-semibold text-neutral-900 mb-3">Legacy Storage Backfill</h2>
            <div className="rounded-xl border border-neutral-200 bg-white p-4">
              <div className="flex flex-wrap items-center gap-2 mb-3">
                <div className="text-xs text-neutral-500 mr-2">Scope:</div>
                {["Documents", "Exports", "Migration Workbooks", "All Legacy Development Assets"].map(s => (
                  canAdmin && (
                  <button key={s} data-testid={`backfill-scope-${s.replace(/ /g, "-").toLowerCase()}`}
                          onClick={() => startBackfill(s)}
                          className="px-2 py-1 rounded text-xs border border-neutral-200 hover:bg-neutral-100">
                    {s}
                  </button>
                  )
                ))}
                <div className="ml-auto text-xs text-neutral-400">
                  Legacy source records are always retained.
                </div>
              </div>
              <table className="w-full text-sm">
                <thead className="bg-neutral-50 text-neutral-500 text-xs uppercase">
                  <tr>
                    <th className="text-left px-3 py-2">Scope</th>
                    <th className="text-left px-3 py-2">Status</th>
                    <th className="text-left px-3 py-2">Found</th>
                    <th className="text-left px-3 py-2">Migrated</th>
                    <th className="text-left px-3 py-2">Verified</th>
                    <th className="text-left px-3 py-2">Failed</th>
                    <th className="text-left px-3 py-2">Source retained</th>
                  </tr>
                </thead>
                <tbody>
                  {backfills.length === 0 && <tr><td colSpan={7} className="px-3 py-3 text-center text-neutral-500">No backfill jobs yet.</td></tr>}
                  {backfills.slice(0, 10).map(b => (
                    <tr key={b.storage_backfill_job_id} className="border-t border-neutral-100" data-testid={`backfill-row-${b.storage_backfill_job_id}`}>
                      <td className="px-3 py-2">{b.scope}</td>
                      <td className="px-3 py-2">
                        <span className={`px-2 py-0.5 rounded-full text-xs ${statusColor(b.status)}`}>{b.status}</span>
                      </td>
                      <td className="px-3 py-2">{b.found}</td>
                      <td className="px-3 py-2">{b.migrated}</td>
                      <td className="px-3 py-2 text-emerald-700">{b.verified}</td>
                      <td className={`px-3 py-2 ${b.failed > 0 ? "text-rose-700 font-semibold" : ""}`}>{b.failed}</td>
                      <td className="px-3 py-2">{b.source_retained ? "Yes" : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* New Job modal */}
        {newJob && (
          <div className="fixed inset-0 z-30 bg-black/40 flex items-center justify-center" data-testid="commit-new-job-modal">
            <div className="bg-white rounded-xl border border-neutral-200 w-[560px] max-w-full p-5 space-y-3">
              <div className="text-lg font-semibold">Create commit job</div>
              <div className="text-xs text-rose-700 bg-rose-50 border border-rose-200 p-2 rounded">
                No-Go dry runs are excluded from this list. Real ACE data requires Controlled Commit + Admin approval + Stage B instruction.
              </div>
              <label className="block text-xs text-neutral-500">Approved dry run
                <select data-testid="new-job-dryrun-select"
                          className="w-full mt-1 px-3 py-2 rounded-lg border border-neutral-200"
                          value={newJob.migration_dry_run_id}
                          onChange={e => setNewJob({ ...newJob, migration_dry_run_id: e.target.value })}>
                  <option value="">Select…</option>
                  {eligibleDryRuns.map(d => (
                    <option key={d.migration_dry_run_id} value={d.migration_dry_run_id}>
                      {d.name} — {d.migration_dry_run_id.slice(0, 8)} — rows {d.row_count}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-xs text-neutral-500">Name
                <input data-testid="new-job-name-input"
                        className="w-full mt-1 px-3 py-2 rounded-lg border border-neutral-200"
                        value={newJob.name}
                        onChange={e => setNewJob({ ...newJob, name: e.target.value })} />
              </label>
              <label className="block text-xs text-neutral-500">Mode
                <select data-testid="new-job-mode-select"
                          className="w-full mt-1 px-3 py-2 rounded-lg border border-neutral-200"
                          value={newJob.mode}
                          onChange={e => setNewJob({ ...newJob, mode: e.target.value })}>
                  <option value="Rehearsal">Rehearsal (no canonical writes)</option>
                  {canAdmin && <option value="Controlled Commit">Controlled Commit (canonical writes, Admin only)</option>}
                </select>
              </label>
              <div className="flex items-center justify-end gap-2 pt-2">
                <button data-testid="new-job-cancel" onClick={() => setNewJob(null)}
                        className="px-3 py-2 rounded-lg text-sm border border-neutral-200">Cancel</button>
                <button data-testid="new-job-save" onClick={createJob}
                        className="px-3 py-2 rounded-lg text-sm bg-indigo-600 text-white hover:bg-indigo-700">Create</button>
              </div>
            </div>
          </div>
        )}

        {/* Typed confirmation for controlled commit */}
        {confirmCommit !== null && (
          <div className="fixed inset-0 z-30 bg-black/40 flex items-center justify-center" data-testid="commit-confirm-modal">
            <div className="bg-white rounded-xl border border-rose-200 w-[520px] max-w-full p-5 space-y-3">
              <div className="text-lg font-semibold text-rose-700 flex items-center gap-2">
                <Warning weight="fill" /> Irreversible operation
              </div>
              <div className="text-sm">
                This will write <b>canonical DCC records</b>. Rollback is available but staged
                idempotent commit does NOT provide full atomic rollback. Type
                <code className="mx-1 px-1 py-0.5 rounded bg-neutral-100">COMMIT ACE MIGRATION</code>
                to confirm.
              </div>
              <input data-testid="commit-confirm-input"
                      className="w-full px-3 py-2 rounded-lg border border-neutral-200"
                      value={confirmCommit}
                      onChange={e => setConfirmCommit(e.target.value)}
                      autoFocus placeholder="COMMIT ACE MIGRATION" />
              <div className="flex items-center justify-end gap-2">
                <button data-testid="commit-confirm-cancel" onClick={() => setConfirmCommit(null)}
                        className="px-3 py-2 rounded-lg text-sm border border-neutral-200">Cancel</button>
                <button data-testid="commit-confirm-run" onClick={() => execute(confirmCommit)}
                        disabled={busy === "Execute" || confirmCommit !== "COMMIT ACE MIGRATION"}
                        className="px-3 py-2 rounded-lg text-sm bg-rose-600 text-white hover:bg-rose-700 disabled:opacity-40">
                  Execute
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Typed confirmation for rollback */}
        {confirmRollback !== null && (
          <div className="fixed inset-0 z-30 bg-black/40 flex items-center justify-center" data-testid="rollback-confirm-modal">
            <div className="bg-white rounded-xl border border-rose-200 w-[520px] max-w-full p-5 space-y-3">
              <div className="text-lg font-semibold text-rose-700">Confirm rollback</div>
              <div className="text-sm">
                This will attempt to reverse canonical writes. Later user edits will block destructive rollback. Type
                <code className="mx-1 px-1 py-0.5 rounded bg-neutral-100">ROLL BACK MIGRATION</code>
                to confirm.
              </div>
              <input data-testid="rollback-confirm-input"
                      className="w-full px-3 py-2 rounded-lg border border-neutral-200"
                      value={confirmRollback}
                      onChange={e => setConfirmRollback(e.target.value)}
                      autoFocus placeholder="ROLL BACK MIGRATION" />
              <div className="flex items-center justify-end gap-2">
                <button onClick={() => setConfirmRollback(null)}
                        className="px-3 py-2 rounded-lg text-sm border border-neutral-200">Cancel</button>
                <button data-testid="rollback-confirm-run" onClick={() => executeRollback(confirmRollback)}
                        disabled={confirmRollback !== "ROLL BACK MIGRATION"}
                        className="px-3 py-2 rounded-lg text-sm bg-rose-600 text-white hover:bg-rose-700 disabled:opacity-40">
                  Rollback
                </button>
              </div>
            </div>
          </div>
        )}

        <div className="text-xs text-neutral-400 mt-6">
          Stage A · Sanitised fictional fixtures only · No real ACE data has been imported.
        </div>
      </div>
    </div>
  );
}
