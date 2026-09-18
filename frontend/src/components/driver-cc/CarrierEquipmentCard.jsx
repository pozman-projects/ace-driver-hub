/**
 * MR-05 · Carrier Details Card
 *
 * Displays canonical current state only:
 *   - Primary Vehicle (rego + make/model)
 *   - Carrier Configuration
 *   - Carrier Status  (canonical Vehicle lifecycle values only)
 *   - Tray            (Equipment number + canonical ownership)
 *   - Trailer         (Equipment number + canonical ownership)
 *
 * All edits go through EXISTING canonical services:
 *   POST /api/driver-vehicle-assignments/reassign  (explicit Save)
 *   PUT  /api/vehicles/{id}                        (carrier_configuration / vehicle_status)
 *   POST /api/vehicle-equipment-couplings/reassign (tray / trailer)
 *
 * Ownership terminology intentionally displayed AS-IS (canonical enum).
 */
import React, { useCallback, useEffect, useRef, useState } from "react";
import { MagnifyingGlass, Warning } from "@phosphor-icons/react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "../../lib/api";
import { ManagementCard, InlineField, ROLE_CAN_EDIT } from "./driverCCUtils";

// Canonical Vehicle lifecycle (EB-R02C locked list — no deprecated values).
const VEHICLE_STATUSES = [
  "Active", "In Workshop", "Retired", "Sold", "Written Off", "Pending Disposal",
];

const CARRIER_CONFIGS = [
  "Single Deck", "Two Deck", "Three Deck", "Prime Mover", "Rigid", "Other",
];

export default function CarrierEquipmentCard({ data, role, driverId, onSaved }) {
  const canEdit = ROLE_CAN_EDIT.has(role);
  const vehicle = data?.vehicle || null;
  const trayEq = data?.tray_equipment || null;
  const trailerEq = data?.trailer_equipment || null;

  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);

  // Pending selections (never mutate backend until Save)
  const [pendingVehicle, setPendingVehicle] = useState(null);
  const [pendingTray, setPendingTray] = useState(null);
  const [pendingTrailer, setPendingTrailer] = useState(null);
  const [vDraft, setVDraft] = useState(null);
  //     { carrier_configuration, vehicle_status }

  const dirty = !!(
    pendingVehicle || pendingTray || pendingTrailer ||
    (vDraft && (
      vDraft.carrier_configuration !== (vehicle?.carrier_configuration || "") ||
      vDraft.vehicle_status !== (vehicle?.vehicle_status || "")
    ))
  );

  const beginEdit = () => {
    setEditing(true);
    setPendingVehicle(null); setPendingTray(null); setPendingTrailer(null);
    setVDraft({
      carrier_configuration: vehicle?.carrier_configuration || "",
      vehicle_status: vehicle?.vehicle_status || "",
    });
  };
  const cancel = () => {
    setEditing(false);
    setPendingVehicle(null); setPendingTray(null); setPendingTrailer(null);
    setVDraft(null);
  };

  const save = async () => {
    setSaving(true);
    let reassignmentDone = false;
    try {
      // 1) Primary Vehicle reassignment
      if (pendingVehicle && pendingVehicle.id !== vehicle?.id) {
        if (!window.confirm(`Reassign primary Vehicle?\n\nFrom: ${vehicle?.registration_number || "—"}\nTo: ${pendingVehicle.registration_number}\n\nHistory is preserved.`)) {
          setSaving(false); return;
        }
        await api.post("/driver-vehicle-assignments/reassign", {
          driver_id: driverId,
          vehicle_id: pendingVehicle.id,
          is_primary: true,
          start_date: new Date().toISOString().slice(0, 10),
        });
        reassignmentDone = true;
      }
      // 2) Vehicle field edits — MR-05-FIX Defect 1:
      // Draft is always compared against the EFFECTIVE vehicle (selected new
      // vehicle if pending, else current). We never silently drop visible edits.
      const effVehicle = pendingVehicle || vehicle;
      const effVehicleId = effVehicle?.id;
      if (effVehicleId && vDraft) {
        const patch = {};
        if (vDraft.carrier_configuration !== (effVehicle?.carrier_configuration || ""))
          patch.carrier_configuration = vDraft.carrier_configuration;
        if (vDraft.vehicle_status !== (effVehicle?.vehicle_status || ""))
          patch.vehicle_status = vDraft.vehicle_status;
        if (Object.keys(patch).length) {
          await api.put(`/vehicles/${effVehicleId}`, patch);
        }
      }
      // 3) Tray reassignment (against effective vehicle)
      if (pendingTray && effVehicleId) {
        await api.post("/vehicle-equipment-couplings/reassign", {
          vehicle_id: effVehicleId,
          equipment_id: pendingTray.id,
          role: "Tray",
          start_date: new Date().toISOString().slice(0, 10),
        });
      }
      // 4) Trailer reassignment
      if (pendingTrailer && effVehicleId) {
        await api.post("/vehicle-equipment-couplings/reassign", {
          vehicle_id: effVehicleId,
          equipment_id: pendingTrailer.id,
          role: "Trailer",
          start_date: new Date().toISOString().slice(0, 10),
        });
      }
      toast.success("Carrier saved");
      setEditing(false);
      setPendingVehicle(null); setPendingTray(null); setPendingTrailer(null); setVDraft(null);
      onSaved && onSaved();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Save failed");
      // MR-05-FIX Defect 1 · Partial-failure: refresh canonical state so the
      // UI does not keep displaying stale pre-save relationships.
      if (reassignmentDone && onSaved) {
        try { await onSaved(); } catch { /* ignore */ }
      }
    } finally { setSaving(false); }
  };

  return (
    <ManagementCard
      testid="card-car-carrier" section="car-carrier"
      title="Carrier Details" subtitle="Primary Vehicle + Tray + Trailer"
      canEdit={canEdit}
      editing={editing} onEditToggle={beginEdit}
      saving={saving} dirty={!!dirty}
      onSave={save} onCancel={cancel}
    >
      {!editing ? (
        <ViewMode vehicle={vehicle} trayEq={trayEq} trailerEq={trailerEq} />
      ) : (
        <EditMode
          vehicle={vehicle}
          trayEq={trayEq}
          trailerEq={trailerEq}
          vDraft={vDraft} setVDraft={setVDraft}
          pendingVehicle={pendingVehicle} setPendingVehicle={setPendingVehicle}
          pendingTray={pendingTray} setPendingTray={setPendingTray}
          pendingTrailer={pendingTrailer} setPendingTrailer={setPendingTrailer}
        />
      )}
    </ManagementCard>
  );
}

