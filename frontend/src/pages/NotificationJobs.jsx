import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "../lib/api";
import { ArrowClockwise, Play } from "@phosphor-icons/react";
import { useAuth } from "../context/AuthContext";
import { formatDateTime } from "../lib/notifications";

const JOB_TYPES = [
  { slug: "compliance-scan", label: "Compliance Scan" },
  { slug: "critical-scan", label: "Critical Scan" },
  { slug: "process-snoozes", label: "Process Snoozes" },
  { slug: "process-escalations", label: "Process Escalations" },
  { slug: "retry-deliveries", label: "Retry Deliveries" },
  { slug: "reconcile", label: "Reconcile" },
];

export default function NotificationJobs() {
  const { user } = useAuth();
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(null);
  const [confirm, setConfirm] = useState(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/notification-jobs");
      setJobs(data || []);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { refresh(); }, [refresh]);

  const canRunSnooze = ["Admin", "Manager"].includes(user?.role);

  const runJob = async (slug) => {
    setRunning(slug);
    setConfirm(null);
    try {
      const { data } = await api.post(`/notification-jobs/${slug}`);
      toast.success(`${slug} · ${data.status} · ${data.records_scanned ?? 0} scanned`);
      refresh();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setRunning(null); }
  };

  return (
    <section data-testid="notification-jobs">
      <div className="mb-3 flex items-center justify-between flex-wrap gap-2">
        <div className="text-xs text-slate-500">
          Job execution is <strong>manual only</strong> in development. Production must invoke these endpoints from a durable scheduler.
        </div>
        <button onClick={refresh} data-testid="jobs-refresh" className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-900">
          <ArrowClockwise size={12} /> Refresh
        </button>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 mb-4">
        {JOB_TYPES.map((j) => (
          <button
            key={j.slug}
            data-testid={`job-run-${j.slug}`}
            disabled={running === j.slug || (j.slug === "process-snoozes" && !canRunSnooze)}
            onClick={() => setConfirm(j)}
            className="border border-slate-200 hover:border-slate-400 rounded-lg px-3 py-2 text-left disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500">{j.slug}</div>
            <div className="text-xs font-medium text-slate-800 inline-flex items-center gap-1">
              <Play size={10} weight="bold" /> Run {j.label}
            </div>
          </button>
        ))}
      </div>

      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200">
                {["Job type", "Status", "Started", "Completed", "Scanned", "Events", "Created", "Updated", "Deliveries", "Triggered by"].map((h) => (
                  <th key={h} className="text-left px-4 py-3 text-[10px] uppercase tracking-[0.2em] font-semibold text-slate-500">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading && <tr><td colSpan={10} className="px-4 py-14 text-center text-slate-400 text-sm">Loading…</td></tr>}
              {!loading && jobs.length === 0 && <tr><td colSpan={10} className="px-4 py-14 text-center text-slate-500 text-sm">No job runs yet.</td></tr>}
              {!loading && jobs.map((j) => (
                <tr key={j.notification_job_run_id} data-testid={`job-row-${j.notification_job_run_id}`}
                  className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                  <td className="px-4 py-2 text-xs text-slate-700">{j.job_type}</td>
                  <td className="px-4 py-2">
                    <span className={`inline-flex text-[10px] font-medium uppercase tracking-[0.15em] px-2 py-0.5 rounded-full border ${_tone(j.status)}`}>
                      {j.status}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-xs text-slate-500">{formatDateTime(j.started_at)}</td>
                  <td className="px-4 py-2 text-xs text-slate-500">{formatDateTime(j.completed_at)}</td>
                  <td className="px-4 py-2 text-xs text-slate-700 text-right">{j.records_scanned ?? 0}</td>
                  <td className="px-4 py-2 text-xs text-slate-700 text-right">{j.events_created ?? 0}</td>
                  <td className="px-4 py-2 text-xs text-emerald-700 text-right">{j.notifications_created ?? 0}</td>
                  <td className="px-4 py-2 text-xs text-cyan-700 text-right">{j.notifications_updated ?? 0}</td>
                  <td className="px-4 py-2 text-xs text-blue-700 text-right">{j.deliveries_created ?? 0}</td>
                  <td className="px-4 py-2 text-xs text-slate-500 truncate max-w-[160px]">{j.triggered_by}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {confirm && (
        <ConfirmDialog job={confirm}
          onConfirm={() => runJob(confirm.slug)}
          onClose={() => setConfirm(null)}
          running={running === confirm.slug}
        />
      )}
    </section>
  );
}

function _tone(status) {
  if (status === "Completed") return "bg-emerald-50 text-emerald-700 border-emerald-200";
  if (status === "Completed with Warnings") return "bg-amber-50 text-amber-700 border-amber-200";
  if (status === "Running") return "bg-blue-50 text-blue-700 border-blue-200";
  if (status === "Failed") return "bg-red-50 text-red-700 border-red-200";
  return "bg-slate-100 text-slate-600 border-slate-200";
}

function ConfirmDialog({ job, onConfirm, onClose, running }) {
  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4" data-testid="job-confirm" onClick={onClose}>
      <div className="bg-white w-full sm:max-w-md rounded-xl shadow-xl border border-slate-200" onClick={(e) => e.stopPropagation()}>
        <div className="px-5 py-4 border-b border-slate-200">
          <div className="font-display font-semibold text-slate-900">Run {job.label}?</div>
          <div className="text-[11px] text-slate-500 mt-1">
            This will trigger the <code>{job.slug}</code> job synchronously.
            Repeated scans are idempotent and do not create duplicate alerts.
          </div>
        </div>
        <div className="px-5 py-4 flex justify-end gap-2">
          <button onClick={onClose} className="text-sm text-slate-600 hover:text-slate-900 px-3 py-1.5 rounded-md">Cancel</button>
          <button onClick={onConfirm} disabled={running} data-testid="job-confirm-run"
            className="text-sm text-white bg-slate-900 hover:bg-slate-800 disabled:opacity-40 px-4 py-1.5 rounded-md">
            {running ? "Running…" : "Run job"}
          </button>
        </div>
      </div>
    </div>
  );
}
