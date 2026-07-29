/**
 * EB-10.1 · Activation Template Detail + Item Editor page
 * Route: /administration/activation-templates/:templateId
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { toast } from "sonner";
import AppHeader from "../components/app/AppHeader";
import api, { formatApiErrorDetail } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import {
  CaretLeft, PencilSimple, Copy, Archive as ArchiveIcon, ArrowClockwise,
  ArrowUp, ArrowDown, Plus, LockKey, X, Check,
} from "@phosphor-icons/react";

const CATEGORIES = ["Driver Identity", "Account Setup", "Driver Setup", "Communication",
  "Vehicle Assignment", "Equipment Assignment", "Owner Relationship",
  "Licence and Compliance", "Documents", "System Access", "Training",
  "Administration", "Other"];
const COMPLETION_TYPES = ["Automatic", "Manual", "Conditional Automatic",
  "Conditional Manual", "Informational"];

const EMPTY_ITEM = {
  label: "", item_key: "", description: "", category: "Driver Identity",
  completion_type: "Manual", source_entity_type: null, source_field: null,
  source_rule: null, mandatory: true, conditional: false, condition_rule: null,
  display_order: 0, evidence_required: false, evidence_category: null,
  override_allowed: false, override_max_days: 30,
};

export default function ActivationTemplateDetailPage() {
  const { templateId } = useParams();
  const { user } = useAuth();
  const canManage = ["Admin", "Manager"].includes(user?.role);
  const [tpl, setTpl] = useState(null);
  const [usage, setUsage] = useState(null);
  const [items, setItems] = useState([]);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null); // item being edited (null | 'new' | item)
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [{ data: tRes }, { data: uRes }, { data: iRes }] = await Promise.all([
        api.get(`/activation/templates/${templateId}`),
        api.get(`/activation/templates/${templateId}/usage`),
        api.get(`/activation/templates/${templateId}/items`, { params: { include_archived: includeArchived } }),
      ]);
      setTpl(tRes); setUsage(uRes); setItems(iRes);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Load failed");
    } finally { setLoading(false); }
  }, [templateId, includeArchived]);

  useEffect(() => { refresh(); }, [refresh]);

  const locked = usage?.locked;

  const saveItem = async (item) => {
    setBusy(true);
    try {
      // Validation (frontend mirror of backend)
      if (!item.label?.trim()) throw new Error("Label required");
      if (!item.item_key?.trim()) throw new Error("Item Key required");
      if (!/^[a-z0-9_.-]+$/i.test(item.item_key)) throw new Error("Item Key must be machine-safe (letters, digits, . _ -)");
      if (item.override_allowed && (!item.override_max_days || item.override_max_days < 1)) throw new Error("Override maximum days must be > 0");
      if (item.conditional && !item.condition_rule) throw new Error("Conditional items require condition_rule");
      if (item.source_entity_type === "vehicle_defect" && item.override_allowed) throw new Error("Critical-defect items cannot be overrideable");
      if (editing === "new") {
        await api.post(`/activation/templates/${templateId}/items`, item);
      } else {
        await api.put(`/activation/template-items/${editing.activation_template_item_id}`, item);
      }
      toast.success("Item saved");
      setEditing(null);
      await refresh();
    } catch (e) {
      const msg = e?.message && !e?.response ? e.message : formatApiErrorDetail(e?.response?.data?.detail) || "Save failed";
      toast.error(msg);
    } finally { setBusy(false); }
  };

  const duplicateItem = async (item) => {
    try {
      await api.post(`/activation/template-items/${item.activation_template_item_id}/duplicate`);
      toast.success("Item duplicated");
      await refresh();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Duplicate failed");
    }
  };
  const archiveItem = async (item) => {
    if (!window.confirm(`Archive item "${item.label}"?`)) return;
    try {
      await api.delete(`/activation/template-items/${item.activation_template_item_id}`);
      toast.success("Item archived");
      await refresh();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Archive failed");
    }
  };
  const restoreItem = async (item) => {
    try {
      await api.post(`/activation/template-items/${item.activation_template_item_id}/restore`);
      toast.success("Item restored");
      await refresh();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Restore failed");
    }
  };
  const move = async (item, dir) => {
    const active = items.filter((i) => !i.is_archived);
    const idx = active.findIndex((i) => i.activation_template_item_id === item.activation_template_item_id);
    const target = dir === "up" ? idx - 1 : idx + 1;
    if (target < 0 || target >= active.length) return;
    const newOrder = [...active];
    [newOrder[idx], newOrder[target]] = [newOrder[target], newOrder[idx]];
    try {
      await api.post(`/activation/templates/${templateId}/items/reorder`,
                      { order: newOrder.map((i) => i.activation_template_item_id) });
      await refresh();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Reorder failed");
    }
  };

  const cloneTemplate = async () => {
    try {
      const { data } = await api.post(`/activation/templates/${templateId}/clone`);
      toast.success(`Cloned as v${data.version}`);
      // The user usually wants to edit the clone
      window.location.href = `/administration/activation-templates/${data.activation_template_id}`;
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Clone failed");
    }
  };

  if (loading) return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader showBack />
      <div className="max-w-6xl mx-auto p-8 space-y-3">
        {[1,2,3,4,5,6].map((i) => <div key={i} className="h-14 bg-white rounded-xl border border-slate-200 animate-pulse" />)}
      </div>
    </div>
  );

  if (!tpl) return null;

  return (
    <div className="min-h-screen bg-slate-50" data-testid="template-detail-page">
      <AppHeader showBack />
      <main className="max-w-6xl mx-auto px-4 lg:px-8 py-6">
        {/* Header */}
        <div className="mb-6 bg-white border border-slate-200 rounded-xl p-5">
          <div className="text-[10px] uppercase tracking-[0.22em] text-slate-500 mb-1">
            <Link to="/administration/activation-templates" data-testid="template-back" className="hover:text-slate-900 inline-flex items-center gap-1">
              <CaretLeft size={10} /> Back to Templates
            </Link>
          </div>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <h1 className="font-display text-2xl font-semibold text-slate-900" data-testid="template-name-heading">{tpl.name} <span className="text-slate-400 font-normal text-lg">v{tpl.version}</span></h1>
              <div className="text-sm text-slate-600 mt-1">{tpl.description || <span className="italic text-slate-400">No description</span>}</div>
              <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                <Badge>{tpl.driver_type}</Badge>
                <Badge>{tpl.company_ref}</Badge>
                {tpl.is_default && <Badge tone="ok">Default</Badge>}
                {tpl.is_active ? <Badge tone="ok">Active</Badge> : <Badge tone="warn">Inactive</Badge>}
                {tpl.is_archived && <Badge tone="danger">Archived</Badge>}
                {locked && (
                  <Badge tone="warn" testid="template-lock-badge">
                    <LockKey size={10} weight="fill" /> Locked · applied to {usage.used_by_activation_records} driver{usage.used_by_activation_records === 1 ? "" : "s"}
                  </Badge>
                )}
              </div>
              {locked && (
                <div className="mt-2 text-[11px] text-amber-800 bg-amber-50 border border-amber-200 rounded px-2 py-1.5" data-testid="template-lock-notice">
                  This template is applied to at least one driver. Structural changes (renaming Item Keys) are blocked to protect historical activation records. Use <strong>Clone as new version</strong> before making structural changes.
                </div>
              )}
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              {canManage && (
                <>
                  <button data-testid="template-clone-btn" onClick={cloneTemplate} className="text-xs px-3 py-1.5 rounded border border-slate-200 hover:bg-slate-50 inline-flex items-center gap-1">
                    <Copy size={12} /> Clone as new version
                  </button>
                </>
              )}
            </div>
          </div>
          <div className="mt-3 grid grid-cols-2 sm:grid-cols-5 gap-2 text-center text-[10px]">
            <Stat label="Version" value={`v${tpl.version}`} testid="stat-version" />
            <Stat label="Items" value={items.filter((i) => !i.is_archived).length} testid="stat-items" />
            <Stat label="Mandatory" value={items.filter((i) => !i.is_archived && i.mandatory).length} testid="stat-mandatory" />
            <Stat label="Applied to" value={usage?.used_by_activation_records ?? 0} testid="stat-usage" />
            <Stat label="Updated" value={tpl.updated_at ? new Date(tpl.updated_at).toLocaleDateString() : "—"} testid="stat-updated" />
          </div>
        </div>

        {/* Items table */}
        <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
          <div className="px-4 py-2 border-b border-slate-100 flex items-center justify-between">
            <div className="text-[10px] uppercase tracking-[0.22em] text-slate-500">Checklist Items</div>
            <div className="flex items-center gap-2">
              <label className="flex items-center gap-1.5 text-[11px] text-slate-600">
                <input data-testid="items-include-archived" type="checkbox" checked={includeArchived} onChange={(e) => setIncludeArchived(e.target.checked)} />
                Show archived
              </label>
              {canManage && (
                <button data-testid="item-add-btn" onClick={() => setEditing("new")} className="text-xs px-3 py-1.5 rounded bg-slate-900 text-white hover:bg-slate-800 inline-flex items-center gap-1">
                  <Plus size={12} weight="bold" /> Add item
                </button>
              )}
            </div>
          </div>
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-[10px] uppercase tracking-[0.15em] text-slate-500">
              <tr>
                <th className="px-2 py-2 w-12 text-center">#</th>
                <th className="px-2 py-2 text-left">Item</th>
                <th className="px-2 py-2 text-left">Category</th>
                <th className="px-2 py-2 text-left">Type</th>
                <th className="px-2 py-2 text-center">Mand.</th>
                <th className="px-2 py-2 text-center">Evid.</th>
                <th className="px-2 py-2 text-center">Ovr.</th>
                <th className="px-2 py-2 text-right w-40">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((it) => (
                <tr key={it.activation_template_item_id} data-testid={`item-row-${it.activation_template_item_id}`} className={`border-t border-slate-100 ${it.is_archived ? "opacity-50" : ""}`}>
                  <td className="px-2 py-1.5 text-center font-mono text-xs text-slate-500">{it.display_order}</td>
                  <td className="px-2 py-1.5">
                    <div className="font-medium text-slate-900">{it.label}</div>
                    <div className="text-[10px] font-mono text-slate-400">{it.item_key}</div>
                  </td>
                  <td className="px-2 py-1.5 text-slate-600">{it.category}</td>
                  <td className="px-2 py-1.5 text-slate-600">{it.completion_type}</td>
                  <td className="px-2 py-1.5 text-center">{it.mandatory ? <Check size={12} className="inline text-emerald-600" weight="bold" /> : ""}</td>
                  <td className="px-2 py-1.5 text-center">{it.evidence_required ? <Check size={12} className="inline text-blue-600" weight="bold" /> : ""}</td>
                  <td className="px-2 py-1.5 text-center">{it.override_allowed ? `${it.override_max_days}d` : ""}</td>
                  <td className="px-2 py-1.5 text-right space-x-1 whitespace-nowrap">
                    {canManage && !it.is_archived && (
                      <>
                        <button data-testid={`item-up-${it.activation_template_item_id}`} onClick={() => move(it, "up")} title="Move up" className="p-1 rounded hover:bg-slate-100"><ArrowUp size={12} /></button>
                        <button data-testid={`item-down-${it.activation_template_item_id}`} onClick={() => move(it, "down")} title="Move down" className="p-1 rounded hover:bg-slate-100"><ArrowDown size={12} /></button>
                        <button data-testid={`item-edit-${it.activation_template_item_id}`} onClick={() => setEditing(it)} title="Edit" className="p-1 rounded hover:bg-slate-100"><PencilSimple size={12} /></button>
                        <button data-testid={`item-duplicate-${it.activation_template_item_id}`} onClick={() => duplicateItem(it)} title="Duplicate" className="p-1 rounded hover:bg-slate-100"><Copy size={12} /></button>
                        <button data-testid={`item-archive-${it.activation_template_item_id}`} onClick={() => archiveItem(it)} title="Archive" className="p-1 rounded hover:bg-red-50 text-red-700"><ArchiveIcon size={12} /></button>
                      </>
                    )}
                    {canManage && it.is_archived && (
                      <button data-testid={`item-restore-${it.activation_template_item_id}`} onClick={() => restoreItem(it)} title="Restore" className="p-1 rounded hover:bg-emerald-50 text-emerald-700"><ArrowClockwise size={12} /></button>
                    )}
                  </td>
                </tr>
              ))}
              {items.length === 0 && (
                <tr><td colSpan={8} data-testid="items-empty" className="px-4 py-6 text-center text-sm text-slate-400 italic">No items yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </main>

      {editing !== null && (
        <ItemDialog
          initial={editing === "new" ? { ...EMPTY_ITEM, display_order: items.length } : editing}
          isNew={editing === "new"}
          locked={locked}
          onCancel={() => setEditing(null)}
          onSubmit={saveItem}
          busy={busy}
        />
      )}
    </div>
  );
}

