import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import AppHeader from "../components/app/AppHeader";
import api, { formatApiErrorDetail } from "../lib/api";
import { toast } from "sonner";
import { useAuth } from "../context/AuthContext";
import { ArrowClockwise, ShieldCheck, Warning, CheckCircle } from "@phosphor-icons/react";

const GATE_COLOR = {
  PASS: "bg-emerald-50 text-emerald-800 border-emerald-200",
  PASS_WITH_WARNINGS: "bg-amber-50 text-amber-800 border-amber-200",
  FAIL: "bg-rose-50 text-rose-800 border-rose-200",
};

const SEVERITY_COLOR = {
  Info: "bg-slate-100 text-slate-700",
  Warning: "bg-amber-50 text-amber-700",
  Error: "bg-rose-50 text-rose-700",
  Critical: "bg-rose-200 text-rose-900",
};

export default function IntegrityAdminPage() {
  const { user } = useAuth();
  const canManage = user?.role === "Manager" || user?.role === "Admin";
  const canAdmin = user?.role === "Admin";

  const [runs, setRuns] = useState([]);
  const [findings, setFindings] = useState([]);
  const [gate, setGate] = useState(null);
  const [selectedRun, setSelectedRun] = useState(null);
  const [busy, setBusy] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [rr, gg] = await Promise.all([
        api.get("/integrity/runs?limit=20"),
        api.get("/integrity/release-gate").catch(() => ({ data: null })),
      ]);
      setRuns(rr.data || []);
      setGate(gg.data);
      if (rr.data?.length) {
        setSelectedRun(rr.data[0].integrity_check_run_id);
      }
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!selectedRun) return;
    api.get(`/integrity/runs/${selectedRun}/findings`)
       .then((r) => setFindings(r.data || []))
       .catch(() => setFindings([]));
  }, [selectedRun]);

  const runNow = async (runType) => {
    setBusy(runType);
    try {
      const { data } = await api.post("/integrity/runs", { run_type: runType });
      toast.success(`${runType}: ${data.rules_evaluated} rules evaluated`);
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setBusy(null); }
  };

  const actOnFinding = async (fid, kind) => {
    setBusy(`${kind}-${fid}`);
    try {
      await api.post(`/integrity/findings/${fid}/${kind}`, { note: "via UI" });
      toast.success(`Finding ${kind}`);
      if (selectedRun) {
        const { data } = await api.get(`/integrity/runs/${selectedRun}/findings`);
        setFindings(data || []);
      }
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setBusy(null); }
  };

  const counts = gate?.findings_by_severity || { Info: 0, Warning: 0, Error: 0, Critical: 0 };

  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader showBack />
      <main className="max-w-7xl mx-auto px-6 py-8" data-testid="integrity-admin-page">
        <div className="flex items-baseline justify-between mb-6">
          <div>
            <h1 className="font-display text-2xl font-semibold text-slate-900">Integrity Administration</h1>
            <p className="text-sm text-slate-500 mt-1">Cross-module integrity engine and release gate.</p>
          </div>
          <button data-testid="int-refresh" onClick={load} disabled={loading}
            className="text-xs px-3 py-1.5 rounded border border-slate-300 bg-white hover:bg-slate-50 flex items-center gap-1.5">
            <ArrowClockwise size={14} weight="bold" /> Refresh
          </button>
        </div>

        {gate && (
          <div className={`border rounded-xl p-5 mb-6 ${GATE_COLOR[gate.gate_result] || "bg-slate-50"}`}
               data-testid="release-gate-banner">
            <div className="flex items-center gap-3">
              <ShieldCheck size={32} weight="duotone" />
              <div className="flex-1">
                <div className="text-xs uppercase tracking-widest opacity-70">Release gate</div>
                <div className="text-2xl font-semibold" data-testid="release-gate-value">
                  {gate.gate_result}
                </div>
              </div>
              <div className="grid grid-cols-4 gap-3 text-center text-xs">
                <div><div className="opacity-70">Critical</div><div className="text-lg font-semibold" data-testid="gate-critical">{counts.Critical}</div></div>
                <div><div className="opacity-70">Error</div><div className="text-lg font-semibold" data-testid="gate-error">{counts.Error}</div></div>
                <div><div className="opacity-70">Warning</div><div className="text-lg font-semibold" data-testid="gate-warning">{counts.Warning}</div></div>
                <div><div className="opacity-70">Info</div><div className="text-lg font-semibold" data-testid="gate-info">{counts.Info}</div></div>
              </div>
            </div>
            <div className="mt-3 text-xs opacity-70" data-testid="release-gate-note">
              Rules evaluated: <b>{gate.rules_evaluated}</b> · Run ID: <span className="font-mono">{gate.integrity_check_run_id?.slice(0, 8)}</span>
              {gate.gate_result === "FAIL" && " · EB-17 blocked until resolved."}
            </div>
          </div>
        )}

        {canManage && (
          <div className="mb-6 flex flex-wrap gap-2" data-testid="int-actions">
            <button disabled={busy === "FullSystem"}
              onClick={() => runNow("FullSystem")}
              data-testid="run-full-system"
              className="text-xs px-3 py-1.5 rounded border border-cyan-300 bg-cyan-50 text-cyan-800 hover:bg-cyan-100">
              Run Full Integrity Check
            </button>
            {canAdmin && (
              <button disabled={busy === "PreReleaseGate"}
                onClick={() => runNow("PreReleaseGate")}
                data-testid="run-release-gate"
                className="text-xs px-3 py-1.5 rounded border border-slate-300 bg-white text-slate-700 hover:bg-slate-50">
                Run Pre-Release Gate
              </button>
            )}
            {["Registers", "Relationships", "Compliance", "Numbering",
                "Activation", "DocumentsStorage",
                "NotificationsAutomation", "Migration"].map((d) => (
              <button key={d} disabled={busy === d}
                onClick={() => runNow(d)}
                data-testid={`run-${d}`}
                className="text-xs px-3 py-1.5 rounded border border-slate-300 bg-white text-slate-700 hover:bg-slate-50">
                {d}
              </button>
            ))}
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="md:col-span-1">
            <h2 className="font-display font-semibold text-slate-900 mb-2">Recent runs</h2>
            <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
              <ul data-testid="int-runs">
                {runs.map((r) => (
                  <li key={r.integrity_check_run_id}
                      onClick={() => setSelectedRun(r.integrity_check_run_id)}
                      data-testid={`int-run-${r.integrity_check_run_id.slice(0, 8)}`}
                      className={`px-3 py-2 border-b border-slate-100 cursor-pointer text-xs ${
                        selectedRun === r.integrity_check_run_id ? "bg-slate-50" : ""}`}>
                    <div className="font-semibold text-slate-900">{r.run_type}</div>
                    <div className="text-slate-500">{r.started_at}</div>
                    <div className="mt-1 space-x-1">
                      {["Critical", "Error", "Warning", "Info"].map((s) => (
                        <span key={s} className={`inline-block px-1.5 py-0.5 rounded text-[10px] ${SEVERITY_COLOR[s]}`}>
                          {s[0]}:{(r.findings_by_severity || {})[s] || 0}
                        </span>
                      ))}
                    </div>
                  </li>
                ))}
                {runs.length === 0 && (
                  <li className="p-4 text-center text-slate-500 text-sm">No runs yet</li>
                )}
              </ul>
            </div>
          </div>
          <div className="md:col-span-2">
            <h2 className="font-display font-semibold text-slate-900 mb-2">Findings</h2>
            <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-slate-600 text-xs uppercase">
                  <tr>
                    <th className="text-left px-3 py-2">Rule</th>
                    <th className="text-left px-3 py-2">Severity</th>
                    <th className="text-left px-3 py-2">Status</th>
                    <th className="text-left px-3 py-2">Context</th>
                    <th className="text-right px-3 py-2">Actions</th>
                  </tr>
                </thead>
                <tbody data-testid="int-findings-tbody">
                  {findings.slice(0, 100).map((f) => (
                    <tr key={f.integrity_check_finding_id} className="border-t border-slate-100"
                        data-testid={`finding-${f.integrity_check_finding_id.slice(0, 8)}`}>
                      <td className="px-3 py-2 font-mono text-xs">{f.rule_key}</td>
                      <td className="px-3 py-2"><span className={`text-[11px] px-2 py-0.5 rounded-full ${SEVERITY_COLOR[f.severity]}`}>{f.severity}</span></td>
                      <td className="px-3 py-2 text-xs">{f.status}</td>
                      <td className="px-3 py-2 text-xs">
                        <code className="font-mono text-[10px]">{JSON.stringify(f.context || {}).slice(0, 60)}</code>
                      </td>
                      <td className="px-3 py-2 text-right">
                        {canManage && f.status !== "Resolved" && (
                          <div className="inline-flex gap-1">
                            {f.status === "Open" && (
                              <button onClick={() => actOnFinding(f.integrity_check_finding_id, "acknowledge")}
                                      data-testid={`ack-${f.integrity_check_finding_id.slice(0,8)}`}
                                      className="text-xs px-2 py-1 rounded border border-slate-300 bg-white hover:bg-slate-50">
                                Ack
                              </button>
                            )}
                            <button onClick={() => actOnFinding(f.integrity_check_finding_id, "resolve")}
                                    data-testid={`resolve-${f.integrity_check_finding_id.slice(0,8)}`}
                                    className="text-xs px-2 py-1 rounded border border-emerald-300 bg-emerald-50 text-emerald-800 hover:bg-emerald-100">
                              Resolve
                            </button>
                            {f.severity !== "Critical" && canManage && (
                              <button onClick={() => actOnFinding(f.integrity_check_finding_id, "accept-risk")}
                                      data-testid={`accept-${f.integrity_check_finding_id.slice(0,8)}`}
                                      className="text-xs px-2 py-1 rounded border border-amber-300 bg-amber-50 text-amber-800 hover:bg-amber-100">
                                Accept Risk
                              </button>
                            )}
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                  {findings.length === 0 && (
                    <tr><td colSpan={5} className="p-6 text-center text-slate-500">No findings for selected run</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
