import React, { useEffect, useState, useCallback } from "react";
import { Link, useParams } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { ArrowLeft, CheckCircle, XCircle, Warning } from "@phosphor-icons/react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api/migration-prep`;
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem("ace_token")}` } });

const TABS = ["Summary", "Rows", "Changes", "Issues", "Identifiers",
              "Relationships", "Compliance", "Activation", "Documents",
              "Rollback", "Go / No-Go"];


function severityStyle(s) {
  return s === "Critical" ? "bg-rose-100 text-rose-800"
    : s === "Error" ? "bg-rose-100 text-rose-800"
    : s === "Warning" ? "bg-amber-100 text-amber-800"
    : "bg-slate-100 text-slate-700";
}


export default function MigrationDryRunDetailPage() {
  const { dryRunId } = useParams();
  const [tab, setTab] = useState("Summary");
  const [dr, setDr] = useState(null);
  const [rows, setRows] = useState([]);
  const [changes, setChanges] = useState([]);
  const [issues, setIssues] = useState([]);
  const [ident, setIdent] = useState(null);
  const [rel, setRel] = useState(null);
  const [comp, setComp] = useState(null);
  const [act, setAct] = useState(null);
  const [docs, setDocs] = useState(null);
  const [rollback, setRollback] = useState(null);
  const [gng, setGng] = useState(null);
  const [filter, setFilter] = useState({ entity: "", status: "", severity: "" });

  const load = useCallback(async () => {
    try {
      const [d, r, c, i, id, rl, cm, ac, dm, rb] = await Promise.all([
        axios.get(`${API}/dry-runs/${dryRunId}`, auth()),
        axios.get(`${API}/dry-runs/${dryRunId}/rows`, auth()),
        axios.get(`${API}/dry-runs/${dryRunId}/changes`, auth()),
        axios.get(`${API}/dry-runs/${dryRunId}/issues`, auth()),
        axios.get(`${API}/dry-runs/${dryRunId}/identifier-impact`, auth()),
        axios.get(`${API}/dry-runs/${dryRunId}/relationship-impact`, auth()),
        axios.get(`${API}/dry-runs/${dryRunId}/compliance-impact`, auth()),
        axios.get(`${API}/dry-runs/${dryRunId}/activation-impact`, auth()),
        axios.get(`${API}/dry-runs/${dryRunId}/document-manifest`, auth()),
        axios.get(`${API}/dry-runs/${dryRunId}/rollback-manifest`, auth()).catch(() => ({ data: null })),
      ]);
      setDr(d.data); setRows(r.data); setChanges(c.data); setIssues(i.data);
      setIdent(id.data); setRel(rl.data); setComp(cm.data); setAct(ac.data);
      setDocs(dm.data); setRollback(rb.data);
      // Try existing Go/No-Go
      try {
        const g = await axios.get(`${API}/dry-runs/${dryRunId}/go-no-go`, auth());
        setGng(g.data);
      } catch {
        setGng(null);
      }
    } catch (err) {
      toast.error(`Load failed: ${err.response?.data?.detail || err.message}`);
    }
  }, [dryRunId]);

  useEffect(() => { load(); }, [load]);

  const computeGng = async () => {
    try {
      const r = await axios.post(`${API}/dry-runs/${dryRunId}/go-no-go`, {}, auth());
      setGng(r.data);
      toast.success(`Computed: ${r.data.result}`);
    } catch (err) {
      toast.error(`Compute failed: ${err.response?.data?.detail || err.message}`);
    }
  };

  const decideGng = async (action) => {
    try {
      await axios.post(`${API}/go-no-go/${gng.migration_go_no_go_report_id}/${action}`,
        { approval_note: "" }, auth());
      toast.success(action === "approve" ? "Approved" : "Rejected");
      load();
    } catch (err) {
      toast.error(`${action} failed: ${err.response?.data?.detail || err.message}`);
    }
  };

  const resolveIssue = async (issueId) => {
    const resolution_type = window.prompt("Resolution type (e.g. Reject Row, Ignore Warning, Preserve Canonical)?");
    if (!resolution_type) return;
    try {
      await axios.post(`${API}/issues/${issueId}/resolve`,
        { resolution_type, resolution_note: "" }, auth());
      toast.success("Resolved");
      load();
    } catch (err) {
      toast.error(`Resolve failed: ${err.response?.data?.detail || err.message}`);
    }
  };

  const reopenIssue = async (issueId) => {
    try {
      await axios.post(`${API}/issues/${issueId}/reopen`, {}, auth());
      toast.success("Reopened");
      load();
    } catch (err) {
      toast.error(`Reopen failed: ${err.response?.data?.detail || err.message}`);
    }
  };

  if (!dr) return <div className="p-6 text-sm text-slate-500">Loading…</div>;

  const filteredIssues = issues.filter(i =>
    (!filter.entity || i.entity_type === filter.entity) &&
    (!filter.status || i.status === filter.status) &&
    (!filter.severity || i.severity === filter.severity));

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900" data-testid="dry-run-detail-page">
      <div className="max-w-7xl mx-auto px-6 py-8">
        <Link to="/migration-preparation/dry-runs" data-testid="btn-back-dry-runs"
              className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-800 mb-2">
          <ArrowLeft size={12} /> Back to Dry Runs
        </Link>
        <div className="flex items-baseline gap-3">
          <h1 className="text-2xl font-bold tracking-tight">{dr.name}</h1>
          <span className={`text-[10px] uppercase tracking-[0.14em] px-1.5 py-0.5 rounded-full ${
            dr.status === "Preview Ready" ? "bg-emerald-100 text-emerald-800"
              : dr.status === "Failed" ? "bg-rose-100 text-rose-800"
              : "bg-slate-100 text-slate-700"}`}>{dr.status}</span>
        </div>

        {/* Tabs */}
        <div className="mt-4 border-b border-slate-200 overflow-x-auto">
          <div className="flex gap-1 min-w-max">
            {TABS.map(t => (
              <button key={t} onClick={() => setTab(t)}
                       data-testid={`tab-${t.toLowerCase().replace(/[ /]/g, "-")}`}
                       className={`px-3 py-2 text-xs font-medium border-b-2 transition-colors ${
                         tab === t ? "border-cyan-600 text-cyan-800" : "border-transparent text-slate-500 hover:text-slate-800"}`}>
                {t}
              </button>
            ))}
          </div>
        </div>

        {/* Tab content */}
        <div className="mt-4">
          {tab === "Summary" && (
            <div className="grid md:grid-cols-4 gap-3" data-testid="summary-content">
              <Card label="Rows" value={dr.row_count} testid="s-rows"/>
              <Card label="Valid" value={dr.valid_row_count} tone="ok" testid="s-valid"/>
              <Card label="Warning" value={dr.warning_row_count} tone="warn" testid="s-warn"/>
              <Card label="Blocking" value={dr.invalid_row_count} tone="bad" testid="s-block"/>
              <Card label="Proposed Creates" value={dr.proposed_create_count} testid="s-creates"/>
              <Card label="Proposed Updates" value={dr.proposed_update_count} testid="s-updates"/>
              <Card label="Blocking Issues" value={dr.blocking_issue_count} tone="bad" testid="s-bi"/>
              <Card label="Warning Issues" value={dr.warning_issue_count} tone="warn" testid="s-wi"/>
            </div>
          )}

          {tab === "Rows" && <TableView data={rows} cols={[
            ["source_row_number", "Row"], ["target_entity_type", "Entity"],
            ["match_status", "Match"], ["proposed_action", "Action"],
            ["row_status", "Status"], ["issue_count", "Issues"],
          ]} testid="rows-table"/>}

          {tab === "Changes" && <TableView data={changes} cols={[
            ["target_entity_type", "Entity"], ["target_field", "Field"],
            ["current_value", "Current"], ["proposed_value", "Proposed"],
            ["change_type", "Change"], ["conflict_status", "Conflict"],
          ]} testid="changes-table"/>}

          {tab === "Issues" && (
            <div data-testid="issues-content">
              <div className="mb-3 flex flex-wrap gap-2 text-xs">
                <select className="border border-slate-200 rounded-md px-2 py-1"
                        value={filter.severity}
                        onChange={e => setFilter({ ...filter, severity: e.target.value })}>
                  <option value="">All severities</option>
                  {["Info", "Warning", "Error", "Critical"].map(s => <option key={s}>{s}</option>)}
                </select>
                <select className="border border-slate-200 rounded-md px-2 py-1"
                        value={filter.status}
                        onChange={e => setFilter({ ...filter, status: e.target.value })}>
                  <option value="">All statuses</option>
                  {["Open", "In Review", "Resolved", "Accepted Risk", "Rejected"].map(s => <option key={s}>{s}</option>)}
                </select>
              </div>
              <div className="rounded-lg border border-slate-200 bg-white overflow-x-auto">
                <table className="min-w-full divide-y divide-slate-200 text-sm">
                  <thead className="bg-slate-50 text-left text-[10px] uppercase tracking-[0.14em] text-slate-500">
                    <tr>
                      <th className="px-3 py-2">Severity</th>
                      <th className="px-3 py-2">Code</th>
                      <th className="px-3 py-2">Entity · Field</th>
                      <th className="px-3 py-2">Message</th>
                      <th className="px-3 py-2">Status</th>
                      <th className="px-3 py-2 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {filteredIssues.map(i => (
                      <tr key={i.migration_issue_id}
                          data-testid={`issue-row-${i.migration_issue_id}`}>
                        <td className="px-3 py-2">
                          <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${severityStyle(i.severity)}`}>{i.severity}</span>
                        </td>
                        <td className="px-3 py-2 font-mono text-[10px]">{i.issue_code}</td>
                        <td className="px-3 py-2 text-xs">{i.entity_type} · {i.field_name || "—"}</td>
                        <td className="px-3 py-2 text-xs">{i.message}</td>
                        <td className="px-3 py-2 text-[11px]">{i.status}</td>
                        <td className="px-3 py-2 text-right">
                          {i.status === "Open" ? (
                            <button onClick={() => resolveIssue(i.migration_issue_id)}
                                     data-testid={`btn-resolve-${i.migration_issue_id}`}
                                     className="text-[11px] text-emerald-700 hover:underline">Resolve</button>
                          ) : (
                            <button onClick={() => reopenIssue(i.migration_issue_id)}
                                     data-testid={`btn-reopen-${i.migration_issue_id}`}
                                     className="text-[11px] text-slate-500 hover:underline">Reopen</button>
                          )}
                        </td>
                      </tr>
                    ))}
                    {filteredIssues.length === 0 && (
                      <tr><td colSpan="6" className="px-3 py-6 text-center text-xs text-slate-500">
                        No issues match this filter.
                      </td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {tab === "Identifiers" && ident && (
            <div className="rounded-lg border border-slate-200 bg-white p-4" data-testid="ident-content">
              <div className="text-sm font-semibold mb-2">Driver Code</div>
              <div className="text-xs text-slate-700 space-y-1">
                <div>Valid: <b>{ident.driver_code.valid}</b></div>
                <div>Invalid / historical: <b>{ident.driver_code.invalid}</b></div>
                <div>Projected next live: <b>{ident.driver_code.projected_next_live}</b></div>
                <div className="text-slate-500">{ident.driver_code.notes}</div>
              </div>
              <div className="text-sm font-semibold mb-2 mt-4">Dispatch Number</div>
              <div className="text-xs text-slate-700 space-y-1">
                <div>Reserved hits: <b>{JSON.stringify(ident.dispatch_number.reserved_hits)}</b></div>
                <div>Reserved permanent: <b>{JSON.stringify(ident.dispatch_number.reserved_permanent)}</b></div>
                <div>Active proposals: <b>{ident.dispatch_number.active_proposals.length}</b></div>
                <div className="text-slate-500">{ident.dispatch_number.notes}</div>
              </div>
            </div>
          )}

          {tab === "Relationships" && rel && (
            <Notes data={rel} testid="rel-content"/>
          )}
          {tab === "Compliance" && comp && (
            <Notes data={comp} testid="comp-content"/>
          )}
          {tab === "Activation" && act && (
            <div className="space-y-3" data-testid="act-content">
              {(act.preview || []).map((p, idx) => (
                <div key={idx} className="rounded border border-slate-200 bg-white p-3 text-xs">
                  <div>Row #{p.source_row_number} → <b>{p.projected_activation_status}</b> / <b>{p.projected_readiness_status}</b></div>
                  {p.projected_blocking_items?.length > 0 && (
                    <div className="text-rose-700">Blockers: {p.projected_blocking_items.join(", ")}</div>
                  )}
                  <div className="text-[10px] text-slate-500 italic mt-1">{p.notes}</div>
                </div>
              ))}
              {(!act.preview || act.preview.length === 0) && (
                <div className="text-xs text-slate-500">No Driver-target rows in this dry run.</div>
              )}
            </div>
          )}
          {tab === "Documents" && docs && (
            <Notes data={docs} testid="docs-content"/>
          )}
          {tab === "Rollback" && rollback && (
            <div className="rounded-lg border border-slate-200 bg-white p-4" data-testid="rollback-content">
              <div className="text-sm font-semibold mb-2">Rollback preview (not applied)</div>
              <div className="text-xs text-slate-700 space-y-1">
                <div>Would create field: <b>{rollback.would_create_field_count}</b></div>
                <div>Would update field: <b>{rollback.would_update_field_count}</b></div>
                <div>Deterministic: <b>{String(rollback.deterministic)}</b></div>
                <div>Applied: <b className="text-emerald-700">{String(rollback.applied)}</b></div>
                <div className="text-slate-500">{rollback.notes}</div>
              </div>
            </div>
          )}
          {tab === "Go / No-Go" && (
            <div className="space-y-4" data-testid="gng-content">
              {!gng && (
                <div className="rounded-lg border border-slate-200 bg-white p-4">
                  <button onClick={computeGng} data-testid="btn-compute-gng"
                           className="rounded-md bg-slate-900 hover:bg-slate-800 text-white px-3 py-1.5 text-xs font-medium">
                    Compute Go / No-Go
                  </button>
                </div>
              )}
              {gng && (
                <div className={`rounded-lg border px-4 py-4 ${
                  gng.result === "GO" ? "border-emerald-200 bg-emerald-50"
                    : gng.result === "CONDITIONAL GO" ? "border-amber-200 bg-amber-50"
                    : "border-rose-200 bg-rose-50"}`}>
                  <div className={`text-lg font-bold ${
                    gng.result === "GO" ? "text-emerald-800"
                      : gng.result === "CONDITIONAL GO" ? "text-amber-800"
                      : "text-rose-800"}`} data-testid="gng-result">{gng.result}</div>
                  <div className="text-xs text-slate-700 mt-2 space-y-1">
                    <div>Open blocking issues: <b>{gng.open_blocking_issue_count}</b></div>
                    <div>Critical issues: <b>{gng.critical_issue_count}</b></div>
                    <div>Warning issues: <b>{gng.warning_issue_count}</b></div>
                    <div>Profiles approved: <b>{String(gng.approved_profiles_ok)}</b></div>
                    <div>Rollback ready: <b>{String(gng.rollback_ready)}</b></div>
                    <div>Approval status: <b>{gng.approval_status}</b></div>
                  </div>
                  {gng.result !== "NO-GO" && gng.approval_status === "Pending" && (
                    <div className="mt-3 flex gap-2">
                      <button onClick={() => decideGng("approve")} data-testid="btn-gng-approve"
                               className="rounded-md bg-emerald-600 hover:bg-emerald-700 text-white px-3 py-1.5 text-xs font-medium">
                        Approve readiness
                      </button>
                      <button onClick={() => decideGng("reject")} data-testid="btn-gng-reject"
                               className="rounded-md bg-slate-200 hover:bg-slate-300 text-slate-800 px-3 py-1.5 text-xs font-medium">
                        Reject
                      </button>
                    </div>
                  )}
                  <button onClick={computeGng} data-testid="btn-recompute-gng"
                           className="text-[11px] text-cyan-700 hover:underline mt-3">Recompute</button>
                </div>
              )}
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-[11px] text-slate-600" data-testid="no-commit-notice">
                <b>No commit endpoint exists in EB-12.</b> Approving readiness records intent only; the real migration is performed by the explicit EB-13 commit step which is not implemented here.
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}


function Card({ label, value, tone = "slate", testid }) {
  const t = { slate: "text-slate-700", ok: "text-emerald-700",
              warn: "text-amber-700", bad: "text-rose-700" }[tone];
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3" data-testid={testid}>
      <div className="text-[10px] uppercase tracking-[0.14em] text-slate-500">{label}</div>
      <div className={`text-2xl font-semibold ${t}`}>{value}</div>
    </div>
  );
}

function TableView({ data, cols, testid }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white overflow-x-auto" data-testid={testid}>
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50 text-left text-[10px] uppercase tracking-[0.14em] text-slate-500">
          <tr>{cols.map(([_, l]) => <th key={l} className="px-3 py-2">{l}</th>)}</tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {data.slice(0, 200).map((row, idx) => (
            <tr key={idx}>
              {cols.map(([k]) => <td key={k} className="px-3 py-2 text-xs">
                {typeof row[k] === "object" ? JSON.stringify(row[k]) : String(row[k] ?? "—")}
              </td>)}
            </tr>
          ))}
          {data.length === 0 && <tr><td colSpan={cols.length} className="px-3 py-6 text-center text-xs text-slate-500">No data.</td></tr>}
          {data.length > 200 && <tr><td colSpan={cols.length} className="px-3 py-2 text-[10px] text-slate-500 italic">Showing first 200 of {data.length}. Full data available via API.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function Notes({ data, testid }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 text-xs text-slate-700" data-testid={testid}>
      <div className="text-[11px] text-slate-500 italic mb-2">{data.notes}</div>
      <pre className="text-[11px] whitespace-pre-wrap max-h-96 overflow-auto">{JSON.stringify(data, null, 2)}</pre>
    </div>
  );
}