function Badge({ children, tone = "neutral", testid }) {
  const cls = tone === "ok" ? "border-emerald-200 bg-emerald-50 text-emerald-700"
    : tone === "warn" ? "border-amber-200 bg-amber-50 text-amber-700"
    : tone === "danger" ? "border-red-200 bg-red-50 text-red-700"
    : "border-slate-200 bg-slate-50 text-slate-600";
  return <span data-testid={testid} className={`inline-flex items-center gap-1 text-[10px] uppercase tracking-[0.15em] border ${cls} rounded-full px-2 py-0.5`}>{children}</span>;
}

function Stat({ label, value, testid }) {
  return (
    <div data-testid={testid} className="border border-slate-200 rounded px-2 py-1.5 bg-slate-50">
      <div className="text-[9px] uppercase tracking-[0.15em] text-slate-500">{label}</div>
      <div className="text-sm font-semibold text-slate-800">{value}</div>
    </div>
  );
}

function ItemDialog({ initial, isNew, locked, onCancel, onSubmit, busy }) {
  const [form, setForm] = useState(initial);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const disabled = busy;
  return (
    <div className="fixed inset-0 bg-black/40 grid place-items-center z-50 p-4" data-testid="item-dialog" onClick={onCancel}>
      <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl p-5 max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-base font-semibold text-slate-900">{isNew ? "Add checklist item" : "Edit checklist item"}</h3>
          <button data-testid="item-dialog-close" onClick={onCancel} className="p-1 rounded hover:bg-slate-100"><X size={14} /></button>
        </div>
        {locked && !isNew && (
          <div className="mb-3 text-[11px] text-amber-800 bg-amber-50 border border-amber-200 rounded px-2 py-1.5">
            Template is locked. Non-structural edits are allowed; Item Key renames are blocked server-side to protect historical activations.
          </div>
        )}
        <div className="grid grid-cols-2 gap-3 text-sm">
          <Field label="Label *"><input data-testid="field-label" value={form.label || ""} onChange={(e) => set("label", e.target.value)} className="input" /></Field>
          <Field label="Item Key *"><input data-testid="field-item-key" value={form.item_key || ""} onChange={(e) => set("item_key", e.target.value)} className="input font-mono text-xs" /></Field>
          <Field label="Category" full>
            <select data-testid="field-category" value={form.category} onChange={(e) => set("category", e.target.value)} className="input">
              {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </Field>
          <Field label="Completion Type">
            <select data-testid="field-completion-type" value={form.completion_type} onChange={(e) => set("completion_type", e.target.value)} className="input">
              {COMPLETION_TYPES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </Field>
          <Field label="Display Order">
            <input data-testid="field-display-order" type="number" min="0" value={form.display_order ?? 0} onChange={(e) => set("display_order", Number(e.target.value))} className="input" />
          </Field>
          <Field label="Source Entity Type"><input data-testid="field-source-entity" value={form.source_entity_type || ""} onChange={(e) => set("source_entity_type", e.target.value || null)} placeholder="driver / document / licence / …" className="input font-mono text-xs" /></Field>
          <Field label="Source Field"><input data-testid="field-source-field" value={form.source_field || ""} onChange={(e) => set("source_field", e.target.value || null)} placeholder="e.g. mobile_number" className="input font-mono text-xs" /></Field>
          <Field label="Description" full>
            <textarea data-testid="field-description" value={form.description || ""} onChange={(e) => set("description", e.target.value || null)} className="input h-16" />
          </Field>
          <Field label="Mandatory">
            <input data-testid="field-mandatory" type="checkbox" checked={!!form.mandatory} onChange={(e) => set("mandatory", e.target.checked)} />
          </Field>
          <Field label="Evidence required">
            <input data-testid="field-evidence-required" type="checkbox" checked={!!form.evidence_required} onChange={(e) => set("evidence_required", e.target.checked)} />
          </Field>
          <Field label="Override allowed">
            <input data-testid="field-override-allowed" type="checkbox" checked={!!form.override_allowed} onChange={(e) => set("override_allowed", e.target.checked)} />
          </Field>
          {form.override_allowed && (
            <Field label="Override max days">
              <input data-testid="field-override-max-days" type="number" min="1" max="365" value={form.override_max_days ?? 30} onChange={(e) => set("override_max_days", Number(e.target.value))} className="input" />
            </Field>
          )}
          <Field label="Conditional">
            <input data-testid="field-conditional" type="checkbox" checked={!!form.conditional} onChange={(e) => set("conditional", e.target.checked)} />
          </Field>
          {form.conditional && (
            <Field label="Condition rule (JSON)" full>
              <textarea data-testid="field-condition-rule" value={form.condition_rule ? JSON.stringify(form.condition_rule) : ""}
                        onChange={(e) => {
                          try { set("condition_rule", e.target.value ? JSON.parse(e.target.value) : null); }
                          catch { /* keep partial */ }
                        }}
                        placeholder='{"driver_type_in":["Contractor Driver"]}'
                        className="input font-mono text-xs h-16" />
            </Field>
          )}
        </div>
        <div className="mt-4 flex items-center justify-end gap-2">
          <button data-testid="item-dialog-cancel" onClick={onCancel} disabled={disabled} className="text-xs px-3 py-1.5 rounded text-slate-600 hover:text-slate-900 disabled:opacity-50">Cancel</button>
          <button data-testid="item-dialog-save" onClick={() => onSubmit(form)} disabled={disabled} className="text-xs px-3 py-1.5 rounded bg-slate-900 text-white hover:bg-slate-800 disabled:opacity-50 inline-flex items-center gap-1">
            {busy && <div className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />} Save
          </button>
        </div>
      </div>
      <style>{`.input { width: 100%; border: 1px solid rgb(226 232 240); border-radius: 0.375rem; padding: 0.375rem 0.5rem; font-size: 0.875rem; } .input:focus { outline: none; border-color: rgb(6 182 212); box-shadow: 0 0 0 2px rgba(6, 182, 212, 0.2); }`}</style>
    </div>
  );
}

function Field({ label, full, children }) {
  return (
    <label className={`block ${full ? "col-span-2" : ""}`}>
      <div className="text-[10px] uppercase tracking-[0.15em] text-slate-500 mb-1">{label}</div>
      {children}
    </label>
  );
}
