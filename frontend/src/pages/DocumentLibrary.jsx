import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import AppHeader from "../components/app/AppHeader";
import api, { formatApiErrorDetail } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { toast } from "sonner";
import {
  Plus,
  MagnifyingGlass,
  X,
  Archive,
  ArrowClockwise,
  Eye,
  Download,
  UploadSimple,
  Warning,
  ClockCounterClockwise,
  ArrowUpRight,
} from "@phosphor-icons/react";

const DOCUMENT_TYPES = [
  "Driver Licence", "Vehicle Registration", "Vehicle Insurance", "Vehicle Inspection",
  "Vehicle Defect", "Vehicle Maintenance", "Equipment Compliance", "Driver Contract",
  "Driver Pass", "Profile Photo", "Supporting Document", "Other",
];

const ENTITY_TYPES = [
  "Driver", "Owner", "Vehicle", "Equipment", "DriverLicence", "VehicleRegistration",
  "VehicleInsurancePolicy", "VehicleInspection", "VehicleDefect", "VehicleMaintenanceTask",
  "EquipmentCompliance", "General",
];

const REL_TYPES = ["Evidence", "Contract", "Identification", "Photo", "Supporting", "Generated Export", "Other"];
const SENSITIVITIES = ["Standard", "Internal", "Confidential", "Restricted"];
const STATUSES = ["Active", "Superseded", "Under Review", "Rejected", "Archived", "Quarantined"];

const STATUS_STYLES = {
  Active: "bg-emerald-50 text-emerald-700 border-emerald-200",
  Superseded: "bg-slate-100 text-slate-500 border-slate-200",
  "Under Review": "bg-blue-50 text-blue-700 border-blue-200",
  Rejected: "bg-red-50 text-red-700 border-red-200",
  Archived: "bg-slate-100 text-slate-500 border-slate-200",
  Quarantined: "bg-amber-50 text-amber-700 border-amber-200",
};

const SENS_STYLES = {
  Standard: "bg-slate-100 text-slate-600 border-slate-200",
  Internal: "bg-cyan-50 text-cyan-700 border-cyan-200",
  Confidential: "bg-amber-50 text-amber-700 border-amber-200",
  Restricted: "bg-red-50 text-red-700 border-red-200",
};

function humanBytes(n) {
  if (!n) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}

