/*
 * MR-08B-P3 · Canonical Report Builder page.
 *
 * V1 workflow: pick source → pick fields → filters → sort → run → export.
 * No PDF, no saved-report, no scheduling, no charts. Backend is the security
 * authority; this page mirrors role-filtered field metadata.
 */
import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem("ace_token")}` } });

export default function ReportBuilderPage() {
  const [sources, setSources] = useState([]);
  const [source, setSource] = useState("");
  const [fields, setFields] = useState([]);
  const [operators, setOperators] = useState({});
  const [selected, setSelected] = useState([]);
  const [filters, setFilters] = useState([]);
  const [sort, setSort] = useState([]);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [runError, setRunError] = useState(null);

  useEffect(() => {
    axios.get(`${API}/reports/sources`, auth()).then((r) => setSources(r.data || []))
      .catch((e) => toast.error(e.response?.data?.detail || e.message));
  }, []);

  useEffect(() => {
    if (!source) return;
    setSelected([]); setFilters([]); setSort([]); setPreview(null);
    axios.get(`${API}/reports/sources/${source}/fields`, auth())
      .then((r) => { setFields(r.data.fields || []); setOperators(r.data.operators || {}); })
      .catch((e) => toast.error(e.response?.data?.detail || e.message));
  }, [source]);

  const fieldByKey = useMemo(() => Object.fromEntries(fields.map((f) => [f.key, f])), [fields]);

  const toggleField = (key) => setSelected((prev) =>
    prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]);

  const runReport = async () => {
    setLoading(true); setRunError(null);
    try {
      const r = await axios.post(`${API}/reports/run`, {
        source, fields: selected, filters, sort, include_archived: includeArchived, limit: 200,
      }, auth());
      setPreview(r.data);
    } catch (e) {
      const detail = e.response?.data?.detail || e.message;
      setRunError(typeof detail === "string" ? detail : JSON.stringify(detail));
    } finally { setLoading(false); }
  };

  const doExport = async (format) => {
    try {
      const r = await axios.post(`${API}/reports/export/${format}`, {
        source, fields: selected, filters, sort, include_archived: includeArchived,
      }, auth());
      const eid = r.data.export?.id;
      if (!eid) throw new Error("Export id missing");
      // download via authenticated fetch → blob → link
      const dl = await axios.get(`${API}/reports/exports/${eid}/download`, {
        ...auth(), responseType: "blob",
      });
      const url = URL.createObjectURL(dl.data);
      const a = document.createElement("a");
      a.href = url; a.download = r.data.filename || `report.${format}`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error(e.response?.data?.detail || e.message);
    }
  };

  return (
    <div className="max-w-6xl mx-auto p-6" data-testid="report-builder-page">
      <Link to="/" className="text-slate-500 text-sm hover:text-slate-900" data-testid="rb-back">← Back to DCC</Link>
      <h1 className="text-2xl font-semibold text-slate-900 mt-2">Report Builder</h1>
      <p className="text-sm text-slate-600 mt-1 mb-6">
        Read canonical data across the 13 approved DCC domains. CSV or XLSX only. Sensitive fields and
        Restricted document metadata are enforced server-side.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="md:col-span-1 space-y-4">
          <div>
            <div className="text-[10px] uppercase tracking-[0.16em] text-slate-500 mb-1">1 · Data Source</div>
            <select value={source} onChange={(e) => setSource(e.target.value)}
                    data-testid="rb-source" className="w-full border border-slate-300 rounded px-2 py-1.5 text-sm">
              <option value="">Choose a source…</option>
              {sources.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
            </select>
          </div>

          {source && (
            <>
              <div>
                <div className="text-[10px] uppercase tracking-[0.16em] text-slate-500 mb-1 flex justify-between items-center">
                  <span>2 · Fields</span>
                  <button className="text-xs text-slate-600 underline"
                          onClick={() => setSelected(fields.map((f) => f.key))}
                          data-testid="rb-select-all">Select All</button>
                </div>
                <div className="border border-slate-200 rounded max-h-64 overflow-auto p-2">
                  {fields.map((f) => (
                    <label key={f.key} className="flex items-center gap-2 text-sm py-0.5"
                           data-testid={`rb-field-${f.key}`}>
                      <input type="checkbox" checked={selected.includes(f.key)}
                             onChange={() => toggleField(f.key)} />
                      <span>{f.label}</span>
                      <span className="text-[10px] text-slate-400 ml-auto">{f.type}</span>
                    </label>
                  ))}
                </div>
              </div>

              <div>
                <div className="text-[10px] uppercase tracking-[0.16em] text-slate-500 mb-1 flex justify-between items-center">
                  <span>3 · Filters</span>
                  <button className="text-xs text-slate-600 underline" data-testid="rb-add-filter"
                          onClick={() => setFilters([...filters, { field: fields[0]?.key || "", operator: "equals", value: "" }])}>
                    + Add
                  </button>
                </div>
                {filters.map((flt, i) => {
                  const f = fieldByKey[flt.field];
                  const ops = f ? (operators[f.type] || []) : [];
                  return (
                    <div key={i} className="flex items-center gap-1 mb-1" data-testid={`rb-filter-${i}`}>
                      <select className="text-xs border rounded px-1 py-1"
                              value={flt.field}
                              onChange={(e) => { const c = [...filters]; c[i].field = e.target.value; setFilters(c); }}>
                        {fields.map((f) => <option key={f.key} value={f.key}>{f.label}</option>)}
                      </select>
                      <select className="text-xs border rounded px-1 py-1"
                              value={flt.operator}
                              onChange={(e) => { const c = [...filters]; c[i].operator = e.target.value; setFilters(c); }}>
                        {ops.map((o) => <option key={o}>{o}</option>)}
                      </select>
                      <input className="flex-1 text-xs border rounded px-1 py-1"
                             value={flt.value ?? ""}
                             onChange={(e) => { const c = [...filters]; c[i].value = e.target.value; setFilters(c); }} />
                      <button className="text-xs text-rose-500"
                              onClick={() => setFilters(filters.filter((_, j) => j !== i))}>×</button>
                    </div>
                  );
                })}
              </div>

              <div>
                <div className="text-[10px] uppercase tracking-[0.16em] text-slate-500 mb-1 flex justify-between items-center">
                  <span>4 · Sort (max 2)</span>
                  <button className="text-xs text-slate-600 underline" data-testid="rb-add-sort"
                          onClick={() => sort.length < 2 && setSort([...sort, { field: fields[0]?.key || "", direction: "asc" }])}>
                    + Add
                  </button>
                </div>
                {sort.map((s, i) => (
                  <div key={i} className="flex items-center gap-1 mb-1" data-testid={`rb-sort-${i}`}>
                    <select className="text-xs border rounded px-1 py-1"
                            value={s.field}
                            onChange={(e) => { const c = [...sort]; c[i].field = e.target.value; setSort(c); }}>
                      {fields.filter((f) => f.sortable).map((f) => <option key={f.key} value={f.key}>{f.label}</option>)}
                    </select>
                    <select className="text-xs border rounded px-1 py-1"
                            value={s.direction}
                            onChange={(e) => { const c = [...sort]; c[i].direction = e.target.value; setSort(c); }}>
                      <option value="asc">Asc</option><option value="desc">Desc</option>
                    </select>
                    <button className="text-xs text-rose-500"
                            onClick={() => setSort(sort.filter((_, j) => j !== i))}>×</button>
                  </div>
                ))}
              </div>

              <label className="flex items-center gap-2 text-xs text-slate-600">
                <input type="checkbox" checked={includeArchived}
                       onChange={(e) => setIncludeArchived(e.target.checked)}
                       data-testid="rb-include-archived" />
                Include archived records
              </label>

              <div className="flex gap-2 pt-2">
                <button onClick={runReport} disabled={!selected.length || loading}
                        data-testid="rb-run"
                        className="text-sm px-3 py-1.5 bg-slate-900 text-white rounded hover:bg-slate-800 disabled:opacity-40">
                  {loading ? "Running…" : "Run Report"}
                </button>
                <button onClick={() => doExport("csv")} disabled={!preview}
                        data-testid="rb-export-csv"
                        className="text-sm px-3 py-1.5 border border-slate-300 rounded hover:bg-slate-50 disabled:opacity-40">CSV</button>
                <button onClick={() => doExport("xlsx")} disabled={!preview}
                        data-testid="rb-export-xlsx"
                        className="text-sm px-3 py-1.5 border border-slate-300 rounded hover:bg-slate-50 disabled:opacity-40">XLSX</button>
              </div>
            </>
          )}
        </div>

        <div className="md:col-span-2" data-testid="rb-preview">
          <div className="text-[10px] uppercase tracking-[0.16em] text-slate-500 mb-1">Preview</div>
          {runError && <div className="text-xs text-rose-700 bg-rose-50 border border-rose-200 rounded p-2 mb-2" data-testid="rb-error">{runError}</div>}
          {!preview && !runError && <div className="text-sm text-slate-500">Configure and run a report to see results.</div>}
          {preview && (
            <div className="border border-slate-200 rounded overflow-auto">
              <div className="text-[11px] text-slate-500 p-2 border-b border-slate-100">
                {preview.row_count} row{preview.row_count === 1 ? "" : "s"}
                {preview.truncated && " · truncated — export for full result"}
              </div>
              <table className="w-full text-xs" data-testid="rb-table">
                <thead>
                  <tr className="bg-slate-50">
                    {preview.fields.map((f) => (
                      <th key={f.key} className="text-left px-2 py-1 border-b border-slate-100">{f.label}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {preview.rows.map((row, i) => (
                    <tr key={i} className="odd:bg-white even:bg-slate-50/40">
                      {preview.fields.map((f) => (
                        <td key={f.key} className="px-2 py-1 border-b border-slate-100">{row[f.key] ?? ""}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
