/**
 * MR-08A · Driver Setup Card — Driver Code + Dispatch #
 *
 * View mode:
 *   - Driver Code (canonical)
 *   - Dispatch Number (canonical, may be inactive 100–999 for Inactive drivers)
 *   - Start Date, Driver Status, Contract link, history link
 *
 * Edit mode:
 *   - Driver Code: current + suggestion preview (`GET /numbering/driver-code/suggestion`,
 *                  non-mutating) + Auto or Manual choice. Save performs canonical
 *                  reserve + driver update (allocation is the last mutation so
 *                  reservation is not orphaned unnecessarily).
 *   - Dispatch: current + manual active edit ONLY (1–99 excl 13). Inactive 999-down
 *               is system-driven on status transition — not exposed as a manual pick.
 *   - Start Date + Status remain editable.
 *
 * Backend authorities:
 *   POST /numbering/driver-code/reserve  (automatic or manual)
 *   PUT  /drivers/{id}                    (persists driver_code, driver_status, start_date)
 *   POST /numbering/dispatch/reserve      (active reservation)
 *
 * Backend owns collision + reserved (0/13) + range validation.
 */
import React, { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { CaretRight, ArrowsClockwise } from "@phosphor-icons/react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "../../lib/api";
import { ROLE_CAN_EDIT_SETUP, ManagementCard, InlineField, EditInput } from "./driverCCUtils";

export default function DriverSetupCard({ data, role, onSaved }) {
  const d = data.driver || {};
  const canEdit = ROLE_CAN_EDIT_SETUP.has(role);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);
  const initial = useRef({});
  const [codeSuggestion, setCodeSuggestion] = useState(null);
  const [codeMode, setCodeMode] = useState("keep"); // keep | auto | manual

  const startEdit = () => {
    const f = {
      start_date: d.start_date || "",
      driver_status: d.driver_status || "Active",
      driver_code: d.driver_code || "",
      dispatch_number: d.dispatch_number || "",
    };
    initial.current = f;
    setForm(f);
    setCodeMode("keep");
    setCodeSuggestion(null);
    setEditing(true);
  };
  const dirty = editing && (
    JSON.stringify({ start_date: form.start_date, driver_status: form.driver_status }) !==
    JSON.stringify({ start_date: initial.current.start_date, driver_status: initial.current.driver_status })
    || codeMode !== "keep"
    || form.dispatch_number !== (initial.current.dispatch_number || "")
  );

  const previewCode = useCallback(async () => {
    // Non-mutating: uses /suggestion only (never /reserve).
    try {
      const { data: s } = await api.get("/numbering/driver-code/suggestion");
      setCodeSuggestion(s.suggested_driver_code);
    } catch {
      setCodeSuggestion(null);
      toast.error("Suggestion unavailable");
    }
  }, []);

  const save = async () => {
    setSaving(true);
    let codeReservationId = null;
    let dispatchReservationId = null;
    // MR-08A-FIX2 · Track WHERE we are in the reserve → PUT → consume sequence.
    // Only release reservations if the Driver PUT itself failed. Once the
    // Driver record has been mutated, releasing would falsely mark an
    // owned number as Released. In that case surface the error and refresh
    // canonical state, but LEAVE the reservation intact for reconciliation.
    let driverWriteSucceeded = false;
    let codeConsumed = false;
    let dispatchConsumed = false;
    try {
      const patch = {};
      if (form.start_date !== initial.current.start_date) patch.start_date = form.start_date;
      if (form.driver_status !== initial.current.driver_status) patch.driver_status = form.driver_status;

      // Driver Code allocation (canonical reserve → PUT → consume)
      if (codeMode === "auto") {
        const { data: res } = await api.post("/numbering/driver-code/reserve", {});
        codeReservationId = res.reservation_id;
        patch.driver_code = res.identifier_value;
      } else if (codeMode === "manual") {
        const raw = String(form.driver_code || "").trim();
        if (!raw) throw new Error("Driver Code is required for manual allocation");
        if (raw !== (initial.current.driver_code || "")) {
          const { data: res } = await api.post("/numbering/driver-code/reserve",
                                               { value: raw, manual: true });
          codeReservationId = res.reservation_id;
          patch.driver_code = res.identifier_value;
        }
      }
      // MR-08A-FIX Defect 4 · When target status is Inactive, do NOT reserve
      // any manual active Dispatch. Backend allocates 100-999 automatically.
      // Same applies when the driver already holds an inactive number and
      // the target is Active — backend restores/allocates 1-99.
      const targetStatus = form.driver_status;
      const priorDispatch = String(initial.current.dispatch_number || "").trim();
      const newDispatch = String(form.dispatch_number || "").trim();
      const priorStatus = initial.current.driver_status;
      const priorIsInactive = priorStatus === "Inactive";
      const targetIsInactive = targetStatus === "Inactive";
      const statusTransitionAutoDispatch =
        (targetIsInactive && !priorIsInactive) ||
        (targetStatus === "Active" && priorIsInactive);
      const dispatchChanged = newDispatch !== priorDispatch && newDispatch !== "";
      if (dispatchChanged && !targetIsInactive && !statusTransitionAutoDispatch) {
        const { data: res } = await api.post("/numbering/dispatch/reserve",
                                             { value: Number(newDispatch), driver_id: d.id });
        dispatchReservationId = res.reservation_id;
        patch.dispatch_number = res.dispatch_number;
      }

      if (Object.keys(patch).length) {
        await api.put(`/drivers/${d.id}`, patch);
      }
      driverWriteSucceeded = true;

      // MR-08A-FIX Defect 1 · Successful save must consume reservations.
      // MR-08A-FIX2 · Each consume is independent; failure of one does NOT
      // release any already-successful consume nor release the failing
      // reservation (Driver already owns the number).
      if (codeReservationId) {
        try {
          await api.post("/numbering/driver-code/consume",
                         { reservation_id: codeReservationId, driver_id: d.id });
          codeConsumed = true;
        } catch (consumeErr) {
          throw consumeErr;
        }
      }
      if (dispatchReservationId) {
        try {
          await api.post("/numbering/dispatch/consume",
                         { reservation_id: dispatchReservationId, driver_id: d.id });
          dispatchConsumed = true;
        } catch (consumeErr) {
          throw consumeErr;
        }
      }

      toast.success("Driver setup saved");
      setEditing(false);
      setCodeMode("keep");
      setCodeSuggestion(null);
      await onSaved?.();
    } catch (err) {
      if (!driverWriteSucceeded) {
        // Pre-write failure — safe to release any newly-created reservations.
        if (codeReservationId && !codeConsumed) {
          try { await api.post("/numbering/driver-code/release", { reservation_id: codeReservationId }); }
          catch { /* best-effort */ }
        }
        if (dispatchReservationId && !dispatchConsumed) {
          try { await api.post("/numbering/dispatch/release", { reservation_id: dispatchReservationId }); }
          catch { /* best-effort */ }
        }
      }
      // MR-08A-FIX2 · If driverWriteSucceeded but a consume failed, DO NOT
      // release — the Driver already owns the number. Surface the error and
      // refresh canonical state so the UI stops showing stale values.
      toast.error(formatApiErrorDetail(err?.response?.data?.detail) || err.message || "Save failed");
      await onSaved?.();
    } finally { setSaving(false); }
  };

  const contract = data.documents?.driver_contract;
  const allocSource = (data.allocation_events || []).find((e) => e.identifier_type === "Driver Code");
  const src = allocSource
    ? (allocSource.automatic ? "Automatic" : allocSource.manual_override ? "Manual override" : "System")
    : "—";

  return (
    <ManagementCard
      testid="card-driver-setup" section="driver-setup"
      title="Driver Setup" subtitle="Identifiers, status, contract"
      canEdit={canEdit}
      editing={editing} saving={saving} dirty={dirty}
      onEditToggle={startEdit}
      onCancel={() => { setEditing(false); setCodeMode("keep"); setCodeSuggestion(null); }}
      onSave={save}
    >
      {editing ? (
        <>
          {/* Driver Code (Auto / Manual / Keep) */}
          <div>
            <div className="text-[10px] uppercase tracking-[0.15em] text-slate-500 mb-1">Driver Code</div>
            <div className="flex items-center gap-2 flex-wrap">
              <select
                data-testid="driver-code-mode"
                value={codeMode}
                onChange={(e) => setCodeMode(e.target.value)}
                className="border border-slate-200 rounded-md px-2 py-1.5 text-sm"
              >
                <option value="keep">Keep {d.driver_code ? `(#${d.driver_code})` : "current"}</option>
                <option value="auto">Automatic (next available)</option>
                <option value="manual">Manual…</option>
              </select>
              {codeMode === "manual" && (
                <input
                  data-testid="driver-code-manual-input"
                  value={form.driver_code || ""}
                  onChange={(e) => setForm({ ...form, driver_code: e.target.value })}
                  placeholder="Driver Code"
                  className="w-32 border border-slate-200 rounded-md px-2 py-1.5 text-sm font-mono"
                />
              )}
              {codeMode === "auto" && (
                <button
                  type="button"
                  data-testid="driver-code-preview-btn"
                  onClick={previewCode}
                  className="text-[11px] px-2 py-1 rounded border border-slate-200 hover:bg-slate-50 inline-flex items-center gap-1"
                ><ArrowsClockwise size={11} /> Preview</button>
              )}
            </div>
            {codeMode === "auto" && codeSuggestion && (
              <div className="text-[11px] text-slate-500 mt-1" data-testid="driver-code-suggestion">
                Suggestion: <b className="font-mono">{codeSuggestion}</b> — reserved on Save
              </div>
            )}
          </div>

          {/* Dispatch (manual active only) — MR-08A-FIX Defect 4:
              disabled when target status is Inactive; backend allocates 999-down. */}
          <div>
            <div className="text-[10px] uppercase tracking-[0.15em] text-slate-500 mb-1">Dispatch #</div>
            <input
              data-testid="edit-dispatch-number"
              value={form.dispatch_number || ""}
              onChange={(e) => setForm({ ...form, dispatch_number: e.target.value.replace(/[^0-9]/g, "") })}
              placeholder="1–99 excl 13"
              disabled={form.driver_status === "Inactive"}
              className="w-32 border border-slate-200 rounded-md px-2 py-1.5 text-sm font-mono disabled:bg-slate-50 disabled:text-slate-400"
            />
            {form.driver_status === "Inactive" ? (
              <div data-testid="dispatch-inactive-hint" className="text-[10px] text-slate-500 mt-0.5">
                Inactive Dispatch is allocated automatically.
              </div>
            ) : initial.current.driver_status === "Inactive" && form.driver_status === "Active" ? (
              <div data-testid="dispatch-reactivate-hint" className="text-[10px] text-slate-500 mt-0.5">
                Backend will restore your previous active number if free, or auto-allocate 1–99.
              </div>
            ) : (
              <div className="text-[10px] text-slate-500 mt-0.5">Inactive numbers are allocated automatically by status.</div>
            )}
          </div>

          <EditInput label="Start Date" type="date" value={form.start_date} onChange={(v) => setForm({ ...form, start_date: v })} testid="edit-start-date" />
          <div>
            <div className="text-[10px] uppercase tracking-[0.15em] text-slate-500 mb-1">Status</div>
            <select
              value={form.driver_status}
              onChange={(e) => setForm({ ...form, driver_status: e.target.value })}
              data-testid="edit-driver-status"
              className="w-full border border-slate-200 rounded-md px-2 py-1.5 text-sm"
            >
              {
                // MR-07B-FIX · Only Admin/Manager may transition a Driver into
                // Active. Allocator sees setup transitions only.
                // MR-07B-FIX2 · Archived is a canonical archive-endpoint action
                // (DELETE /api/drivers/{id}); it is NOT selectable from setup.
                // Current-state passthrough preserved for either state so an
                // already-Active or already-Archived driver still renders a
                // valid option in the select.
                (["Active", "Training", "Probation", "On Leave", "Inactive", "Archived"])
                  .filter((s) => {
                    if (s === "Archived") return form.driver_status === "Archived";
                    if (s !== "Active") return true;
                    if (["Admin", "Manager"].includes(role)) return true;
                    return form.driver_status === "Active"; // already Active — allow passthrough
                  })
                  .map((s) => <option key={s} value={s}>{s}</option>)
              }
            </select>
          </div>
        </>
      ) : (
        <>
          <InlineField label="Driver Code" value={d.driver_code} testid="field-driver-code" mono />
          <InlineField label="Dispatch #" value={d.dispatch_number} testid="field-dispatch-number" mono />
          <InlineField label="Start Date" value={d.start_date} testid="field-start-date" />
          <InlineField label="Status" value={d.driver_status} testid="field-driver-status" />
          <InlineField label="Allocation" value={src} testid="field-allocation-source" />
          <div className="grid grid-cols-[110px_1fr] gap-3 items-baseline">
            <div className="text-[10px] uppercase tracking-[0.15em] text-slate-500">Contract</div>
            <div className="text-sm">
              {contract ? (
                <Link to={`/documents?doc=${contract.id}`} data-testid="driver-contract-link"
                      className="text-cyan-700 hover:underline inline-flex items-center gap-1">
                  Open contract <CaretRight size={11} />
                </Link>
              ) : <span data-testid="driver-contract-empty" className="text-slate-300">Not on file</span>}
            </div>
          </div>
          <div className="grid grid-cols-[110px_1fr] gap-3 items-baseline">
            <div className="text-[10px] uppercase tracking-[0.15em] text-slate-500">History</div>
            <Link to="/administration/numbering" data-testid="allocation-history-link" className="text-cyan-700 hover:underline text-sm">
              {(data.allocation_events || []).length} events · Numbering admin
            </Link>
          </div>
        </>
      )}
    </ManagementCard>
  );
}
