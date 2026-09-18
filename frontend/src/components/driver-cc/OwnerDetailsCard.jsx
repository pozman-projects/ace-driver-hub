/**
 * MR-05 · Owner Details Card
 * Canonical single-source data:
 *   - Driving For        <- current DriverOwnerRelationship + Owner.name
 *   - Owner Mobile       <- Owner.mobile_number
 *   - Owner Email        <- Owner.email
 *   - Truck Ownership    <- primary Vehicle.ownership_model (canonical enum)
 *
 * In-card Edit / Save / Cancel. Owner search + inline "+ New Owner" modal.
 * Saves route through canonical endpoints only:
 *   POST /api/owners
 *   PUT  /api/owners/{id}
 *   POST /api/driver-owner-relationships   (with is_current=true which auto-closes prior)
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { MagnifyingGlass, Plus, Warning, X } from "@phosphor-icons/react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "../../lib/api";
import { ManagementCard, InlineField, EditInput, ROLE_CAN_EDIT } from "./driverCCUtils";

export default function OwnerDetailsCard({ data, role, driverId, onSaved }) {
  const canEdit = ROLE_CAN_EDIT.has(role);
  const owner = data?.owner || null;
  const relationship = data?.owner_relationship || null;
  const vehicle = data?.vehicle || null;

  const [editing, setEditing] = useState(false);
  // Pending owner selection (relationship change) — { id, name, mobile_number, email }
  const [pendingOwner, setPendingOwner] = useState(null);
  // Contact edits — { mobile_number, email } (targets pendingOwner || current owner)
  const [contactDraft, setContactDraft] = useState(null);
  const [saving, setSaving] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);

  const activeOwner = pendingOwner || owner;
  const dirty = !!pendingOwner || (contactDraft && (
    contactDraft.mobile_number !== (activeOwner?.mobile_number || "") ||
    contactDraft.email !== (activeOwner?.email || "")
  ));

  const beginEdit = () => {
    setEditing(true);
    setPendingOwner(null);
    setContactDraft({
      mobile_number: owner?.mobile_number || "",
      email: owner?.email || "",
    });
  };
  const cancel = () => {
    setEditing(false); setPendingOwner(null); setContactDraft(null);
  };

  const save = async () => {
    setSaving(true);
    try {
      // 1. Reassign relationship if a different owner selected
      if (pendingOwner && pendingOwner.id !== owner?.id) {
        await api.post("/driver-owner-relationships", {
          driver_id: driverId,
          owner_id: pendingOwner.id,
          is_current: true,
          start_date: new Date().toISOString().slice(0, 10),
        });
      }
      // 2. Contact edit on the effective owner (the one we saved into if newly linked)
      const targetOwnerId = pendingOwner?.id || owner?.id;
      if (targetOwnerId && contactDraft) {
        const patch = {};
        const base = pendingOwner || owner;
        if (contactDraft.mobile_number !== (base?.mobile_number || "")) patch.mobile_number = contactDraft.mobile_number;
        if (contactDraft.email !== (base?.email || "")) patch.email = contactDraft.email;
        if (Object.keys(patch).length > 0) {
          await api.put(`/owners/${targetOwnerId}`, patch);
        }
      }
      toast.success("Owner details saved");
      setEditing(false); setPendingOwner(null); setContactDraft(null);
      onSaved && onSaved();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Save failed");
    } finally { setSaving(false); }
  };

  const onOwnerCreated = (created) => {
    setCreateOpen(false);
    setPendingOwner(created);
    setContactDraft({
      mobile_number: created?.mobile_number || "",
      email: created?.email || "",
    });
    toast.success(`Owner "${created.name}" created — Save to link`);
  };

  return (
    <ManagementCard
      testid="card-owner-details" section="owner"
      title="Owner Details" subtitle="Driving For + canonical Owner"
      canEdit={canEdit}
      editing={editing} onEditToggle={beginEdit}
      saving={saving} dirty={!!dirty}
      onSave={save} onCancel={cancel}
    >
      {!editing ? (
        <>
          <InlineField label="Driving For" value={owner?.name} testid="owner-driving-for" />
          <InlineField label="Truck Owner" value={vehicle?.ownership_model} testid="owner-truck-ownership" />
          <InlineField label="Owner Mobile" value={owner?.mobile_number} testid="owner-mobile" />
          <InlineField label="Owner Email" value={owner?.email} testid="owner-email" />
          {relationship?.start_date && (
            <div className="text-[10px] text-slate-400 pt-1">Current since {relationship.start_date}</div>
          )}
        </>
      ) : (
        <>
          <OwnerPicker
            currentOwner={owner}
            pendingOwner={pendingOwner}
            onSelect={(o) => {
              setPendingOwner(o);
              setContactDraft({
                mobile_number: o?.mobile_number || "",
                email: o?.email || "",
              });
            }}
            onCreateOpen={() => setCreateOpen(true)}
          />
          <div className="rounded border border-amber-200 bg-amber-50 px-2 py-1.5 text-[11px] text-amber-800 flex gap-1.5" data-testid="owner-shared-warning">
            <Warning size={13} weight="fill" className="mt-0.5 shrink-0" />
            Contact changes update the canonical Owner record and affect every Driver linked to this Owner.
          </div>
          <EditInput
            label="Owner Mobile"
            value={contactDraft?.mobile_number}
            onChange={(v) => setContactDraft((s) => ({ ...s, mobile_number: v }))}
            testid="owner-mobile-input"
          />
          <EditInput
            label="Owner Email" type="email"
            value={contactDraft?.email}
            onChange={(v) => setContactDraft((s) => ({ ...s, email: v }))}
            testid="owner-email-input"
          />
          <InlineField label="Truck Owner" value={vehicle?.ownership_model} testid="owner-truck-ownership-readonly" />
        </>
      )}
      {createOpen && (
        <NewOwnerModal onClose={() => setCreateOpen(false)} onCreated={onOwnerCreated} />
      )}
    </ManagementCard>
  );
}

// ─── Owner picker (search + select + create button) ────────────────────────
function OwnerPicker({ currentOwner, pendingOwner, onSelect, onCreateOpen }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const debounceRef = useRef(null);
  const anchorRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      try {
        const { data } = await api.get("/owners", { params: { include_archived: false } });
        const term = q.trim().toLowerCase();
        const filtered = term
          ? data.filter((o) =>
              (o.name || "").toLowerCase().includes(term) ||
              (o.abn || "").toLowerCase().includes(term) ||
              (o.email || "").toLowerCase().includes(term))
          : data;
        setResults(filtered.slice(0, 25));
      } catch { setResults([]); }
    }, 200);
    return () => clearTimeout(debounceRef.current);
  }, [q, open]);

  useEffect(() => {
    const h = (e) => { if (anchorRef.current && !anchorRef.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  const displayLabel = pendingOwner
    ? `Pending: ${pendingOwner.name}`
    : currentOwner?.name || "— No owner —";

  return (
    <div ref={anchorRef} className="relative" data-testid="owner-picker">
      <div className="text-[10px] uppercase tracking-[0.15em] text-slate-500 mb-1">Driving For</div>
      <div className="flex items-stretch gap-1.5">
        <button
          type="button"
          data-testid="owner-picker-toggle"
          onClick={() => setOpen((v) => !v)}
          className={`flex-1 text-left text-sm px-2 py-1.5 rounded-md border ${pendingOwner ? "border-amber-300 bg-amber-50" : "border-slate-200"} hover:border-cyan-400`}
        >
          <span className="inline-flex items-center gap-1.5"><MagnifyingGlass size={12} /> {displayLabel}</span>
        </button>
        <button
          type="button"
          data-testid="owner-create-open"
          onClick={onCreateOpen}
          title="Create new Owner"
          className="px-2 py-1.5 rounded-md border border-slate-200 hover:bg-slate-50 text-xs inline-flex items-center gap-1"
        ><Plus size={11} weight="bold" /> New</button>
      </div>
      {pendingOwner && currentOwner && pendingOwner.id !== currentOwner.id && (
        <div className="text-[10px] mt-1 text-amber-700" data-testid="owner-pending-banner">
          Pending reassignment: <b>{currentOwner.name}</b> → <b>{pendingOwner.name}</b>
        </div>
      )}
      {open && (
        <div className="absolute z-20 left-0 right-0 mt-1 bg-white border border-slate-200 rounded-md shadow-lg max-h-64 overflow-auto" data-testid="owner-picker-menu">
          <input
            autoFocus data-testid="owner-picker-input"
            value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="Search owner name / ABN / email"
            className="w-full text-sm px-2 py-1.5 border-b border-slate-100 outline-none"
          />
          {results.length === 0 && (
            <div className="text-xs text-slate-400 px-2 py-2">No matches</div>
          )}
          {results.map((o) => (
            <button
              key={o.id} type="button"
              data-testid={`owner-picker-option-${o.id}`}
              onClick={() => { onSelect(o); setOpen(false); setQ(""); }}
              className="w-full text-left px-2 py-1.5 hover:bg-slate-50 text-xs border-b border-slate-50 last:border-b-0"
            >
              <div className="font-medium text-slate-900">{o.name}</div>
              <div className="text-[10px] text-slate-500">{[o.owner_type, o.abn, o.email].filter(Boolean).join(" · ")}</div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── + New Owner Modal ─────────────────────────────────────────────────────
function NewOwnerModal({ onClose, onCreated }) {
  const [form, setForm] = useState({
    name: "", owner_type: "Business", mobile_number: "", email: "", abn: "",
  });
  const [saving, setSaving] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) { toast.error("Name is required"); return; }
    setSaving(true);
    try {
      const payload = { ...form };
      Object.keys(payload).forEach((k) => { if (payload[k] === "") delete payload[k]; });
      const { data } = await api.post("/owners", payload);
      onCreated(data);
    } catch (e2) {
      toast.error(formatApiErrorDetail(e2?.response?.data?.detail) || "Create failed");
    } finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" data-testid="owner-create-modal">
      <form onSubmit={submit} className="bg-white rounded-xl w-full max-w-md shadow-xl">
        <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between">
          <div className="text-sm font-semibold text-slate-900">New Owner</div>
          <button type="button" onClick={onClose} data-testid="owner-create-close" className="text-slate-500 hover:text-slate-900"><X size={14} /></button>
        </div>
        <div className="p-4 space-y-3">
          <EditInput label="Name" value={form.name} onChange={(v) => setForm((s) => ({ ...s, name: v }))} testid="owner-create-name" />
          <label className="block">
            <div className="text-[10px] uppercase tracking-[0.15em] text-slate-500 mb-1">Owner Type</div>
            <select
              data-testid="owner-create-type"
              value={form.owner_type}
              onChange={(e) => setForm((s) => ({ ...s, owner_type: e.target.value }))}
              className="w-full border border-slate-200 rounded-md px-2 py-1.5 text-sm"
            >
              {["Individual", "Business", "Trust", "Other"].map((t) => (<option key={t} value={t}>{t}</option>))}
            </select>
          </label>
          <EditInput label="Mobile" value={form.mobile_number} onChange={(v) => setForm((s) => ({ ...s, mobile_number: v }))} testid="owner-create-mobile" />
          <EditInput label="Email" type="email" value={form.email} onChange={(v) => setForm((s) => ({ ...s, email: v }))} testid="owner-create-email" />
          <EditInput label="ABN" value={form.abn} onChange={(v) => setForm((s) => ({ ...s, abn: v }))} testid="owner-create-abn" />
        </div>
        <div className="px-4 py-3 border-t border-slate-100 flex items-center justify-end gap-2">
          <button type="button" onClick={onClose} className="text-xs px-3 py-1.5 rounded text-slate-600 hover:text-slate-900">Cancel</button>
          <button type="submit" disabled={saving} data-testid="owner-create-submit"
                  className="text-xs px-3 py-1.5 rounded bg-slate-900 text-white hover:bg-slate-800 disabled:opacity-50">
            {saving ? "Creating…" : "Create Owner"}
          </button>
        </div>
      </form>
    </div>
  );
}
