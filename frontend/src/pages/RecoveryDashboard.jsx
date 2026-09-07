import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import AppHeader from "../components/app/AppHeader";
import api, { formatApiErrorDetail } from "../lib/api";
import { toast } from "sonner";
import { useAuth } from "../context/AuthContext";
import { Database, ArrowClockwise, ShieldCheck, Warning, CheckCircle, ClockCounterClockwise } from "@phosphor-icons/react";

const RESULT_STYLE = {
  PASS: { cls: "bg-emerald-50 text-emerald-800 border-emerald-200", icon: "check" },
  PASS_WITH_WARNINGS: { cls: "bg-amber-50 text-amber-800 border-amber-200", icon: "warn" },
  FAIL: { cls: "bg-rose-50 text-rose-800 border-rose-200", icon: "warn" },
  Passed: { cls: "bg-emerald-50 text-emerald-800 border-emerald-200", icon: "check" },
  Failed: { cls: "bg-rose-50 text-rose-800 border-rose-200", icon: "warn" },
  Completed: { cls: "bg-emerald-50 text-emerald-800 border-emerald-200", icon: "check" },
  "Completed with Warnings": { cls: "bg-amber-50 text-amber-800 border-amber-200", icon: "warn" },
  Running: { cls: "bg-sky-50 text-sky-800 border-sky-200", icon: "clock" },
  Cancelled: { cls: "bg-slate-100 text-slate-700 border-slate-200", icon: "warn" },
  Reconciled: { cls: "bg-emerald-50 text-emerald-800 border-emerald-200", icon: "check" },
};

const TABS_ALL = [
  { key: "overview", label: "Overview", roles: null },
  { key: "backups", label: "Backups", roles: ["Compliance", "Manager", "Admin"] },
  { key: "rehearsals", label: "Restore Rehearsals", roles: ["Compliance", "Manager", "Admin"] },
  { key: "reconciliation", label: "Reconciliation", roles: ["Compliance", "Manager", "Admin"] },
  { key: "rpo_rto", label: "RPO/RTO", roles: ["Compliance", "Manager", "Admin"] },
  { key: "gate", label: "Recovery Gate", roles: null },
];

