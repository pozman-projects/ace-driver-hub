import React, { useCallback, useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import AppHeader from "../components/app/AppHeader";
import api, { formatApiErrorDetail } from "../lib/api";
import { toast } from "sonner";
import { useAuth } from "../context/AuthContext";
import {
  Gauge, Clock, EnvelopeSimple, ShieldCheck, ArrowClockwise,
  Warning, CheckCircle, XCircle, ListChecks,
} from "@phosphor-icons/react";

/**
 * EB-15 — Automation & Delivery Operations Hub.
 * Read-first status page for Allocators+, action panels for Managers/Admins.
 */
export default function AutomationHub() {
  const { user } = useAuth();
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/automation/status");
      setStatus(data);
    } catch (e) {
      toast.error(
        formatApiErrorDetail(e?.response?.data?.detail) || "Failed to load automation status",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

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

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
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
            </div>

            <div className="mt-6 text-xs text-slate-500" data-testid="automation-tz-note">
              Timezone: <b>{status.default_timezone}</b> · Quiet hours{" "}
              {status.quiet_hours_start}:00–{status.quiet_hours_end}:00
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