// ─── View mode ─────────────────────────────────────────────────────────────
function ViewMode({ vehicle, trayEq, trailerEq }) {
  if (!vehicle) return <div data-testid="vehicle-empty" className="text-xs text-slate-400 italic">No primary vehicle assignment.</div>;
  return (
    <>
      <InlineField label="Vehicle" value={vehicle.registration_number} testid="field-vehicle-rego" mono />
      <InlineField label="Config" value={vehicle.carrier_configuration} testid="field-vehicle-config" />
      <InlineField label="Status" value={vehicle.vehicle_status} testid="field-vehicle-status" />
      <div className="pt-2 border-t border-slate-100 mt-2 space-y-1.5">
        <div className="text-[10px] uppercase tracking-[0.15em] text-slate-500">Tray</div>
        {trayEq ? (
          <div className="grid grid-cols-[110px_1fr] gap-3 items-baseline">
            <div data-testid="field-tray-number" className="font-mono text-sm">{trayEq.equipment_number || "—"}</div>
            <div data-testid="field-tray-ownership" className="text-[11px] text-slate-500">{trayEq.ownership_model || "—"}{trayEq.equipment_status ? ` · ${trayEq.equipment_status}` : ""}</div>
          </div>
        ) : (
          <div data-testid="tray-empty" className="text-xs text-slate-400 italic">No coupled Tray.</div>
        )}
      </div>
      <div className="pt-1.5 space-y-1.5">
        <div className="text-[10px] uppercase tracking-[0.15em] text-slate-500">Trailer</div>
        {trailerEq ? (
          <div className="grid grid-cols-[110px_1fr] gap-3 items-baseline">
            <div data-testid="field-trailer-number" className="font-mono text-sm">{trailerEq.equipment_number || "—"}</div>
            <div data-testid="field-trailer-ownership" className="text-[11px] text-slate-500">{trailerEq.ownership_model || "—"}{trailerEq.equipment_status ? ` · ${trailerEq.equipment_status}` : ""}</div>
          </div>
        ) : (
          <div data-testid="trailer-empty" className="text-xs text-slate-400 italic">No coupled Trailer.</div>
        )}
      </div>
    </>
  );
}

