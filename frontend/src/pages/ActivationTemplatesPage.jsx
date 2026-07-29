/**
 * EB-10 · Activation Templates admin — /administration/activation-templates
 */
import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import AppHeader from "../components/app/AppHeader";
import api, { formatApiErrorDetail } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Copy, Archive as ArchiveIcon, PencilSimple, Plus } from "@phosphor-icons/react";

export default function ActivationTemplatesPage() {
  const { user } = useAuth();
  const canManage = ["Admin", "Manager"].includes(user?.role);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: "", driver_type: "Employee Driver", company_ref: "ACE", is_default: false });

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/activation/templates");
      setRows(data);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Load failed");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const create = async () => {
    if (!form.name.trim()) { toast.error("Name required"); return; }
    try {
      await api.post("/activation/templates", form);
      setCreating(false);
      setForm({ name: "", driver_type: "Employee Driver", company_ref: "ACE", is_default: false });
      toast.success("Template created");
      await refresh();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Create failed");
    }
  };
  const clone = async (id) => {
    try { await api.post(`/activation/templates/${id}/clone`); toast.success("Cloned"); await refresh(); }
    catch (e) { toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Clone failed"); }
  };
  const archive = async (id) => {
    if (!window.confirm("Archive template?")) return;
    try { await api.delete(`/activation/templates/${id}`); toast.success("Archived"); await refresh(); }
    catch (e) { toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Archive failed"); }
  };

  return (
    <div className="min-h-screen bg-slate-50" data-testid="templates-page">
      <AppHeader showBack />
      <main className="max-w-6xl mx-auto px-4 lg:px-8 py-6">
        <div className="flex items-center justify-between mb-6">
          <h1 className="font-display text-2xl font-semibold text-slate-900">Activation Templates</h1>
          {canManage && (
            <button data-testid="template-create" onClick={() => setCreating(!creating)} className="text-xs px-3 py-1.5 rounded bg-slate-900 text-white hover:bg-slate-800 inline-flex items-center gap-1">
              <Plus size={12} weight="bold" /> New template
            </button>
          )}
        </div>
        {creating && (
          <div className="mb-4 bg-white border border-slate-200 rounded-lg p-4 space-y-2" data-testid="template-create-form">
            <input data-testid="template-name" placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm" />
            <div className="grid grid-cols-3 gap-2">
              <input data-testid="template-company" placeholder="Company" value={form.company_ref} onChange={(e) => setForm({ ...form, company_ref: e.target.value })} className="border border-slate-200 rounded px-2 py-1.5 text-sm" />
              <select data-testid="template-driver-type" value={form.driver_type} onChange={(e) => setForm({ ...form, driver_type: e.target.value })} className="border border-slate-200 rounded px-2 py-1.5 text-sm">
                {["Employee Driver", "Contractor Driver", "Owner Driver", "Relief Driver", "Trainee Driver", "Other"].map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
              <label className="flex items-center gap-2 text-xs text-slate-700">
                <input data-testid="template-default" type="checkbox" checked={form.is_default} onChange={(e) => setForm({ ...form, is_default: e.target.checked })} /> Default
              </label>
            </div>
            <div className="flex items-center gap-2">
              <button data-testid="template-save" onClick={create} className="text-xs px-3 py-1.5 rounded bg-slate-900 text-white hover:bg-slate-800">Save</button>
              <button onClick={() => setCreating(false)} className="text-xs px-3 py-1.5 rounded text-slate-600 hover:text-slate-900">Cancel</button>
            </div>
          </div>
        )}
        {loading ? (
          <div className="text-slate-500 text-sm">Loading…</div>
        ) : (
          <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-[10px] uppercase tracking-[0.15em] text-slate-500">
                <tr>
                  <th className="px-3 py-2 text-left">Name</th>
                  <th className="px-3 py-2 text-left">Driver type</th>
                  <th className="px-3 py-2 text-left">Company</th>
                  <th className="px-3 py-2 text-right">Version</th>
                  <th className="px-3 py-2 text-right">Items</th>
                  <th className="px-3 py-2 text-right">Mandatory</th>
                  <th className="px-3 py-2 text-center">Default</th>
                  <th className="px-3 py-2 text-center">Active</th>
                  <th className="px-3 py-2 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((t) => (
                  <tr key={t.activation_template_id} data-testid={`template-row-${t.activation_template_id}`} className="border-t border-slate-100">
                    <td className="px-3 py-2 font-medium text-slate-800">{t.name}</td>
                    <td className="px-3 py-2 text-slate-600">{t.driver_type}</td>
                    <td className="px-3 py-2 text-slate-600">{t.company_ref}</td>
                    <td className="px-3 py-2 text-right font-mono">v{t.version}</td>
                    <td className="px-3 py-2 text-right">{t.item_count}</td>
                    <td className="px-3 py-2 text-right">{t.mandatory_count}</td>
                    <td className="px-3 py-2 text-center">{t.is_default ? <span className="inline-block text-[9px] uppercase tracking-[0.15em] border border-emerald-200 bg-emerald-50 text-emerald-700 rounded-full px-1.5">Default</span> : "—"}</td>
                    <td className="px-3 py-2 text-center">{t.is_active && !t.is_archived ? "Yes" : t.is_archived ? "Archived" : "No"}</td>
                    <td className="px-3 py-2 text-right space-x-2">
                      {canManage && !t.is_archived && (
                        <>
                          <button data-testid={`template-clone-${t.activation_template_id}`} onClick={() => clone(t.activation_template_id)} className="text-[11px] px-2 py-1 rounded border border-slate-200 text-slate-700 hover:bg-slate-50 inline-flex items-center gap-1"><Copy size={11} /> Clone</button>
                          <button data-testid={`template-archive-${t.activation_template_id}`} onClick={() => archive(t.activation_template_id)} className="text-[11px] px-2 py-1 rounded border border-red-200 text-red-700 hover:bg-red-50 inline-flex items-center gap-1"><ArchiveIcon size={11} /> Archive</button>
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}
