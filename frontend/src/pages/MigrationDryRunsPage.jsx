import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { ArrowLeft, PlayCircle, ArrowClockwise, Archive } from "@phosphor-icons/react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api/migration-prep`;
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem("ace_token")}` } });


export default function MigrationDryRunsPage() {
  const nav = useNavigate();
  const [dryRuns, setDryRuns] = useState([]);
  const [profiles, setProfiles] = useState([]);
  const [wbs, setWbs] = useState([]);
  const [form, setForm] = useState({ name: "", profile_id: "", workbook_id: "" });
  const [busy, setBusy] = useState({});

  const load = async () => {
    try {
      const [d, p, w] = await Promise.all([
        axios.get(`${API}/dry-runs`, auth()),
        axios.get(`${API}/mapping-profiles`, auth()),
        axios.get(`${API}/workbooks`, auth()),
      ]);
      setDryRuns(d.data || []); setProfiles(p.data || []); setWbs(w.data || []);
    } catch (err) {
      toast.error(`Load failed: ${err.response?.data?.detail || err.message}`);
    }
  };
  useEffect(() => { load(); }, []);

  const create = async () => {
    if (!form.name || !form.profile_id || !form.workbook_id) {
      toast.error("Name, profile, workbook required"); return;
    }
    try {
      const r = await axios.post(`${API}/dry-runs`, {
        name: form.name,
        mapping_profile_ids: [form.profile_id],
        source_workbook_ids: [form.workbook_id],
      }, auth());
      const drId = r.data.migration_dry_run_id;
      setBusy(b => ({ ...b, [drId]: true }));
      await axios.post(`${API}/dry-runs/${drId}/execute`, {}, auth());
      toast.success("Dry run executed");
      setForm({ name: "", profile_id: "", workbook_id: "" });
      load();
      setBusy(b => ({ ...b, [drId]: false }));
      nav(`/migration-preparation/dry-runs/${drId}`);
    } catch (err) {
      toast.error(`Dry run failed: ${err.response?.data?.detail || err.message}`);
    }
  };

  const rerun = async (id) => {
    setBusy(b => ({ ...b, [id]: true }));
    try {
      await axios.post(`${API}/dry-runs/${id}/rerun`, {}, auth());
      toast.success("Re-ran");
      load();
    } catch (err) {
      toast.error(`Rerun failed: ${err.response?.data?.detail || err.message}`);
    } finally { setBusy(b => ({ ...b, [id]: false })); }
  };

  const archive = async (id) => {
    if (!window.confirm("Archive this dry run?")) return;
    try {
      await axios.post(`${API}/dry-runs/${id}/archive`, {}, auth());
      toast.success("Archived");
      load();
    } catch (err) {
      toast.error(`Archive failed: ${err.response?.data?.detail || err.message}`);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900" data-testid="dry-runs-page">
      <div className="max-w-6xl mx-auto px-6 py-8">
        <Link to="/migration-preparation" data-testid="btn-back-hub"
              className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-800 mb-2">
          <ArrowLeft size={12} /> Back to Migration Hub
        </Link>
        <h1 className="text-2xl font-bold tracking-tight">Dry Runs</h1>

        <div className="mt-6 rounded-lg border border-slate-200 bg-white p-4">
          <div className="text-sm font-semibold mb-3">Create + execute dry run</div>
          <div className="grid md:grid-cols-4 gap-3 text-sm">
            <input placeholder="Dry run name *" data-testid="input-dr-name"
                    className="border border-slate-200 rounded-md px-2 py-1.5"
                    value={form.name}
                    onChange={e => setForm({ ...form, name: e.target.value })}/>
            <select className="border border-slate-200 rounded-md px-2 py-1.5"
                    data-testid="select-dr-profile"
                    value={form.profile_id}
                    onChange={e => setForm({ ...form, profile_id: e.target.value })}>
              <option value="">Mapping profile…</option>
              {profiles.map(p => <option key={p.migration_mapping_profile_id} value={p.migration_mapping_profile_id}>
                {p.name} · v{p.profile_version} · {p.status}
              </option>)}
            </select>
            <select className="border border-slate-200 rounded-md px-2 py-1.5"
                    data-testid="select-dr-workbook"
                    value={form.workbook_id}
                    onChange={e => setForm({ ...form, workbook_id: e.target.value })}>
              <option value="">Workbook…</option>
              {wbs.map(w => <option key={w.migration_source_workbook_id} value={w.migration_source_workbook_id}>
                {w.display_name || w.original_file_name}
              </option>)}
            </select>
            <button onClick={create} data-testid="btn-execute-dry-run"
                     className="rounded-md bg-slate-900 hover:bg-slate-800 text-white px-3 py-1.5 text-xs font-medium inline-flex items-center gap-1.5">
              <PlayCircle size={13} /> Execute dry run
            </button>
          </div>
        </div>

        <div className="mt-6 rounded-lg border border-slate-200 bg-white overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-sm" data-testid="dry-runs-table">
            <thead className="bg-slate-50 text-left text-[10px] uppercase tracking-[0.14em] text-slate-500">
              <tr>
                <th className="px-3 py-2">Name</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Rows</th>
                <th className="px-3 py-2">Valid / Warn / Block</th>
                <th className="px-3 py-2">Creates / Updates</th>
                <th className="px-3 py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {dryRuns.map(d => (
                <tr key={d.migration_dry_run_id}
                    data-testid={`row-dr-${d.migration_dry_run_id}`}>
                  <td className="px-3 py-2">
                    <Link to={`/migration-preparation/dry-runs/${d.migration_dry_run_id}`}
                          className="font-medium hover:underline">{d.name}</Link>
                    <div className="text-[10px] text-slate-500">{(d.completed_at || d.requested_at || "").slice(0, 16).replace("T", " ")} · {d.requested_by}</div>
                  </td>
                  <td className="px-3 py-2">
                    <span className={`text-[10px] uppercase tracking-[0.14em] px-1.5 py-0.5 rounded-full ${
                      d.status === "Preview Ready" ? "bg-emerald-100 text-emerald-800"
                        : d.status === "Failed" ? "bg-rose-100 text-rose-800"
                        : "bg-slate-100 text-slate-700"}`}>{d.status}</span>
                  </td>
                  <td className="px-3 py-2 text-xs">{d.row_count}</td>
                  <td className="px-3 py-2 text-xs">
                    <span className="text-emerald-700">{d.valid_row_count}</span> · <span className="text-amber-700">{d.warning_row_count}</span> · <span className="text-rose-700">{d.invalid_row_count}</span>
                  </td>
                  <td className="px-3 py-2 text-xs">{d.proposed_create_count} · {d.proposed_update_count}</td>
                  <td className="px-3 py-2 text-right">
                    <div className="inline-flex gap-1.5">
                      <button onClick={() => rerun(d.migration_dry_run_id)}
                               disabled={busy[d.migration_dry_run_id]}
                               data-testid={`btn-rerun-${d.migration_dry_run_id}`}
                               className="text-[11px] text-cyan-700 hover:underline disabled:opacity-50 inline-flex items-center gap-1">
                        <ArrowClockwise size={11} /> Rerun
                      </button>
                      <button onClick={() => archive(d.migration_dry_run_id)}
                               data-testid={`btn-archive-dr-${d.migration_dry_run_id}`}
                               className="text-[11px] text-slate-500 hover:text-rose-700 inline-flex items-center gap-1">
                        <Archive size={11} /> Archive
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {dryRuns.length === 0 && (
                <tr><td colSpan="6" className="px-3 py-6 text-center text-xs text-slate-500">
                  No dry runs yet.
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