export default function DocumentLibrary() {
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [sensitivityFilter, setSensitivityFilter] = useState("all");
  const [showArchived, setShowArchived] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [preview, setPreview] = useState(null);
  const [versionsOf, setVersionsOf] = useState(null);
  const [searchParams, setSearchParams] = useSearchParams();

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (typeFilter !== "all") params.document_type = typeFilter;
      if (statusFilter !== "all") params.status = statusFilter;
      if (sensitivityFilter !== "all") params.sensitivity = sensitivityFilter;
      if (showArchived) params.include_archived = true;
      const { data } = await api.get("/documents", { params });
      setItems(data || []);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally {
      setLoading(false);
    }
  }, [typeFilter, statusFilter, sensitivityFilter, showArchived]);

  useEffect(() => { refresh(); }, [refresh]);

  // Deep-link support: /documents?doc=<id> auto-opens the preview modal
  useEffect(() => {
    const docId = searchParams.get("doc");
    if (!docId || loading || !items.length) return;
    if (preview?.id === docId) return;
    const target = items.find((d) => d.id === docId);
    if (target) {
      setPreview(target);
      // Clear the query so back-nav doesn't re-open it
      const next = new URLSearchParams(searchParams);
      next.delete("doc");
      setSearchParams(next, { replace: true });
    }
  }, [searchParams, items, loading, preview, setSearchParams]);

  const filtered = useMemo(() => {
    if (!search.trim()) return items;
    const q = search.toLowerCase();
    return items.filter((d) => [
      d.title, d.description, d.document_type, d.category,
      d.uploaded_by, d.original_filename,
    ].filter(Boolean).some((v) => String(v).toLowerCase().includes(q)));
  }, [items, search]);

  const canUpload = user && ["Admin", "Manager", "Allocator", "Compliance"].includes(user.role);
  const canArchive = user && ["Admin", "Manager"].includes(user.role);

  const archive = async (d) => {
    if (!window.confirm(`Archive "${d.title}"?`)) return;
    try { await api.delete(`/documents/${d.id}`); toast.success("Archived"); refresh(); }
    catch (e) { toast.error(formatApiErrorDetail(e?.response?.data?.detail)); }
  };
  const restore = async (d) => {
    try { await api.post(`/documents/${d.id}/restore`); toast.success("Restored"); refresh(); }
    catch (e) { toast.error(formatApiErrorDetail(e?.response?.data?.detail)); }
  };

  const download = async (d) => {
    try {
      const res = await api.get(`/documents/${d.id}/download`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = d.original_filename || d.title;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Download failed");
    }
  };

  return (
    <div className="min-h-screen bg-slate-50" data-testid="document-library-page">
      <AppHeader showBack />
      <main className="max-w-[1600px] mx-auto w-full px-6 lg:px-12 py-6">
        <section className="mb-5 flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4">
          <div>
            <div className="text-[10px] uppercase tracking-[0.25em] text-cyan-600 mb-1 flex items-center gap-2">
              <span className="inline-flex h-1.5 w-1.5 rounded-full bg-cyan-500" />
              Documents &amp; Evidence
            </div>
            <h1 className="font-display text-2xl lg:text-3xl font-semibold tracking-tight text-slate-900 leading-tight">
              Document Library
              <span className="ml-3 text-sm text-slate-500 font-normal" data-testid="document-count">
                {loading ? "…" : `${filtered.length} / ${items.length}`}
              </span>
            </h1>
            <p className="mt-1.5 text-sm text-slate-500 max-w-xl leading-snug">
              Canonical evidence store — every file is versioned, private, and linked back to a master record.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <div className="relative w-48">
              <MagnifyingGlass size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text" value={search} onChange={(e) => setSearch(e.target.value)}
                placeholder="Search title, filename…"
                data-testid="document-search"
                className="w-full pl-9 pr-3 py-2.5 text-sm border border-slate-200 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-cyan-500/20 focus:border-cyan-500"
              />
            </div>
            <FilterSelect value={typeFilter} onChange={setTypeFilter} options={["all", ...DOCUMENT_TYPES]} label="all types" testid="filter-type" />
            <FilterSelect value={statusFilter} onChange={setStatusFilter} options={["all", ...STATUSES]} label="all statuses" testid="filter-status" />
            <FilterSelect value={sensitivityFilter} onChange={setSensitivityFilter} options={["all", ...SENSITIVITIES]} label="all sensitivity" testid="filter-sensitivity" />
            <label className="inline-flex items-center gap-2 text-xs text-slate-600 cursor-pointer select-none">
              <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} data-testid="filter-archived" className="rounded" />
              Show archived
            </label>
            {canUpload && (
              <button
                onClick={() => setUploadOpen(true)}
                data-testid="document-upload-button"
                className="inline-flex items-center gap-2 bg-slate-900 text-white hover:bg-slate-800 rounded-lg px-4 py-2.5 text-sm font-medium"
              >
                <UploadSimple size={16} weight="bold" />
                Upload
              </button>
            )}
          </div>
        </section>

        <section className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
          <div className="px-6 py-3 border-b border-slate-200 flex items-center justify-between text-xs text-slate-500">
            <div className="uppercase tracking-[0.2em] font-semibold">Documents</div>
            <div className="text-[11px]">{loading ? "Loading…" : `${filtered.length} shown`}</div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="document-table">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200">
                  {["Title", "Type", "Version", "Status", "Sensitivity", "Uploaded", "Size", ""].map((h) => (
                    <th key={h} className="text-left px-6 py-3 text-[10px] uppercase tracking-[0.2em] font-semibold text-slate-500">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {loading && (
                  <tr><td colSpan={8} className="px-6 py-14 text-center text-sm text-slate-400" data-testid="document-loading">Loading…</td></tr>
                )}
                {!loading && filtered.length === 0 && (
                  <tr><td colSpan={8} className="px-6 py-14 text-center text-sm text-slate-500" data-testid="document-empty">No documents match this filter.</td></tr>
                )}
                {!loading && filtered.map((d) => (
                  <tr key={d.id} className={`border-b border-slate-100 last:border-0 hover:bg-slate-50 transition-colors ${d.is_archived ? "opacity-60" : ""}`} data-testid={`document-row-${d.id}`}>
                    <td className="px-6 py-3.5">
                      <div className="font-medium text-slate-900">{d.title}</div>
                      <div className="text-[11px] text-slate-500 truncate max-w-[240px]">{d.display_filename || d.original_filename}</div>
                    </td>
                    <td className="px-6 py-3.5 text-slate-700">{d.document_type}</td>
                    <td className="px-6 py-3.5 text-slate-700">
                      <button onClick={() => setVersionsOf(d)} className="inline-flex items-center gap-1 text-cyan-700 hover:underline" data-testid={`document-versions-${d.id}`}>
                        <ClockCounterClockwise size={14} /> history
                      </button>
                    </td>
                    <td className="px-6 py-3.5">
                      <span className={`inline-flex items-center text-[11px] font-medium uppercase tracking-[0.15em] px-2.5 py-0.5 rounded-full border ${STATUS_STYLES[d.status] || ""}`}>{d.status}</span>
                    </td>
                    <td className="px-6 py-3.5">
                      <span className={`inline-flex items-center text-[11px] font-medium uppercase tracking-[0.15em] px-2.5 py-0.5 rounded-full border ${SENS_STYLES[d.sensitivity] || ""}`}>{d.sensitivity}</span>
                    </td>
                    <td className="px-6 py-3.5 text-slate-600 text-xs">
                      <div>{d.uploaded_at ? new Date(d.uploaded_at).toLocaleDateString() : "—"}</div>
                      <div className="text-[10px] text-slate-400">{d.uploaded_by}</div>
                    </td>
                    <td className="px-6 py-3.5 text-slate-600 text-xs">{humanBytes(d.file_size_bytes)}</td>
                    <td className="px-6 py-3.5 text-right">
                      <div className="inline-flex items-center gap-1">
                        <button title="Preview" onClick={() => setPreview(d)} data-testid={`document-preview-${d.id}`} className="p-1.5 rounded-md text-slate-400 hover:text-slate-900 hover:bg-slate-100">
                          <Eye size={14} />
                        </button>
                        <button title="Download" onClick={() => download(d)} data-testid={`document-download-${d.id}`} className="p-1.5 rounded-md text-slate-400 hover:text-cyan-700 hover:bg-cyan-50">
                          <Download size={14} />
                        </button>
                        {canArchive && !d.is_archived && (
                          <button title="Archive" onClick={() => archive(d)} data-testid={`document-archive-${d.id}`} className="p-1.5 rounded-md text-slate-400 hover:text-red-600 hover:bg-red-50">
                            <Archive size={14} />
                          </button>
                        )}
                        {canArchive && d.is_archived && (
                          <button title="Restore" onClick={() => restore(d)} data-testid={`document-restore-${d.id}`} className="p-1.5 rounded-md text-slate-400 hover:text-emerald-600 hover:bg-emerald-50">
                            <ArrowClockwise size={14} />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </main>

      {uploadOpen && <UploadDialog onClose={() => setUploadOpen(false)} onDone={() => { setUploadOpen(false); refresh(); }} />}
      {preview && <PreviewModal doc={preview} onClose={() => setPreview(null)} />}
      {versionsOf && <VersionsDialog doc={versionsOf} onClose={() => setVersionsOf(null)} onRefresh={refresh} canUpload={canUpload} />}
    </div>
  );
}

function FilterSelect({ value, onChange, options, label, testid }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} data-testid={testid}
      className="border border-slate-200 rounded-lg px-3 py-2.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-cyan-500/20">
      {options.map((o) => <option key={o} value={o}>{o === "all" ? label : o}</option>)}
    </select>
  );
}

// ---------------------------------------------------------------- Upload dialog
function UploadDialog({ onClose, onDone }) {
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [drag, setDrag] = useState(false);
  const [form, setForm] = useState({
    title: "", document_type: "Supporting Document", category: "", description: "",
    sensitivity: "", entity_type: "", entity_id: "", relationship_type: "Evidence", is_primary: false,
  });
  const [drivers, setDrivers] = useState([]);
  const [vehicles, setVehicles] = useState([]);
  const [equipment, setEquipment] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.allSettled([api.get("/drivers"), api.get("/vehicles"), api.get("/equipment")]).then(([d, v, e]) => {
      if (d.status === "fulfilled") setDrivers(d.value.data || []);
      if (v.status === "fulfilled") setVehicles(v.value.data || []);
      if (e.status === "fulfilled") setEquipment(e.value.data || []);
    });
  }, []);

  const pickFile = (f) => {
    if (!f) return;
    if (f.size > 15 * 1024 * 1024) { setError("File exceeds 15MB"); return; }
    setError(null);
    setFile(f);
    if (!form.title) setForm((p) => ({ ...p, title: f.name.replace(/\.[^.]+$/, "") }));
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!file) { setError("Choose a file"); return; }
    if (!form.title.trim()) { setError("Title required"); return; }
    const fd = new FormData();
    fd.append("file", file);
    fd.append("title", form.title.trim());
    fd.append("document_type", form.document_type);
    if (form.category) fd.append("category", form.category);
    if (form.description) fd.append("description", form.description);
    if (form.sensitivity) fd.append("sensitivity", form.sensitivity);
    if (form.entity_type && form.entity_id) {
      fd.append("entity_type", form.entity_type);
      fd.append("entity_id", form.entity_id);
      fd.append("relationship_type", form.relationship_type);
      fd.append("is_primary", form.is_primary ? "true" : "false");
    }
    setSubmitting(true);
    setError(null);
    try {
      await api.post("/documents/upload", fd, {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (evt) => {
          if (evt.total) setProgress(Math.round((evt.loaded * 100) / evt.total));
        },
      });
      toast.success("Uploaded");
      onDone();
    } catch (e) {
      setError(formatApiErrorDetail(e?.response?.data?.detail) || "Upload failed");
    } finally {
      setSubmitting(false);
      setProgress(0);
    }
  };

  const entityItems = form.entity_type === "Driver" ? drivers
    : form.entity_type === "Vehicle" ? vehicles
    : form.entity_type === "Equipment" ? equipment
    : [];

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-end sm:items-center justify-center p-0 sm:p-6" data-testid="document-upload-dialog" onClick={onClose}>
      <div className="bg-white w-full sm:max-w-xl rounded-t-2xl sm:rounded-2xl shadow-xl border border-slate-200 max-h-[92vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="px-6 py-5 border-b border-slate-200 flex items-center justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.25em] text-slate-500 mb-1">Upload</div>
            <div className="font-display font-semibold text-slate-900">New Document</div>
          </div>
          <button onClick={onClose} className="p-2 text-slate-400 hover:text-slate-900 rounded-md hover:bg-slate-100"><X size={18} /></button>
        </div>
        <form onSubmit={submit} className="px-6 py-5 space-y-4 overflow-y-auto">
          <div
            onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); pickFile(e.dataTransfer.files?.[0]); }}
            onClick={() => inputRef.current?.click()}
            data-testid="document-upload-drop"
            className={`border-2 border-dashed rounded-xl px-6 py-8 text-center cursor-pointer transition-colors ${
              drag ? "border-cyan-500 bg-cyan-50" : "border-slate-300 hover:border-cyan-400"
            }`}
          >
            <UploadSimple size={28} className="mx-auto mb-2 text-slate-400" />
            {file ? (
              <div>
                <div className="font-medium text-slate-900 text-sm">{file.name}</div>
                <div className="text-[11px] text-slate-500">{humanBytes(file.size)}</div>
              </div>
            ) : (
              <div className="text-sm text-slate-500">Drop a file here or click to pick</div>
            )}
            <input ref={inputRef} type="file" hidden data-testid="document-upload-file" onChange={(e) => pickFile(e.target.files?.[0])}
              accept=".pdf,.jpg,.jpeg,.png,.webp,.doc,.docx,.xls,.xlsx,.csv" />
          </div>

          <Field label="Title" required>
            <input type="text" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} data-testid="document-field-title"
              className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm" />
          </Field>
          <Field label="Document Type" required>
            <select value={form.document_type} onChange={(e) => setForm({ ...form, document_type: e.target.value })} data-testid="document-field-type"
              className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm bg-white">
              {DOCUMENT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </Field>
          <Field label="Sensitivity">
            <select value={form.sensitivity} onChange={(e) => setForm({ ...form, sensitivity: e.target.value })} data-testid="document-field-sensitivity"
              className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm bg-white">
              <option value="">Default for this type</option>
              {SENSITIVITIES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </Field>
          <Field label="Category">
            <input type="text" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} data-testid="document-field-category"
              className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm" />
          </Field>
          <Field label="Description">
            <input type="text" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} data-testid="document-field-description"
              className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm" />
          </Field>

          <div className="border-t border-slate-100 pt-4 space-y-3">
            <div className="text-[11px] uppercase tracking-[0.2em] font-semibold text-slate-500">Link to record (optional)</div>
            <div className="grid grid-cols-2 gap-3">
              <select value={form.entity_type} onChange={(e) => setForm({ ...form, entity_type: e.target.value, entity_id: "" })} data-testid="document-field-entity-type"
                className="border border-slate-200 rounded-lg px-3 py-2.5 text-sm bg-white">
                <option value="">— entity —</option>
                {ENTITY_TYPES.map((e) => <option key={e} value={e}>{e}</option>)}
              </select>
              {["Driver", "Vehicle", "Equipment"].includes(form.entity_type) ? (
                <select value={form.entity_id} onChange={(e) => setForm({ ...form, entity_id: e.target.value })} data-testid="document-field-entity-id"
                  className="border border-slate-200 rounded-lg px-3 py-2.5 text-sm bg-white">
                  <option value="">— select —</option>
                  {entityItems.map((it) => (
                    <option key={it.id} value={it.id}>
                      {it.full_name || it.name || it.registration_number || it.equipment_number || it.id}
                    </option>
                  ))}
                </select>
              ) : (
                <input type="text" value={form.entity_id} onChange={(e) => setForm({ ...form, entity_id: e.target.value })}
                  placeholder="record id" data-testid="document-field-entity-id-text"
                  className="border border-slate-200 rounded-lg px-3 py-2.5 text-sm" disabled={!form.entity_type || form.entity_type === "General"} />
              )}
            </div>
            <div className="grid grid-cols-2 gap-3 items-center">
              <select value={form.relationship_type} onChange={(e) => setForm({ ...form, relationship_type: e.target.value })} data-testid="document-field-rel-type"
                className="border border-slate-200 rounded-lg px-3 py-2.5 text-sm bg-white" disabled={!form.entity_type}>
                {REL_TYPES.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
              <label className="inline-flex items-center gap-2 text-sm text-slate-600 cursor-pointer">
                <input type="checkbox" checked={form.is_primary} onChange={(e) => setForm({ ...form, is_primary: e.target.checked })} data-testid="document-field-primary"
                  disabled={!form.entity_type} />
                Primary evidence
              </label>
            </div>
          </div>

          {error && (
            <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2 flex items-center gap-2" data-testid="document-upload-error">
              <Warning size={14} weight="bold" /> {error}
            </div>
          )}
          {submitting && progress > 0 && (
            <div className="text-xs text-slate-500">Uploading… {progress}%</div>
          )}

          <div className="pt-2 flex items-center justify-end gap-3 border-t border-slate-100 mt-4 pt-4">
            <button type="button" onClick={onClose} className="text-sm text-slate-600 hover:text-slate-900 px-4 py-2.5 rounded-lg">Cancel</button>
            <button type="submit" disabled={submitting} data-testid="document-upload-submit"
              className="inline-flex items-center gap-2 bg-slate-900 text-white hover:bg-slate-800 rounded-lg px-5 py-2.5 text-sm font-medium disabled:opacity-60">
              {submitting ? "Uploading…" : "Upload"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function Field({ label, required, children }) {
  return (
    <div>
      <label className="block text-[11px] uppercase tracking-[0.2em] font-semibold text-slate-500 mb-2">
        {label}{required && <span className="text-red-500 ml-1">*</span>}
      </label>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------- Preview modal
function PreviewModal({ doc, onClose }) {
  const [url, setUrl] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    let alive = true;
    let objUrl = null;
    api.get(`/documents/${doc.id}/preview`, { responseType: "blob" })
      .then((res) => { if (!alive) return; objUrl = URL.createObjectURL(res.data); setUrl(objUrl); })
      .catch((e) => { if (alive) setError(formatApiErrorDetail(e?.response?.data?.detail) || "Preview not available"); });
    return () => { alive = false; if (objUrl) URL.revokeObjectURL(objUrl); };
  }, [doc.id]);

  const isImage = (doc.mime_type || "").startsWith("image/");
  return (
    <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-6" data-testid="document-preview-modal" onClick={onClose}>
      <div className="bg-white w-full max-w-4xl max-h-[90vh] rounded-2xl shadow-xl border border-slate-200 flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.25em] text-slate-500 mb-1">{doc.document_type}</div>
            <div className="font-display font-semibold text-slate-900">{doc.title}</div>
          </div>
          <button onClick={onClose} className="p-2 text-slate-400 hover:text-slate-900 rounded-md hover:bg-slate-100"><X size={18} /></button>
        </div>
        <div className="flex-1 overflow-auto p-4 bg-slate-100">
          {error ? (
            <div className="text-center text-sm text-slate-500 py-16">{error}</div>
          ) : !url ? (
            <div className="text-center text-sm text-slate-400 py-16">Loading preview…</div>
          ) : isImage ? (
            <img src={url} alt={doc.title} className="max-w-full max-h-[70vh] mx-auto rounded-lg" />
          ) : (
            <iframe title={doc.title} src={url} className="w-full h-[70vh] bg-white rounded-lg border border-slate-200" />
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- Versions dialog
function VersionsDialog({ doc, onClose, onRefresh, canUpload }) {
  const [versions, setVersions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const inputRef = useRef(null);
  const [changeNote, setChangeNote] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/documents/${doc.id}/versions`);
      setVersions(data || []);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setLoading(false); }
  }, [doc.id]);

  useEffect(() => { load(); }, [load]);

  const uploadNew = async (f) => {
    if (!f) return;
    const fd = new FormData();
    fd.append("file", f);
    if (changeNote) fd.append("change_note", changeNote);
    setUploading(true);
    try {
      await api.post(`/documents/${doc.id}/versions`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success("New version uploaded");
      setChangeNote("");
      await load();
      onRefresh?.();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Version upload failed");
    } finally { setUploading(false); }
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-6" data-testid="document-versions-dialog" onClick={onClose}>
      <div className="bg-white w-full max-w-2xl max-h-[90vh] rounded-2xl shadow-xl border border-slate-200 flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.25em] text-slate-500 mb-1">Version history</div>
            <div className="font-display font-semibold text-slate-900">{doc.title}</div>
          </div>
          <button onClick={onClose} className="p-2 text-slate-400 hover:text-slate-900 rounded-md hover:bg-slate-100"><X size={18} /></button>
        </div>
        <div className="flex-1 overflow-auto p-6 space-y-2">
          {loading && <div className="text-sm text-slate-400 py-6 text-center">Loading…</div>}
          {!loading && versions.map((v) => (
            <div key={v.id} className={`flex items-center justify-between border rounded-lg px-4 py-3 ${v.is_current ? "border-cyan-300 bg-cyan-50/30" : "border-slate-200"}`}>
              <div>
                <div className="text-sm font-medium text-slate-900">v{v.version_number} {v.is_current && <span className="text-[10px] uppercase tracking-[0.15em] text-cyan-700 ml-1">current</span>}</div>
                <div className="text-[11px] text-slate-500">{v.change_note || "—"} · {humanBytes(v.file_size_bytes)}</div>
                <div className="text-[10px] text-slate-400">{v.uploaded_by} · {new Date(v.uploaded_at).toLocaleString()}</div>
              </div>
              <div className="flex items-center gap-1">
                <a
                  href={`/#/${v.id}`}
                  onClick={async (e) => {
                    e.preventDefault();
                    try {
                      const res = await api.get(`/documents/${doc.id}/versions/${v.id}/download`, { responseType: "blob" });
                      const url = URL.createObjectURL(res.data);
                      const a = document.createElement("a");
                      a.href = url; a.download = v.original_filename || `v${v.version_number}`; a.click();
                      URL.revokeObjectURL(url);
                    } catch (err) { toast.error("Download failed"); }
                  }}
                  className="p-1.5 rounded-md text-slate-400 hover:text-cyan-700 hover:bg-cyan-50"
                  title="Download"
                >
                  <Download size={14} />
                </a>
              </div>
            </div>
          ))}
        </div>
        {canUpload && (
          <div className="border-t border-slate-100 px-6 py-4 space-y-2">
            <input type="text" value={changeNote} onChange={(e) => setChangeNote(e.target.value)} placeholder="Optional change note"
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" data-testid="document-version-change-note" />
            <input ref={inputRef} type="file" hidden onChange={(e) => uploadNew(e.target.files?.[0])} data-testid="document-version-file"
              accept=".pdf,.jpg,.jpeg,.png,.webp,.doc,.docx,.xls,.xlsx,.csv" />
            <button
              onClick={() => inputRef.current?.click()}
              disabled={uploading}
              data-testid="document-new-version-button"
              className="w-full inline-flex items-center justify-center gap-2 bg-slate-900 text-white hover:bg-slate-800 rounded-lg px-4 py-2.5 text-sm font-medium disabled:opacity-60"
            >
              <Plus size={14} weight="bold" />
              {uploading ? "Uploading…" : "Upload new version"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
