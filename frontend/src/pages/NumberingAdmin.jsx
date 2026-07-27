import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import AppHeader from "../components/app/AppHeader";
import api, { formatApiErrorDetail } from "../lib/api";
import { toast } from "sonner";
import { useAuth } from "../context/AuthContext";
import { ArrowClockwise, Play, ArrowUpRight } from "@phosphor-icons/react";
import { formatDateTime } from "../lib/notifications";

/**
 * EB-08 — Numbering Administration.
 *
 * Read-first view of the Driver Code sequence, active dispatch numbers,
 * reusable pool, active reservations and recent allocation events.
 * Admin/Manager can trigger the two maintenance jobs.
 */
export default function NumberingAdmin() {
  const { user } = useAuth();
  const [sequence, setSequence] = useState(null);
  const [suggestion, setSuggestion] = useState(null);
  const [avail, setAvail] = useState(null);
  const [reservations, setReservations] = useState([]);
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(null);

  const canManage = user?.role === "Admin" || user?.role === "Manager";
  const canEditSequence = user?.role === "Admin";

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [seq, sug, av, res, evs] = await Promise.all([
        api.get("/numbering/driver-code/sequence"),
        api.get("/numbering/driver-code/suggestion"),
        api.get("/numbering/dispatch/available"),
        api.get("/numbering/dispatch/reservations", { params: { only_active: true } }),
        api.get("/numbering/allocation-events"),
      ]);
      setSequence(seq.data);
      setSuggestion(sug.data);
      setAvail(av.data);
      setReservations(res.data || []);
      setEvents((evs.data || []).slice(0, 50));
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const runJob = async (slug) => {
    setRunning(slug);
    try {
      const { data } = await api.post(`/numbering/jobs/${slug}`);
      toast.success(`${slug} · ${JSON.stringify(data)}`);
      refresh();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setRunning(null); }
  };

  const editSequence = async () => {
    const raw = prompt("New Driver Code sequence value (integer). This is audited.");
    if (raw == null) return;
    const value = parseInt(raw.trim(), 10);
    if (Number.isNaN(value) || value < 0) return toast.error("Invalid value");
    try {
      await api.put("/numbering/driver-code/sequence", {
        value, reason: "Manual sequence adjustment from admin page",
      });
      toast.success(`Sequence set to ${value}`);
      refresh();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    }
  };

  return (
    <div className="min-h-screen bg-slate-50" data-testid="numbering-admin">
      <AppHeader showBack />
      <main className="max-w-[1400px] mx-auto w-full px-6 lg:px-12 py-6">
        <section className="mb-4 flex items-end justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.25em] text-cyan-600 mb-1 flex items-center gap-2">
              <span className="inline-flex h-1.5 w-1.5 rounded-full bg-cyan-500" />
              Administration
            </div>
            <h1 className="font-display text-2xl lg:text-3xl font-semibold tracking-tight text-slate-900 leading-tight">
              Numbering
            </h1>
            <p className="text-xs text-slate-500 mt-1">
              Driver Code sequence, active Dispatch Numbers, reservations and audit history.
            </p>
          </div>
          <button onClick={refresh} data-testid="numbering-refresh"
            className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-900">
            <ArrowClockwise size={12} /> Refresh
          </button>
        </section>

        <section className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-5">
          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm" data-testid="numbering-driver-code-card">
            <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500 mb-2">Driver Code Sequence</div>
            {loading ? <div className="text-sm text-slate-400">Loading…</div> : (
              <>
                <div className="font-display text-3xl font-semibold text-slate-900">{sequence?.value ?? "—"}</div>
                <div className="text-[11px] text-slate-500 mt-1">
                  Next automatic suggestion: <strong data-testid="numbering-suggestion">{suggestion?.suggested_driver_code}</strong>
                </div>
                <div className="text-[10px] text-slate-400 mt-1">Updated by {sequence?.updated_by || "system"} · {formatDateTime(sequence?.updated_at)}</div>
                {canEditSequence && (
                  <button onClick={editSequence} data-testid="numbering-edit-sequence"
                    className="mt-3 text-xs text-cyan-700 hover:text-cyan-900">
                    Edit sequence (audited) →
                  </button>
                )}
              </>
            )}
          </div>

          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm lg:col-span-2" data-testid="numbering-dispatch-card">
            <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500 mb-2">Dispatch Numbers</div>
            {loading ? <div className="text-sm text-slate-400">Loading…</div> : avail && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <Stat label="Active in use" value={avail.in_use.length} testid="numbering-in-use-count" />
                <Stat label="Reusable" value={avail.reusable.length} testid="numbering-reusable-count" />
                <Stat label="Next new" value={avail.next_new ?? "—"} testid="numbering-next-new" />
                <Stat label="Inactive in use" value={avail.inactive_in_use.length} testid="numbering-inactive-count" />
                <div className="col-span-2 md:col-span-4">
                  <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500 mb-1">Reusable numbers</div>
                  <div className="flex flex-wrap gap-1.5">
                    {avail.reusable.slice(0, 30).map((n) => (
                      <span key={n} className="text-[11px] border border-slate-200 rounded-full px-2 py-0.5 bg-slate-50 text-slate-700">{n}</span>
                    ))}
                    {avail.reusable.length === 0 && <span className="text-[11px] text-slate-400">None yet — every issued number is still active.</span>}
                  </div>
                </div>
                <div className="col-span-2 md:col-span-4">
                  <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500 mb-1">Permanently reserved</div>
                  <div className="flex flex-wrap gap-1.5">
                    {avail.reserved_permanent.map((n) => (
                      <span key={n} className="text-[11px] border border-red-200 bg-red-50 text-red-700 rounded-full px-2 py-0.5">{n}</span>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        </section>

        <section className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-5">
          <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm" data-testid="numbering-reservations">
            <div className="px-5 py-3 border-b border-slate-200 flex items-center justify-between">
              <div className="text-[10px] uppercase tracking-[0.2em] font-semibold text-slate-500">Active Reservations</div>
              <span className="text-[10px] text-slate-500">{reservations.length}</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-200">
                    {["Type", "Value", "Reserved by", "Expires"].map((h) => (
                      <th key={h} className="text-left px-4 py-2 text-[10px] uppercase tracking-[0.2em] font-semibold text-slate-500">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {reservations.length === 0 && (
                    <tr><td colSpan={4} className="px-4 py-6 text-center text-slate-500 text-xs">No active reservations.</td></tr>
                  )}
                  {reservations.map((r) => (
                    <tr key={r.reservation_id} data-testid={`numbering-res-${r.reservation_id}`}
                      className="border-b border-slate-100 last:border-0">
                      <td className="px-4 py-2 text-xs text-slate-700">{r.identifier_type}</td>
                      <td className="px-4 py-2 text-xs font-medium text-slate-900">{r.identifier_value}</td>
                      <td className="px-4 py-2 text-xs text-slate-500 truncate max-w-[180px]">{r.reserved_by}</td>
                      <td className="px-4 py-2 text-xs text-slate-500">{formatDateTime(r.expires_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm" data-testid="numbering-events">
            <div className="px-5 py-3 border-b border-slate-200 flex items-center justify-between">
              <div className="text-[10px] uppercase tracking-[0.2em] font-semibold text-slate-500">Recent Allocation Events</div>
              <span className="text-[10px] text-slate-500">{events.length}</span>
            </div>
            <div className="overflow-x-auto max-h-[380px]">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-200 sticky top-0">
                    {["When", "Type", "Value", "Action", "By", "Reason"].map((h) => (
                      <th key={h} className="text-left px-4 py-2 text-[10px] uppercase tracking-[0.2em] font-semibold text-slate-500">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {events.length === 0 && (
                    <tr><td colSpan={6} className="px-4 py-6 text-center text-slate-500 text-xs">No events yet.</td></tr>
                  )}
                  {events.map((e) => (
                    <tr key={e.allocation_event_id} data-testid={`numbering-evt-${e.allocation_event_id}`}
                      className="border-b border-slate-100 last:border-0">
                      <td className="px-4 py-2 text-[11px] text-slate-500">{formatDateTime(e.performed_at)}</td>
                      <td className="px-4 py-2 text-[11px] text-slate-600">{e.identifier_type}</td>
                      <td className="px-4 py-2 text-[11px] text-slate-900 font-medium">{e.identifier_value}</td>
                      <td className="px-4 py-2 text-[11px]">
                        <span className={`inline-flex text-[10px] font-medium uppercase tracking-[0.15em] px-1.5 py-0.5 rounded border ${_actionTone(e.action)}`}>
                          {e.action}
                        </span>
                        {e.sequence_advanced && <span className="ml-1 text-[10px] text-emerald-700" title="Sequence advanced">↑</span>}
                        {e.manual_override && <span className="ml-1 text-[10px] text-amber-700" title="Manual override">⚠</span>}
                      </td>
                      <td className="px-4 py-2 text-[11px] text-slate-500 truncate max-w-[140px]">{e.performed_by}</td>
                      <td className="px-4 py-2 text-[11px] text-slate-500 truncate max-w-[220px]">{e.reason || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        {canManage && (
          <section className="flex flex-wrap gap-2" data-testid="numbering-jobs">
            <button
              onClick={() => runJob("expire-reservations")}
              disabled={running === "expire-reservations"}
              data-testid="numbering-run-expire"
              className="inline-flex items-center gap-2 bg-slate-900 text-white hover:bg-slate-800 rounded-lg px-4 py-2 text-xs font-medium disabled:opacity-40"
            >
              <Play size={12} weight="bold" /> Expire Reservations
            </button>
            <button
              onClick={() => runJob("reconcile")}
              disabled={running === "reconcile"}
              data-testid="numbering-run-reconcile"
              className="inline-flex items-center gap-2 border border-slate-300 text-slate-800 hover:border-slate-400 rounded-lg px-4 py-2 text-xs font-medium disabled:opacity-40"
            >
              <Play size={12} weight="bold" /> Run Reconciliation
            </button>
            <Link
              to="/notifications/all?entity_type=General"
              data-testid="numbering-open-notifications"
              className="ml-auto inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-900"
            >
              Reconciliation notifications <ArrowUpRight size={11} weight="bold" />
            </Link>
          </section>
        )}
      </main>
    </div>
  );
}

function Stat({ label, value, testid }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500">{label}</div>
      <div className="font-display text-xl font-semibold text-slate-900" data-testid={testid}>{value}</div>
    </div>
  );
}

function _actionTone(a) {
  if (a === "Allocated" || a === "Reserved") return "bg-emerald-50 text-emerald-700 border-emerald-200";
  if (a === "Rejected") return "bg-red-50 text-red-700 border-red-200";
  if (a === "Overridden") return "bg-amber-50 text-amber-800 border-amber-200";
  if (a === "Released" || a === "Cancelled" || a === "Expired") return "bg-slate-100 text-slate-600 border-slate-200";
  return "bg-blue-50 text-blue-700 border-blue-200";
}
