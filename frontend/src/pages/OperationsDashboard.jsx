import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import AppHeader from "../components/app/AppHeader";
import api, { formatApiErrorDetail } from "../lib/api";
import { toast } from "sonner";
import { ArrowClockwise, Gauge } from "@phosphor-icons/react";

const HEALTH_COLOR = {
  Healthy: "bg-emerald-50 text-emerald-800 border-emerald-200",
  Warning: "bg-amber-50 text-amber-800 border-amber-200",
  Critical: "bg-rose-50 text-rose-800 border-rose-200",
  Disabled: "bg-slate-100 text-slate-700 border-slate-200",
  Unknown: "bg-slate-100 text-slate-700 border-slate-200",
};

export default function OperationsDashboard() {
  const [s, setS] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/operations/summary");
      setS(data);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Failed to load");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader showBack />
      <main className="max-w-7xl mx-auto px-6 py-8" data-testid="operations-dashboard">
        <div className="flex items-baseline justify-between mb-6">
          <h1 className="font-display text-2xl font-semibold text-slate-900">
            Operations Command Dashboard
          </h1>
          <button data-testid="ops-refresh" onClick={load} disabled={loading}
            className="text-xs px-3 py-1.5 rounded border border-slate-300 bg-white hover:bg-slate-50 flex items-center gap-1.5">
            <ArrowClockwise size={14} weight="bold" /> Refresh
          </button>
        </div>

        {loading && !s && <div className="text-sm text-slate-500">Loading…</div>}

        {s && (
          <>
            <div className={`border rounded-xl p-4 mb-6 flex items-center gap-4 ${HEALTH_COLOR[s.overall_health] || HEALTH_COLOR.Unknown}`}
                 data-testid="ops-health-banner">
              <Gauge size={28} weight="duotone" />
              <div className="flex-1">
                <div className="text-xs uppercase tracking-widest opacity-70">Overall operational health</div>
                <div className="text-lg font-semibold" data-testid="ops-health-value">{s.overall_health}</div>
              </div>
              <div className="text-right text-xs">
                <div>Migration: <b>{s.migration_state}</b></div>
                <div>Storage: <b>{s.storage_integrity_state}</b></div>
              </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
              {[
                ["Active Drivers", s.active_drivers, "metric-active"],
                ["Inactive Drivers", s.inactive_drivers, "metric-inactive"],
                ["Ready Drivers", s.ready_drivers, "metric-ready"],
                ["Blocked Drivers", s.blocked_drivers, "metric-blocked"],
                ["Overrides", s.drivers_with_overrides, "metric-overrides"],
                ["Missing Mandatory", s.drivers_missing_mandatory, "metric-missing"],
                ["Expired Compliance", s.expired_compliance, "metric-exp-cmp"],
                ["Critical Defects (Veh)", s.critical_defect_vehicles, "metric-critdef"],
                ["Overdue Maintenance", s.overdue_maintenance, "metric-overdue"],
                ["Incidents (open)", s.active_notification_incidents, "metric-incidents"],
                ["Dead-letters", s.dead_letter_deliveries, "metric-deadletter"],
                ["Failed Jobs", s.failed_scheduled_jobs, "metric-failed-jobs"],
              ].map(([label, val, tid]) => (
                <div key={label} data-testid={tid}
                     className="bg-white border border-slate-200 rounded-lg p-4">
                  <div className="text-[11px] uppercase tracking-widest text-slate-500">{label}</div>
                  <div className="text-2xl font-semibold text-slate-900 mt-1">{String(val ?? "—")}</div>
                </div>
              ))}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <NavCard to="/operations/driver-readiness" title="Driver Readiness" tid="nav-driver-readiness" />
              <NavCard to="/operations/compliance-workload" title="Compliance Workload" tid="nav-compliance" />
              <NavCard to="/operations/migration-readiness" title="Migration Readiness" tid="nav-migration" />
            </div>
          </>
        )}
      </main>
    </div>
  );
}

function NavCard({ to, title, tid }) {
  return (
    <Link to={to} data-testid={tid}
      className="bg-white border border-slate-200 rounded-xl p-5 hover:shadow-md hover:-translate-y-0.5 hover:border-cyan-300 transition-all block">
      <div className="font-display font-semibold text-slate-900">{title}</div>
    </Link>
  );
}
