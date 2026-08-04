import React, { useCallback, useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import AppHeader from "../components/app/AppHeader";
import api, { formatApiErrorDetail } from "../lib/api";
import { toast } from "sonner";
import { useAuth } from "../context/AuthContext";
import {
  Gauge, Clock, EnvelopeSimple, ShieldCheck, ArrowClockwise,
  Warning, CheckCircle, XCircle, ListChecks, Camera,
} from "@phosphor-icons/react";

/**
 * EB-15 — Automation & Delivery Operations Hub.
 * Read-first status page for Allocators+, action panels for Managers/Admins.
 * EB-16 adds Automation Health History.
 */
export default function AutomationHub() {
  const { user } = useAuth();
  const [status, setStatus] = useState(null);
  const [snapshots, setSnapshots] = useState([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [statusRes, snapRes] = await Promise.all([
        api.get("/automation/status"),
        api.get("/automation/health-snapshots?limit=50").catch(() => ({ data: [] })),
      ]);
      setStatus(statusRes.data);
      setSnapshots(snapRes.data || []);
    } catch (e) {
      toast.error(
        formatApiErrorDetail(e?.response?.data?.detail) || "Failed to load automation status",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const takeSnapshot = async () => {
    setBusy(true);
    try {
      await api.post("/automation/health-snapshots");
      toast.success("Health snapshot captured");
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setBusy(false); }
  };

  const canManage = user?.role === "Manager" || user?.role === "Admin";

  if (user && !["Allocator", "Compliance", "Manager", "Admin"].includes(user.role)) {
    return <Navigate to="/" replace />;
  }

  const healthColor = {
    Healthy: "bg-emerald-50 text-emerald-800 border-emerald-200",
    Warning: "bg-amber-50 text-amber-800 border-amber-200",
    Critical: "bg-rose-50 text-rose-800 border-rose-200",
    Disabled: "bg-slate-100 text-slate-700 border-slate-200",
  }[status?.overall_health] || "bg-slate-100 text-slate-700 border-slate-200";

  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader showBack />
      <main className="max-w-7xl mx-auto px-6 py-8" data-testid="automation-hub">
        <div className="flex items-baseline justify-between mb-6">
          <div>
            <h1 className="font-display text-2xl font-semibold text-slate-900">
              Automation & Delivery
            </h1>
            <p className="text-sm text-slate-500 mt-1">
              Scheduler jobs, notification deliveries, providers and templates.
            </p>
          </div>
          <button
            data-testid="automation-refresh"
            className="text-xs px-3 py-1.5 rounded-md border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 flex items-center gap-1.5"
            onClick={load} disabled={loading}
          >
            <ArrowClockwise size={14} weight="bold" /> Refresh
          </button>
        </div>

        {loading && !status && (
          <div className="text-sm text-slate-500">Loading status…</div>
        )}

        {status && (
          <>
            <div className={`border rounded-xl p-4 mb-6 flex items-center gap-4 ${healthColor}`}
                 data-testid="automation-health-banner">
              <Gauge size={28} weight="duotone" />
              <div className="flex-1">
                <div className="text-xs uppercase tracking-widest opacity-70">Overall health</div>
                <div className="text-lg font-semibold" data-testid="automation-health-value">
                  {status.overall_health}
                </div>
              </div>
              <div className="text-right text-xs">
                <div>Scheduler: <b>{status.scheduler_enabled ? "Enabled" : "Disabled"}</b></div>
                <div>Delivery: <b>{status.delivery_enabled ? "Live" : "Development Outbox"}</b></div>
                <div>Test mode: <b>{status.test_mode ? "On" : "Off"}</b></div>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
              <Metric label="Job definitions" value={status.job_definitions} icon={ListChecks} testid="metric-job-defs" />
              <Metric label="Enabled jobs" value={status.enabled_jobs} icon={CheckCircle} testid="metric-enabled" />
              <Metric label="Deliveries pending" value={status.deliveries_pending} icon={Clock} testid="metric-pending" />
              <Metric label="Retry scheduled" value={status.deliveries_retry_scheduled} icon={ArrowClockwise} testid="metric-retry" />
              <Metric label="Dead letter" value={status.deliveries_dead_letter} icon={Warning} testid="metric-dead" />
              <Metric label="Failed runs" value={status.recent_failed_runs} icon={XCircle} testid="metric-failed" />
              <Metric label="Email provider" value={status.email_provider} icon={EnvelopeSimple} testid="metric-email" />
              <Metric label="SMS provider" value={status.sms_provider} icon={ShieldCheck} testid="metric-sms" />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <NavCard to="/administration/automation/jobs"
                       title="Scheduled Jobs"
                       desc="Registry, manual runs, enable/disable, event history."
                       testid="nav-jobs" />
              <NavCard to="/administration/automation/deliveries"
                       title="Notification Deliveries"
                       desc="Pending, retry, dead-letter queues with mask-safe recipients."
                       testid="nav-deliveries" />
              <NavCard to="/administration/automation/providers"
                       title="Providers & Circuit Breakers"
                       desc="Development, SMTP, SendGrid, Twilio. Health probes & resets."
                       testid="nav-providers" />
              <NavCard to="/administration/automation/templates"
                       title="Template Studio"
                       desc="Create drafts, preview, approve, clone and archive templates."
                       testid="nav-templates" />
              <NavCard to="/administration/automation/incidents"
                       title="Escalation Incidents"
                       desc="Open incidents with ack/resolve/reopen actions per rule."
                       testid="nav-incidents" />
              <NavCard to="/administration/integrity"
                       title="Integrity & Release Gate"
                       desc="Cross-module integrity findings and release gate."
                       testid="nav-integrity" />
              <NavCard to="/operations"
                       title="Operations Dashboard"
                       desc="Live operational health, dead-letters and open incidents."
                       testid="nav-ops" />
            </div>

            <div className="mt-6 text-xs text-slate-500" data-testid="automation-tz-note">
              Timezone: <b>{status.default_timezone}</b> · Quiet hours{" "}
              {status.quiet_hours_start}:00–{status.quiet_hours_end}:00
            </div>

            {/* EB-16 · Health History */}
            <div className="mt-8" data-testid="health-history-section">
              <div className="flex items-baseline justify-between mb-3">
                <h2 className="font-display text-lg font-semibold text-slate-900">
                  Health history (last 50 snapshots)
                </h2>
                {canManage && (
                  <button
                    data-testid="capture-snapshot"
                    disabled={busy}
                    onClick={takeSnapshot}
                    className="text-xs px-3 py-1.5 rounded border border-cyan-300 bg-cyan-50 text-cyan-800 hover:bg-cyan-100 flex items-center gap-1.5">
                    <Camera size={14} weight="bold" /> Capture Snapshot
                  </button>
                )}
              </div>
              <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
                {snapshots.length === 0 && (
                  <div className="p-4 text-sm text-slate-500 text-center">
                    No health snapshots yet — use Capture Snapshot above.
                  </div>
                )}
                {snapshots.length > 0 && (
                  <>
                    {/* Simple accessible bar chart */}
                    <div className="p-4 flex items-end gap-1 overflow-x-auto" data-testid="health-chart">
                      {[...snapshots].reverse().slice(-30).map((s) => {
                        const value = (s.dead_letters || 0) + (s.failed_jobs || 0) + (s.open_incidents || 0);
                        const h = Math.max(6, Math.min(80, 6 + value * 4));
                        const color = s.overall_health === "Critical" ? "bg-rose-500"
                          : s.overall_health === "Warning" ? "bg-amber-400" : "bg-emerald-500";
                        return (
                          <div key={s.automation_health_snapshot_id}
                               title={`${s.captured_at} · ${s.overall_health} · combined=${value}`}
                               style={{ height: `${h}px` }}
                               data-testid={`chart-bar-${s.automation_health_snapshot_id.slice(0, 8)}`}
                               className={`w-3 rounded-t ${color}`} />
                        );
                      })}
                    </div>
                    <table className="w-full text-xs" data-testid="health-history-table">
                      <thead className="bg-slate-50 text-slate-600 uppercase">
                        <tr>
                          <th className="text-left px-3 py-2">Captured</th>
                          <th className="text-left px-3 py-2">Health</th>
                          <th className="text-left px-3 py-2">Dead-letters</th>
                          <th className="text-left px-3 py-2">Failed jobs</th>
                          <th className="text-left px-3 py-2">Open incidents</th>
                          <th className="text-left px-3 py-2">Blocked drivers</th>
                          <th className="text-left px-3 py-2">Migration</th>
                        </tr>
                      </thead>
                      <tbody>
                        {snapshots.slice(0, 15).map((s) => (
                          <tr key={s.automation_health_snapshot_id} className="border-t border-slate-100">
                            <td className="px-3 py-1.5">{s.captured_at}</td>
                            <td className="px-3 py-1.5">
                              <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                                s.overall_health === "Critical" ? "bg-rose-50 text-rose-700"
                                : s.overall_health === "Warning" ? "bg-amber-50 text-amber-700"
                                : "bg-emerald-50 text-emerald-700"
                              }`}>{s.overall_health}</span>
                            </td>
                            <td className="px-3 py-1.5">{s.dead_letters}</td>
                            <td className="px-3 py-1.5">{s.failed_jobs}</td>
                            <td className="px-3 py-1.5">{s.open_incidents}</td>
                            <td className="px-3 py-1.5">{s.blocked_drivers}</td>
                            <td className="px-3 py-1.5">{s.migration_state}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </>
                )}
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}

function Metric({ label, value, icon: Icon, testid }) {
  return (
    <div className="bg-white border border-slate-200 rounded-lg p-4 flex items-center gap-3"
         data-testid={testid}>
      <div className="p-2 bg-indigo-50 text-indigo-700 rounded-lg">
        <Icon size={18} weight="duotone" />
      </div>
      <div className="min-w-0">
        <div className="text-[11px] uppercase tracking-widest text-slate-500">{label}</div>
        <div className="text-lg font-semibold text-slate-900 truncate">{String(value ?? "—")}</div>
      </div>
    </div>
  );
}

function NavCard({ to, title, desc, testid }) {
  return (
    <Link
      to={to} data-testid={testid}
      className="bg-white border border-slate-200 rounded-xl p-5 hover:shadow-md hover:-translate-y-0.5 hover:border-cyan-300 transition-all block">
      <div className="font-display font-semibold text-slate-900 text-base">{title}</div>
      <div className="text-xs text-slate-500 mt-1">{desc}</div>
    </Link>
  );
}
