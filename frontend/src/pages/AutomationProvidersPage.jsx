import React, { useCallback, useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import AppHeader from "../components/app/AppHeader";
import api, { formatApiErrorDetail } from "../lib/api";
import { toast } from "sonner";
import { useAuth } from "../context/AuthContext";
import { ArrowClockwise, Pulse, Shield, EnvelopeSimple, DeviceMobile } from "@phosphor-icons/react";

/**
 * EB-15 — Providers & Circuit Breakers.
 * Manager+ can trigger health probes. Admin can reset circuit breakers.
 */
export default function AutomationProvidersPage() {
  const { user } = useAuth();
  const canManage = user?.role === "Manager" || user?.role === "Admin";
  const canAdmin = user?.role === "Admin";

  const [rows, setRows] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [busy, setBusy] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [p, t] = await Promise.all([
        api.get("/automation/providers"),
        api.get("/automation/notification-templates"),
      ]);
      setRows(p.data || []);
      setTemplates(t.data || []);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Failed to load providers");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (user && !canManage) return <Navigate to="/administration/automation" replace />;

  const probe = async (key) => {
    setBusy(`probe-${key}`);
    try {
      const { data } = await api.post(`/automation/providers/${key}/health-check`);
      toast.success(`Probe ${key}: ${data.configured ? "OK" : data.config_error}`);
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setBusy(null); }
  };

  const reset = async (key) => {
    setBusy(`reset-${key}`);
    try {
      await api.post(`/automation/providers/${key}/reset-circuit`);
      toast.success(`Circuit reset for ${key}`);
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setBusy(null); }
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader showBack />
      <main className="max-w-7xl mx-auto px-6 py-8" data-testid="automation-providers-page">
        <div className="flex items-baseline justify-between mb-6">
          <div>
            <h1 className="font-display text-2xl font-semibold text-slate-900">
              Providers & Templates
            </h1>
            <p className="text-sm text-slate-500 mt-1">
              <Link to="/administration/automation" className="text-cyan-700 hover:underline">
                ← Automation Hub
              </Link>
            </p>
          </div>
          <button
            data-testid="providers-refresh"
            className="text-xs px-3 py-1.5 rounded-md border border-slate-300 bg-white hover:bg-slate-50 flex items-center gap-1.5"
            onClick={load} disabled={loading}
          ><ArrowClockwise size={14} weight="bold" /> Refresh</button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
          {rows.map((r) => (
            <div key={`${r.provider_key}-${r.channel}`}
                 data-testid={`provider-card-${r.provider_key}`}
                 className="bg-white border border-slate-200 rounded-xl p-4">
              <div className="flex items-center gap-3 mb-3">
                <div className="p-2 bg-indigo-50 text-indigo-700 rounded-lg">
                  {r.channel === "email" ? <EnvelopeSimple size={18} weight="duotone" />
                                          : <DeviceMobile size={18} weight="duotone" />}
                </div>
                <div className="flex-1">
                  <div className="font-semibold text-slate-900 capitalize">
                    {r.provider_key} <span className="text-slate-500 text-xs">({r.channel})</span>
                  </div>
                  <div className="text-xs text-slate-500">
                    {r.configured ? "Configured" : (r.config_error || "Missing config")}
                  </div>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs mb-3">
                <div>Circuit:{" "}
                  <b className={
                    r.circuit_state === "open" ? "text-rose-700"
                    : r.circuit_state === "half-open" ? "text-amber-700" : "text-emerald-700"
                  }>{r.circuit_state || "closed"}</b>
                </div>
                <div>Consecutive failures: <b>{r.consecutive_failures || 0}</b></div>
                <div>Immune: <b>{r.immune_from_circuit ? "Yes" : "No"}</b></div>
                <div>Last probe: <span className="text-slate-500">{r.last_probe_at || "—"}</span></div>
              </div>
              <div className="flex gap-2">
                <button
                  disabled={busy === `probe-${r.provider_key}`}
                  onClick={() => probe(r.provider_key)}
                  data-testid={`probe-${r.provider_key}`}
                  className="text-xs px-3 py-1 rounded border border-cyan-300 bg-cyan-50 text-cyan-800 hover:bg-cyan-100 flex items-center gap-1">
                  <Pulse size={12} weight="bold" /> Health Check
                </button>
                {canAdmin && (
                  <button
                    disabled={busy === `reset-${r.provider_key}`}
                    onClick={() => reset(r.provider_key)}
                    data-testid={`reset-${r.provider_key}`}
                    className="text-xs px-3 py-1 rounded border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 flex items-center gap-1">
                    <Shield size={12} weight="bold" /> Reset Circuit
                  </button>
                )}
              </div>
            </div>
          ))}
          {rows.length === 0 && (
            <div className="text-sm text-slate-500 p-4">No providers</div>
          )}
        </div>

        <h2 className="font-display text-lg font-semibold text-slate-900 mb-3">
          Notification Templates
        </h2>
        <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-600 text-xs uppercase tracking-wider">
              <tr>
                <th className="text-left px-4 py-2">Template Key</th>
                <th className="text-left px-4 py-2">Channel</th>
                <th className="text-left px-4 py-2">Version</th>
                <th className="text-left px-4 py-2">Status</th>
                <th className="text-left px-4 py-2">Subject</th>
                <th className="text-left px-4 py-2">Variables</th>
              </tr>
            </thead>
            <tbody data-testid="templates-tbody">
              {templates.map((t) => (
                <tr key={t.notification_template_id} className="border-t border-slate-100"
                    data-testid={`template-row-${t.template_key}-${t.version}`}>
                  <td className="px-4 py-2 font-mono text-xs">{t.template_key}</td>
                  <td className="px-4 py-2 text-xs">{t.channel}</td>
                  <td className="px-4 py-2 text-xs">v{t.version}</td>
                  <td className="px-4 py-2">
                    <span className={`text-[11px] px-2 py-0.5 rounded-full ${
                      t.status === "Approved" ? "bg-emerald-50 text-emerald-700"
                      : t.status === "Draft" ? "bg-amber-50 text-amber-700"
                      : "bg-slate-100 text-slate-700"
                    }`}>{t.status}</span>
                  </td>
                  <td className="px-4 py-2 text-xs truncate max-w-xs">{t.subject_template}</td>
                  <td className="px-4 py-2 text-xs font-mono">
                    {(t.allowed_variables || []).join(", ") || "—"}
                  </td>
                </tr>
              ))}
              {templates.length === 0 && (
                <tr><td colSpan={6} className="p-6 text-center text-slate-500 text-sm">No templates</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </main>
    </div>
  );
}