function StatusBadge({ value }) {
  const s = RESULT_STYLE[value] || { cls: "bg-slate-100 text-slate-700 border-slate-200", icon: null };
  return (
    <span data-testid={`status-${value}`} aria-label={`status ${value}`}
          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs border ${s.cls}`}>
      {s.icon === "check" && <CheckCircle size={12} weight="bold" />}
      {s.icon === "warn" && <Warning size={12} weight="bold" />}
      {s.icon === "clock" && <ClockCounterClockwise size={12} weight="bold" />}
      {value}
    </span>
  );
}

export default function RecoveryDashboard() {
  const { user } = useAuth();
  const isAdmin = user?.role === "Admin";
  const canApprove = user?.role === "Manager" || user?.role === "Admin";
  const canViewAdmin = ["Compliance", "Manager", "Admin"].includes(user?.role);

  const [tab, setTab] = useState("overview");
  const [status, setStatus] = useState(null);
  const [config, setConfig] = useState(null);
  const [backups, setBackups] = useState([]);
  const [rehearsals, setRehearsals] = useState([]);
  const [gate, setGate] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(null);
  const [cfgForm, setCfgForm] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const promises = [api.get("/recovery/status"), api.get("/recovery/gate")];
      if (canViewAdmin) {
        promises.push(api.get("/recovery/configuration"));
        promises.push(api.get("/backups"));
        promises.push(api.get("/recovery/rehearsals"));
      }
      const results = await Promise.all(promises);
      setStatus(results[0].data);
      setGate(results[1].data);
      if (canViewAdmin) {
        setConfig(results[2].data);
        setBackups(results[3].data || []);
        setRehearsals(results[4].data || []);
      }
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setLoading(false); }
  }, [canViewAdmin]);

  useEffect(() => { load(); }, [load]);

  const createBackup = async () => {
    setBusy("backup");
    try {
      const { data } = await api.post("/backups", {});
      toast.success(`Backup ${data.state}`);
      await load();
    } catch (e) { toast.error(formatApiErrorDetail(e?.response?.data?.detail)); }
    finally { setBusy(null); }
  };

  const validateBackup = async (id) => {
    setBusy(`v-${id}`);
    try {
      const { data } = await api.post(`/backups/${id}/validate`);
      toast.success(`Validation: ${data.result}`);
      await load();
    } catch (e) { toast.error(formatApiErrorDetail(e?.response?.data?.detail)); }
    finally { setBusy(null); }
  };

  const startRehearsal = async (id) => {
    setBusy(`r-${id}`);
    try {
      const { data } = await api.post("/recovery/rehearsals",
        { backup_run_id: id, approved: true });
      toast.success(`Rehearsal: ${data.final_state}`);
      await load();
    } catch (e) { toast.error(formatApiErrorDetail(e?.response?.data?.detail)); }
    finally { setBusy(null); }
  };

  const saveConfig = async () => {
    if (!cfgForm) return;
    setBusy("cfg");
    try {
      const { data } = await api.post("/recovery/configuration", cfgForm);
      toast.success(`Configuration updated (${data.label})`);
      setCfgForm(null);
      await load();
    } catch (e) { toast.error(formatApiErrorDetail(e?.response?.data?.detail)); }
    finally { setBusy(null); }
  };

  const tabs = TABS_ALL.filter((t) => !t.roles || t.roles.includes(user?.role));

  return (
    <div className="min-h-screen bg-slate-50" data-testid="recovery-dashboard">
      <AppHeader />
      <main className="max-w-[1500px] mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <div className="flex items-center gap-3">
              <Database size={28} className="text-slate-800" weight="duotone" />
              <h1 className="text-3xl font-semibold text-slate-900">Recovery & Backup</h1>
            </div>
            <div className="text-sm text-slate-500 mt-1">
              EB-17b · Backup / Restore / Disaster-Recovery / RPO-RTO — fictional/test environment only
            </div>
            {config && (
              <div data-testid="fictional-marker" role="note"
                   className="inline-block mt-2 px-2 py-0.5 text-[11px] bg-amber-50 text-amber-800 border border-amber-200 rounded">
                {config.label}
              </div>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Link to="/administration/security"
                  className="text-sm text-slate-500 hover:text-slate-900 underline">
              Security Control Centre →
            </Link>
            {isAdmin && (
              <button data-testid="btn-create-backup" onClick={createBackup}
                      disabled={busy === "backup"}
                      className="px-4 py-2 bg-slate-900 text-white rounded-lg text-sm font-medium hover:bg-slate-700 disabled:opacity-50">
                {busy === "backup" ? "Creating…" : "Create Backup"}
              </button>
            )}
          </div>
        </div>

        {/* Posture tiles */}
        <div className="grid grid-cols-4 gap-4 mb-6">
          <Tile testid="tile-gate" label="Recovery Gate"
                value={gate?.result || "—"}
                sub={`${(gate?.errors || []).length} errors`} />
          <Tile testid="tile-latest-backup" label="Latest Backup"
                value={status?.latest_backup?.state || "—"}
                sub={`age ${status?.backup_age_minutes ?? "—"}m`} />
          <Tile testid="tile-latest-rehearsal" label="Latest Rehearsal"
                value={status?.latest_rehearsal?.final_state || "—"}
                sub={`RTO ${status?.achieved_rto_minutes ?? "—"}m`} />
          <Tile testid="tile-unreconciled" label="Unreconciled"
                value={status?.outstanding_reconciliation_differences ?? 0}
                sub={config ? `RPO≤${config.rpo_target_minutes}m · RTO≤${config.rto_target_minutes}m` : ""} />
        </div>

        {/* Tabs */}
        <div className="flex gap-1 mb-4 border-b border-slate-200" data-testid="recovery-tabs">
          {tabs.map((t) => (
            <button key={t.key} data-testid={`tab-${t.key}`}
                    onClick={() => setTab(t.key)}
                    className={`px-4 py-2 text-sm border-b-2 -mb-px ${
                      tab === t.key ? "border-slate-900 text-slate-900 font-medium"
                                    : "border-transparent text-slate-500 hover:text-slate-800"
                    }`}>{t.label}</button>
          ))}
        </div>

        {loading && <div data-testid="recovery-loading" className="p-6 text-sm text-slate-500">Loading recovery posture…</div>}

        {!loading && tab === "overview" && (
          <div data-testid="overview-panel" className="grid grid-cols-2 gap-6">
            <div className="bg-white rounded-xl border border-slate-200 p-5">
              <div className="text-sm text-slate-500 mb-2">Recent Failures</div>
              {(gate?.errors || []).length === 0 ? (
                <div data-testid="failures-empty" className="text-emerald-700 text-sm flex items-center gap-2">
                  <CheckCircle size={16} weight="bold" /> No recent failures.
                </div>
              ) : (
                <ul className="space-y-1 text-sm text-rose-800">
                  {gate.errors.map((e, i) => <li key={i}>• {e}</li>)}
                </ul>
              )}
              <div className="text-sm text-slate-500 mt-4 mb-2">Warnings</div>
              {(gate?.warnings || []).length === 0 ? (
                <div className="text-slate-500 text-xs">None.</div>
              ) : (
                <ul className="space-y-1 text-sm text-amber-800">
                  {gate.warnings.map((w, i) => <li key={i}>• {w}</li>)}
                </ul>
              )}
            </div>
            <div className="bg-white rounded-xl border border-slate-200 p-5">
              <div className="text-sm text-slate-500 mb-2">Configuration (fictional / test)</div>
              {config ? (
                <div className="space-y-1 text-xs">
                  {Object.entries(config).filter(([k]) => !k.startsWith("_")).map(([k, v]) => (
                    <div key={k} className="flex justify-between border-b border-slate-100 pb-1">
                      <span className="text-slate-600">{k}</span>
                      <span className="font-mono text-slate-900">{String(v)}</span>
                    </div>
                  ))}
                </div>
              ) : <div className="text-xs text-slate-500">Compliance+ required.</div>}
            </div>
          </div>
        )}

        {!loading && tab === "backups" && (
          <div data-testid="backups-panel" className="bg-white rounded-xl border border-slate-200 p-4 overflow-x-auto">
            {backups.length === 0 && <div data-testid="backups-empty" className="p-6 text-sm text-slate-500">No backups yet.</div>}
            {backups.length > 0 && (
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-slate-500 border-b border-slate-200">
                    <th className="text-left px-2 py-2">Started</th>
                    <th className="text-left px-2 py-2">State</th>
                    <th className="text-left px-2 py-2">Records</th>
                    <th className="text-left px-2 py-2">Artifacts</th>
                    <th className="text-left px-2 py-2">Checksum</th>
                    <th className="text-right px-2 py-2">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {backups.map((b) => (
                    <tr key={b.backup_run_id} data-testid={`backup-${b.backup_run_id}`} className="border-b border-slate-100">
                      <td className="px-2 py-2">{new Date(b.started_at).toLocaleString()}</td>
                      <td className="px-2 py-2"><StatusBadge value={b.state} /></td>
                      <td className="px-2 py-2">{Object.values(b.record_counts_by_domain || {}).reduce((a, x) => a + x, 0)}</td>
                      <td className="px-2 py-2">{b.artifact_count}</td>
                      <td className="px-2 py-2 font-mono truncate max-w-[220px]" title={b.manifest_checksum || ""}>
                        {b.manifest_checksum ? b.manifest_checksum.slice(0, 12) + "…" : "—"}
                      </td>
                      <td className="px-2 py-2 text-right space-x-2">
                        {canApprove && (
                          <button data-testid={`btn-validate-${b.backup_run_id}`}
                                  onClick={() => validateBackup(b.backup_run_id)}
                                  className="text-xs text-slate-800 underline">Validate</button>
                        )}
                        {isAdmin && (
                          <button data-testid={`btn-rehearse-${b.backup_run_id}`}
                                  onClick={() => startRehearsal(b.backup_run_id)}
                                  className="text-xs text-slate-800 underline">Start Rehearsal</button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        {!loading && tab === "rehearsals" && (
          <div data-testid="rehearsals-panel" className="bg-white rounded-xl border border-slate-200 p-4 overflow-x-auto">
            {rehearsals.length === 0 && <div data-testid="rehearsals-empty" className="p-6 text-sm text-slate-500">No restore rehearsals yet.</div>}
            {rehearsals.length > 0 && (
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-slate-500 border-b border-slate-200">
                    <th className="text-left px-2 py-2">Started</th>
                    <th className="text-left px-2 py-2">State</th>
                    <th className="text-left px-2 py-2">Duration</th>
                    <th className="text-left px-2 py-2">Integrity</th>
                    <th className="text-left px-2 py-2">Security</th>
                    <th className="text-left px-2 py-2">Residue</th>
                  </tr>
                </thead>
                <tbody>
                  {rehearsals.map((r) => (
                    <tr key={r.restore_rehearsal_id} data-testid={`rehearsal-${r.restore_rehearsal_id}`} className="border-b border-slate-100">
                      <td className="px-2 py-2">{new Date(r.started_at).toLocaleString()}</td>
                      <td className="px-2 py-2"><StatusBadge value={r.final_state} /></td>
                      <td className="px-2 py-2">{(r.duration_seconds || 0).toFixed(2)}s</td>
                      <td className="px-2 py-2"><StatusBadge value={r.integrity_gate || "—"} /></td>
                      <td className="px-2 py-2"><StatusBadge value={r.security_gate || "—"} /></td>
                      <td className="px-2 py-2">{r.no_residue ? "clear" : "present"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        {!loading && tab === "reconciliation" && (
          <div data-testid="reconciliation-panel" className="bg-white rounded-xl border border-slate-200 p-4">
            {(!rehearsals[0] || !rehearsals[0].reconciliation) ? (
              <div data-testid="reconciliation-empty" className="p-6 text-sm text-slate-500">
                No reconciliation record yet. Run a rehearsal to populate.
              </div>
            ) : (
              <div>
                <div className="text-sm text-slate-500 mb-3">Latest reconciliation · <StatusBadge value={rehearsals[0].reconciliation.result} /></div>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  {Object.entries(rehearsals[0].reconciliation.checks || {}).map(([k, v]) => (
                    <div key={k} className="flex justify-between border border-slate-100 rounded px-2 py-1">
                      <span className="font-mono text-slate-700">{k}</span>
                      <StatusBadge value={v} />
                    </div>
                  ))}
                </div>
                {(rehearsals[0].reconciliation.differences || []).length > 0 && (
                  <div className="mt-4">
                    <div className="text-sm font-medium text-rose-800 mb-2">Differences</div>
                    <pre className="bg-slate-50 text-xs p-3 rounded overflow-auto">
                      {JSON.stringify(rehearsals[0].reconciliation.differences, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {!loading && tab === "rpo_rto" && (
          <div data-testid="rpo-rto-panel" className="bg-white rounded-xl border border-slate-200 p-5">
            {!config ? <div className="text-sm text-slate-500">Compliance+ required.</div> : (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <Tile testid="tile-rpo" label="RPO target / achieved"
                        value={`${config.rpo_target_minutes}m / ${status?.achieved_rpo_minutes ?? "—"}m`} />
                  <Tile testid="tile-rto" label="RTO target / achieved"
                        value={`${config.rto_target_minutes}m / ${status?.achieved_rto_minutes ?? "—"}m`} />
                </div>
                {isAdmin && (
                  <div className="border-t border-slate-200 pt-4">
                    <div className="text-sm font-medium text-slate-800 mb-2">Update Development/Test Configuration</div>
                    <div className="grid grid-cols-3 gap-2 text-xs">
                      <label>RPO minutes
                        <input data-testid="cfg-rpo" type="number" min={1} max={100000}
                               defaultValue={config.rpo_target_minutes}
                               onChange={(e) => setCfgForm({
                                 ...(cfgForm || {
                                   environment: config.environment,
                                   rpo_target_minutes: config.rpo_target_minutes,
                                   rto_target_minutes: config.rto_target_minutes,
                                   backup_age_warning_hours: config.backup_age_warning_hours,
                                 }),
                                 rpo_target_minutes: Number(e.target.value),
                               })}
                               className="w-full border border-slate-200 rounded px-2 py-1"/>
                      </label>
                      <label>RTO minutes
                        <input data-testid="cfg-rto" type="number" min={1} max={100000}
                               defaultValue={config.rto_target_minutes}
                               onChange={(e) => setCfgForm({
                                 ...(cfgForm || {
                                   environment: config.environment,
                                   rpo_target_minutes: config.rpo_target_minutes,
                                   rto_target_minutes: config.rto_target_minutes,
                                   backup_age_warning_hours: config.backup_age_warning_hours,
                                 }),
                                 rto_target_minutes: Number(e.target.value),
                               })}
                               className="w-full border border-slate-200 rounded px-2 py-1"/>
                      </label>
                      <label>Age warning (h)
                        <input data-testid="cfg-age" type="number" min={1} max={720}
                               defaultValue={config.backup_age_warning_hours}
                               onChange={(e) => setCfgForm({
                                 ...(cfgForm || {
                                   environment: config.environment,
                                   rpo_target_minutes: config.rpo_target_minutes,
                                   rto_target_minutes: config.rto_target_minutes,
                                   backup_age_warning_hours: config.backup_age_warning_hours,
                                 }),
                                 backup_age_warning_hours: Number(e.target.value),
                               })}
                               className="w-full border border-slate-200 rounded px-2 py-1"/>
                      </label>
                    </div>
                    <div className="mt-3 flex gap-2">
                      <button data-testid="btn-save-config" onClick={saveConfig}
                              disabled={!cfgForm || busy === "cfg"}
                              className="px-3 py-1.5 bg-slate-900 text-white rounded text-xs disabled:opacity-40">
                        Save (Development/Test only)
                      </button>
                      <div className="text-[11px] text-slate-500 self-center">
                        Production-approved values require future explicit process — not settable here.
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {!loading && tab === "gate" && (
          <div data-testid="gate-panel" className="bg-white rounded-xl border border-slate-200 p-5">
            <div className="text-sm text-slate-500 mb-2">Recovery Readiness Gate</div>
            <div data-testid="gate-result" className="mb-4">
              <StatusBadge value={gate?.result || "—"} />
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs">
              {Object.entries(gate?.checks || {}).map(([k, v]) => (
                <div key={k} data-testid={`gate-check-${k}`}
                     className="flex justify-between border border-slate-100 rounded px-2 py-1">
                  <span className="font-mono text-slate-700">{k}</span>
                  <StatusBadge value={v} />
                </div>
              ))}
            </div>
            {(gate?.errors || []).length > 0 && (
              <div className="mt-4">
                <div className="text-sm font-medium text-rose-800 mb-1">Blocking errors</div>
                <ul className="text-xs text-rose-800 space-y-1">
                  {gate.errors.map((e, i) => <li key={i}>• {e}</li>)}
                </ul>
              </div>
            )}
            {(gate?.warnings || []).length > 0 && (
              <div className="mt-4">
                <div className="text-sm font-medium text-amber-800 mb-1">Warnings</div>
                <ul className="text-xs text-amber-800 space-y-1">
                  {gate.warnings.map((w, i) => <li key={i}>• {w}</li>)}
                </ul>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}

function Tile({ label, value, sub, testid }) {
  return (
    <div data-testid={testid} className="border rounded-xl p-4 bg-white border-slate-200">
      <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div className="text-xl font-semibold text-slate-900 mt-1">{value}</div>
      {sub && <div className="text-xs mt-1 text-slate-500">{sub}</div>}
    </div>
  );
}
