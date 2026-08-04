import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import AppHeader from "../components/app/AppHeader";
import api, { formatApiErrorDetail } from "../lib/api";
import { toast } from "sonner";
import { useAuth } from "../context/AuthContext";
import { Play, Pause, PlayCircle, Clock, ArrowClockwise } from "@phosphor-icons/react";

/**
 * EB-15 — Automation Jobs Page.
 * Registry of scheduled jobs. Manager+ can enable/disable and Run-Now.
 */
export default function AutomationJobsPage() {
  const { user } = useAuth();
  const canManage = user?.role === "Manager" || user?.role === "Admin";

  const [jobs, setJobs] = useState([]);
  const [runs, setRuns] = useState([]);
  const [selectedRun, setSelectedRun] = useState(null);
  const [category, setCategory] = useState("All");
  const [busy, setBusy] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [j, r] = await Promise.all([
        api.get("/automation/jobs"),
        api.get("/automation/job-runs?limit=50"),
      ]);
      setJobs(j.data || []);
      setRuns(r.data || []);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Failed to load jobs");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const categories = useMemo(() => {
    const set = new Set(jobs.map((j) => j.category).filter(Boolean));
    return ["All", ...Array.from(set).sort()];
  }, [jobs]);

  const filtered = category === "All" ? jobs : jobs.filter((j) => j.category === category);

  const toggleJob = async (job) => {
    setBusy(job.job_key);
    try {
      const path = job.enabled ? "disable" : "enable";
      await api.post(`/automation/jobs/${job.job_key}/${path}`);
      toast.success(`${job.job_key} ${path}d`);
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setBusy(null); }
  };

  const runNow = async (job) => {
    setBusy(`run-${job.job_key}`);
    try {
      const { data } = await api.post(`/automation/jobs/${job.job_key}/run`, {});
      toast.success(`Run ${data.status} — ${job.job_key}`);
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setBusy(null); }
  };

  const openRun = async (runId) => {
    try {
      const { data } = await api.get(`/automation/job-runs/${runId}`);
      setSelectedRun(data);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    }
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader showBack />
      <main className="max-w-7xl mx-auto px-6 py-8" data-testid="automation-jobs-page">
        <div className="flex items-baseline justify-between mb-6">
          <div>
            <h1 className="font-display text-2xl font-semibold text-slate-900">Scheduled Jobs</h1>
            <p className="text-sm text-slate-500 mt-1">
              <Link to="/administration/automation" className="text-cyan-700 hover:underline">
                ← Automation Hub
              </Link>
            </p>
          </div>
          <button
            data-testid="jobs-refresh"
            className="text-xs px-3 py-1.5 rounded-md border border-slate-300 bg-white hover:bg-slate-50 flex items-center gap-1.5"
            onClick={load} disabled={loading}
          ><ArrowClockwise size={14} weight="bold" /> Refresh</button>
        </div>

        <div className="mb-4 flex gap-2 flex-wrap" data-testid="jobs-category-filter">
          {categories.map((c) => (
            <button
              key={c} onClick={() => setCategory(c)}
              data-testid={`jobs-cat-${c.toLowerCase()}`}
              className={`text-xs px-3 py-1 rounded-full border ${
                c === category
                  ? "bg-slate-900 border-slate-900 text-white"
                  : "bg-white border-slate-300 text-slate-700 hover:border-slate-400"
              }`}
            >{c}</button>
          ))}
        </div>

        <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-600 text-xs uppercase tracking-wider">
              <tr>
                <th className="text-left px-4 py-2">Job Key</th>
                <th className="text-left px-4 py-2">Category</th>
                <th className="text-left px-4 py-2">Schedule</th>
                <th className="text-left px-4 py-2">Enabled</th>
                <th className="text-left px-4 py-2">Last Run</th>
                <th className="text-right px-4 py-2">Actions</th>
              </tr>
            </thead>
            <tbody data-testid="jobs-tbody">
              {filtered.map((j) => (
                <tr key={j.job_key} className="border-t border-slate-100" data-testid={`job-row-${j.job_key}`}>
                  <td className="px-4 py-2 font-mono text-xs">{j.job_key}</td>
                  <td className="px-4 py-2">{j.category}</td>
                  <td className="px-4 py-2 font-mono text-xs">{j.schedule_expression}</td>
                  <td className="px-4 py-2">
                    <span className={`text-[11px] px-2 py-0.5 rounded-full ${
                      j.enabled ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"
                    }`}>{j.enabled ? "Enabled" : "Disabled"}</span>
                  </td>
                  <td className="px-4 py-2 text-xs text-slate-500">{j.last_run_at || "—"}</td>
                  <td className="px-4 py-2 text-right">
                    {canManage && (
                      <div className="inline-flex gap-2">
                        <button
                          disabled={busy === `run-${j.job_key}`}
                          onClick={() => runNow(j)}
                          data-testid={`run-${j.job_key}`}
                          className="text-xs px-2 py-1 rounded border border-cyan-300 bg-cyan-50 text-cyan-800 hover:bg-cyan-100 flex items-center gap-1"
                        ><PlayCircle size={12} weight="bold" /> Run</button>
                        <button
                          disabled={busy === j.job_key}
                          onClick={() => toggleJob(j)}
                          data-testid={`toggle-${j.job_key}`}
                          className="text-xs px-2 py-1 rounded border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 flex items-center gap-1"
                        >
                          {j.enabled ? <Pause size={12} weight="bold" /> : <Play size={12} weight="bold" />}
                          {j.enabled ? "Disable" : "Enable"}
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr><td colSpan={6} className="p-6 text-center text-slate-500 text-sm">No jobs found</td></tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Recent runs */}
        <div className="mt-8">
          <h2 className="font-display text-lg font-semibold text-slate-900 mb-3">Recent Runs</h2>
          <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-600 text-xs uppercase tracking-wider">
                <tr>
                  <th className="text-left px-4 py-2">Job</th>
                  <th className="text-left px-4 py-2">Status</th>
                  <th className="text-left px-4 py-2">Trigger</th>
                  <th className="text-left px-4 py-2">Duration</th>
                  <th className="text-left px-4 py-2">Started</th>
                  <th className="text-right px-4 py-2">Actions</th>
                </tr>
              </thead>
              <tbody data-testid="runs-tbody">
                {runs.map((r) => (
                  <tr key={r.scheduled_job_run_id} className="border-t border-slate-100"
                      data-testid={`run-row-${r.scheduled_job_run_id}`}>
                    <td className="px-4 py-2 font-mono text-xs">{r.job_key}</td>
                    <td className="px-4 py-2">
                      <StatusPill status={r.status} />
                    </td>
                    <td className="px-4 py-2 text-xs">{r.trigger_type}</td>
                    <td className="px-4 py-2 text-xs">{r.duration_ms ? `${r.duration_ms} ms` : "—"}</td>
                    <td className="px-4 py-2 text-xs text-slate-500">{r.started_at}</td>
                    <td className="px-4 py-2 text-right">
                      <button
                        onClick={() => openRun(r.scheduled_job_run_id)}
                        data-testid={`view-run-${r.scheduled_job_run_id}`}
                        className="text-xs px-2 py-1 rounded border border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
                      >View</button>
                    </td>
                  </tr>
                ))}
                {runs.length === 0 && (
                  <tr><td colSpan={6} className="p-6 text-center text-slate-500 text-sm">No runs yet</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {selectedRun && (
          <RunDetail run={selectedRun} onClose={() => setSelectedRun(null)} />
        )}
      </main>
    </div>
  );
}

function StatusPill({ status }) {
  const map = {
    Completed: "bg-emerald-50 text-emerald-700",
    Running: "bg-cyan-50 text-cyan-700",
    Failed: "bg-rose-50 text-rose-700",
    "Skipped Due to Lock": "bg-amber-50 text-amber-700",
    Cancelled: "bg-slate-100 text-slate-700",
  };
  return (
    <span className={`text-[11px] px-2 py-0.5 rounded-full ${map[status] || "bg-slate-100 text-slate-700"}`}>
      {status}
    </span>
  );
}

function RunDetail({ run, onClose }) {
  return (
    <div className="fixed inset-0 bg-black/40 z-40 flex items-center justify-center p-4"
         onClick={onClose} data-testid="run-detail-modal">
      <div className="bg-white rounded-xl max-w-3xl w-full max-h-[80vh] overflow-auto p-6"
           onClick={(e) => e.stopPropagation()}>
        <div className="flex items-baseline justify-between mb-4">
          <h3 className="font-display text-lg font-semibold">Run: {run.job_key}</h3>
          <button onClick={onClose} data-testid="run-detail-close"
                  className="text-slate-500 hover:text-slate-900 text-sm">✕</button>
        </div>
        <div className="grid grid-cols-2 gap-3 text-xs mb-4">
          <div><b>Status:</b> {run.status}</div>
          <div><b>Trigger:</b> {run.trigger_type}</div>
          <div><b>Started:</b> {run.started_at}</div>
          <div><b>Completed:</b> {run.completed_at || run.failed_at || "—"}</div>
          <div><b>Duration:</b> {run.duration_ms ? `${run.duration_ms} ms` : "—"}</div>
          <div><b>Correlation:</b> <span className="font-mono">{run.correlation_id}</span></div>
        </div>
        {run.result_summary && (
          <div className="mb-4">
            <div className="text-xs uppercase tracking-widest text-slate-500 mb-1">Result summary</div>
            <pre className="text-xs bg-slate-50 p-3 rounded overflow-auto">{JSON.stringify(run.result_summary, null, 2)}</pre>
          </div>
        )}
        {run.failure_reason && (
          <div className="mb-4 p-3 bg-rose-50 border border-rose-200 rounded text-xs text-rose-800">
            <b>Failure:</b> {run.failure_reason}
          </div>
        )}
        <div>
          <div className="text-xs uppercase tracking-widest text-slate-500 mb-1">Events</div>
          <ul className="text-xs space-y-1">
            {(run.events || []).map((e) => (
              <li key={e.scheduled_job_event_id} className="border-l-2 border-slate-200 pl-2">
                <span className="font-semibold">{e.event_type}</span> · {e.performed_at} · {e.performed_by}
              </li>
            ))}
            {(!run.events || run.events.length === 0) && (
              <li className="text-slate-500">No events</li>
            )}
          </ul>
        </div>
      </div>
    </div>
  );
}
