import React, { useCallback, useEffect, useState, useMemo } from "react";
import { Link } from "react-router-dom";
import AppHeader from "../components/app/AppHeader";
import api, { formatApiErrorDetail } from "../lib/api";
import { toast } from "sonner";
import { ArrowClockwise } from "@phosphor-icons/react";

const FILTERS = [
  ["all", "All"], ["ready", "Ready"], ["ready-with-override", "Ready with Override"],
  ["incomplete", "Incomplete"], ["blocked", "Blocked"], ["no-vehicle", "No Vehicle"],
];

export default function DriverReadinessPage() {
  const [rows, setRows] = useState([]);
  const [filter, setFilter] = useState("all");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const q = filter === "all" ? "" : `?filter=${encodeURIComponent(filter)}`;
      const { data } = await api.get(`/operations/driver-readiness${q}`);
      setRows(data || []);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setLoading(false); }
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader showBack />
      <main className="max-w-7xl mx-auto px-6 py-8" data-testid="driver-readiness-page">
        <div className="flex items-baseline justify-between mb-6">
          <div>
            <h1 className="font-display text-2xl font-semibold text-slate-900">Driver Readiness Workload</h1>
            <Link to="/operations" className="text-cyan-700 text-sm hover:underline">← Operations</Link>
          </div>
          <button data-testid="dr-refresh" onClick={load} disabled={loading}
            className="text-xs px-3 py-1.5 rounded border border-slate-300 bg-white hover:bg-slate-50 flex items-center gap-1.5">
            <ArrowClockwise size={14} weight="bold" /> Refresh
          </button>
        </div>
        <div className="mb-4 flex gap-2 flex-wrap" data-testid="dr-filters">
          {FILTERS.map(([k, l]) => (
            <button key={k} onClick={() => setFilter(k)}
              data-testid={`dr-filter-${k}`}
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
                <th className="text-left px-4 py-2">Driver</th>
                <th className="text-left px-4 py-2">Code / Dispatch</th>
                <th className="text-left px-4 py-2">Readiness</th>
                <th className="text-left px-4 py-2">%</th>
                <th className="text-left px-4 py-2">Outstanding</th>
                <th className="text-left px-4 py-2">Overrides</th>
                <th className="text-left px-4 py-2">Vehicle</th>
                <th className="text-right px-4 py-2">Actions</th>
              </tr>
            </thead>
            <tbody data-testid="dr-tbody">
              {rows.map((r) => (
                <tr key={r.driver_id} className="border-t border-slate-100"
                    data-testid={`dr-row-${r.driver_id}`}>
                  <td className="px-4 py-2">{r.driver_name}</td>
                  <td className="px-4 py-2 text-xs font-mono">
                    {r.driver_code || "—"} / {r.dispatch_number ?? "—"}
                  </td>
                  <td className="px-4 py-2"><ReadinessPill s={r.readiness_status} /></td>
                  <td className="px-4 py-2">{r.completion_pct}%</td>
                  <td className="px-4 py-2">{r.outstanding_mandatory}</td>
                  <td className="px-4 py-2">{r.active_overrides}</td>
                  <td className="px-4 py-2 text-xs">{r.vehicle?.registration_number || "—"}</td>
                  <td className="px-4 py-2 text-right">
                    <Link to={`/drivers/${r.driver_id}`}
                       data-testid={`dr-open-${r.driver_id}`}
                       className="text-xs px-2 py-1 rounded border border-slate-300 bg-white hover:bg-slate-50">
                      Open DCC
                    </Link>
                  </td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr><td colSpan={8} className="p-6 text-center text-slate-500">No drivers match filter</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </main>
    </div>
  );
}

function ReadinessPill({ s }) {
  const m = {
    Ready: "bg-emerald-50 text-emerald-700",
    "Ready with Override": "bg-cyan-50 text-cyan-700",
    Incomplete: "bg-amber-50 text-amber-700",
    Blocked: "bg-rose-50 text-rose-700",
  };
  return <span className={`text-[11px] px-2 py-0.5 rounded-full ${m[s] || "bg-slate-100 text-slate-700"}`}>{s || "—"}</span>;
}