// ─── Edit mode ─────────────────────────────────────────────────────────────
function EditMode({
  vehicle, trayEq, trailerEq,
  vDraft, setVDraft,
  pendingVehicle, setPendingVehicle,
  pendingTray, setPendingTray,
  pendingTrailer, setPendingTrailer,
}) {
  return (
    <>
      <VehiclePicker
        currentVehicle={vehicle}
        pendingVehicle={pendingVehicle}
        onSelect={(v) => {
          // MR-05-FIX Defect 1 · reset draft to the SELECTED vehicle's canonical values
          setPendingVehicle(v);
          setVDraft({
            carrier_configuration: v?.carrier_configuration || "",
            vehicle_status: v?.vehicle_status || "",
          });
        }}
      />
      <label className="block">
        <div className="text-[10px] uppercase tracking-[0.15em] text-slate-500 mb-1">Config</div>
        <select
          data-testid="edit-carrier-config"
          value={vDraft?.carrier_configuration || ""}
          onChange={(e) => setVDraft((s) => ({ ...s, carrier_configuration: e.target.value }))}
          className="w-full border border-slate-200 rounded-md px-2 py-1.5 text-sm"
        >
          <option value="">— unset —</option>
          {CARRIER_CONFIGS.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </label>
      <label className="block">
        <div className="text-[10px] uppercase tracking-[0.15em] text-slate-500 mb-1">Status</div>
        <select
          data-testid="edit-vehicle-status"
          value={vDraft?.vehicle_status || ""}
          onChange={(e) => setVDraft((s) => ({ ...s, vehicle_status: e.target.value }))}
          className="w-full border border-slate-200 rounded-md px-2 py-1.5 text-sm"
        >
          <option value="">— unset —</option>
          {VEHICLE_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </label>

      <div className="pt-2 border-t border-slate-100 mt-2">
        <EquipmentSlot
          role="Tray" testidPrefix="tray"
          currentEq={trayEq} pendingEq={pendingTray} onSelect={setPendingTray}
        />
      </div>
      <div className="pt-1.5">
        <EquipmentSlot
          role="Trailer" testidPrefix="trailer"
          currentEq={trailerEq} pendingEq={pendingTrailer} onSelect={setPendingTrailer}
        />
      </div>
      {(pendingVehicle || pendingTray || pendingTrailer) && (
        <div className="rounded border border-amber-200 bg-amber-50 px-2 py-1.5 text-[11px] text-amber-800 flex gap-1.5" data-testid="carrier-pending-banner">
          <Warning size={13} weight="fill" className="mt-0.5 shrink-0" />
          Pending reassignment — click Save to apply. Backend enforces history + one-active-per-role.
        </div>
      )}
    </>
  );
}

// ─── Vehicle picker ────────────────────────────────────────────────────────
function VehiclePicker({ currentVehicle, pendingVehicle, onSelect }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const anchorRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    const t = setTimeout(async () => {
      try {
        const { data } = await api.get("/vehicles", { params: { include_archived: false } });
        const term = q.trim().toLowerCase();
        const filtered = term
          ? data.filter((v) => (v.registration_number || "").toLowerCase().includes(term)
              || (v.make || "").toLowerCase().includes(term)
              || (v.model || "").toLowerCase().includes(term))
          : data;
        setResults(filtered.filter((v) => !v.is_archived).slice(0, 30));
      } catch { setResults([]); }
    }, 200);
    return () => clearTimeout(t);
  }, [q, open]);

  useEffect(() => {
    const h = (e) => { if (anchorRef.current && !anchorRef.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  const label = pendingVehicle
    ? `Pending: ${pendingVehicle.registration_number}`
    : currentVehicle?.registration_number || "— No primary vehicle —";

  return (
    <div ref={anchorRef} className="relative" data-testid="vehicle-picker">
      <div className="text-[10px] uppercase tracking-[0.15em] text-slate-500 mb-1">Vehicle</div>
      <button
        type="button"
        data-testid="vehicle-picker-toggle"
        onClick={() => setOpen((v) => !v)}
        className={`w-full text-left text-sm px-2 py-1.5 rounded-md border ${pendingVehicle ? "border-amber-300 bg-amber-50" : "border-slate-200"} hover:border-cyan-400`}
      ><MagnifyingGlass size={12} className="inline mr-1" /> {label}</button>
      {pendingVehicle && currentVehicle && pendingVehicle.id !== currentVehicle.id && (
        <div className="text-[10px] mt-1 text-amber-700" data-testid="vehicle-pending-banner">
          Pending: <b>{currentVehicle.registration_number || "—"}</b> → <b>{pendingVehicle.registration_number}</b>
        </div>
      )}
      {open && (
        <div className="absolute z-20 left-0 right-0 mt-1 bg-white border border-slate-200 rounded-md shadow-lg max-h-64 overflow-auto" data-testid="vehicle-picker-menu">
          <input
            autoFocus data-testid="vehicle-picker-input"
            value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="Search rego / make / model"
            className="w-full text-sm px-2 py-1.5 border-b border-slate-100 outline-none"
          />
          {results.length === 0 && <div className="text-xs text-slate-400 px-2 py-2">No matches</div>}
          {results.map((v) => (
            <button
              key={v.id} type="button"
              data-testid={`vehicle-picker-option-${v.id}`}
              onClick={() => { onSelect(v); setOpen(false); setQ(""); }}
              className="w-full text-left px-2 py-1.5 hover:bg-slate-50 text-xs border-b border-slate-50 last:border-b-0"
            >
              <div className="font-medium font-mono text-slate-900">{v.registration_number}</div>
              <div className="text-[10px] text-slate-500">{[v.make, v.model, v.carrier_configuration, v.vehicle_status].filter(Boolean).join(" · ")}</div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Equipment slot (Tray / Trailer) ───────────────────────────────────────
function EquipmentSlot({ role, testidPrefix, currentEq, pendingEq, onSelect }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const anchorRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    const t = setTimeout(async () => {
      try {
        const { data } = await api.get("/equipment", { params: { include_archived: false } });
        const term = q.trim().toLowerCase();
        const only = data.filter((e) => e.equipment_type === role && !e.is_archived);
        const filtered = term
          ? only.filter((e) => (e.equipment_number || "").toLowerCase().includes(term))
          : only;
        setResults(filtered.slice(0, 30));
      } catch { setResults([]); }
    }, 200);
    return () => clearTimeout(t);
  }, [q, open, role]);

  useEffect(() => {
    const h = (e) => { if (anchorRef.current && !anchorRef.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  const label = pendingEq
    ? `Pending: ${pendingEq.equipment_number}`
    : currentEq?.equipment_number || `— No ${role} —`;

  return (
    <div ref={anchorRef} className="relative" data-testid={`${testidPrefix}-picker`}>
      <div className="text-[10px] uppercase tracking-[0.15em] text-slate-500 mb-1">{role}</div>
      <button
        type="button"
        data-testid={`${testidPrefix}-picker-toggle`}
        onClick={() => setOpen((v) => !v)}
        className={`w-full text-left text-sm px-2 py-1.5 rounded-md border ${pendingEq ? "border-amber-300 bg-amber-50" : "border-slate-200"} hover:border-cyan-400 font-mono`}
      >{label}</button>
      <div className="text-[10px] mt-0.5 text-slate-500">
        {(pendingEq || currentEq)?.ownership_model || "—"}
      </div>
      {open && (
        <div className="absolute z-20 left-0 right-0 mt-1 bg-white border border-slate-200 rounded-md shadow-lg max-h-64 overflow-auto">
          <input
            autoFocus data-testid={`${testidPrefix}-picker-input`}
            value={q} onChange={(e) => setQ(e.target.value)}
            placeholder={`Search ${role} number`}
            className="w-full text-sm px-2 py-1.5 border-b border-slate-100 outline-none"
          />
          {results.length === 0 && <div className="text-xs text-slate-400 px-2 py-2">No {role} equipment</div>}
          {results.map((e) => (
            <button
              key={e.id} type="button"
              data-testid={`${testidPrefix}-picker-option-${e.id}`}
              onClick={() => { onSelect(e); setOpen(false); setQ(""); }}
              className="w-full text-left px-2 py-1.5 hover:bg-slate-50 text-xs border-b border-slate-50 last:border-b-0"
            >
              <div className="font-medium font-mono text-slate-900">{e.equipment_number}</div>
              <div className="text-[10px] text-slate-500">{[e.ownership_model, e.equipment_status].filter(Boolean).join(" · ")}</div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
