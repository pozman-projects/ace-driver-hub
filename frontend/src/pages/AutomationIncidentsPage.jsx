import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import AppHeader from "../components/app/AppHeader";
import api, { formatApiErrorDetail } from "../lib/api";
import { toast } from "sonner";
import { useAuth } from "../context/AuthContext";
import { ArrowClockwise } from "@phosphor-icons/react";

const FILTERS = [
  ["all", "All"], ["active-true", "Active"], ["active-false", "Resolved"],
];

export default function AutomationIncidentsPage() {
  const { user } = useAuth();
  const canManage = user?.role === "Manager" || user?.role === "Admin";
  const [rows, setRows] = useState([]);
  const [selected, setSelected] = useState(null);
  const [filter, setFilter] = useState("active-true");
  const [busy, setBusy] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = filter === "active-true" ? "?active=true"
        : filter === "active-false" ? "?active=false" : "";
      const { data } = await api.get(`/automation/escalation-incidents${params}`);
      setRows(data || []);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setLoading(false); }
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  const act = async (row, kind) => {
    setBusy(`${kind}-${row.notification_escalation_incident_id}`);
    try {
      const r = await api.post(
        `/automation/escalation-incidents/${row.notification_escalation_incident_id}/${kind}`);
      toast.success(`${kind} → ${row.rule_key}`);
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setBusy(null); }
  };

  const openDetail = async (row) => {
    try {
      const { data } = await api.get(
        `/automation/escalation-incidents/${row.notification_escalation_incident_id}`);
      setSelected(data);
    } catch (e) { toast.error(formatApiErrorDetail(e?.response?.data?.detail)); }
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader showBack />
      <main className="max-w-7xl mx-auto px-6 py-8" data-testid="incidents-page">
        <div className="flex items-baseline justify-between mb-6">
          <div>
            <h1 className="font-display text-2xl font-semibold text-slate-900">Escalation Incidents</h1>
            <Link to="/administration/automation" className="text-cyan-700 text-sm hover:underline">← Automation Hub</Link>
          </div>
          <button data-testid="inc-refresh" onClick={load} disabled={loading}
            className="text-xs px-3 py-1.5 rounded border border-slate-300 bg-white hover:bg-slate-50 flex items-center gap-1.5">
            <ArrowClockwise size={14} weight="bold" /> Refresh
          </button>
        </div>
        <div className="mb-4 flex gap-2 flex-wrap" data-testid="inc-filters">
          {FILTERS.map(([k, l]) => (
            <button key={k} onClick={() => setFilter(k)}
              data-testid={`inc-filter-${k}`}
              className={`text-xs px-3 py-1 rounded-full border ${
                filter === k ? "bg-slate-900 border-slate-900 text-white"
                              : "bg-white border-slate-300 text-slate-700"}`}>
              {l}
            </button>
          ))}
        </div>
        <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-600 text-xs uppercase">
              <tr>
                <th className="text-left px-4 py-2">Rule</th>
                <th className="text-left px-4 py-2">Source</th>
                <th className="text-left px-4 py-2">Level</th>
                <th className="text-left px-4 py-2">Active</th>
                <th className="text-left px-4 py-2">First</th>
                <th className="text-left px-4 py-2">Acknowledged</th>
                <th className="text-right px-4 py-2">Actions</th>
              </tr>
            </thead>
            <tbody data-testid="inc-tbody">
              {rows.map((r) => (
                <tr key={r.notification_escalation_incident_id} className="border-t border-slate-100"
                    data-testid={`inc-row-${r.notification_escalation_incident_id}`}>
                  <td className="px-4 py-2 font-mono text-xs">{r.rule_key}</td>
                  <td className="px-4 py-2 text-xs">{r.source_entity}/{r.source_id}</td>
                  <td className="px-4 py-2">L{r.current_level}</td>
                  <td className="px-4 py-2">{r.active ? "Yes" : "No"}</td>
                  <td className="px-4 py-2 text-xs">{r.first_seen_at}</td>
                  <td className="px-4 py-2 text-xs">{r.acknowledged_at || "—"}</td>
                  <td className="px-4 py-2 text-right">
                    <div className="inline-flex gap-1">
                      <button onClick={() => openDetail(r)}
                              data-testid={`inc-view-${r.notification_escalation_incident_id}`}
                              className="text-xs px-2 py-1 rounded border border-slate-300 bg-white hover:bg-slate-50">
                        View
                      </button>
                      {canManage && r.active && !r.acknowledged_at && (
                        <button onClick={() => act(r, "acknowledge")}
                                disabled={busy?.startsWith("acknowledge-")}
                                data-testid={`inc-ack-${r.notification_escalation_incident_id}`}
                                className="text-xs px-2 py-1 rounded border border-cyan-300 bg-cyan-50 text-cyan-800 hover:bg-cyan-100">
                          Ack
                        </button>
                      )}
                      {canManage && r.active && (
                        <button onClick={() => act(r, "resolve")}
                                disabled={busy?.startsWith("resolve-")}
                                data-testid={`inc-resolve-${r.notification_escalation_incident_id}`}
                                className="text-xs px-2 py-1 rounded border border-emerald-300 bg-emerald-50 text-emerald-800 hover:bg-emerald-100">
                          Resolve
                        </button>
                      )}
                      {canManage && !r.active && (
                        <button onClick={() => act(r, "reopen")}
                                disabled={busy?.startsWith("reopen-")}
                                data-testid={`inc-reopen-${r.notification_escalation_incident_id}`}
                                className="text-xs px-2 py-1 rounded border border-amber-300 bg-amber-50 text-amber-800 hover:bg-amber-100">
                          Reopen
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr><td colSpan={7} className="p-6 text-center text-slate-500">No incidents</td></tr>
              )}
            </tbody>
          </table>
        </div>

        {selected && (
          <div className="fixed inset-0 bg-black/40 z-40 flex items-center justify-center p-4"
               onClick={() => setSelected(null)} data-testid="inc-detail-modal">
            <div className="bg-white rounded-xl max-w-2xl w-full p-6 max-h-[80vh] overflow-auto"
                 onClick={(e) => e.stopPropagation()}>
              <div className="flex justify-between items-baseline mb-3">
                <h3 className="font-semibold">Incident {selected.rule_key}</h3>
                <button onClick={() => setSelected(null)} data-testid="inc-detail-close" className="text-slate-500">✕</button>
              </div>
              <pre className="text-xs bg-slate-50 p-3 rounded">{JSON.stringify(selected, null, 2)}</pre>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
