/**
 * EB-10 · Activation Jobs admin — /administration/activation-jobs
 */
import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import AppHeader from "../components/app/AppHeader";
import api, { formatApiErrorDetail } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { ArrowsClockwise, ShieldCheck, ArrowClockwise } from "@phosphor-icons/react";

export default function ActivationJobsPage() {
  const { user } = useAuth();
  const canRun = ["Admin", "Manager"].includes(user?.role);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/activation/jobs");
      setRows(data);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Load failed");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const run = async (path, label) => {
    if (!window.confirm(`Run job: ${label}?`)) return;
    setBusy(true);
    try {
      await api.post(`/activation/jobs/${path}`);
      toast.success(`${label} completed`);
      await refresh();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Job failed");
    } finally { setBusy(false); }
  };

  return (
    <div className="min-h-screen bg-slate-50" data-testid="jobs-page">
      <AppHeader showBack />
      <main className="max-w-6xl mx-auto px-4 lg:px-8 py-6">
        <div className="flex items-center justify-between mb-6">
          <h1 className="font-display text-2xl font-semibold text-slate-900">Activation Jobs</h1>
          {canRun && (
            <div className="flex items-center gap-2">
              <button data-testid="job-recalc-all" disabled={busy} onClick={() => run("recalculate-all", "Recalculate all")} className="text-xs px-3 py-1.5 rounded border border-slate-200 hover:bg-slate-50 inline-flex items-center gap-1 disabled:opacity-50">
                <ArrowsClockwise size={12} /> Recalculate all
              </button>
              <button data-testid="job-expire-overrides" disabled={busy} onClick={() => run("expire-overrides", "Expire overrides")} className="text-xs px-3 py-1.5 rounded border border-slate-200 hover:bg-slate-50 inline-flex items-center gap-1 disabled:opacity-50">
                <ShieldCheck size={12} /> Expire overrides
              </button>
              <button data-testid="job-reconcile" disabled={busy} onClick={() => run("reconcile", "Reconcile")} className="text-xs px-3 py-1.5 rounded border border-slate-200 hover:bg-slate-50 inline-flex items-center gap-1 disabled:opacity-50">
                <ArrowClockwise size={12} /> Reconcile
              </button>
            </div>
          )}
        </div>
        {loading ? (
          <div className="text-slate-500 text-sm">Loading…</div>
        ) : rows.length === 0 ? (
          <div data-testid="jobs-empty" className="text-slate-500 text-sm italic">No jobs run yet.</div>
        ) : (
          <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-[10px] uppercase tracking-[0.15em] text-slate-500">
                <tr>
                  <th className="px-3 py-2 text-left">Type</th>
                  <th className="px-3 py-2 text-left">Started</th>
                  <th className="px-3 py-2 text-left">Completed</th>
                  <th className="px-3 py-2 text-right">Counts</th>
                  <th className="px-3 py-2 text-right">Failures</th>
                  <th className="px-3 py-2 text-left">By</th>
                  <th className="px-3 py-2 text-left">Correlation</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((j) => (
                  <tr key={j.job_id} data-testid={`job-row-${j.job_id}`} className="border-t border-slate-100">
                    <td className="px-3 py-2 font-medium">{j.job_type}</td>
                    <td className="px-3 py-2 text-slate-600">{new Date(j.started_at).toLocaleString()}</td>
                    <td className="px-3 py-2 text-slate-600">{j.completed_at ? new Date(j.completed_at).toLocaleString() : "—"}</td>
                    <td className="px-3 py-2 text-right font-mono text-xs">{JSON.stringify(j.counts)}</td>
                    <td className="px-3 py-2 text-right">{(j.failures || []).length}</td>
                    <td className="px-3 py-2 text-slate-600">{j.performed_by}</td>
                    <td className="px-3 py-2 font-mono text-[10px] text-slate-400">{(j.correlation_id || "").slice(0, 8)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}
