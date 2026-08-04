import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import AppHeader from "../components/app/AppHeader";
import api, { formatApiErrorDetail } from "../lib/api";
import { toast } from "sonner";
import { useAuth } from "../context/AuthContext";
import { ArrowClockwise, ArrowCounterClockwise, XCircle, CheckSquare } from "@phosphor-icons/react";

/**
 * EB-15 — Notification Deliveries.
 * Filter by status. Manager+ can Retry / Cancel / Resolve dead-letter.
 */
const STATUSES = ["All", "Pending", "Queued", "Retry Scheduled", "Sent",
                    "Failed", "Dead Letter", "Cancelled", "Resolved"];

export default function AutomationDeliveriesPage() {
  const { user } = useAuth();
  const canManage = user?.role === "Manager" || user?.role === "Admin";

  const [rows, setRows] = useState([]);
  const [status, setStatus] = useState("All");
  const [selected, setSelected] = useState(null);
  const [attempts, setAttempts] = useState([]);
  const [busy, setBusy] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const q = status === "All" ? "" : `?status=${encodeURIComponent(status)}`;
      const { data } = await api.get(`/automation/deliveries${q}`);
      setRows(data || []);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Failed to load deliveries");
    } finally { setLoading(false); }
  }, [status]);

  useEffect(() => { load(); }, [load]);

  const openDetail = async (row) => {
    setSelected(row);
    try {
      const { data } = await api.get(`/automation/deliveries/${row.notification_delivery_id}/attempts`);
      setAttempts(data || []);
    } catch { setAttempts([]); }
  };

  const act = async (row, kind) => {
    const id = row.notification_delivery_id;
    setBusy(`${kind}-${id}`);
    try {
      const body = kind === "resolve" ? { note: "Resolved via UI" } : undefined;
      const { data } = await api.post(`/automation/deliveries/${id}/${kind}`, body);
      toast.success(`Delivery now ${data.delivery_status}`);
      load();
      if (selected?.notification_delivery_id === id) setSelected(null);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setBusy(null); }
  };

  const counts = useMemo(() => {
    const c = {};
    rows.forEach((r) => { c[r.delivery_status] = (c[r.delivery_status] || 0) + 1; });
    return c;
  }, [rows]);

  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader showBack />
      <main className="max-w-7xl mx-auto px-6 py-8" data-testid="automation-deliveries-page">
        <div className="flex items-baseline justify-between mb-6">
          <div>
            <h1 className="font-display text-2xl font-semibold text-slate-900">Notification Deliveries</h1>
            <p className="text-sm text-slate-500 mt-1">
              <Link to="/administration/automation" className="text-cyan-700 hover:underline">
                ← Automation Hub
              </Link>
            </p>
          </div>
          <button
            data-testid="deliveries-refresh"
            className="text-xs px-3 py-1.5 rounded-md border border-slate-300 bg-white hover:bg-slate-50 flex items-center gap-1.5"
            onClick={load} disabled={loading}
          ><ArrowClockwise size={14} weight="bold" /> Refresh</button>
        </div>

        <div className="mb-4 flex gap-2 flex-wrap" data-testid="deliveries-filter">
          {STATUSES.map((s) => (
            <button
              key={s} onClick={() => setStatus(s)}
              data-testid={`filter-${s.replace(/\s+/g, "-").toLowerCase()}`}
              className={`text-xs px-3 py-1 rounded-full border ${
                s === status
                  ? "bg-slate-900 border-slate-900 text-white"
                  : "bg-white border-slate-300 text-slate-700 hover:border-slate-400"
              }`}
            >{s}{counts[s] ? ` (${counts[s]})` : ""}</button>
          ))}
        </div>

        <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-600 text-xs uppercase tracking-wider">
              <tr>
                <th className="text-left px-4 py-2">Channel</th>
                <th className="text-left px-4 py-2">Recipient</th>
                <th className="text-left px-4 py-2">Status</th>
                <th className="text-left px-4 py-2">Attempts</th>
                <th className="text-left px-4 py-2">Provider</th>
                <th className="text-left px-4 py-2">Next retry</th>
                <th className="text-right px-4 py-2">Actions</th>
              </tr>
            </thead>
            <tbody data-testid="deliveries-tbody">
              {rows.map((r) => {
                const recipient = r.email_address || r.mobile_number ||
                                    r.email_address_masked || r.mobile_number_masked || "—";
                return (
                  <tr key={r.notification_delivery_id} className="border-t border-slate-100"
                      data-testid={`delivery-row-${r.notification_delivery_id}`}>
                    <td className="px-4 py-2">{r.channel}</td>
                    <td className="px-4 py-2 font-mono text-xs">{recipient}</td>
                    <td className="px-4 py-2"><StatusPill status={r.delivery_status} /></td>
                    <td className="px-4 py-2 text-xs">{r.attempts_made || 0}</td>
                    <td className="px-4 py-2 text-xs">{r.provider || "—"}</td>
                    <td className="px-4 py-2 text-xs text-slate-500">{r.next_retry_at || "—"}</td>
                    <td className="px-4 py-2 text-right">
                      <div className="inline-flex gap-1">
                        <button onClick={() => openDetail(r)}
                                data-testid={`view-${r.notification_delivery_id}`}
                                className="text-xs px-2 py-1 rounded border border-slate-300 bg-white text-slate-700 hover:bg-slate-50">
                          View
                        </button>
                        {canManage && ["Failed", "Dead Letter", "Retry Scheduled"].includes(r.delivery_status) && (
                          <button
                            disabled={busy === `retry-${r.notification_delivery_id}`}
                            onClick={() => act(r, "retry")}
                            data-testid={`retry-${r.notification_delivery_id}`}
                            className="text-xs px-2 py-1 rounded border border-cyan-300 bg-cyan-50 text-cyan-800 hover:bg-cyan-100 flex items-center gap-1">
                            <ArrowCounterClockwise size={12} weight="bold" /> Retry
                          </button>
                        )}
                        {canManage && !["Sent", "Cancelled"].includes(r.delivery_status) && (
                          <button
                            disabled={busy === `cancel-${r.notification_delivery_id}`}
                            onClick={() => act(r, "cancel")}
                            data-testid={`cancel-${r.notification_delivery_id}`}
                            className="text-xs px-2 py-1 rounded border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 flex items-center gap-1">
                            <XCircle size={12} weight="bold" /> Cancel
                          </button>
                        )}
                        {canManage && r.delivery_status === "Dead Letter" && (
                          <button
                            disabled={busy === `resolve-${r.notification_delivery_id}`}
                            onClick={() => act(r, "resolve")}
                            data-testid={`resolve-${r.notification_delivery_id}`}
                            className="text-xs px-2 py-1 rounded border border-emerald-300 bg-emerald-50 text-emerald-800 hover:bg-emerald-100 flex items-center gap-1">
                            <CheckSquare size={12} weight="bold" /> Resolve
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
              {rows.length === 0 && (
                <tr><td colSpan={7} className="p-6 text-center text-slate-500 text-sm">No deliveries</td></tr>
              )}
            </tbody>
          </table>
        </div>

        {selected && (
          <DeliveryDetail row={selected} attempts={attempts} onClose={() => { setSelected(null); setAttempts([]); }} />
        )}
      </main>
    </div>
  );
}

function StatusPill({ status }) {
  const map = {
    Sent: "bg-emerald-50 text-emerald-700",
    Pending: "bg-cyan-50 text-cyan-700",
    Queued: "bg-cyan-50 text-cyan-700",
    "Retry Scheduled": "bg-amber-50 text-amber-700",
    Failed: "bg-rose-50 text-rose-700",
    "Dead Letter": "bg-rose-100 text-rose-800",
    Cancelled: "bg-slate-100 text-slate-700",
    Resolved: "bg-slate-100 text-slate-700",
  };
  return (
    <span className={`text-[11px] px-2 py-0.5 rounded-full ${map[status] || "bg-slate-100 text-slate-700"}`}>
      {status}
    </span>
  );
}

function DeliveryDetail({ row, attempts, onClose }) {
  return (
    <div className="fixed inset-0 bg-black/40 z-40 flex items-center justify-center p-4"
         onClick={onClose} data-testid="delivery-detail-modal">
      <div className="bg-white rounded-xl max-w-3xl w-full max-h-[80vh] overflow-auto p-6"
           onClick={(e) => e.stopPropagation()}>
        <div className="flex items-baseline justify-between mb-4">
          <h3 className="font-display text-lg font-semibold">Delivery</h3>
          <button onClick={onClose} data-testid="delivery-detail-close"
                  className="text-slate-500 hover:text-slate-900 text-sm">✕</button>
        </div>
        <div className="grid grid-cols-2 gap-3 text-xs mb-4">
          <div><b>Status:</b> {row.delivery_status}</div>
          <div><b>Channel:</b> {row.channel}</div>
          <div><b>Provider:</b> {row.provider || "—"}</div>
          <div><b>Attempts:</b> {row.attempts_made || 0}</div>
          <div><b>Recipient:</b> {row.email_address_masked || row.mobile_number_masked || "—"}</div>
          <div><b>Next retry:</b> {row.next_retry_at || "—"}</div>
          <div className="col-span-2"><b>Last failure:</b> {row.last_failure_reason || "—"}</div>
        </div>
        <div>
          <div className="text-xs uppercase tracking-widest text-slate-500 mb-1">Attempts</div>
          <table className="w-full text-xs">
            <thead className="text-slate-500">
              <tr><th className="text-left py-1">#</th><th className="text-left py-1">Status</th>
                  <th className="text-left py-1">Provider</th><th className="text-left py-1">When</th>
                  <th className="text-left py-1">Failure</th></tr>
            </thead>
            <tbody>
              {attempts.map((a) => (
                <tr key={a.notification_delivery_attempt_id} className="border-t border-slate-100">
                  <td className="py-1">{a.attempt_number}</td>
                  <td className="py-1">{a.status}</td>
                  <td className="py-1">{a.provider}</td>
                  <td className="py-1">{a.completed_at || a.failed_at || a.started_at}</td>
                  <td className="py-1 text-rose-700">{a.failure_reason || "—"}</td>
                </tr>
              ))}
              {attempts.length === 0 && (
                <tr><td colSpan={5} className="py-3 text-center text-slate-500">No attempts</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
