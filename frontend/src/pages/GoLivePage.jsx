import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "../lib/api";

const RUN_STATE_STYLE = {
  Draft: "bg-slate-100 text-slate-700",
  "Awaiting Approval": "bg-amber-100 text-amber-900",
  Approved: "bg-sky-100 text-sky-900",
  Running: "bg-indigo-100 text-indigo-900",
  Monitoring: "bg-violet-100 text-violet-900",
  Completed: "bg-emerald-100 text-emerald-900",
  Aborted: "bg-rose-100 text-rose-900",
  "Rolled Back": "bg-rose-200 text-rose-950",
  Failed: "bg-rose-600 text-white",
};

const STATE_LABEL = {
  Draft: "READY TO START", Approved: "READY TO START",
  Running: "RUNNING", Monitoring: "MONITORING",
  Aborted: "ABORTED", "Rolled Back": "ROLLED BACK",
  Completed: "RELEASED",
  "Awaiting Approval": "AWAITING APPROVAL", Failed: "FAILED",
};

export default function GoLivePage() {
  const [tab, setTab] = useState("overview");
  const [runs, setRuns] = useState([]);
  const [pre, setPre] = useState(null);
  const [dep, setDep] = useState(null);
  const [current, setCurrent] = useState(null);
  const [monitoring, setMonitoring] = useState([]);
  const [migList, setMigList] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r, p, d, m] = await Promise.all([
        api.get("/go-live/runs"), api.get("/go-live/prerequisites"),
        api.get("/go-live/deployment-package"),
        api.get("/go-live/migration-authorisation"),
      ]);
      setRuns(r.data); setPre(p.data); setDep(d.data); setMigList(m.data);
      if (r.data[0]) {
        const detail = await api.get(`/go-live/runs/${r.data[0].go_live_run_id}`);
        setCurrent(detail.data);
        const mon = await api.get(`/go-live/runs/${r.data[0].go_live_run_id}/monitoring`);
        setMonitoring(mon.data);
      }
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Load failed");
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const createRun = async (mode) => {
    try {
      await api.post("/go-live/runs", { mode });
      toast.success(`${mode} run created`);
      await load();
    } catch (e) { toast.error(formatApiErrorDetail(e?.response?.data?.detail)); }
  };

  const doAbort = async () => {
    if (!current) return;
    const reason = window.prompt("Abort reason (e.g. integrity_fail):") || "";
    if (!reason.trim()) return;
    try {
      await api.post(`/go-live/runs/${current.run.go_live_run_id}/abort`,
                      { reason, authority: "Ops" });
      toast.success("Aborted");
      await load();
    } catch (e) { toast.error(formatApiErrorDetail(e?.response?.data?.detail)); }
  };

  const doRollback = async () => {
    if (!current) return;
    try {
      await api.post(`/go-live/runs/${current.run.go_live_run_id}/rollback`);
      toast.success("Rolled back");
      await load();
    } catch (e) { toast.error(formatApiErrorDetail(e?.response?.data?.detail)); }
  };

  const overallLabel = current?.run
    ? (STATE_LABEL[current.run.status] || current.run.status)
    : (pre?.state === "BLOCKED" ? "BLOCKED" : "READY TO START");

  const stateStyle = current?.run ? RUN_STATE_STYLE[current.run.status] || "" : "bg-slate-100 text-slate-700";

  return (
    <div data-testid="golive-page" className="p-6 max-w-[1400px] mx-auto">
      <header className="mb-4">
        <h1 data-testid="golive-title" className="text-2xl font-semibold text-slate-900">
          Go-Live Control Centre
        </h1>
        <p className="text-sm text-slate-600">
          EB-18 framework · Fictional / DRY_RUN by default · No live providers ·
          No public webhooks · No irreversible actions.
        </p>
      </header>

      <div className="flex gap-1 border-b border-slate-200 mb-4">
        {[["overview","Overview"],["prerequisites","Prerequisites"],
          ["cutover","Cutover"],["migration","Migration Authorisation"],
          ["monitoring","Monitoring"],["rollback","Rollback"],
          ["decision","Release Decision"]].map(([k,l]) => (
          <button key={k} data-testid={`tab-${k}`} onClick={() => setTab(k)}
                    className={`px-3 py-2 text-sm border-b-2 -mb-px ${
                      tab === k ? "border-slate-900 text-slate-900 font-medium"
                                 : "border-transparent text-slate-500 hover:text-slate-900"}`}>{l}</button>
        ))}
      </div>

      {loading && <div data-testid="gl-loading" className="text-sm text-slate-500">Loading…</div>}

      {tab === "overview" && !loading && (
        <div data-testid="tab-overview-panel" className="space-y-4">
          <div data-testid="gl-overall"
                 className={`rounded p-4 ${stateStyle} border border-slate-200`}>
            <div className="text-lg font-semibold" data-testid="gl-overall-label">
              {overallLabel}
            </div>
            <div className="text-xs mt-1">
              Mode: {current?.run?.execution_mode || "—"} ·
              Environment: {current?.run?.environment || "—"} ·
              Version: {dep?.application_version || "—"}
            </div>
          </div>
          <div className="flex gap-2">
            <button data-testid="btn-create-dryrun"
                     onClick={() => createRun("DRY_RUN")}
                     className="px-3 py-1.5 bg-slate-900 text-white rounded text-sm">
              Create DRY_RUN
            </button>
            <button data-testid="btn-create-rehearsal"
                     onClick={() => createRun("REHEARSAL")}
                     className="px-3 py-1.5 border border-slate-300 rounded text-sm">
              Create REHEARSAL
            </button>
            <div className="text-xs text-slate-500 self-center italic">
              PRODUCTION mode requires explicit approval marker and is not exposed as a one-click.
            </div>
          </div>
          <div className="border border-slate-200 rounded p-3">
            <h2 className="text-sm font-semibold mb-2">Recent runs</h2>
            {runs.length === 0 && (
              <div data-testid="runs-empty" className="text-xs text-slate-500">No runs yet.</div>
            )}
            <ul className="text-xs">
              {runs.map((r) => (
                <li key={r.go_live_run_id} data-testid={`run-${r.go_live_run_id}`}
                      className="border-b border-slate-100 py-1 flex justify-between">
                  <span>{r.execution_mode} · {r.environment} · {r.status}</span>
                  <span className="text-slate-500">{new Date(r.created_at).toLocaleString()}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {tab === "prerequisites" && !loading && pre && (
        <div data-testid="tab-prerequisites-panel">
          <div data-testid="pre-state" className="text-lg font-semibold mb-2">
            Prerequisite: {pre.state}
          </div>
          <div className="text-xs text-slate-500 mb-3">
            Result: {pre.result} · captured {new Date(pre.created_at).toLocaleString()}
          </div>
          {pre.blockers?.length > 0 && (
            <div>
              <div className="text-xs font-medium">Blockers</div>
              <ul data-testid="pre-blockers" className="text-xs list-disc list-inside text-rose-800">
                {pre.blockers.map((b) => <li key={b}>{b}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}

      {tab === "cutover" && !loading && current && (
        <div data-testid="tab-cutover-panel">
          <h2 className="text-sm font-semibold mb-2">Cutover steps (33)</h2>
          <ul className="text-xs">
            {current.steps.filter((s) => s.kind === "cutover").map((s) => (
              <li key={s.go_live_step_id} data-testid={`step-${s.step_key}`}
                    className="border-b border-slate-100 py-1 flex justify-between">
                <span>{s.order + 1}. {s.label}{s.critical ? " *" : ""}</span>
                <span className="text-slate-500">{s.status}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {tab === "migration" && !loading && (
        <div data-testid="tab-migration-panel">
          {migList.length === 0 && (
            <div data-testid="mig-empty" className="text-xs text-slate-500">
              No migration authorisation record.
            </div>
          )}
          <ul className="text-xs">
            {migList.map((m) => (
              <li key={m.go_live_migration_authorisation_id}
                    data-testid={`mig-${m.go_live_migration_authorisation_id}`}
                    className="border-b border-slate-100 py-1">
                Status: <b>{m.status}</b> · GO: {m.go_decision || "—"} ·
                marker: {String(!!m.explicit_real_data_marker)}
              </li>
            ))}
          </ul>
        </div>
      )}

      {tab === "monitoring" && !loading && (
        <div data-testid="tab-monitoring-panel">
          {monitoring.length === 0 && (
            <div data-testid="mon-empty" className="text-xs text-slate-500">No monitoring snapshots.</div>
          )}
          <ul className="text-xs">
            {monitoring.map((m) => (
              <li key={m.go_live_monitoring_snapshot_id}
                    data-testid={`mon-${m.go_live_monitoring_snapshot_id}`}
                    className="border-b border-slate-100 py-1 flex justify-between">
                <span>{new Date(m.observed_at).toLocaleString()}</span>
                <span>{m.overall_state}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {tab === "rollback" && !loading && current && (
        <div data-testid="tab-rollback-panel">
          <button data-testid="btn-rollback"
                   onClick={doRollback}
                   className="px-3 py-1.5 border border-rose-300 rounded text-sm text-rose-800">
            Trigger Controlled Rollback (framework)
          </button>
          <div className="text-xs text-slate-500 mt-2">
            Executes state transitions only. No Production disable is issued during EB-18 framework.
          </div>
        </div>
      )}

      {tab === "decision" && !loading && (
        <div data-testid="tab-decision-panel">
          {current && (
            <>
              <button data-testid="btn-abort"
                       onClick={doAbort}
                       className="px-3 py-1.5 border border-rose-300 rounded text-sm text-rose-800 mr-2">
                Abort
              </button>
              <span className="text-xs text-slate-500">
                Release decision computed by <code>GET /api/go-live/release-decision</code> per run.
              </span>
            </>
          )}
        </div>
      )}
    </div>
  );
}
