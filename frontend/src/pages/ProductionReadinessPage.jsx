import React, { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "../lib/api";

const RESULT_STYLE = {
  READY: { bg: "bg-emerald-50", border: "border-emerald-300",
           text: "text-emerald-900", label: "READY" },
  CONDITIONALLY_READY: { bg: "bg-amber-50", border: "border-amber-300",
                          text: "text-amber-900", label: "CONDITIONALLY READY" },
  NOT_READY: { bg: "bg-rose-50", border: "border-rose-300",
                text: "text-rose-900", label: "NOT READY" },
};

const GATE_PILL = (v) => {
  if (v === "PASS") return "bg-emerald-100 text-emerald-800";
  if (v === "PASS_WITH_WARNINGS") return "bg-amber-100 text-amber-900";
  if (v === "UNKNOWN") return "bg-slate-100 text-slate-600";
  return "bg-rose-100 text-rose-800";
};

export default function ProductionReadinessPage() {
  const [gate, setGate] = useState(null);
  const [status, setStatus] = useState(null);
  const [checklist, setChecklist] = useState([]);
  const [conditions, setConditions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [g, s, c, cd] = await Promise.all([
        api.get("/production-readiness/gate"),
        api.get("/production-readiness/status"),
        api.get("/production-readiness/checklist"),
        api.get("/production-readiness/conditions"),
      ]);
      setGate(g.data); setStatus(s.data);
      setChecklist(c.data); setConditions(cd.data);
    } catch (e) {
      setError(formatApiErrorDetail(e?.response?.data?.detail) || "Failed to load");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const style = useMemo(
    () => (gate ? RESULT_STYLE[gate.result] : RESULT_STYLE.NOT_READY),
    [gate]
  );

  const updateItem = async (item, next) => {
    if (item.kind === "system") return;
    try {
      const body = { status: next, owner: "operator-ui" };
      if (next === "Waived") body.evidence = { note: "ui-waived" };
      await api.post(`/production-readiness/checklist/${item.item_id}/update`, body);
      toast.success(`${item.item_id} → ${next}`);
      await load();
    } catch (e) { toast.error(formatApiErrorDetail(e?.response?.data?.detail)); }
  };

  return (
    <div data-testid="pr-page" className="p-6 max-w-[1400px] mx-auto space-y-6">
      <header>
        <h1 data-testid="pr-title" className="text-2xl font-semibold tracking-tight text-slate-900">
          Production Readiness
        </h1>
        <p className="text-sm text-slate-600">
          EB-17c fictional gate. Aggregates Integrity · Security · Recovery ·
          UAT · Sign-offs · Checklist · Conditions. Worst status wins.
        </p>
      </header>

      {loading && (
        <div data-testid="pr-loading" className="text-sm text-slate-500">Loading readiness snapshot…</div>
      )}
      {error && (
        <div data-testid="pr-error" role="alert"
               className="text-sm text-rose-800 bg-rose-50 border border-rose-200 rounded p-3">
          {error}
        </div>
      )}

      {gate && (
        <div data-testid="pr-overall"
               className={`rounded p-4 border ${style.bg} ${style.border}`}>
          <div className="flex items-center gap-3">
            <span data-testid="pr-overall-label"
                    className={`text-lg font-semibold ${style.text}`}>
              {style.label}
            </span>
            <span data-testid="pr-eb18-entry"
                    className="text-xs px-2 py-0.5 rounded border border-slate-300 bg-white">
              EB-18 entry: <b>{gate.eb18_entry}</b>
            </span>
          </div>
          {gate.blockers.length > 0 && (
            <div className="mt-3">
              <div className="text-xs font-medium text-slate-700">Blockers:</div>
              <ul data-testid="pr-blockers" className="text-xs text-rose-800 list-disc list-inside">
                {gate.blockers.map((b) => <li key={b} data-testid={`blocker-${b}`}>{b}</li>)}
              </ul>
            </div>
          )}
          {gate.warnings.length > 0 && (
            <div className="mt-2">
              <div className="text-xs font-medium text-slate-700">Warnings:</div>
              <ul data-testid="pr-warnings" className="text-xs text-amber-900 list-disc list-inside">
                {gate.warnings.map((w) => <li key={w}>{w}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}

      {status && (
        <>
          <section data-testid="pr-gate-cards" className="grid grid-cols-4 gap-3">
            <GateCard label="Integrity" value={status.integrity_gate} />
            <GateCard label="Security" value={status.security_gate} />
            <GateCard label="Recovery" value={status.recovery_gate} />
            <GateCard label="Migration" value={status.migration_readiness} />
            <GateCard label="Configuration" value={status.configuration_readiness} />
            <GateCard label="Storage" value={status.storage_readiness} />
            <GateCard label="Scheduler" value={status.scheduler_readiness} />
            <GateCard label="Rollback plan" value={status.rollback_readiness} />
          </section>

          <section data-testid="pr-uat-summary" className="border border-slate-200 rounded p-4">
            <h2 className="text-sm font-semibold mb-2">UAT summary</h2>
            <div className="grid grid-cols-5 gap-2 text-sm">
              <Stat testId="uat-completion" label="Completion" value={`${status.uat_completion_pct}%`} />
              <Stat testId="uat-passed" label="Passed" value={status.uat_cases_passed} />
              <Stat testId="uat-failed" label="Failed" value={status.uat_cases_failed} />
              <Stat testId="uat-blocked" label="Blocked" value={status.uat_cases_blocked} />
              <Stat testId="uat-total" label="Total" value={status.uat_cases_total} />
            </div>
          </section>

          <section data-testid="pr-defects" className="border border-slate-200 rounded p-4">
            <h2 className="text-sm font-semibold mb-2">Open Defects</h2>
            <div className="grid grid-cols-3 gap-2 text-sm">
              <Stat testId="defects-critical" label="Critical" value={status.open_critical_defects}
                      alertOn={status.open_critical_defects > 0} />
              <Stat testId="defects-high" label="High" value={status.open_high_defects}
                      alertOn={status.open_high_defects > 0} />
              <Stat testId="defects-medium" label="Medium" value={status.open_medium_defects} />
            </div>
          </section>

          <section data-testid="pr-signoffs" className="border border-slate-200 rounded p-4">
            <h2 className="text-sm font-semibold mb-2">Sign-offs</h2>
            <div className="grid grid-cols-4 gap-2 text-xs">
              {Object.entries(status.signoff_state).map(([area, st]) => (
                <div key={area} data-testid={`signoff-status-${area.replace(/\s+/g, "-")}`}
                       className={`border border-slate-200 rounded p-2 ${
                         st === "Approved" ? "bg-emerald-50" :
                         st === "Approved with Conditions" ? "bg-amber-50" :
                         st === "Rejected" ? "bg-rose-50" : "bg-slate-50"}`}>
                  <div className="font-medium">{area}</div>
                  <div>{st}</div>
                </div>
              ))}
            </div>
          </section>

          <section data-testid="pr-conditions" className="border border-slate-200 rounded p-4">
            <h2 className="text-sm font-semibold mb-2">Conditions register ({conditions.length})</h2>
            {conditions.length === 0 && (
              <div data-testid="conditions-empty" className="text-xs text-slate-500">No conditions recorded.</div>
            )}
            <ul className="text-xs space-y-1">
              {conditions.map((c) => (
                <li key={c.condition_id} data-testid={`cond-${c.condition_id}`}
                      className="flex gap-2">
                  <span className="w-16">{c.risk_level}</span>
                  <span className="flex-1">{c.description}</span>
                  <span className="text-slate-500">{c.status}</span>
                </li>
              ))}
            </ul>
          </section>

          <section data-testid="pr-checklist" className="border border-slate-200 rounded p-4">
            <h2 className="text-sm font-semibold mb-2">
              Go-Live Checklist ({status.checklist_completed}/{status.checklist_total})
            </h2>
            <ul className="text-xs">
              {checklist.map((it) => (
                <li key={it.item_id} data-testid={`chk-${it.item_id}`}
                      className="flex items-center gap-2 border-b border-slate-100 py-1 last:border-b-0">
                  <span className={`inline-block w-16 text-[11px] ${
                    it.status === "Complete" ? "text-emerald-700" :
                    it.status === "Waived" ? "text-amber-800" : "text-slate-500"}`}>
                    {it.status}
                  </span>
                  <span className="flex-1">{it.label}</span>
                  <span className="text-slate-400 text-[11px]">{it.kind}</span>
                  {it.kind === "human" && (
                    <button data-testid={`chk-complete-${it.item_id}`}
                              onClick={() => updateItem(it, "Complete")}
                              className="text-[11px] px-1.5 py-0.5 border border-slate-300 rounded hover:bg-slate-50">
                      Mark Complete
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </div>
  );
}

function GateCard({ label, value }) {
  return (
    <div data-testid={`gatecard-${label.toLowerCase().replace(/\s+/g, "-")}`}
           className="border border-slate-200 rounded p-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className={`inline-block mt-1 px-2 py-0.5 rounded text-xs ${GATE_PILL(value)}`}>{value}</div>
    </div>
  );
}
function Stat({ testId, label, value, alertOn }) {
  return (
    <div data-testid={testId}
           className={`border rounded p-2 ${alertOn ? "bg-rose-50 border-rose-200" : "border-slate-200"}`}>
      <div className="text-xs text-slate-500">{label}</div>
      <div className="text-lg font-semibold">{value}</div>
    </div>
  );
}
