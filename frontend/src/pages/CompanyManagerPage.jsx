/*
 * MR-08B-P2 · Canonical Company Manager page.
 *
 * Frontend visibility mirror only — backend `role_matrix.CAN_MANAGE_COMPANY`
 * (Admin/Manager) is the security authority. Compliance / Allocator / ReadOnly
 * see the list but not the mutation controls.
 *
 * The page is intentionally minimalist: list, create, edit, archive, set
 * default. No branding, no theme, no skin — those belong to later MR-08B
 * packages.
 */
import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import {
  Buildings,
  CaretLeft,
  PencilSimple,
  Archive,
  Star,
  Plus,
  X,
} from "@phosphor-icons/react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem("ace_token")}` } });
const MANAGE_ROLES = new Set(["Admin", "Manager"]);

export default function CompanyManagerPage() {
  const role = localStorage.getItem("ace_role") || "";
  const canManage = MANAGE_ROLES.has(role);

  const [companies, setCompanies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [draftName, setDraftName] = useState("");

  const reload = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/companies?include_archived=true`, auth());
      setCompanies(r.data || []);
    } catch (err) {
      toast.error(`Could not load Companies: ${err.response?.data?.detail || err.message}`);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { reload(); }, []);

  const active = useMemo(() => companies.filter((c) => !c.is_archived), [companies]);
  const archived = useMemo(() => companies.filter((c) => c.is_archived), [companies]);

  const create = async () => {
    const name = (draftName || "").trim();
    if (!name) { toast.error("Company name is required"); return; }
    try {
      await axios.post(`${API}/companies`, { name }, auth());
      toast.success(`Company '${name}' created`);
      setShowCreate(false); setDraftName("");
      reload();
    } catch (err) {
      toast.error(err.response?.data?.detail || err.message);
    }
  };

  const rename = async (company) => {
    const name = (draftName || "").trim();
    if (!name) { toast.error("Company name is required"); return; }
    try {
      await axios.put(`${API}/companies/${company.id}`, { name }, auth());
      toast.success(`Company renamed`);
      setEditingId(null); setDraftName("");
      reload();
    } catch (err) {
      toast.error(err.response?.data?.detail || err.message);
    }
  };

  const archive = async (company) => {
    if (company.is_default) {
      toast.error("Set another Company as Default before archiving this one.");
      return;
    }
    if (!window.confirm(`Archive '${company.name}'? Existing records referencing this Company are preserved. It will no longer be selectable for new records.`)) return;
    try {
      await axios.delete(`${API}/companies/${company.id}`, auth());
      toast.success("Company archived");
      reload();
    } catch (err) {
      const d = err.response?.data?.detail;
      const msg = typeof d === "string" ? d : (d?.message || err.message);
      toast.error(msg);
    }
  };

  const setDefault = async (company) => {
    if (!window.confirm(`Set '${company.name}' as the Default Company for new records? Existing records are not changed.`)) return;
    try {
      await axios.put(`${API}/settings/default-company`, { company_id: company.id }, auth());
      toast.success(`Default Company set to '${company.name}'`);
      reload();
    } catch (err) {
      toast.error(err.response?.data?.detail || err.message);
    }
  };

  return (
    <div className="max-w-4xl mx-auto p-6" data-testid="company-manager-page">
      <div className="flex items-center gap-3 mb-4">
        <Link to="/" className="text-slate-500 hover:text-slate-900 inline-flex items-center gap-1 text-sm" data-testid="company-back">
          <CaretLeft size={14} /> Back to DCC
        </Link>
      </div>
      <div className="flex items-start justify-between mb-6">
        <div>
          <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.24em] text-slate-500">
            <Buildings size={12} /> Administration
          </div>
          <h1 className="text-2xl font-semibold text-slate-900 mt-1">Company Manager</h1>
          <p className="text-sm text-slate-600 mt-1 max-w-2xl">
            Canonical Company records. Default Company is applied to <b>new records only</b> — existing records are never
            rewritten. Company Administration is limited to Admin and Manager roles.
          </p>
        </div>
        {canManage && (
          <button
            onClick={() => { setShowCreate(true); setDraftName(""); }}
            data-testid="btn-create-company"
            className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-md bg-slate-900 text-white hover:bg-slate-800"
          >
            <Plus size={12} /> New Company
          </button>
        )}
      </div>

      {loading ? (
        <div className="text-sm text-slate-500" data-testid="company-loading">Loading…</div>
      ) : (
        <>
          <section data-testid="company-list-active" className="mb-6">
            <div className="text-[10px] uppercase tracking-[0.18em] text-slate-500 mb-2">Active</div>
            <div className="rounded-md border border-slate-200 divide-y divide-slate-100">
              {active.length === 0 && (
                <div className="p-4 text-sm text-slate-500" data-testid="company-empty">
                  No active Companies. Create one to enable Default Company.
                </div>
              )}
              {active.map((c) => (
                <div key={c.id} data-testid={`company-row-${c.id}`}
                     className="flex items-center gap-3 px-4 py-3">
                  <div className="flex-1 min-w-0">
                    {editingId === c.id ? (
                      <div className="flex items-center gap-2">
                        <input
                          value={draftName}
                          onChange={(e) => setDraftName(e.target.value)}
                          data-testid={`edit-company-name-${c.id}`}
                          className="flex-1 border border-slate-300 rounded px-2 py-1 text-sm"
                        />
                        <button onClick={() => rename(c)}
                                data-testid={`save-company-${c.id}`}
                                className="text-xs px-2 py-1 bg-emerald-600 text-white rounded">
                          Save
                        </button>
                        <button onClick={() => { setEditingId(null); setDraftName(""); }}
                                className="text-xs px-2 py-1 bg-slate-200 rounded">
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <div>
                        <div className="font-medium text-slate-900 text-sm inline-flex items-center gap-2"
                             data-testid={`company-name-${c.id}`}>
                          {c.name}
                          {c.is_default && (
                            <span data-testid={`default-badge-${c.id}`}
                                   className="text-[9.5px] uppercase tracking-[0.14em] px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-800 inline-flex items-center gap-1">
                              <Star size={9} weight="fill" /> Default
                            </span>
                          )}
                        </div>
                        <div className="text-[11px] text-slate-500 mt-0.5">ID: <code>{c.id}</code></div>
                      </div>
                    )}
                  </div>
                  {canManage && editingId !== c.id && (
                    <div className="flex items-center gap-2 shrink-0">
                      {!c.is_default && (
                        <button onClick={() => setDefault(c)}
                                data-testid={`btn-set-default-${c.id}`}
                                className="text-xs px-2 py-1 border border-amber-300 text-amber-800 rounded hover:bg-amber-50 inline-flex items-center gap-1">
                          <Star size={11} /> Set Default
                        </button>
                      )}
                      <button onClick={() => { setEditingId(c.id); setDraftName(c.name); }}
                              data-testid={`btn-edit-company-${c.id}`}
                              className="text-xs px-2 py-1 border border-slate-300 rounded hover:bg-slate-50 inline-flex items-center gap-1">
                        <PencilSimple size={11} /> Rename
                      </button>
                      <button onClick={() => archive(c)}
                              disabled={c.is_default}
                              data-testid={`btn-archive-company-${c.id}`}
                              className="text-xs px-2 py-1 border border-rose-300 text-rose-700 rounded hover:bg-rose-50 disabled:opacity-40 disabled:cursor-not-allowed inline-flex items-center gap-1">
                        <Archive size={11} /> Archive
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>

          {archived.length > 0 && (
            <section data-testid="company-list-archived">
              <div className="text-[10px] uppercase tracking-[0.18em] text-slate-500 mb-2">Archived</div>
              <div className="rounded-md border border-slate-200 divide-y divide-slate-100 opacity-70">
                {archived.map((c) => (
                  <div key={c.id} className="px-4 py-2 text-sm text-slate-600 flex items-center gap-2">
                    <span>{c.name}</span>
                    <span className="text-[9.5px] uppercase tracking-[0.14em] px-1.5 py-0.5 rounded-full bg-slate-200 text-slate-600">Archived</span>
                  </div>
                ))}
              </div>
            </section>
          )}
        </>
      )}

      {showCreate && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 flex items-center justify-center p-4"
             data-testid="create-company-modal">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-5">
            <div className="flex items-center justify-between mb-3">
              <div className="text-sm font-semibold text-slate-900">New Company</div>
              <button onClick={() => setShowCreate(false)}
                      data-testid="close-create-modal"
                      className="text-slate-400 hover:text-slate-700"><X size={14} /></button>
            </div>
            <label className="text-[11px] uppercase tracking-[0.12em] text-slate-500">Company Name</label>
            <input
              autoFocus
              value={draftName}
              onChange={(e) => setDraftName(e.target.value)}
              placeholder="e.g. ACE Car Freighters"
              data-testid="input-new-company-name"
              className="w-full border border-slate-300 rounded px-2 py-1.5 text-sm mt-1 mb-4"
            />
            <div className="flex justify-end gap-2">
              <button onClick={() => setShowCreate(false)}
                      className="text-xs px-3 py-1.5 border border-slate-300 rounded">Cancel</button>
              <button onClick={create}
                      data-testid="btn-save-new-company"
                      className="text-xs px-3 py-1.5 bg-slate-900 text-white rounded hover:bg-slate-800">
                Create
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
