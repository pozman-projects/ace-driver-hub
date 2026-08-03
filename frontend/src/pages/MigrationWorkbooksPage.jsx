import React, { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { ArrowLeft, FileArrowUp, Archive } from "@phosphor-icons/react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api/migration-prep`;
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem("ace_token")}` } });


export default function MigrationWorkbooksPage() {
  const [wbs, setWbs] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [form, setForm] = useState({
    profile_name: "", display_name: "", source_system: "",
    business_owner: "", data_domain: "Driver", authority_level: "Authoritative",
    expected_frequency: "one-off",
  });
  const fileRef = useRef();

  const load = async () => {
    try {
      const r = await axios.get(`${API}/workbooks`, auth());
      setWbs(r.data || []);
    } catch (err) {
      toast.error(`Load failed: ${err.response?.data?.detail || err.message}`);
    }
  };

  useEffect(() => { load(); }, []);

  const upload = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file) { toast.error("Choose an .xlsx or .csv file first"); return; }
    if (!form.profile_name) { toast.error("Profile name required"); return; }
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      Object.entries(form).forEach(([k, v]) => fd.append(k, v));
      await axios.post(`${API}/workbooks/profile`, fd, {
        ...auth(),
        headers: { ...auth().headers, "Content-Type": "multipart/form-data" },
      });
      toast.success(`Workbook profiled — ${file.name}`);
      setForm({ ...form, profile_name: "" });
      if (fileRef.current) fileRef.current.value = "";
      load();
    } catch (err) {
      toast.error(`Upload failed: ${err.response?.data?.detail || err.message}`);
    } finally { setUploading(false); }
  };

  const archive = async (id) => {
    if (!window.confirm("Archive this workbook?")) return;
    try {
      await axios.post(`${API}/workbooks/${id}/archive`, {}, auth());
      toast.success("Archived");
      load();
    } catch (err) {
      toast.error(`Archive failed: ${err.response?.data?.detail || err.message}`);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900" data-testid="workbooks-page">
      <div className="max-w-6xl mx-auto px-6 py-8">
        <Link to="/migration-preparation" data-testid="btn-back-hub"
              className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-800 mb-2">
          <ArrowLeft size={12} /> Back to Migration Hub
        </Link>
        <h1 className="text-2xl font-bold tracking-tight">Source Workbook Inventory</h1>
        <p className="text-sm text-slate-600 mt-1">Sanitised development workbooks only. Real ACE data must not be uploaded here.</p>

        <div className="mt-6 rounded-lg border border-slate-200 bg-white p-4" data-testid="upload-form">
          <div className="text-sm font-semibold mb-3">Upload sanitised workbook</div>
          <div className="grid md:grid-cols-3 gap-3 text-sm">
            <input placeholder="Profile name *" data-testid="input-profile-name"
                    className="border border-slate-200 rounded-md px-2 py-1.5 text-sm"
                    value={form.profile_name}
                    onChange={e => setForm({ ...form, profile_name: e.target.value })}/>
            <input placeholder="Display name"
                    className="border border-slate-200 rounded-md px-2 py-1.5 text-sm"
                    value={form.display_name}
                    onChange={e => setForm({ ...form, display_name: e.target.value })}/>
            <select className="border border-slate-200 rounded-md px-2 py-1.5 text-sm"
                    data-testid="select-authority"
                    value={form.authority_level}
                    onChange={e => setForm({ ...form, authority_level: e.target.value })}>
              {["Authoritative", "Supporting", "Historical", "Reference Only", "Unknown"]
                .map(v => <option key={v} value={v}>{v}</option>)}
            </select>
            <input placeholder="Source system (e.g. Sanitised fixture)"
                    className="border border-slate-200 rounded-md px-2 py-1.5 text-sm"
                    value={form.source_system}
                    onChange={e => setForm({ ...form, source_system: e.target.value })}/>
            <input placeholder="Business owner"
                    className="border border-slate-200 rounded-md px-2 py-1.5 text-sm"
                    value={form.business_owner}
                    onChange={e => setForm({ ...form, business_owner: e.target.value })}/>
            <select className="border border-slate-200 rounded-md px-2 py-1.5 text-sm"
                    value={form.data_domain}
                    onChange={e => setForm({ ...form, data_domain: e.target.value })}>
              {["Driver", "Owner", "Vehicle", "Equipment", "Relationship", "Compliance", "Document"]
                .map(v => <option key={v} value={v}>{v}</option>)}
            </select>
            <input ref={fileRef} type="file" accept=".xlsx,.csv" data-testid="input-file"
                    className="text-xs md:col-span-2 border border-slate-200 rounded-md px-2 py-1.5"/>
            <button onClick={upload} disabled={uploading}
                     data-testid="btn-upload-workbook"
                     className="rounded-md bg-slate-900 hover:bg-slate-800 disabled:opacity-50 text-white px-3 py-1.5 text-xs font-medium inline-flex items-center gap-1.5">
              <FileArrowUp size={13} /> {uploading ? "Uploading…" : "Profile workbook"}
            </button>
          </div>
        </div>

        <div className="mt-6 rounded-lg border border-slate-200 bg-white overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-sm" data-testid="workbooks-table">
            <thead className="bg-slate-50 text-left text-[10px] uppercase tracking-[0.14em] text-slate-500">
              <tr>
                <th className="px-3 py-2">Name</th>
                <th className="px-3 py-2">Authority</th>
                <th className="px-3 py-2">Sheets</th>
                <th className="px-3 py-2">Checksum</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {wbs.map(w => (
                <tr key={w.migration_source_workbook_id}
                    data-testid={`row-wb-${w.migration_source_workbook_id}`}>
                  <td className="px-3 py-2">
                    <div className="font-medium">{w.display_name || w.original_file_name}</div>
                    <div className="text-[10px] text-slate-500">{w.source_system} · {w.uploaded_by}</div>
                  </td>
                  <td className="px-3 py-2 text-xs">{w.authority_level}</td>
                  <td className="px-3 py-2 text-xs">{w.detected_sheet_count}</td>
                  <td className="px-3 py-2 font-mono text-[10px] text-slate-500">{w.file_sha256?.slice(0, 12)}…</td>
                  <td className="px-3 py-2">
                    <span className="text-[10px] uppercase tracking-[0.14em] px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-700">
                      {w.status}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button onClick={() => archive(w.migration_source_workbook_id)}
                             data-testid={`btn-archive-wb-${w.migration_source_workbook_id}`}
                             className="text-[11px] text-slate-500 hover:text-rose-700 inline-flex items-center gap-1">
                      <Archive size={11} /> Archive
                    </button>
                  </td>
                </tr>
              ))}
              {wbs.length === 0 && (
                <tr><td colSpan="6" className="px-3 py-6 text-center text-xs text-slate-500">
                  No workbooks profiled yet. Upload a sanitised .xlsx or .csv to begin.
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
