import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import AppHeader from "../components/app/AppHeader";
import api, { formatApiErrorDetail } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { toast } from "sonner";
import {
  UploadSimple, X, CheckCircle, Warning, ArrowClockwise, ArrowCounterClockwise, Files, Play,
  ArrowLeft, ArrowRight, ClipboardText,
} from "@phosphor-icons/react";

const STAGES = [
  { key: "upload", label: "Upload" },
  { key: "sheet", label: "Sheet" },
  { key: "map", label: "Map" },
  { key: "validate", label: "Validate" },
  { key: "conflicts", label: "Conflicts" },
  { key: "commit", label: "Commit" },
];

export default function ImportWizard() {
  const { jobId } = useParams();
  const { user } = useAuth();
  const nav = useNavigate();
  const [job, setJob] = useState(null);
  const [template, setTemplate] = useState(null);
  const [sheetInfo, setSheetInfo] = useState(null);
  const [rows, setRows] = useState([]);
  const [conflicts, setConflicts] = useState([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  const stage = useMemo(() => {
    if (!job) return "upload";
    if (!job.source_file_id) return "upload";
    if (!job.sheet_name) return "sheet";
    if (!job.mapping_id) return "map";
    if (["Ready for Validation", "Validating"].includes(job.status)) return "validate";
    if (["Validation Failed"].includes(job.status)) return "conflicts";
    if (["Ready to Commit", "Committing", "Committed", "Partially Committed", "Commit Failed", "Rolled Back"].includes(job.status)) return "commit";
    return "validate";
  }, [job]);

  const refresh = useCallback(async () => {
    try {
      const { data } = await api.get(`/imports/${jobId}`);
      setJob(data);
      const t = await api.get(`/import-templates/${data.target_domain}`);
      setTemplate(t.data);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setLoading(false); }
  }, [jobId]);
  useEffect(() => { refresh(); }, [refresh]);

  const canWrite = user && ["Admin", "Manager", "Compliance", "Allocator"].includes(user.role);
  const canRollback = user && ["Admin", "Manager"].includes(user.role);

  if (loading) return <div className="min-h-screen bg-slate-50"><AppHeader showBack /><div className="p-10 text-center text-slate-400">Loading…</div></div>;
  if (!job) return null;

  return (
    <div className="min-h-screen bg-slate-50" data-testid="import-wizard-page">
      <AppHeader showBack />
      <main className="max-w-[1600px] mx-auto w-full px-6 lg:px-12 py-6">
        <section className="mb-5">
          <div className="text-[10px] uppercase tracking-[0.25em] text-cyan-600 mb-1 flex items-center gap-2">
            <span className="inline-flex h-1.5 w-1.5 rounded-full bg-cyan-500" />
            <Link to="/imports" className="hover:text-cyan-800">Import Centre</Link>
          </div>
          <h1 className="font-display text-2xl lg:text-3xl font-semibold tracking-tight text-slate-900 leading-tight capitalize">
            {template?.label || job.target_domain}
            <span className="ml-3 text-xs text-slate-500 font-normal">{job.mode} · {job.status}</span>
          </h1>
        </section>

        {/* Stepper */}
        <section className="mb-6 flex items-center gap-2 flex-wrap" data-testid="import-stepper">
          {STAGES.map((s, i) => {
            const active = s.key === stage;
            const idxCur = STAGES.findIndex((x) => x.key === stage);
            const done = i < idxCur;
            return (
              <div key={s.key} className="flex items-center gap-2">
                <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium ${
                  active ? "bg-slate-900 text-white" : done ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                    : "bg-white text-slate-500 border border-slate-200"
                }`} data-testid={`stepper-${s.key}`}>
                  <span className="inline-flex h-4 w-4 rounded-full items-center justify-center text-[10px] font-semibold border">
                    {done ? "✓" : i + 1}
                  </span>
                  {s.label}
                </div>
                {i < STAGES.length - 1 && <ArrowRight size={12} className="text-slate-300" />}
              </div>
            );
          })}
        </section>

        {stage === "upload" && <StageUpload job={job} onDone={refresh} canWrite={canWrite} />}
        {stage === "sheet" && <StageSheet job={job} onDone={refresh} sheetInfo={sheetInfo} setSheetInfo={setSheetInfo} />}
        {stage === "map" && <StageMap job={job} template={template} onDone={refresh} />}
        {stage === "validate" && <StageValidate job={job} onDone={refresh} />}
        {stage === "conflicts" && <StageConflicts job={job} onRefresh={refresh} />}
        {stage === "commit" && <StageCommit job={job} onRefresh={refresh} canRollback={canRollback} />}
      </main>
    </div>
  );
}

// ---------------------------------------------------------------- Stage: Upload
function StageUpload({ job, onDone, canWrite }) {
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const submit = async () => {
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    setBusy(true); setError(null);
    try {
      await api.post(`/imports/${job.id}/file`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success("File uploaded");
      onDone();
    } catch (e) {
      setError(formatApiErrorDetail(e?.response?.data?.detail) || "Upload failed");
    } finally { setBusy(false); }
  };
  return (
    <Panel title="Step 2 · Upload spreadsheet" description="Supported: .xlsx, .xlsm, .csv (max 20MB). Macros are never executed.">
      <div onClick={() => inputRef.current?.click()} data-testid="wizard-upload-drop"
        className="border-2 border-dashed border-slate-300 hover:border-cyan-400 rounded-xl px-6 py-10 text-center cursor-pointer">
        <UploadSimple size={28} className="mx-auto mb-2 text-slate-400" />
        {file ? <div className="text-sm text-slate-900 font-medium">{file.name}</div>
          : <div className="text-sm text-slate-500">Drop or click to choose a spreadsheet</div>}
        <input ref={inputRef} type="file" hidden accept=".xlsx,.xlsm,.csv" data-testid="wizard-upload-input"
          onChange={(e) => setFile(e.target.files?.[0] || null)} />
      </div>
      {error && <ErrorLine text={error} />}
      <div className="flex justify-end mt-4">
        <button onClick={submit} disabled={!file || !canWrite || busy} data-testid="wizard-upload-submit"
          className="inline-flex items-center gap-2 bg-slate-900 text-white hover:bg-slate-800 rounded-lg px-5 py-2.5 text-sm font-medium disabled:opacity-60">
          {busy ? "Uploading…" : "Upload"} <ArrowRight size={14} weight="bold" />
        </button>
      </div>
    </Panel>
  );
}

// ---------------------------------------------------------------- Stage: Sheet
function StageSheet({ job, onDone, sheetInfo, setSheetInfo }) {
  const [selected, setSelected] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    setError(null);
    api.get(`/imports/${job.id}/sheets`)
      .then(({ data }) => setSheetInfo(data))
      .catch((e) => setError(formatApiErrorDetail(e?.response?.data?.detail)));
  }, [job.id, setSheetInfo]);

  const choose = async () => {
    if (!selected) return;
    setBusy(true);
    try {
      await api.post(`/imports/${job.id}/inspect`, { sheet_name: selected });
      toast.success("Sheet selected");
      onDone();
    } catch (e) {
      setError(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setBusy(false); }
  };

  return (
    <Panel title="Step 3 · Select sheet" description="Choose the sheet containing your source data.">
      {!sheetInfo ? <div className="text-sm text-slate-400 py-6 text-center">Inspecting…</div> : (
        <div className="space-y-2" data-testid="wizard-sheet-list">
          {sheetInfo.sheets.map((s) => (
            <label key={s.name} className={`flex items-center gap-3 border rounded-lg px-4 py-3 cursor-pointer ${
              selected === s.name ? "border-cyan-500 bg-cyan-50/40" : "border-slate-200 hover:border-slate-400"
            }`} data-testid={`wizard-sheet-${s.name}`}>
              <input type="radio" name="sheet" value={s.name} checked={selected === s.name} onChange={() => setSelected(s.name)} />
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-slate-900">{s.name}{s.hidden && <span className="ml-2 text-[10px] uppercase tracking-[0.15em] text-amber-700 bg-amber-50 border border-amber-200 rounded px-1.5 py-0.5">hidden</span>}</div>
                <div className="text-[11px] text-slate-500">{s.row_count} rows · {s.column_count} columns · headers: {s.headers.slice(0, 5).join(", ")}{s.headers.length > 5 ? "…" : ""}</div>
              </div>
            </label>
          ))}
        </div>
      )}
      {error && <ErrorLine text={error} />}
      <div className="flex justify-end mt-4">
        <button onClick={choose} disabled={!selected || busy} data-testid="wizard-sheet-submit"
          className="inline-flex items-center gap-2 bg-slate-900 text-white hover:bg-slate-800 rounded-lg px-5 py-2.5 text-sm font-medium disabled:opacity-60">
          {busy ? "Saving…" : "Use this sheet"} <ArrowRight size={14} weight="bold" />
        </button>
      </div>
    </Panel>
  );
}

// ---------------------------------------------------------------- Stage: Map
function StageMap({ job, template, onDone }) {
  const [headers, setHeaders] = useState([]);
  const [mapping, setMapping] = useState({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.get(`/imports/${job.id}/sheets`).then(({ data }) => {
      const s = data.sheets.find((x) => x.name === job.sheet_name);
      if (s) {
        setHeaders(s.headers);
        // Auto-guess: match header→field by lowercase substring similarity
        const auto = {};
        for (const h of s.headers) {
          const low = h.toLowerCase().replace(/[^a-z0-9]/g, "");
          const match = (template?.fields || []).find((f) => low.includes(f.key.replace(/_/g, "")) || low === f.label.toLowerCase().replace(/[^a-z0-9]/g, ""));
          if (match) auto[h] = match.key;
        }
        setMapping(auto);
      }
    });
  }, [job.id, job.sheet_name, template]);

  const save = async () => {
    setBusy(true); setError(null);
    try {
      await api.post(`/imports/${job.id}/mapping`, { field_mappings: mapping });
      toast.success("Mapping saved");
      onDone();
    } catch (e) {
      setError(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setBusy(false); }
  };

  return (
    <Panel title="Step 4 · Map columns" description="Match each source column to a canonical field. Leave blank to ignore.">
      <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500 mb-2">
        Required fields: {template?.required_fields?.join(", ") || "—"}
      </div>
      <div className="border border-slate-200 rounded-xl divide-y divide-slate-100" data-testid="wizard-mapping-list">
        {headers.map((h) => (
          <div key={h} className="grid grid-cols-2 gap-4 px-4 py-2.5 items-center">
            <div className="text-sm text-slate-900 font-medium truncate">{h}</div>
            <select value={mapping[h] || ""} onChange={(e) => setMapping({ ...mapping, [h]: e.target.value })}
              data-testid={`wizard-mapping-${h.replace(/[^a-z0-9]/gi, "-")}`}
              className="border border-slate-200 rounded-lg px-3 py-2 text-sm bg-white">
              <option value="">— ignore —</option>
              {(template?.fields || []).map((f) => (
                <option key={f.key} value={f.key}>
                  {f.label}{f.required ? " *" : ""}{f.unique ? " (unique)" : ""}
                </option>
              ))}
            </select>
          </div>
        ))}
      </div>
      {error && <ErrorLine text={error} />}
      <div className="flex justify-end mt-4">
        <button onClick={save} disabled={busy} data-testid="wizard-mapping-submit"
          className="inline-flex items-center gap-2 bg-slate-900 text-white hover:bg-slate-800 rounded-lg px-5 py-2.5 text-sm font-medium disabled:opacity-60">
          {busy ? "Saving…" : "Save mapping"} <ArrowRight size={14} weight="bold" />
        </button>
      </div>
    </Panel>
  );
}

// ---------------------------------------------------------------- Stage: Validate
function StageValidate({ job, onDone }) {
  const [busy, setBusy] = useState(false);
  const [summary, setSummary] = useState(null);
  const [rows, setRows] = useState([]);
  const [error, setError] = useState(null);

  const runValidate = async () => {
    setBusy(true); setError(null);
    try {
      await api.post(`/imports/${job.id}/validate`);
      const [s, r] = await Promise.all([
        api.get(`/imports/${job.id}/validation-summary`),
        api.get(`/imports/${job.id}/rows`, { params: { limit: 100 } }),
      ]);
      setSummary(s.data); setRows(r.data.rows);
      onDone();
    } catch (e) {
      setError(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setBusy(false); }
  };
  useEffect(() => { if (job.status === "Ready for Validation") runValidate(); }, []);   // eslint-disable-line
  useEffect(() => {
    if (["Ready to Commit", "Validation Failed"].includes(job.status)) {
      Promise.all([
        api.get(`/imports/${job.id}/validation-summary`),
        api.get(`/imports/${job.id}/rows`, { params: { limit: 100 } }),
      ]).then(([s, r]) => { setSummary(s.data); setRows(r.data.rows); }).catch(() => {});
    }
  }, [job]);

  return (
    <Panel title="Step 5 · Dry run" description="Every row is normalised, matched against canonical data, and checked for conflicts. No changes are written yet.">
      <div className="flex items-center justify-between mb-4">
        <button onClick={runValidate} disabled={busy} data-testid="wizard-validate-run"
          className="inline-flex items-center gap-2 bg-slate-900 text-white hover:bg-slate-800 rounded-lg px-4 py-2 text-sm font-medium disabled:opacity-60">
          <Play size={14} weight="bold" /> {busy ? "Validating…" : "Re-run validation"}
        </button>
        {summary && <div className="text-xs text-slate-500">{summary.rows} rows · {summary.blocking_unresolved} blocking</div>}
      </div>
      {error && <ErrorLine text={error} />}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-6 gap-2 mb-4 text-center" data-testid="wizard-validate-summary">
          {Object.entries(summary.by_action).map(([k, v]) => (
            <div key={k} className="border border-slate-200 rounded-lg px-3 py-2 bg-white">
              <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500">{k}</div>
              <div className="font-display text-xl font-semibold text-slate-900">{v}</div>
            </div>
          ))}
        </div>
      )}
      {rows.length > 0 && <RowTable rows={rows} />}
    </Panel>
  );
}

// ---------------------------------------------------------------- Stage: Conflicts
function StageConflicts({ job, onRefresh }) {
  const [conflicts, setConflicts] = useState([]);
  useEffect(() => {
    api.get(`/imports/${job.id}/conflicts`, { params: { include_resolved: true } })
      .then(({ data }) => setConflicts(data));
  }, [job.id]);
  const resolve = async (c, resolution) => {
    try {
      await api.put(`/import-conflicts/${c.id}`, { resolution });
      const { data } = await api.get(`/imports/${job.id}/conflicts`, { params: { include_resolved: true } });
      setConflicts(data);
      await onRefresh();
    } catch (e) { toast.error(formatApiErrorDetail(e?.response?.data?.detail)); }
  };
  const unresolved = conflicts.filter((c) => c.resolution === "Unresolved");
  return (
    <Panel title="Step 6 · Resolve conflicts" description="Blocking conflicts must be resolved before commit is allowed.">
      {conflicts.length === 0 ? <div className="text-sm text-slate-500 py-6 text-center">No conflicts detected. Continue to commit.</div> : (
        <div className="space-y-2" data-testid="wizard-conflicts-list">
          {conflicts.map((c) => (
            <div key={c.id} className={`border rounded-lg px-4 py-3 ${c.severity === "Blocking" ? "border-red-200 bg-red-50/40" : "border-amber-200 bg-amber-50/40"}`}>
              <div className="flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500">Row {c.import_row_id?.slice(0, 8)} · {c.conflict_type}</div>
                  <div className="text-sm text-slate-900 truncate"><b>{c.field_name}</b>: source “{JSON.stringify(c.source_value)}” vs existing “{JSON.stringify(c.existing_value)}”</div>
                  <div className="text-[11px] text-slate-500">{c.notes}</div>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`text-[10px] uppercase tracking-[0.15em] rounded-full px-2 py-0.5 border ${c.severity === "Blocking" ? "border-red-300 text-red-700" : "border-amber-300 text-amber-700"}`}>{c.severity}</span>
                  {c.resolution === "Unresolved" ? (
                    <>
                      <button onClick={() => resolve(c, "Skip Row")} data-testid={`conflict-skip-${c.id}`}
                        className="text-xs bg-white border border-slate-200 hover:border-slate-400 rounded px-2 py-1">Skip</button>
                      <button onClick={() => resolve(c, "Keep Existing Value")} data-testid={`conflict-keep-${c.id}`}
                        className="text-xs bg-white border border-slate-200 hover:border-slate-400 rounded px-2 py-1">Keep existing</button>
                      <button onClick={() => resolve(c, "Map to Existing Record")} data-testid={`conflict-map-${c.id}`}
                        className="text-xs bg-cyan-600 text-white hover:bg-cyan-700 rounded px-2 py-1">Map existing</button>
                    </>
                  ) : (
                    <span className="text-[11px] text-emerald-700">{c.resolution}</span>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
      <div className="mt-4 text-xs text-slate-500">{unresolved.filter((c) => c.severity === "Blocking").length} blocking unresolved</div>
    </Panel>
  );
}

// ---------------------------------------------------------------- Stage: Commit
function StageCommit({ job, onRefresh, canRollback }) {
  const [busy, setBusy] = useState(false);
  const [commits, setCommits] = useState([]);
  const [confirmOpen, setConfirmOpen] = useState(false);

  useEffect(() => {
    api.get(`/imports/${job.id}/commit-history`).then(({ data }) => setCommits(data)).catch(() => {});
  }, [job]);

  const commit = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/imports/${job.id}/commit`, {});
      toast.success(`Created ${data.created_count}, Updated ${data.updated_count}`);
      setConfirmOpen(false);
      await onRefresh();
      const h = await api.get(`/imports/${job.id}/commit-history`);
      setCommits(h.data);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setBusy(false); }
  };

  const rollback = async () => {
    if (!window.confirm("Rollback will archive newly-created records and revert updates where possible. Continue?")) return;
    setBusy(true);
    try {
      await api.post(`/imports/${job.id}/rollback`);
      toast.success("Rolled back");
      await onRefresh();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setBusy(false); }
  };

  const isReady = job.status === "Ready to Commit";
  const isCommitted = ["Committed", "Partially Committed"].includes(job.status);

  return (
    <Panel title="Step 7 · Commit" description="Review the summary carefully. Commit is explicit and audited.">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-6">
        <StatChip label="Rows" value={job.total_rows} />
        <StatChip label="Create" value={job.total_rows - (job.updated_rows + job.unchanged_rows + job.skipped_rows)} tone="green" />
        <StatChip label="Update" value={job.updated_rows || 0} tone="cyan" />
        <StatChip label="Skip" value={job.skipped_rows || 0} />
      </div>
      {isReady && (
        <div className="mt-2">
          <button onClick={() => setConfirmOpen(true)} disabled={busy} data-testid="wizard-commit-button"
            className="inline-flex items-center gap-2 bg-emerald-600 text-white hover:bg-emerald-700 rounded-lg px-5 py-2.5 text-sm font-medium disabled:opacity-60">
            <CheckCircle size={16} weight="bold" /> Commit import
          </button>
        </div>
      )}
      {isCommitted && commits.length > 0 && (
        <div className="mt-4 space-y-2" data-testid="wizard-commit-history">
          {commits.map((c) => (
            <div key={c.id} className="border border-slate-200 rounded-lg px-4 py-3">
              <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500">Commit #{c.commit_sequence} · {new Date(c.committed_at).toLocaleString()}</div>
              <div className="text-sm text-slate-800">Created <b className="text-emerald-700">{c.created_count}</b>, updated <b className="text-cyan-700">{c.updated_count}</b>, skipped {c.skipped_count}, failed {c.failed_count}</div>
              <div className="text-[10px] text-slate-400">by {c.committed_by}</div>
            </div>
          ))}
        </div>
      )}
      {isCommitted && canRollback && (
        <div className="mt-4">
          <button onClick={rollback} disabled={busy} data-testid="wizard-rollback-button"
            className="inline-flex items-center gap-2 bg-white border border-red-200 text-red-700 hover:bg-red-50 rounded-lg px-4 py-2 text-sm">
            <ArrowCounterClockwise size={14} weight="bold" /> Rollback this import
          </button>
        </div>
      )}
      {job.status === "Rolled Back" && (
        <div className="mt-4 text-sm text-slate-500 border border-slate-200 rounded-lg px-4 py-3 bg-slate-50">
          This import has been rolled back. Created records are archived; updates were reverted where possible.
        </div>
      )}
      {confirmOpen && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 flex items-center justify-center p-6" onClick={() => setConfirmOpen(false)} data-testid="wizard-commit-confirm">
          <div className="bg-white w-full max-w-md rounded-xl shadow-xl border border-slate-200 p-6" onClick={(e) => e.stopPropagation()}>
            <div className="font-display font-semibold text-slate-900 mb-1">Commit this import?</div>
            <div className="text-sm text-slate-500 mb-4">This will create canonical records. Rollback is available immediately after.</div>
            <div className="flex justify-end gap-3">
              <button onClick={() => setConfirmOpen(false)} className="text-sm text-slate-600 hover:text-slate-900 px-4 py-2 rounded-lg">Cancel</button>
              <button onClick={commit} disabled={busy} data-testid="wizard-commit-confirm-yes"
                className="bg-emerald-600 text-white hover:bg-emerald-700 rounded-lg px-5 py-2 text-sm font-medium disabled:opacity-60">
                {busy ? "Committing…" : "Yes, commit"}
              </button>
            </div>
          </div>
        </div>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------- helpers
function Panel({ title, description, children }) {
  return (
    <section className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
      <div className="text-[10px] uppercase tracking-[0.25em] text-slate-500 mb-1">{title}</div>
      <div className="text-sm text-slate-500 mb-4 max-w-2xl">{description}</div>
      {children}
    </section>
  );
}

function StatChip({ label, value, tone }) {
  const bg = tone === "green" ? "text-emerald-700" : tone === "cyan" ? "text-cyan-700" : "text-slate-700";
  return (
    <div className="border border-slate-200 rounded-lg px-3 py-2 bg-white">
      <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500">{label}</div>
      <div className={`font-display text-xl font-semibold ${bg}`}>{value ?? 0}</div>
    </div>
  );
}

function ErrorLine({ text }) {
  return (
    <div className="mt-3 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2 flex items-center gap-2">
      <Warning size={14} weight="bold" /> {text}
    </div>
  );
}

function RowTable({ rows }) {
  return (
    <div className="border border-slate-200 rounded-xl overflow-hidden mt-2" data-testid="wizard-rows-table">
      <div className="overflow-x-auto max-h-[420px]">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-200 sticky top-0">
              {["Row", "Status", "Match", "Action", "Normalised", "Errors / Warnings"].map((h) =>
                <th key={h} className="text-left px-4 py-2 text-[10px] uppercase tracking-[0.2em] font-semibold text-slate-500">{h}</th>
              )}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                <td className="px-4 py-2 text-slate-500">{r.row_number}</td>
                <td className="px-4 py-2">
                  <span className={`text-[10px] uppercase tracking-[0.15em] px-2 py-0.5 rounded-full border ${
                    r.validation_status === "Valid" ? "border-emerald-200 text-emerald-700"
                    : r.validation_status === "Warning" ? "border-amber-200 text-amber-700"
                    : r.validation_status === "Error" ? "border-red-200 text-red-700"
                    : "border-slate-200 text-slate-500"
                  }`}>{r.validation_status}</span>
                </td>
                <td className="px-4 py-2 text-slate-600">{r.match_status}</td>
                <td className="px-4 py-2 text-slate-900 font-medium">{r.action}</td>
                <td className="px-4 py-2 text-slate-600 truncate max-w-[280px]">{Object.entries(r.normalised_values || {}).map(([k, v]) => `${k}=${v}`).join(" · ")}</td>
                <td className="px-4 py-2 text-slate-600 max-w-[240px]">
                  {(r.errors || []).map((e, i) => <div key={i} className="text-red-700 text-[11px]">⨯ {e}</div>)}
                  {(r.warnings || []).map((w, i) => <div key={i} className="text-amber-700 text-[11px]">! {w}</div>)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
