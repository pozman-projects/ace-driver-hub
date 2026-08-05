import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import AppHeader from "../components/app/AppHeader";
import api, { formatApiErrorDetail } from "../lib/api";
import { toast } from "sonner";
import { useAuth } from "../context/AuthContext";
import { ShieldCheck, Warning, Lock, CheckCircle } from "@phosphor-icons/react";

const RESULT_COLOR = {
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

const TABS = [
  { key: "overview", label: "Overview" },
  { key: "controls", label: "Controls" },
  { key: "findings", label: "Assessment Findings" },
  { key: "matrix", label: "Permission Matrix" },
  { key: "data", label: "Data Classification" },
  { key: "audit", label: "Audit Integrity" },
  { key: "exceptions", label: "Exceptions" },
];

export default function SecurityControlCentre() {
  const { user } = useAuth();
  const canRun = user?.role === "Manager" || user?.role === "Admin";
  const canApprove = user?.role === "Manager" || user?.role === "Admin";
  const canAdmin = user?.role === "Admin";

  const [tab, setTab] = useState("overview");
  const [status, setStatus] = useState(null);
  const [controls, setControls] = useState([]);
  const [runs, setRuns] = useState([]);
  const [selectedRun, setSelectedRun] = useState(null);
  const [findings, setFindings] = useState([]);
  const [permMatrix, setPermMatrix] = useState(null);
  const [classification, setClassification] = useState(null);
  const [audit, setAudit] = useState(null);
  const [config, setConfig] = useState(null);
  const [exceptions, setExceptions] = useState([]);
  const [busy, setBusy] = useState(null);
  const [loading, setLoading] = useState(true);

  const [showRequest, setShowRequest] = useState(false);
  const [reqForm, setReqForm] = useState({
    control_key: "",
    reason: "",
    risk_acknowledgement: "",
    requested_days: 30,
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [s, c, r] = await Promise.all([
        api.get("/security/status"),
        api.get("/security/controls"),
        api.get("/security/assessments?limit=20"),
      ]);
      setStatus(s.data || null);
      setControls(c.data || []);
      setRuns(r.data || []);
      if (r.data?.length) setSelectedRun(r.data[0].security_assessment_run_id);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!selectedRun) return;
    api.get(`/security/assessments/${selectedRun}/findings`)
      .then((r) => setFindings(r.data || []))
      .catch(() => setFindings([]));
  }, [selectedRun]);

  useEffect(() => {
    if (tab === "matrix" && !permMatrix) {
      api.get("/security/permission-matrix")
        .then((r) => setPermMatrix(r.data))
        .catch((e) => toast.error(formatApiErrorDetail(e?.response?.data?.detail)));
    }
    if (tab === "data" && !classification) {
      api.get("/security/data-classification")
        .then((r) => setClassification(r.data))
        .catch((e) => toast.error(formatApiErrorDetail(e?.response?.data?.detail)));
    }
    if (tab === "audit" && !audit) {
      api.get("/security/audit-integrity")
        .then((r) => setAudit(r.data))
        .catch((e) => toast.error(formatApiErrorDetail(e?.response?.data?.detail)));
    }
    if (tab === "overview" && canRun && !config) {
      api.get("/security/configuration-status")
        .then((r) => setConfig(r.data))
        .catch(() => setConfig(null));
    }
    if (tab === "exceptions") {
      api.get("/security/exceptions")
        .then((r) => setExceptions(r.data || []))
        .catch((e) => toast.error(formatApiErrorDetail(e?.response?.data?.detail)));
    }
  }, [tab, permMatrix, classification, audit, config, canRun]);

  const runAssessment = async () => {
    setBusy("run");
    try {
      const { data } = await api.post("/security/assessments", {});
      toast.success(`Assessment complete: ${data.overall_result}`);
      await load();
      setSelectedRun(data.security_assessment_run_id);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setBusy(null); }
  };

  const submitException = async () => {
    if (!reqForm.control_key || reqForm.reason.length < 10 || reqForm.risk_acknowledgement.length < 10) {
      toast.error("All fields required (reason + risk ack must be at least 10 chars)");
      return;
    }
    setBusy("req");
    try {
      await api.post("/security/exceptions", reqForm);
      toast.success("Exception request submitted");
      setShowRequest(false);
      setReqForm({ control_key: "", reason: "", risk_acknowledgement: "", requested_days: 30 });
      const r = await api.get("/security/exceptions");
      setExceptions(r.data || []);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setBusy(null); }
  };

  const actOnException = async (id, action) => {
    setBusy(`${action}-${id}`);
    try {
      await api.post(`/security/exceptions/${id}/${action}`, { note: "via Security Control Centre" });
      toast.success(`Exception ${action}d`);
      const r = await api.get("/security/exceptions");
      setExceptions(r.data || []);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setBusy(null); }
  };

  const lastRun = status?.last_assessment;
  const counts = lastRun?.findings_by_severity || {};
  const controlsByPart = useMemo(() => {
    const out = {};
    for (const c of controls) {
      out[c.part] = out[c.part] || [];
      out[c.part].push(c);
    }
    return out;
  }, [controls]);

  return (
    <div className="min-h-screen bg-slate-50" data-testid="security-control-centre">
      <AppHeader />
      <main className="max-w-[1500px] mx-auto px-6 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <div className="flex items-center gap-3">
              <ShieldCheck size={28} className="text-slate-800" weight="duotone" />
              <h1 className="text-3xl font-semibold text-slate-900">Security Control Centre</h1>
            </div>
            <div className="text-sm text-slate-500 mt-1">
              EB-17a · Security Foundation — assessment engine, RBAC, secrets validation, audit-log integrity, exceptions
            </div>
          </div>
          <div className="flex gap-2 items-center">
            <Link to="/administration/integrity" className="text-sm text-slate-500 hover:text-slate-900 underline">
              Cross-module Integrity →
            </Link>
            {canRun && (
              <button
                data-testid="btn-run-assessment"
                onClick={runAssessment}
                disabled={busy === "run"}
                className="px-4 py-2 bg-slate-900 text-white rounded-lg text-sm font-medium hover:bg-slate-700 disabled:opacity-50"
              >
                {busy === "run" ? "Running…" : "Run Assessment"}
              </button>
            )}
          </div>
        </div>

        {/* Posture summary tiles */}
        <div className="grid grid-cols-4 gap-4 mb-6">
          <PostureTile
            testid="tile-overall"
            label="Overall Posture"
            value={lastRun?.overall_result || "—"}
            cls={RESULT_COLOR[lastRun?.overall_result] || "bg-slate-100 text-slate-700 border-slate-200"}
          />
          <PostureTile
            testid="tile-controls"
            label="Active Controls"
            value={status?.controls_count ?? 0}
            cls="bg-slate-100 text-slate-800 border-slate-200"
          />
          <PostureTile
            testid="tile-findings"
            label="Latest Findings"
            value={lastRun?.findings_count ?? 0}
            sub={`Critical ${counts.Critical || 0} • Error ${counts.Error || 0} • Warn ${counts.Warning || 0}`}
            cls="bg-slate-100 text-slate-800 border-slate-200"
          />
          <PostureTile
            testid="tile-exceptions"
            label="Exceptions"
            value={`${status?.exceptions?.pending ?? 0} pending`}
            sub={`${status?.exceptions?.approved ?? 0} approved`}
            cls="bg-slate-100 text-slate-800 border-slate-200"
          />
        </div>

        {/* Tabs */}
        <div className="flex gap-1 mb-4 border-b border-slate-200" data-testid="security-tabs">
          {TABS.map((t) => (
            <button
              key={t.key}
              data-testid={`tab-${t.key}`}
              onClick={() => setTab(t.key)}
              className={`px-4 py-2 text-sm border-b-2 -mb-px ${
                tab === t.key ? "border-slate-900 text-slate-900 font-medium" : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {loading && <div className="text-slate-500 text-sm p-6">Loading security posture…</div>}

        {tab === "overview" && !loading && (
          <OverviewTab lastRun={lastRun} config={config} canRun={canRun} runs={runs} />
        )}

        {tab === "controls" && !loading && (
          <ControlsTab controlsByPart={controlsByPart} />
        )}

        {tab === "findings" && !loading && (
          <FindingsTab
            runs={runs}
            selectedRun={selectedRun}
            setSelectedRun={setSelectedRun}
            findings={findings}
            onRequestException={(f) => {
              setReqForm({
                control_key: f.control_key,
                reason: "",
                risk_acknowledgement: "",
                requested_days: 30,
              });
              setShowRequest(true);
            }}
            canRequest={canRun}
          />
        )}

        {tab === "matrix" && !loading && (
          <MatrixTab data={permMatrix} />
        )}

        {tab === "data" && !loading && (
          <DataClassificationTab data={classification} />
        )}

        {tab === "audit" && !loading && (
          <AuditIntegrityTab data={audit} />
        )}

        {tab === "exceptions" && !loading && (
          <ExceptionsTab
            data={exceptions}
            canApprove={canApprove}
            canRequest={canRun}
            onAct={actOnException}
            onNew={() => setShowRequest(true)}
            busy={busy}
          />
        )}
      </main>

      {showRequest && (
        <RequestExceptionModal
          controls={controls}
          form={reqForm}
          setForm={setReqForm}
          onCancel={() => setShowRequest(false)}
          onSubmit={submitException}
          busy={busy === "req"}
        />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────
// Tab components
// ─────────────────────────────────────────────────────────────────────
function PostureTile({ label, value, sub, cls, testid }) {
  return (
    <div data-testid={testid} className={`border rounded-xl p-4 ${cls}`}>
      <div className="text-xs uppercase tracking-wide opacity-70">{label}</div>
      <div className="text-xl font-semibold mt-1">{value}</div>
      {sub && <div className="text-xs mt-1 opacity-70">{sub}</div>}
    </div>
  );
}

function OverviewTab({ lastRun, config, canRun, runs }) {
  return (
    <div className="grid grid-cols-3 gap-6" data-testid="overview-panel">
      <div className="col-span-2 bg-white rounded-xl border border-slate-200 p-6">
        <div className="text-sm text-slate-500 mb-2">Latest Assessment</div>
        {!lastRun && <div className="text-slate-500 text-sm">No assessment run yet.</div>}
        {lastRun && (
          <>
            <div className="text-lg font-semibold text-slate-900" data-testid="overview-result">
              {lastRun.overall_result}
            </div>
            <div className="text-xs text-slate-500 mt-1">
              Run at {new Date(lastRun.started_at).toLocaleString()} by {lastRun.actor}
            </div>
            <div className="grid grid-cols-4 gap-3 mt-4">
              {["Critical", "Error", "Warning", "Info"].map((s) => (
                <div key={s} className={`px-3 py-2 rounded-lg text-xs ${SEVERITY_COLOR[s]}`}>
                  <div className="uppercase opacity-70">{s}</div>
                  <div className="text-lg font-semibold">{lastRun.findings_by_severity?.[s] || 0}</div>
                </div>
              ))}
            </div>
            <div className="text-xs text-slate-500 mt-4">
              Routes assessed: {lastRun.route_count}
            </div>
          </>
        )}
        <div className="mt-6">
          <div className="text-sm font-medium text-slate-700 mb-2">Recent Runs</div>
          {runs.length === 0 && <div className="text-xs text-slate-500">No runs yet.</div>}
          <div className="space-y-1">
            {runs.slice(0, 8).map((r) => (
              <div key={r.security_assessment_run_id}
                   className="text-xs px-3 py-2 border border-slate-200 rounded-lg flex items-center justify-between">
                <span>{new Date(r.started_at).toLocaleString()}</span>
                <span className={`px-2 py-0.5 rounded ${RESULT_COLOR[r.overall_result] || ""}`}>
                  {r.overall_result}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
      <div className="bg-white rounded-xl border border-slate-200 p-6" data-testid="config-panel">
        <div className="text-sm text-slate-500 mb-2 flex items-center gap-2">
          <Lock size={16} /> Configuration Status
        </div>
        {!canRun && (
          <div className="text-xs text-slate-500">Manager or Admin required to view configuration.</div>
        )}
        {canRun && !config && (
          <div className="text-xs text-slate-500">Loading configuration…</div>
        )}
        {canRun && config && (
          <div className="space-y-2 text-xs">
            {Object.entries(config.configuration).map(([k, v]) => (
              <div key={k} className="flex items-center justify-between border-b border-slate-100 pb-1">
                <span className="text-slate-600">{k}</span>
                <span className="font-mono text-slate-900">{String(v)}</span>
              </div>
            ))}
            <div className="mt-3 text-slate-500">
              Leaked keys: <span className="font-semibold">{config.leaked_keys?.length || 0}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function ControlsTab({ controlsByPart }) {
  const parts = Object.keys(controlsByPart).sort((a, b) => Number(a) - Number(b));
  return (
    <div className="space-y-6" data-testid="controls-panel">
      {parts.map((p) => (
        <div key={p} className="bg-white rounded-xl border border-slate-200 p-4">
          <div className="text-sm font-semibold text-slate-800 mb-2">Part {p}</div>
          <div className="grid grid-cols-2 gap-3">
            {controlsByPart[p].map((c) => (
              <div key={c.control_key}
                   data-testid={`control-${c.control_key}`}
                   className="border border-slate-200 rounded-lg p-3">
                <div className="flex items-center justify-between">
                  <div className="text-sm font-medium text-slate-900">{c.title}</div>
                  <span className={`text-xs px-2 py-0.5 rounded ${SEVERITY_COLOR[c.severity]}`}>{c.severity}</span>
                </div>
                <div className="text-xs text-slate-500 mt-1">{c.control_key}</div>
                <div className="text-xs text-slate-700 mt-2">{c.description}</div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function FindingsTab({ runs, selectedRun, setSelectedRun, findings, onRequestException, canRequest }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4" data-testid="findings-panel">
      <div className="flex items-center gap-3 mb-4">
        <span className="text-sm text-slate-600">Assessment run:</span>
        <select
          data-testid="findings-run-select"
          className="border border-slate-200 rounded-lg px-2 py-1 text-sm"
          value={selectedRun || ""}
          onChange={(e) => setSelectedRun(e.target.value)}
        >
          {runs.map((r) => (
            <option key={r.security_assessment_run_id} value={r.security_assessment_run_id}>
              {new Date(r.started_at).toLocaleString()} · {r.overall_result}
            </option>
          ))}
        </select>
      </div>

      {findings.length === 0 && (
        <div className="text-sm text-slate-500 flex items-center gap-2 p-6" data-testid="findings-empty">
          <CheckCircle size={20} className="text-emerald-500" /> No findings for this run.
        </div>
      )}

      {findings.length > 0 && (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs uppercase text-slate-500 border-b border-slate-200">
              <th className="text-left px-2 py-2">Severity</th>
              <th className="text-left px-2 py-2">Control</th>
              <th className="text-left px-2 py-2">Message</th>
              <th className="text-right px-2 py-2">Action</th>
            </tr>
          </thead>
          <tbody>
            {findings.map((f) => (
              <tr key={f.security_assessment_finding_id} data-testid={`finding-${f.security_assessment_finding_id}`}>
                <td className="px-2 py-2">
                  <span className={`text-xs px-2 py-0.5 rounded ${SEVERITY_COLOR[f.severity]}`}>{f.severity}</span>
                </td>
                <td className="px-2 py-2 font-mono text-xs">{f.control_key}</td>
                <td className="px-2 py-2 text-slate-800">{f.message}</td>
                <td className="px-2 py-2 text-right">
                  {canRequest && (
                    <button
                      data-testid={`btn-request-exc-${f.security_assessment_finding_id}`}
                      onClick={() => onRequestException(f)}
                      className="text-xs text-slate-700 underline hover:text-slate-900"
                    >
                      Request exception
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function MatrixTab({ data }) {
  if (!data) return <div className="text-sm text-slate-500">Loading permission matrix…</div>;
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4 overflow-x-auto" data-testid="matrix-panel">
      <div className="text-sm text-slate-500 mb-3">
        {data.routes.length} routes across {data.roles.length} roles
      </div>
      <table className="w-full text-xs">
        <thead>
          <tr className="text-slate-500 border-b border-slate-200">
            <th className="text-left px-2 py-2">Method</th>
            <th className="text-left px-2 py-2">Path</th>
            <th className="text-left px-2 py-2">Auth</th>
            <th className="text-left px-2 py-2">Role Gate</th>
            <th className="text-left px-2 py-2">Allowed Roles</th>
          </tr>
        </thead>
        <tbody>
          {data.routes.map((r) => (
            <tr key={`${r.method}-${r.path}`} className="border-b border-slate-100" data-testid={`matrix-${r.method}-${r.path}`}>
              <td className="px-2 py-1.5 font-semibold">{r.method}</td>
              <td className="px-2 py-1.5 font-mono">{r.path}</td>
              <td className="px-2 py-1.5">{r.auth_type || (r.requires_auth ? "user" : "—")}</td>
              <td className="px-2 py-1.5 font-mono text-slate-600">{r.role_gate || "—"}</td>
              <td className="px-2 py-1.5">
                {r.allowed_roles.length === 0
                  ? <span className="text-slate-400">—</span>
                  : r.allowed_roles.join(", ")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DataClassificationTab({ data }) {
  if (!data) return <div className="text-sm text-slate-500">Loading data classification…</div>;
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4" data-testid="data-panel">
      <div className="text-sm text-slate-500 mb-3">
        PII & Sensitive-Data Inventory ({data.fields.length} fields)
      </div>
      <table className="w-full text-xs">
        <thead>
          <tr className="text-slate-500 border-b border-slate-200">
            <th className="text-left px-2 py-2">Collection</th>
            <th className="text-left px-2 py-2">Field</th>
            <th className="text-left px-2 py-2">Classification</th>
            <th className="text-left px-2 py-2">Sensitivity</th>
            <th className="text-left px-2 py-2">Notes</th>
          </tr>
        </thead>
        <tbody>
          {data.fields.map((f, i) => (
            <tr key={i} className="border-b border-slate-100" data-testid={`data-${f.collection}-${f.field}`}>
              <td className="px-2 py-1.5 font-mono">{f.collection}</td>
              <td className="px-2 py-1.5 font-mono">{f.field}</td>
              <td className="px-2 py-1.5">{f.classification}</td>
              <td className="px-2 py-1.5">{f.sensitivity}</td>
              <td className="px-2 py-1.5 text-slate-600">{f.notes}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AuditIntegrityTab({ data }) {
  if (!data) return <div className="text-sm text-slate-500">Loading audit integrity…</div>;
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4" data-testid="audit-panel">
      <div className="text-sm text-slate-500 mb-3">
        Append-only audit collections — worst status: <span className={`px-2 py-0.5 rounded ${data.worst_status === "OK" ? "bg-emerald-50 text-emerald-800" : "bg-rose-50 text-rose-800"}`} data-testid="audit-worst">
          {data.worst_status}
        </span>
      </div>
      <table className="w-full text-xs">
        <thead>
          <tr className="text-slate-500 border-b border-slate-200">
            <th className="text-left px-2 py-2">Collection</th>
            <th className="text-right px-2 py-2">Rows</th>
            <th className="text-right px-2 py-2">Mutated</th>
            <th className="text-center px-2 py-2">Immutable</th>
          </tr>
        </thead>
        <tbody>
          {data.collections.map((c) => (
            <tr key={c.collection} className="border-b border-slate-100" data-testid={`audit-${c.collection}`}>
              <td className="px-2 py-1.5 font-mono">{c.collection}</td>
              <td className="px-2 py-1.5 text-right">{c.total}</td>
              <td className="px-2 py-1.5 text-right">{c.mutated}</td>
              <td className="px-2 py-1.5 text-center">
                {c.immutable
                  ? <CheckCircle size={16} className="inline text-emerald-600" />
                  : <Warning size={16} className="inline text-rose-600" />}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ExceptionsTab({ data, canApprove, canRequest, onAct, onNew, busy }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4" data-testid="exceptions-panel">
      <div className="flex items-center justify-between mb-3">
        <div className="text-sm text-slate-500">{data.length} exception requests</div>
        {canRequest && (
          <button
            data-testid="btn-new-exception"
            onClick={onNew}
            className="px-3 py-1.5 bg-slate-900 text-white rounded-lg text-xs font-medium"
          >
            Request Exception
          </button>
        )}
      </div>
      {data.length === 0 && (
        <div className="text-sm text-slate-500 p-6" data-testid="exceptions-empty">
          No exceptions on file. All controls are enforced.
        </div>
      )}
      {data.length > 0 && (
        <table className="w-full text-xs">
          <thead>
            <tr className="text-slate-500 border-b border-slate-200">
              <th className="text-left px-2 py-2">Control</th>
              <th className="text-left px-2 py-2">Status</th>
              <th className="text-left px-2 py-2">Requester</th>
              <th className="text-left px-2 py-2">Reason</th>
              <th className="text-left px-2 py-2">Expires</th>
              <th className="text-right px-2 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {data.map((e) => (
              <tr key={e.security_exception_request_id}
                  data-testid={`exception-${e.security_exception_request_id}`}
                  className="border-b border-slate-100">
                <td className="px-2 py-1.5 font-mono">{e.control_key}</td>
                <td className="px-2 py-1.5">
                  <span className={`px-2 py-0.5 rounded ${
                    e.status === "Approved" ? "bg-emerald-50 text-emerald-800" :
                    e.status === "Pending" ? "bg-amber-50 text-amber-800" :
                    e.status === "Rejected" || e.status === "Revoked" || e.status === "Expired"
                      ? "bg-rose-50 text-rose-800" : "bg-slate-100 text-slate-700"
                  }`}>
                    {e.status}
                  </span>
                </td>
                <td className="px-2 py-1.5">{e.requested_by}</td>
                <td className="px-2 py-1.5 text-slate-700 max-w-md truncate" title={e.reason}>{e.reason}</td>
                <td className="px-2 py-1.5">{e.expires_at ? new Date(e.expires_at).toLocaleDateString() : "—"}</td>
                <td className="px-2 py-1.5 text-right space-x-2">
                  {canApprove && e.status === "Pending" && (
                    <>
                      <button
                        data-testid={`btn-approve-${e.security_exception_request_id}`}
                        onClick={() => onAct(e.security_exception_request_id, "approve")}
                        disabled={busy === `approve-${e.security_exception_request_id}`}
                        className="text-emerald-700 underline text-xs">
                        Approve
                      </button>
                      <button
                        data-testid={`btn-reject-${e.security_exception_request_id}`}
                        onClick={() => onAct(e.security_exception_request_id, "reject")}
                        className="text-rose-700 underline text-xs">
                        Reject
                      </button>
                    </>
                  )}
                  {canApprove && e.status === "Approved" && (
                    <button
                      data-testid={`btn-revoke-${e.security_exception_request_id}`}
                      onClick={() => onAct(e.security_exception_request_id, "revoke")}
                      className="text-rose-700 underline text-xs">
                      Revoke
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function RequestExceptionModal({ controls, form, setForm, onCancel, onSubmit, busy }) {
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" data-testid="request-modal">
      <div className="bg-white rounded-xl w-[560px] max-h-[85vh] overflow-auto shadow-xl">
        <div className="p-5 border-b border-slate-200">
          <div className="text-lg font-semibold text-slate-900">Request Security Exception</div>
          <div className="text-xs text-slate-500 mt-1">
            Requester ≠ approver. Critical controls require Admin approval. Reason & risk acknowledgement must be at least 10 characters.
          </div>
        </div>
        <div className="p-5 space-y-4">
          <div>
            <label className="text-xs text-slate-500">Control</label>
            <select
              data-testid="req-control"
              value={form.control_key}
              onChange={(e) => setForm({ ...form, control_key: e.target.value })}
              className="w-full border border-slate-200 rounded-lg px-2 py-1.5 text-sm"
            >
              <option value="">Select a control…</option>
              {controls.map((c) => (
                <option key={c.control_key} value={c.control_key}>
                  [{c.severity}] {c.control_key} — {c.title}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-slate-500">Reason</label>
            <textarea
              data-testid="req-reason"
              rows={3}
              value={form.reason}
              onChange={(e) => setForm({ ...form, reason: e.target.value })}
              className="w-full border border-slate-200 rounded-lg px-2 py-1.5 text-sm"
            />
          </div>
          <div>
            <label className="text-xs text-slate-500">Risk Acknowledgement</label>
            <textarea
              data-testid="req-ack"
              rows={3}
              value={form.risk_acknowledgement}
              onChange={(e) => setForm({ ...form, risk_acknowledgement: e.target.value })}
              className="w-full border border-slate-200 rounded-lg px-2 py-1.5 text-sm"
            />
          </div>
          <div>
            <label className="text-xs text-slate-500">Requested Days (1–365)</label>
            <input
              data-testid="req-days"
              type="number"
              min={1}
              max={365}
              value={form.requested_days}
              onChange={(e) => setForm({ ...form, requested_days: Number(e.target.value) })}
              className="w-full border border-slate-200 rounded-lg px-2 py-1.5 text-sm"
            />
          </div>
        </div>
        <div className="p-4 border-t border-slate-200 flex justify-end gap-2">
          <button
            data-testid="req-cancel"
            onClick={onCancel}
            className="px-3 py-1.5 text-sm text-slate-600 hover:text-slate-900"
          >
            Cancel
          </button>
          <button
            data-testid="req-submit"
            onClick={onSubmit}
            disabled={busy}
            className="px-4 py-1.5 bg-slate-900 text-white rounded-lg text-sm font-medium disabled:opacity-50"
          >
            {busy ? "Submitting…" : "Submit Request"}
          </button>
        </div>
      </div>
    </div>
  );
}
