import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import AppHeader from "../components/app/AppHeader";
import api, { formatApiErrorDetail } from "../lib/api";
import { toast } from "sonner";
import { ArrowClockwise } from "@phosphor-icons/react";

export default function ComplianceWorkloadPage() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/operations/compliance-workload");
      setRows(data || []);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);
  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader showBack />
      <main className="max-w-7xl mx-auto px-6 py-8" data-testid="compliance-workload-page">
        <div className="flex items-baseline justify-between mb-6">
          <div>
            <h1 className="font-display text-2xl font-semibold text-slate-900">Compliance Workload</h1>
            <Link to="/operations" className="text-cyan-700 text-sm hover:underline">← Operations</Link>
          </div>
          <button data-testid="cw-refresh" onClick={load} disabled={loading}
            className="text-xs px-3 py-1.5 rounded border border-slate-300 bg-white hover:bg-slate-50 flex items-center gap-1.5">
            <ArrowClockwise size={14} weight="bold" /> Refresh
          </button>
        </div>
        <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-600 text-xs uppercase">
              <tr>
                <th className="text-left px-4 py-2">Equipment</th>
                <th className="text-left px-4 py-2">Type</th>
                <th className="text-left px-4 py-2">Status</th>
                <th className="text-left px-4 py-2">Expiry</th>
                <th className="text-left px-4 py-2">Days Left</th>
                <th className="text-left px-4 py-2">Verification</th>
                <th className="text-left px-4 py-2">Evidence</th>
              </tr>
            </thead>
            <tbody data-testid="cw-tbody">
              {rows.map((r, i) => (
                <tr key={`${r.equipment_id}-${r.compliance_type}-${i}`} className="border-t border-slate-100"
                    data-testid={`cw-row-${i}`}>
                  <td className="px-4 py-2 font-mono text-xs">{r.equipment_id}</td>
                  <td className="px-4 py-2">{r.compliance_type}</td>
                  <td className="px-4 py-2"><StatusPill s={r.status} /></td>
                  <td className="px-4 py-2 text-xs">{r.expiry_date || "—"}</td>
                  <td className="px-4 py-2 text-xs">{r.days_remaining ?? "—"}</td>
                  <td className="px-4 py-2 text-xs">{r.verification_status || "—"}</td>
                  <td className="px-4 py-2 text-xs">{r.evidence_document_id ? "✓" : "—"}</td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr><td colSpan={7} className="p-6 text-center text-slate-500">No compliance records</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </main>
    </div>
  );
}

function StatusPill({ s }) {
  const m = {
    Compliant: "bg-emerald-50 text-emerald-700",
    Expired: "bg-rose-50 text-rose-700",
    "Under Review": "bg-amber-50 text-amber-700",
    Missing: "bg-slate-100 text-slate-700",
  };
  return <span className={`text-[11px] px-2 py-0.5 rounded-full ${m[s] || "bg-slate-100 text-slate-700"}`}>{s || "—"}</span>;
}
