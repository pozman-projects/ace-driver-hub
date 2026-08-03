import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { ArrowLeft, CheckCircle, Copy, Archive } from "@phosphor-icons/react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api/migration-prep`;
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem("ace_token")}` } });

const TARGETS = ["Driver", "Owner", "Vehicle", "Equipment",
                  "DriverOwnerRelationship", "DriverVehicleAssignment",
                  "DriverEquipmentAssignment", "DriverLicence", "VehicleRegistration",
                  "VehicleInsurance", "VehicleInspection", "VehicleDefect",
                  "VehicleMaintenance", "EquipmentCompliance", "Document"];


export default function MigrationMappingsPage() {
  const [profiles, setProfiles] = useState([]);
  const [wbs, setWbs] = useState([]);
  const [form, setForm] = useState({ name: "", migration_source_workbook_id: "",
                                     target_entity_type: "Driver" });

  const load = async () => {
    try {
      const [p, w] = await Promise.all([
        axios.get(`${API}/mapping-profiles`, auth()),
        axios.get(`${API}/workbooks`, auth()),
      ]);
      setProfiles(p.data || []);
      setWbs(w.data || []);
    } catch (err) {
      toast.error(`Load failed: ${err.response?.data?.detail || err.message}`);
    }
  };
  useEffect(() => { load(); }, []);

  const create = async () => {
    if (!form.name || !form.migration_source_workbook_id) {
      toast.error("Name and workbook required"); return;
    }
    try {
      const r = await axios.post(`${API}/mapping-profiles`, form, auth());
      toast.success(`Profile v${r.data.profile_version} created`);
      setForm({ name: "", migration_source_workbook_id: "", target_entity_type: "Driver" });
      load();
    } catch (err) {
      toast.error(`Create failed: ${err.response?.data?.detail || err.message}`);
    }
  };

  const approve = async (id) => {
    try {
      await axios.post(`${API}/mapping-profiles/${id}/approve`, {}, auth());
      toast.success("Approved");
      load();
    } catch (err) {
      toast.error(`Approve failed: ${err.response?.data?.detail || err.message}`);
    }
  };

  const clone = async (id) => {
    try {
      const r = await axios.post(`${API}/mapping-profiles/${id}/clone`, {}, auth());
      toast.success(`Cloned to v${r.data.profile_version}`);
      load();
    } catch (err) {
      toast.error(`Clone failed: ${err.response?.data?.detail || err.message}`);
    }
  };

  const archive = async (id) => {
    if (!window.confirm("Archive this profile?")) return;
    try {
      await axios.post(`${API}/mapping-profiles/${id}/archive`, {}, auth());
      toast.success("Archived");
      load();
    } catch (err) {
      toast.error(`Archive failed: ${err.response?.data?.detail || err.message}`);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900" data-testid="mappings-page">
      <div className="max-w-6xl mx-auto px-6 py-8">
        <Link to="/migration-preparation" data-testid="btn-back-hub"
              className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-800 mb-2">
          <ArrowLeft size={12} /> Back to Migration Hub
        </Link>
        <h1 className="text-2xl font-bold tracking-tight">Mapping Profiles</h1>

        <div className="mt-6 rounded-lg border border-slate-200 bg-white p-4">
          <div className="text-sm font-semibold mb-3">Create new profile</div>
          <div className="grid md:grid-cols-4 gap-3 text-sm">
            <input placeholder="Profile name *" data-testid="input-profile-name"
                    className="border border-slate-200 rounded-md px-2 py-1.5"
                    value={form.name}
                    onChange={e => setForm({ ...form, name: e.target.value })}/>
            <select className="border border-slate-200 rounded-md px-2 py-1.5"
                    data-testid="select-workbook"
                    value={form.migration_source_workbook_id}
                    onChange={e => setForm({ ...form, migration_source_workbook_id: e.target.value })}>
              <option value="">Select workbook…</option>
              {wbs.map(w => <option key={w.migration_source_workbook_id} value={w.migration_source_workbook_id}>
                {w.display_name || w.original_file_name}
              </option>)}
            </select>
            <select className="border border-slate-200 rounded-md px-2 py-1.5"
                    data-testid="select-target"
                    value={form.target_entity_type}
                    onChange={e => setForm({ ...form, target_entity_type: e.target.value })}>
              {TARGETS.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
            <button onClick={create} data-testid="btn-create-profile"
                     className="rounded-md bg-slate-900 hover:bg-slate-800 text-white px-3 py-1.5 text-xs font-medium">
              Create profile
            </button>
          </div>
        </div>

        <div className="mt-6 rounded-lg border border-slate-200 bg-white overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-sm" data-testid="profiles-table">
            <thead className="bg-slate-50 text-left text-[10px] uppercase tracking-[0.14em] text-slate-500">
              <tr>
                <th className="px-3 py-2">Name</th>
                <th className="px-3 py-2">Target</th>
                <th className="px-3 py-2">Version</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Updated</th>
                <th className="px-3 py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {profiles.map(p => (
                <tr key={p.migration_mapping_profile_id}
                    data-testid={`row-profile-${p.migration_mapping_profile_id}`}>
                  <td className="px-3 py-2 font-medium">{p.name}</td>
                  <td className="px-3 py-2 text-xs">{p.target_entity_type}</td>
                  <td className="px-3 py-2 text-xs">v{p.profile_version}</td>
                  <td className="px-3 py-2">
                    <span className={`text-[10px] uppercase tracking-[0.14em] px-1.5 py-0.5 rounded-full ${
                      p.status === "Approved" ? "bg-emerald-100 text-emerald-800"
                        : p.status === "Superseded" ? "bg-slate-100 text-slate-500"
                        : "bg-amber-100 text-amber-800"}`}>{p.status}</span>
                  </td>
                  <td className="px-3 py-2 text-[10px] text-slate-500">{(p.updated_at || "").slice(0, 16).replace("T", " ")}</td>
                  <td className="px-3 py-2 text-right">
                    <div className="inline-flex gap-1.5">
                      {p.status !== "Approved" && (
                        <button onClick={() => approve(p.migration_mapping_profile_id)}
                                 data-testid={`btn-approve-${p.migration_mapping_profile_id}`}
                                 className="text-[11px] text-emerald-700 hover:underline inline-flex items-center gap-1">
                          <CheckCircle size={11} /> Approve
                        </button>
                      )}
                      <button onClick={() => clone(p.migration_mapping_profile_id)}
                               data-testid={`btn-clone-${p.migration_mapping_profile_id}`}
                               className="text-[11px] text-cyan-700 hover:underline inline-flex items-center gap-1">
                        <Copy size={11} /> Clone
                      </button>
                      <button onClick={() => archive(p.migration_mapping_profile_id)}
                               data-testid={`btn-archive-${p.migration_mapping_profile_id}`}
                               className="text-[11px] text-slate-500 hover:text-rose-700 inline-flex items-center gap-1">
                        <Archive size={11} /> Archive
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {profiles.length === 0 && (
                <tr><td colSpan="6" className="px-3 py-6 text-center text-xs text-slate-500">
                  No mapping profiles yet.
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
