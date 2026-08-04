import React, { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import AppHeader from "../components/app/AppHeader";
import api, { formatApiErrorDetail } from "../lib/api";
import { toast } from "sonner";
import { ArrowClockwise } from "@phosphor-icons/react";

export default function MigrationReadinessPage() {
  const [s, setS] = useState(null);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/operations/migration-readiness");
      setS(data);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const GONO = {
    "GO": "bg-emerald-50 text-emerald-800 border-emerald-200",
    "CONDITIONAL GO": "bg-amber-50 text-amber-800 border-amber-200",
    "NO GO": "bg-rose-50 text-rose-800 border-rose-200",
    "Not Assessed": "bg-slate-100 text-slate-700 border-slate-200",
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader showBack />
      <main className="max-w-6xl mx-auto px-6 py-8" data-testid="migration-readiness-page">
        <div className="flex items-baseline justify-between mb-6">
          <div>
            <h1 className="font-display text-2xl font-semibold text-slate-900">Migration Readiness</h1>
            <Link to="/operations" className="text-cyan-700 text-sm hover:underline">← Operations</Link>
          </div>
          <button data-testid="mr-refresh" onClick={load} disabled={loading}
            className="text-xs px-3 py-1.5 rounded border border-slate-300 bg-white hover:bg-slate-50 flex items-center gap-1.5">
            <ArrowClockwise size={14} weight="bold" /> Refresh
          </button>
        </div>
        {s && (
          <>
            <div className={`border rounded-xl p-5 mb-6 ${GONO[s.go_no_go_recommendation] || GONO["Not Assessed"]}`}
                 data-testid="mr-gono-banner">
              <div className="text-xs uppercase tracking-widest opacity-70">Go / No-Go</div>
              <div className="text-2xl font-semibold" data-testid="mr-gono-value">
                {s.go_no_go_recommendation}
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Card title="Rollback ready" value={s.rollback_ready ? "Yes" : "No"} tid="mr-rollback" />
              <Card title="Storage ready" value={s.storage_ready ? "Yes" : "No"} tid="mr-storage" />
              <Card title="Scheduler ready" value={s.scheduler_ready ? "Yes" : "No"} tid="mr-scheduler" />
              <Card title="Latest commit status"
                     value={s.latest_commit_job?.status || "—"} tid="mr-commit-status" />
            </div>
            <div className="mt-6 p-4 bg-white border border-slate-200 rounded-xl text-xs" data-testid="mr-latest">
              <div className="font-semibold text-slate-900 mb-2">Latest dry run</div>
              <pre className="text-xs bg-slate-50 p-3 rounded overflow-auto max-h-64">
{s.latest_dry_run ? JSON.stringify(s.latest_dry_run, null, 2) : "No dry runs yet"}
              </pre>
            </div>
            <div className="mt-4 text-xs text-slate-500 italic" data-testid="mr-no-commit-btn">
              This dashboard is read-only — commit actions live in the Migration Commit Hub.
            </div>
          </>
        )}
      </main>
    </div>
  );
}
function Card({ title, value, tid }) {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4" data-testid={tid}>
      <div className="text-[11px] uppercase tracking-widest text-slate-500">{title}</div>
      <div className="text-lg font-semibold text-slate-900 mt-1">{value}</div>
    </div>
  );
}
