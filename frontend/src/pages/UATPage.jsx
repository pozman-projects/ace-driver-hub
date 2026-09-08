import React, { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "../lib/api";

const PACKS = ["Driver Lifecycle", "Compliance", "Migration",
  "Notifications", "Operations", "Security", "Recovery"];

const STATUS_STYLE = {
  Passed: "bg-emerald-50 text-emerald-800 border-emerald-200",
  Failed: "bg-rose-50 text-rose-800 border-rose-200",
  Blocked: "bg-amber-50 text-amber-900 border-amber-300",
  "Retest Required": "bg-indigo-50 text-indigo-800 border-indigo-200",
  "Not Applicable": "bg-slate-50 text-slate-600 border-slate-200",
  "In Progress": "bg-sky-50 text-sky-800 border-sky-200",
  Ready: "bg-slate-50 text-slate-700 border-slate-200",
  Draft: "bg-slate-50 text-slate-500 border-slate-200",
  Closed: "bg-slate-100 text-slate-700 border-slate-300",
};

const SEVERITY_STYLE = {
  Critical: "bg-rose-600 text-white",
  High: "bg-rose-100 text-rose-800 border-rose-200 border",
  Medium: "bg-amber-100 text-amber-900 border-amber-300 border",
  Low: "bg-slate-100 text-slate-700 border-slate-300 border",
};

export default function UATPage() {
  const [tab, setTab] = useState("plans");
  const [plans, setPlans] = useState([]);
  const [cases, setCases] = useState([]);
  const [defects, setDefects] = useState([]);
  const [signoffs, setSignoffs] = useState([]);
  const [activeRun, setActiveRun] = useState(null);
  const [runResults, setRunResults] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(null);
  const [newPlanName, setNewPlanName] = useState("EB-17c UAT Plan");
  const [newDefect, setNewDefect] = useState({
    severity: "Medium", title: "", description: "",
  });
  const [signoffForm, setSignoffForm] = useState({
    area: "Technical", status: "Approved", comments: "",
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [p, c, d, s] = await Promise.all([
        api.get("/uat/plans"), api.get("/uat/cases"),
        api.get("/uat/defects"), api.get("/uat/signoffs"),
      ]);
      setPlans(p.data); setCases(c.data);
      setDefects(d.data); setSignoffs(s.data);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Failed to load UAT");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const loadRun = useCallback(async (runId) => {
    try {
      const { data } = await api.get(`/uat/runs/${runId}`);
      setActiveRun(data.run);
      setRunResults(data.results || []);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    }
  }, []);

  const createPlan = async () => {
    if (!newPlanName.trim()) { toast.error("Plan name required"); return; }
    setBusy("create-plan");
    try {
      const { data } = await api.post("/uat/plans", { name: newPlanName });
      toast.success(`Plan created (${data.case_ids.length} cases)`);
      await load();
    } catch (e) { toast.error(formatApiErrorDetail(e?.response?.data?.detail)); }
    finally { setBusy(null); }
  };

  const startPlan = async (planId) => {
    setBusy(planId);
    try {
      const { data } = await api.post(`/uat/plans/${planId}/start`);
      toast.success("Run started");
      await load();
      await loadRun(data.uat_test_run_id);
      setTab("runs");
    } catch (e) { toast.error(formatApiErrorDetail(e?.response?.data?.detail)); }
    finally { setBusy(null); }
  };

  const recordResult = async (caseId, status) => {
    if (!activeRun) return;
    let reason;
    if (status === "Blocked") {
      reason = window.prompt("Reason for Blocked?") || "";
      if (!reason.trim()) return;
    }
    setBusy(`${caseId}-${status}`);
    try {
      await api.post(`/uat/results/${activeRun.uat_test_run_id}`, {
        uat_test_case_id: caseId, status,
        actual_result: `manual-${status}`,
        evidence: { note: "ui-recorded" },
        reason,
      });
      toast.success(`Recorded ${status}`);
      await loadRun(activeRun.uat_test_run_id);
    } catch (e) { toast.error(formatApiErrorDetail(e?.response?.data?.detail)); }
    finally { setBusy(null); }
  };

  const raiseDefect = async () => {
    if (!newDefect.title.trim()) { toast.error("Title required"); return; }
    setBusy("raise-defect");
    try {
      await api.post("/uat/defects", newDefect);
      toast.success("Defect raised");
      setNewDefect({ severity: "Medium", title: "", description: "" });
      await load();
    } catch (e) { toast.error(formatApiErrorDetail(e?.response?.data?.detail)); }
    finally { setBusy(null); }
  };

  const transitionDefect = async (id, to, extra = {}) => {
    setBusy(`${id}-${to}`);
    try {
      await api.post(`/uat/defects/${id}/transition`, { to_state: to, ...extra });
      toast.success(`Defect → ${to}`);
      await load();
    } catch (e) { toast.error(formatApiErrorDetail(e?.response?.data?.detail)); }
    finally { setBusy(null); }
  };

  const createSignoff = async () => {
    setBusy("signoff");
    try {
      await api.post("/uat/signoffs", signoffForm);
      toast.success(`Signed ${signoffForm.area}`);
      await load();
    } catch (e) { toast.error(formatApiErrorDetail(e?.response?.data?.detail)); }
    finally { setBusy(null); }
  };

  const withdrawSignoff = async (sid) => {
    setBusy(sid);
    try {
      await api.post(`/uat/signoffs/${sid}/withdraw`);
      toast.success("Sign-off withdrawn");
      await load();
    } catch (e) { toast.error(formatApiErrorDetail(e?.response?.data?.detail)); }
    finally { setBusy(null); }
  };

  const packCases = useMemo(() => {
    const g = {};
    for (const p of PACKS) g[p] = cases.filter((c) => c.pack === p);
    return g;
  }, [cases]);

  const latestResultByCase = useMemo(() => {
    const m = {};
    for (const r of runResults) {
      if (!m[r.uat_test_case_id] || m[r.uat_test_case_id].attempt < r.attempt)
        m[r.uat_test_case_id] = r;
    }
    return m;
  }, [runResults]);

  return (
    <div data-testid="uat-page" className="p-6 max-w-[1400px] mx-auto">
      <header className="mb-4">
        <h1 data-testid="uat-title" className="text-2xl font-semibold tracking-tight text-slate-900">
          UAT · Sign-offs
        </h1>
        <p className="text-sm text-slate-600">
          EB-17c fictional UAT workspace. No live data. No live providers.
        </p>
      </header>
      <div className="flex gap-1 border-b border-slate-200 mb-4">
        {[
          ["plans", "Plans"], ["runs", "Runs"], ["cases", "Test Cases"],
          ["defects", "Defects"], ["signoffs", "Sign-offs"],
        ].map(([k, l]) => (
          <button key={k} data-testid={`tab-${k}`}
                    onClick={() => setTab(k)}
                    className={`px-3 py-2 text-sm border-b-2 -mb-px ${
                      tab === k ? "border-slate-900 text-slate-900 font-medium"
                                 : "border-transparent text-slate-500 hover:text-slate-900"}`}>
            {l}
          </button>
        ))}
      </div>

      {loading && (
        <div data-testid="uat-loading" className="text-sm text-slate-500">Loading…</div>
      )}

      {tab === "plans" && !loading && (
        <section data-testid="tab-plans-panel" className="space-y-4">
          <div className="flex gap-2 items-end">
            <div className="flex-1">
              <label className="text-xs text-slate-600">New plan name</label>
              <input data-testid="input-plan-name" value={newPlanName}
                       onChange={(e) => setNewPlanName(e.target.value)}
                       className="w-full border border-slate-300 rounded px-2 py-1 text-sm" />
            </div>
            <button data-testid="btn-create-plan" onClick={createPlan}
                     disabled={busy === "create-plan"}
                     className="px-3 py-1.5 bg-slate-900 text-white rounded text-sm disabled:opacity-40">
              Create Plan
            </button>
          </div>
          {plans.length === 0 && (
            <div data-testid="plans-empty" className="text-sm text-slate-500">
              No UAT plans yet — create one to get started.
            </div>
          )}
          <div className="space-y-2">
            {plans.map((p) => (
              <div key={p.uat_test_plan_id} data-testid={`plan-row-${p.uat_test_plan_id}`}
                     className="border border-slate-200 rounded p-3 flex justify-between items-center">
                <div>
                  <div className="font-medium text-sm">{p.name}</div>
                  <div className="text-xs text-slate-500">
                    {p.state} · {p.case_ids?.length} cases · packs: {(p.packs || []).join(", ")}
                  </div>
                </div>
                <div className="flex gap-2">
                  {p.state === "Draft" && (
                    <button data-testid={`btn-start-${p.uat_test_plan_id}`}
                              onClick={() => startPlan(p.uat_test_plan_id)}
                              disabled={busy === p.uat_test_plan_id}
                              className="px-3 py-1 bg-emerald-600 text-white rounded text-xs">
                      Start
                    </button>
                  )}
                  {p.current_run_id && (
                    <button data-testid={`btn-open-run-${p.uat_test_plan_id}`}
                              onClick={() => { loadRun(p.current_run_id); setTab("runs"); }}
                              className="px-3 py-1 border border-slate-300 rounded text-xs">
                      Open Run
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {tab === "runs" && !loading && (
        <section data-testid="tab-runs-panel" className="space-y-4">
          {!activeRun && (
            <div data-testid="runs-empty" className="text-sm text-slate-500">
              Open a run from the Plans tab.
            </div>
          )}
          {activeRun && (
            <>
              <div className="flex justify-between items-center">
                <div>
                  <div className="text-sm font-medium">Run · {activeRun.uat_test_run_id.slice(0, 8)}</div>
                  <div className="text-xs text-slate-500">
                    State: {activeRun.state} · {runResults.length} recorded results
                  </div>
                </div>
                {activeRun.state === "In Progress" && (
                  <button data-testid="btn-close-run"
                            onClick={async () => {
                              await api.post(`/uat/runs/${activeRun.uat_test_run_id}/close`);
                              toast.success("Run closed"); loadRun(activeRun.uat_test_run_id);
                            }}
                            className="px-3 py-1 border border-slate-300 rounded text-xs">
                    Close Run
                  </button>
                )}
              </div>
              {PACKS.map((pack) => (
                <div key={pack} className="border border-slate-200 rounded">
                  <div className="px-3 py-2 bg-slate-50 border-b border-slate-200 text-xs font-medium text-slate-700">
                    {pack}
                  </div>
                  <ul>
                    {packCases[pack].map((c) => {
                      const lr = latestResultByCase[c.uat_test_case_id];
                      return (
                        <li key={c.uat_test_case_id}
                              data-testid={`case-row-${c.uat_test_case_id}`}
                              className="px-3 py-2 border-b border-slate-100 last:border-b-0 flex justify-between items-center">
                          <div className="flex-1">
                            <div className="text-sm">{c.uat_test_case_id} · {c.title}</div>
                            <div className="text-xs text-slate-500">{c.objective}</div>
                          </div>
                          {lr && (
                            <span data-testid={`case-status-${c.uat_test_case_id}`}
                                    className={`text-xs px-2 py-0.5 rounded border ${STATUS_STYLE[lr.status] || ""}`}>
                              {lr.status} (attempt {lr.attempt})
                            </span>
                          )}
                          {activeRun.state === "In Progress" && (
                            <div className="flex gap-1 ml-2">
                              {["Passed", "Failed", "Blocked", "Retest Required"].map((st) => (
                                <button key={st}
                                          data-testid={`btn-mark-${c.uat_test_case_id}-${st.replace(/\s+/g, "-")}`}
                                          onClick={() => recordResult(c.uat_test_case_id, st)}
                                          className="text-[11px] px-1.5 py-0.5 border border-slate-300 rounded hover:bg-slate-50">
                                  {st}
                                </button>
                              ))}
                            </div>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ))}
            </>
          )}
        </section>
      )}

      {tab === "cases" && !loading && (
        <section data-testid="tab-cases-panel">
          <div className="text-sm text-slate-600 mb-2">
            {cases.length} fictional cases across {PACKS.length} packs.
          </div>
          {PACKS.map((pack) => (
            <div key={pack} className="mb-4">
              <h3 className="text-sm font-medium text-slate-700 mb-1">{pack} ({packCases[pack].length})</h3>
              <ul className="text-xs text-slate-600 space-y-1">
                {packCases[pack].map((c) => (
                  <li key={c.uat_test_case_id}>
                    <span className="text-slate-500">{c.uat_test_case_id}</span> · {c.title}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </section>
      )}

      {tab === "defects" && !loading && (
        <section data-testid="tab-defects-panel" className="space-y-4">
          <div className="border border-slate-200 rounded p-3">
            <div className="text-sm font-medium mb-2">Raise Defect</div>
            <div className="grid grid-cols-4 gap-2">
              <select data-testid="input-defect-severity" value={newDefect.severity}
                        onChange={(e) => setNewDefect({ ...newDefect, severity: e.target.value })}
                        className="border border-slate-300 rounded px-2 py-1 text-sm">
                {["Critical", "High", "Medium", "Low"].map((s) => (
                  <option key={s} value={s}>{s}</option>))}
              </select>
              <input data-testid="input-defect-title" placeholder="Title"
                       value={newDefect.title}
                       onChange={(e) => setNewDefect({ ...newDefect, title: e.target.value })}
                       className="col-span-2 border border-slate-300 rounded px-2 py-1 text-sm" />
              <button data-testid="btn-raise-defect" onClick={raiseDefect}
                        className="px-3 py-1.5 bg-slate-900 text-white rounded text-sm">
                Raise
              </button>
            </div>
          </div>
          {defects.length === 0 && (
            <div data-testid="defects-empty" className="text-sm text-slate-500">No defects raised.</div>
          )}
          <div className="space-y-2">
            {defects.map((d) => (
              <div key={d.uat_defect_id} data-testid={`defect-row-${d.uat_defect_id}`}
                     className="border border-slate-200 rounded p-3">
                <div className="flex justify-between items-start">
                  <div>
                    <span className={`text-xs px-2 py-0.5 rounded ${SEVERITY_STYLE[d.severity]}`}>{d.severity}</span>
                    <span className="text-sm ml-2">{d.title}</span>
                    <div className="text-xs text-slate-500 mt-1">State: {d.state}</div>
                  </div>
                  <div className="flex gap-1 flex-wrap justify-end max-w-[400px]">
                    {["Investigating", "Fixed", "Ready for Retest",
                      "Closed", "Reopened", "Deferred"].map((t) => (
                        <button key={t}
                                  data-testid={`btn-defect-${d.uat_defect_id}-${t.replace(/\s+/g, "-")}`}
                                  onClick={() => transitionDefect(d.uat_defect_id, t,
                                    t === "Closed" ? { evidence: { note: "ui-close" } } : {})}
                                  className="text-[11px] px-1.5 py-0.5 border border-slate-300 rounded hover:bg-slate-50">
                          {t}
                        </button>
                      ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {tab === "signoffs" && !loading && (
        <section data-testid="tab-signoffs-panel" className="space-y-4">
          <div className="border border-slate-200 rounded p-3">
            <div className="text-sm font-medium mb-2">Sign-off</div>
            <div className="grid grid-cols-3 gap-2">
              <select data-testid="input-signoff-area" value={signoffForm.area}
                        onChange={(e) => setSignoffForm({ ...signoffForm, area: e.target.value })}
                        className="border border-slate-300 rounded px-2 py-1 text-sm">
                {["Business Operations", "Compliance", "Management",
                   "Technical", "Security", "Data Migration", "Recovery"].map((a) => (
                    <option key={a} value={a}>{a}</option>))}
              </select>
              <select data-testid="input-signoff-status" value={signoffForm.status}
                        onChange={(e) => setSignoffForm({ ...signoffForm, status: e.target.value })}
                        className="border border-slate-300 rounded px-2 py-1 text-sm">
                {["Approved", "Approved with Conditions", "Rejected"].map((s) => (
                  <option key={s} value={s}>{s}</option>))}
              </select>
              <button data-testid="btn-signoff-submit" onClick={createSignoff}
                        className="px-3 py-1.5 bg-slate-900 text-white rounded text-sm">
                Submit
              </button>
            </div>
          </div>
          {signoffs.length === 0 && (
            <div data-testid="signoffs-empty" className="text-sm text-slate-500">No sign-offs yet.</div>
          )}
          <div className="space-y-2">
            {signoffs.map((s) => (
              <div key={s.uat_signoff_id} data-testid={`signoff-row-${s.uat_signoff_id}`}
                     className="border border-slate-200 rounded p-3 flex justify-between items-center">
                <div>
                  <div className="text-sm font-medium">{s.area}</div>
                  <div className="text-xs text-slate-500">
                    {s.status} · by {s.signer} · {new Date(s.signed_at).toLocaleString()}
                    {s.withdrawn && " · WITHDRAWN"}
                  </div>
                </div>
                {!s.withdrawn && (
                  <button data-testid={`btn-withdraw-${s.uat_signoff_id}`}
                            onClick={() => withdrawSignoff(s.uat_signoff_id)}
                            className="px-3 py-1 border border-slate-300 rounded text-xs">
                    Withdraw
                  </button>
                )}
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
