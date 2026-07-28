/**
 * EB-09 · Final Three-Row DCC Driver Command Centre Profile
 * -------------------------------------------------------
 * Desktop-first (1920 × 1080). Three horizontal Management rows on the left,
 * a sticky Compliance Intelligence column on the right.
 *
 * Data comes from the read-only aggregator:
 *   GET /api/drivers/{id}/command-centre-profile
 *
 * Each Management card owns its own edit lifecycle (local save / cancel /
 * dirty warning). No cross-card accidental saves.
 *
 * Legacy profile still reachable via ?view=legacy.
 * Deep-link a section via ?section=<key>.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useSearchParams, Link, Navigate } from "react-router-dom";
import { toast } from "sonner";
import AppHeader from "../components/app/AppHeader";
import api, { formatApiErrorDetail } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import DriverProfileLegacy from "./DriverProfile";
import {
  User,
  ArrowUpRight,
  Phone,
  EnvelopeSimple,
  MapPin,
  IdentificationCard,
  Warning,
  CheckCircle,
  PencilSimple,
  X,
  CaretRight,
  ShieldCheck,
  Truck,
  Files,
  UploadSimple,
  ClipboardText,
  NoteBlank,
  PushPin,
  Bell,
  Buildings,
} from "@phosphor-icons/react";

const ROLE_CAN_EDIT_ACCOUNT = new Set(["Admin", "Manager"]);
const ROLE_CAN_EDIT = new Set(["Admin", "Manager", "Allocator"]);

// ═══════════════════════════════════════════════════════════════════════════
// Page shell
// ═══════════════════════════════════════════════════════════════════════════
export default function DriverCommandCentre() {
  const { driverId } = useParams();
  const [sp] = useSearchParams();
  const legacy = sp.get("view") === "legacy";
  if (legacy) return <DriverProfileLegacy />;
  return <CommandCentreInner driverId={driverId} sectionAnchor={sp.get("section")} />;
}

function CommandCentreInner({ driverId, sectionAnchor }) {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [failed, setFailed] = useState(false);

  const refresh = useCallback(async () => {
    setFailed(false);
    try {
      const { data: d } = await api.get(`/drivers/${driverId}/command-centre-profile`);
      setData(d);
    } catch (err) {
      if (err?.response?.status === 404) { setNotFound(true); return; }
      setFailed(true);
      toast.error(formatApiErrorDetail(err?.response?.data?.detail) || "Could not load Driver Profile");
    } finally {
      setLoading(false);
    }
  }, [driverId]);

  useEffect(() => { refresh(); }, [refresh]);

  useEffect(() => {
    if (!sectionAnchor || loading) return;
    const el = document.querySelector(`[data-section="${sectionAnchor}"]`);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [sectionAnchor, loading]);

  if (notFound) return <Navigate to="/registers/drivers" replace />;

  const driver = data?.driver;
  const role = user?.role || "ReadOnly";

  return (
    <div className="min-h-screen bg-slate-50" data-testid="driver-command-centre">
      <AppHeader showBack />

      <main className="w-full px-4 lg:px-8 py-6 mx-auto" style={{ maxWidth: 1920 }}>
        <ProfileHeader driver={driver} data={data} loading={loading} driverId={driverId} />

        {failed && (
          <div className="mb-4 p-3 rounded-lg bg-red-50 border border-red-200 text-sm text-red-800 flex items-center justify-between" data-testid="profile-load-error">
            <span>Could not load some of the Driver Profile. Try again.</span>
            <button onClick={refresh} className="text-red-900 underline text-xs" data-testid="profile-load-retry">Retry</button>
          </div>
        )}

        <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_420px] gap-6">
          {/* LEFT — Management Layer */}
          <div className="min-w-0 space-y-6">
            {loading ? (
              <SkeletonRow /> ) : data ? (
              <>
                {/* Row 1 */}
                <ManagementRow>
                  <DriverDetailsCard data={data} role={role} onSaved={refresh} />
                  <AccountDetailsCard data={data} role={role} onSaved={refresh} />
                  <DriverSetupCard data={data} role={role} onSaved={refresh} />
                </ManagementRow>
                {/* Row 2 */}
                <ManagementRow>
                  <CommunicationCard data={data} role={role} driverId={driverId} onSaved={refresh} />
                  <CarCarrierCard data={data} />
                  <OwnerDetailsCard data={data} />
                </ManagementRow>
                {/* Row 3 */}
                <ManagementRow>
                  <AdminUtilitiesCard data={data} driverId={driverId} role={role} />
                  <ActivationCard data={data} />
                  <NotesCard data={data} role={role} driverId={driverId} onChanged={refresh} />
                </ManagementRow>
              </>
            ) : null}
          </div>

          {/* RIGHT — Compliance Intelligence Layer (sticky on desktop) */}
          <aside className="xl:sticky xl:top-6 xl:self-start space-y-4" data-testid="compliance-intelligence-layer" data-section="compliance">
            {loading ? <SkeletonRight /> : data ? (
              <>
                <ComplianceOverviewCard data={data} driverId={driverId} />
                <LicenceCard data={data} />
                <TruckRegoCard data={data} />
                <TruckInsuranceCard data={data} />
                <VehicleComplianceCard data={data} />
                <DocumentsCard data={data} driverId={driverId} />
              </>
            ) : null}
          </aside>
        </div>
      </main>
    </div>
  );
}

function ManagementRow({ children }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">{children}</div>
  );
}

function SkeletonRow() {
  return (
    <div className="space-y-6">
      {[1, 2, 3].map((r) => (
        <div key={r} className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[1, 2, 3].map((c) => (
            <div key={c} className="h-52 bg-white rounded-xl border border-slate-200 animate-pulse" />
          ))}
        </div>
      ))}
    </div>
  );
}
function SkeletonRight() {
  return (
    <>
      {[1, 2, 3, 4, 5, 6].map((i) => (
        <div key={i} className="h-32 bg-white rounded-xl border border-slate-200 animate-pulse" />
      ))}
    </>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Header
// ═══════════════════════════════════════════════════════════════════════════
function ProfileHeader({ driver, data, loading, driverId }) {
  const worstStatus = data?.compliance_intelligence?.worst_status;
  const activeAlerts = data?.alert_counts?.active || 0;
  if (loading) return <div className="mb-6 h-24 bg-white rounded-xl border border-slate-200 animate-pulse" />;
  if (!driver) return null;
  return (
    <section className="mb-6" data-testid="driver-cc-header">
      <div className="flex flex-wrap items-start justify-between gap-4 bg-white border border-slate-200 rounded-xl px-6 py-5">
        <div className="flex items-start gap-4 min-w-0">
          <ProfilePhotoBadge photo={data?.documents?.profile_photo} name={driver.full_name} />
          <div className="min-w-0">
            <div className="text-[10px] uppercase tracking-[0.25em] text-slate-500 mb-1">
              <Link to="/registers/drivers" className="hover:text-slate-900" data-testid="cc-back-register">Driver Register</Link>
              <span className="mx-2">/</span>
              <span>Command Centre</span>
            </div>
            <h1 className="font-display text-2xl lg:text-3xl font-semibold text-slate-900 truncate" data-testid="cc-driver-name">
              {driver.full_name}
            </h1>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
              {driver.driver_code && (
                <span data-testid="cc-driver-code" className="inline-flex items-center gap-1 border border-slate-200 rounded-full px-2 py-0.5 text-slate-700 bg-slate-50 font-medium">
                  <IdentificationCard size={11} weight="bold" /> {driver.driver_code}
                </span>
              )}
              {driver.dispatch_number && (
                <span data-testid="cc-dispatch-number" className="inline-flex items-center gap-1 border border-cyan-200 rounded-full px-2 py-0.5 text-cyan-800 bg-cyan-50 font-medium">
                  Dispatch {driver.dispatch_number}
                </span>
              )}
              <StatusPill status={driver.driver_status} testid="cc-driver-status" />
              {driver.company_ref && (
                <span className="inline-flex items-center gap-1 text-slate-600">
                  <Buildings size={11} /> {driver.company_ref}
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <HeaderBadge
            testid="cc-worst-status"
            label="Overall Status"
            value={worstStatus || "—"}
            variant={statusVariant(worstStatus)}
          />
          <HeaderBadge
            testid="cc-active-alerts"
            label="Active Alerts"
            value={String(activeAlerts)}
            variant={activeAlerts > 0 ? "warn" : "ok"}
            linkTo={`/notifications/all?entity_type=Driver&entity_id=${driverId}`}
          />
          <Link
            to={`/drivers/${driverId}?view=legacy`}
            data-testid="cc-legacy-view"
            className="text-xs text-slate-500 hover:text-slate-900 underline decoration-dotted"
          >
            Legacy view
          </Link>
        </div>
      </div>
    </section>
  );
}

function ProfilePhotoBadge({ photo, name }) {
  const initial = (name || "?").slice(0, 1).toUpperCase();
  return (
    <div className="relative">
      <div className="h-14 w-14 rounded-xl bg-slate-900 text-white grid place-items-center font-display font-semibold text-xl" data-testid="cc-profile-photo">
        {photo?.download_url ? (
          <img src={photo.download_url} alt="" className="h-full w-full rounded-xl object-cover" />
        ) : initial}
      </div>
    </div>
  );
}

function HeaderBadge({ label, value, variant = "neutral", testid, linkTo }) {
  const cls = {
    ok: "border-emerald-200 bg-emerald-50 text-emerald-800",
    warn: "border-amber-200 bg-amber-50 text-amber-800",
    danger: "border-red-200 bg-red-50 text-red-800",
    neutral: "border-slate-200 bg-white text-slate-800",
  }[variant];
  const Inner = (
    <div className={`rounded-lg border ${cls} px-3 py-1.5 min-w-[130px]`} data-testid={testid}>
      <div className="text-[9px] uppercase tracking-[0.2em] opacity-80">{label}</div>
      <div className="text-sm font-semibold">{value}</div>
    </div>
  );
  return linkTo ? <Link to={linkTo}>{Inner}</Link> : Inner;
}

// ═══════════════════════════════════════════════════════════════════════════
// Reusable Management Card scaffold with per-card edit lifecycle
// ═══════════════════════════════════════════════════════════════════════════
function ManagementCard({
  title, subtitle, testid, section, canEdit = true, editing, onEditToggle,
  saving, dirty, onSave, onCancel, footer, children,
}) {
  const askIfDirty = (proceed) => {
    if (dirty && !window.confirm("Discard unsaved changes on this card?")) return;
    proceed();
  };
  return (
    <div
      className="bg-white border border-slate-200 rounded-xl shadow-sm flex flex-col h-full min-h-[220px]"
      data-testid={testid}
      data-section={section}
    >
      <div className="px-4 pt-4 pb-3 border-b border-slate-100 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-[0.22em] text-slate-500">{title}</div>
          {subtitle && <div className="text-[11px] text-slate-500 mt-0.5 truncate">{subtitle}</div>}
        </div>
        {canEdit && (
          editing ? (
            <div className="flex items-center gap-1">
              <button
                type="button"
                data-testid={`${testid}-cancel`}
                onClick={() => askIfDirty(onCancel)}
                className="text-[11px] px-2 py-1 rounded text-slate-600 hover:text-slate-900"
              >Cancel</button>
              <button
                type="button"
                data-testid={`${testid}-save`}
                disabled={saving}
                onClick={onSave}
                className="text-[11px] px-2.5 py-1 rounded bg-slate-900 text-white hover:bg-slate-800 disabled:opacity-50"
              >{saving ? "Saving…" : "Save"}</button>
            </div>
          ) : (
            <button
              type="button"
              data-testid={`${testid}-edit`}
              onClick={onEditToggle}
              className="inline-flex items-center gap-1 text-[11px] text-slate-500 hover:text-slate-900"
            ><PencilSimple size={11} weight="bold" /> Edit</button>
          )
        )}
      </div>
      <div className="px-4 py-3 text-sm space-y-2 flex-1">{children}</div>
      {footer && <div className="px-4 py-3 border-t border-slate-100 text-xs text-slate-500">{footer}</div>}
    </div>
  );
}

function InlineField({ label, value, testid, mono }) {
  return (
    <div className="grid grid-cols-[110px_1fr] gap-3 items-baseline">
      <div className="text-[10px] uppercase tracking-[0.15em] text-slate-500">{label}</div>
      <div data-testid={testid} className={`text-sm text-slate-900 ${mono ? "font-mono" : ""} break-words`}>
        {value == null || value === "" ? <span className="text-slate-300">—</span> : value}
      </div>
    </div>
  );
}

function EditInput({ label, value, onChange, type = "text", testid }) {
  return (
    <label className="block">
      <div className="text-[10px] uppercase tracking-[0.15em] text-slate-500 mb-1">{label}</div>
      <input
        type={type}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        data-testid={testid}
        className="w-full border border-slate-200 rounded-md px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500/20 focus:border-cyan-500"
      />
    </label>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Row 1
// ═══════════════════════════════════════════════════════════════════════════
function DriverDetailsCard({ data, role, onSaved }) {
  const d = data.driver || {};
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);
  const initial = useRef({});
  const canEdit = ROLE_CAN_EDIT.has(role);

  const startEdit = () => {
    const f = {
      residential_address: d.residential_address || "",
      mobile_number: d.mobile_number || "",
      email: d.email || "",
      emergency_contact_name: d.emergency_contact_name || "",
      emergency_contact_phone: d.emergency_contact_phone || "",
    };
    initial.current = f;
    setForm(f);
    setEditing(true);
  };
  const dirty = editing && JSON.stringify(form) !== JSON.stringify(initial.current);

  const save = async () => {
    setSaving(true);
    try {
      await api.put(`/drivers/${d.id}`, form);
      toast.success("Driver details saved");
      setEditing(false);
      await onSaved?.();
    } catch (err) {
      toast.error(formatApiErrorDetail(err?.response?.data?.detail) || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <ManagementCard
      testid="card-driver-details"
      section="driver-details"
      title="Driver Details"
      subtitle="Canonical identity + contact"
      canEdit={canEdit}
      editing={editing}
      saving={saving}
      dirty={dirty}
      onEditToggle={startEdit}
      onCancel={() => setEditing(false)}
      onSave={save}
    >
      {editing ? (
        <>
          <EditInput label="Residential Address" value={form.residential_address} onChange={(v) => setForm({ ...form, residential_address: v })} testid="edit-residential-address" />
          <EditInput label="Mobile Number" value={form.mobile_number} onChange={(v) => setForm({ ...form, mobile_number: v })} testid="edit-mobile-number" />
          <EditInput label="Email" type="email" value={form.email} onChange={(v) => setForm({ ...form, email: v })} testid="edit-email" />
          <EditInput label="Emergency Name" value={form.emergency_contact_name} onChange={(v) => setForm({ ...form, emergency_contact_name: v })} testid="edit-emergency-name" />
          <EditInput label="Emergency Phone" value={form.emergency_contact_phone} onChange={(v) => setForm({ ...form, emergency_contact_phone: v })} testid="edit-emergency-phone" />
        </>
      ) : (
        <>
          <InlineField label="Address" value={d.residential_address} testid="field-residential-address" />
          <InlineField label="Mobile" value={d.mobile_number ? <a href={`tel:${d.mobile_number}`} className="text-cyan-700 hover:underline">{d.mobile_number}</a> : null} testid="field-mobile" />
          <InlineField label="Email" value={d.email ? <a href={`mailto:${d.email}`} className="text-cyan-700 hover:underline">{d.email}</a> : null} testid="field-email" />
          <InlineField label="Emergency" value={d.emergency_contact_name || null} testid="field-emergency-name" />
          <InlineField label="Emerg. Phone" value={d.emergency_contact_phone || null} testid="field-emergency-phone" />
        </>
      )}
    </ManagementCard>
  );
}

function AccountDetailsCard({ data, role, onSaved }) {
  const d = data.driver || {};
  const restricted = (data.restricted_fields || []).length > 0;
  const canEdit = ROLE_CAN_EDIT_ACCOUNT.has(role);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);
  const initial = useRef({});

  const startEdit = () => {
    const f = {
      business_name: d.business_name || "",
      abn: d.abn || "",
      payroll_number: d.payroll_number || "",
      payment_percentage: d.payment_percentage ?? "",
    };
    initial.current = f;
    setForm(f);
    setEditing(true);
  };
  const dirty = editing && JSON.stringify(form) !== JSON.stringify(initial.current);

  const save = async () => {
    setSaving(true);
    try {
      const payload = { ...form };
      if (payload.payment_percentage === "" || payload.payment_percentage == null) delete payload.payment_percentage;
      else payload.payment_percentage = Number(payload.payment_percentage);
      await api.put(`/drivers/${d.id}`, payload);
      toast.success("Account details saved");
      setEditing(false);
      await onSaved?.();
    } catch (err) {
      toast.error(formatApiErrorDetail(err?.response?.data?.detail) || "Save failed");
    } finally { setSaving(false); }
  };

  return (
    <ManagementCard
      testid="card-account-details"
      section="account-details"
      title="Account Details"
      subtitle="Business, ABN, payroll"
      canEdit={canEdit}
      editing={editing}
      saving={saving}
      dirty={dirty}
      onEditToggle={startEdit}
      onCancel={() => setEditing(false)}
      onSave={save}
      footer={restricted ? <span data-testid="account-restricted-note">Sensitive financial fields are hidden for your role.</span> : null}
    >
      {restricted && !editing ? (
        <div className="text-xs text-slate-500 italic">Restricted view — sensitive account fields are not returned by the server for your role.</div>
      ) : editing ? (
        <>
          <EditInput label="Business Name" value={form.business_name} onChange={(v) => setForm({ ...form, business_name: v })} testid="edit-business-name" />
          <EditInput label="ABN" value={form.abn} onChange={(v) => setForm({ ...form, abn: v })} testid="edit-abn" />
          <EditInput label="Payroll #" value={form.payroll_number} onChange={(v) => setForm({ ...form, payroll_number: v })} testid="edit-payroll" />
          <EditInput label="Payment %" type="number" value={form.payment_percentage} onChange={(v) => setForm({ ...form, payment_percentage: v })} testid="edit-payment-pct" />
        </>
      ) : (
        <>
          <InlineField label="Business" value={d.business_name} testid="field-business-name" />
          <InlineField label="ABN" value={d.abn} testid="field-abn" mono />
          <InlineField label="Payroll #" value={d.payroll_number} testid="field-payroll" mono />
          <InlineField label="Payment %" value={d.payment_percentage != null ? `${d.payment_percentage}%` : null} testid="field-payment-pct" />
        </>
      )}
    </ManagementCard>
  );
}

function DriverSetupCard({ data, role, onSaved }) {
  const d = data.driver || {};
  const canEdit = ROLE_CAN_EDIT.has(role);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);
  const initial = useRef({});

  const startEdit = () => {
    const f = {
      start_date: d.start_date || "",
      driver_status: d.driver_status || "Active",
    };
    initial.current = f;
    setForm(f);
    setEditing(true);
  };
  const dirty = editing && JSON.stringify(form) !== JSON.stringify(initial.current);
  const save = async () => {
    setSaving(true);
    try {
      await api.put(`/drivers/${d.id}`, form);
      toast.success("Driver setup saved");
      setEditing(false);
      await onSaved?.();
    } catch (err) {
      toast.error(formatApiErrorDetail(err?.response?.data?.detail) || "Save failed");
    } finally { setSaving(false); }
  };

  const contract = data.documents?.driver_contract;
  const allocSource = (data.allocation_events || []).find((e) => e.identifier_type === "Driver Code");
  const src = allocSource
    ? (allocSource.automatic ? "Automatic" : allocSource.manual_override ? "Manual override" : "System")
    : "—";

  return (
    <ManagementCard
      testid="card-driver-setup"
      section="driver-setup"
      title="Driver Setup"
      subtitle="Identifiers, status, contract"
      canEdit={canEdit}
      editing={editing}
      saving={saving}
      dirty={dirty}
      onEditToggle={startEdit}
      onCancel={() => setEditing(false)}
      onSave={save}
    >
      {editing ? (
        <>
          <EditInput label="Start Date" type="date" value={form.start_date} onChange={(v) => setForm({ ...form, start_date: v })} testid="edit-start-date" />
          <div>
            <div className="text-[10px] uppercase tracking-[0.15em] text-slate-500 mb-1">Status</div>
            <select
              value={form.driver_status}
              onChange={(e) => setForm({ ...form, driver_status: e.target.value })}
              data-testid="edit-driver-status"
              className="w-full border border-slate-200 rounded-md px-2 py-1.5 text-sm"
            >
              {["Active", "Inactive", "On Leave", "Archived"].map((s) => <option key={s} value={s}>{s}</option>)}
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
                <Link
                  to={`/documents?doc=${contract.id}`}
                  data-testid="driver-contract-link"
                  className="text-cyan-700 hover:underline inline-flex items-center gap-1"
                >
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

// ═══════════════════════════════════════════════════════════════════════════
// Row 2
// ═══════════════════════════════════════════════════════════════════════════
function CommunicationCard({ data, role, driverId, onSaved }) {
  const canEdit = ROLE_CAN_EDIT.has(role);
  const prefs = data.communication_preferences;
  const driverEmail = data.driver?.email;
  const ownerEmail = data.owner?.contact_email || data.owner?.email;
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);
  const initial = useRef({});

  const startEdit = () => {
    const f = {
      owner_report_email_override: prefs?.owner_report_email_override || "",
      driver_report_email_override: prefs?.driver_report_email_override || "",
      send_daily_report_owner: !!prefs?.send_daily_report_owner,
      send_daily_report_driver: !!prefs?.send_daily_report_driver,
      display_on_dispatch: prefs ? !!prefs.display_on_dispatch : true,
    };
    initial.current = f;
    setForm(f);
    setEditing(true);
  };
  const dirty = editing && JSON.stringify(form) !== JSON.stringify(initial.current);

  const save = async () => {
    setSaving(true);
    try {
      await api.put(`/drivers/${driverId}/communication-preferences`, form);
      toast.success("Communication preferences saved (delivery is simulated)");
      setEditing(false);
      await onSaved?.();
    } catch (err) {
      toast.error(formatApiErrorDetail(err?.response?.data?.detail) || "Save failed");
    } finally { setSaving(false); }
  };

  return (
    <ManagementCard
      testid="card-communication"
      section="communication"
      title="Communication & Integration"
      subtitle="Report delivery preferences"
      canEdit={canEdit}
      editing={editing}
      saving={saving}
      dirty={dirty}
      onEditToggle={startEdit}
      onCancel={() => setEditing(false)}
      onSave={save}
      footer={<span>Delivery is <strong>simulated only</strong>. Canonical emails remain source of truth.</span>}
    >
      {editing ? (
        <>
          <EditInput label="Owner report override" type="email" value={form.owner_report_email_override} onChange={(v) => setForm({ ...form, owner_report_email_override: v })} testid="edit-owner-report-email" />
          <EditInput label="Driver report override" type="email" value={form.driver_report_email_override} onChange={(v) => setForm({ ...form, driver_report_email_override: v })} testid="edit-driver-report-email" />
          <ToggleRow label="Daily report to Owner" value={form.send_daily_report_owner} onChange={(v) => setForm({ ...form, send_daily_report_owner: v })} testid="edit-toggle-owner-daily" />
          <ToggleRow label="Daily report to Driver" value={form.send_daily_report_driver} onChange={(v) => setForm({ ...form, send_daily_report_driver: v })} testid="edit-toggle-driver-daily" />
          <ToggleRow label="Display on Dispatch" value={form.display_on_dispatch} onChange={(v) => setForm({ ...form, display_on_dispatch: v })} testid="edit-toggle-display-dispatch" />
        </>
      ) : (
        <>
          <InlineField label="Owner email" value={ownerEmail || null} testid="field-owner-email" />
          <InlineField label="Owner report" value={prefs?.owner_report_email_override ? <span><em className="text-amber-700">override</em> {prefs.owner_report_email_override}</span> : (ownerEmail || null)} testid="field-owner-report" />
          <InlineField label="Driver email" value={driverEmail || null} testid="field-driver-email" />
          <InlineField label="Driver report" value={prefs?.driver_report_email_override ? <span><em className="text-amber-700">override</em> {prefs.driver_report_email_override}</span> : (driverEmail || null)} testid="field-driver-report" />
          <InlineField label="Daily owner" value={prefs?.send_daily_report_owner ? "On" : "Off"} testid="field-daily-owner" />
          <InlineField label="Daily driver" value={prefs?.send_daily_report_driver ? "On" : "Off"} testid="field-daily-driver" />
          <InlineField label="On dispatch" value={prefs?.display_on_dispatch === false ? "Hidden" : "Visible"} testid="field-display-dispatch" />
        </>
      )}
    </ManagementCard>
  );
}

function ToggleRow({ label, value, onChange, testid }) {
  return (
    <label className="flex items-center justify-between text-sm py-1">
      <span className="text-slate-700">{label}</span>
      <button
        type="button"
        role="switch"
        aria-checked={value}
        data-testid={testid}
        onClick={() => onChange(!value)}
        className={`w-9 h-5 rounded-full transition-colors ${value ? "bg-cyan-500" : "bg-slate-300"}`}
      >
        <span className={`block h-4 w-4 rounded-full bg-white shadow transform transition-transform ${value ? "translate-x-4" : "translate-x-0.5"} mt-0.5`} />
      </button>
    </label>
  );
}

function CarCarrierCard({ data }) {
  const v = data.vehicle;
  const dva = data.vehicle_assignment;
  const equipment = data.equipment_assignments || [];
  return (
    <ManagementCard
      testid="card-car-carrier"
      section="car-carrier"
      title="Car Carrier & Equipment"
      subtitle="Vehicle + tray + trailer"
      canEdit={false}
    >
      {v ? (
        <>
          <InlineField label="Vehicle" value={<Link to="/registers/vehicles" className="text-cyan-700 hover:underline">{v.registration_number}</Link>} testid="field-vehicle-rego" mono />
          <InlineField label="Make/Model" value={[v.make, v.model].filter(Boolean).join(" ") || null} testid="field-vehicle-make" />
          <InlineField label="Config" value={v.carrier_config || v.body_type || null} testid="field-vehicle-config" />
          <InlineField label="Since" value={dva?.effective_from} testid="field-vehicle-since" />
        </>
      ) : (
        <div data-testid="vehicle-empty" className="text-xs text-slate-400 italic">No primary vehicle assignment.</div>
      )}
      <div className="pt-2 border-t border-slate-100 mt-2">
        <div className="text-[10px] uppercase tracking-[0.15em] text-slate-500 mb-1">Equipment</div>
        {equipment.length === 0 ? (
          <div data-testid="equipment-empty" className="text-xs text-slate-400 italic">No active equipment.</div>
        ) : (
          <ul className="space-y-1">
            {equipment.slice(0, 4).map((row) => (
              <li key={row.assignment?.id || row.assignment?.driver_equipment_assignment_id} className="flex items-center justify-between text-xs">
                <span className="truncate font-mono text-slate-800">
                  {row.equipment?.equipment_number || row.assignment?.equipment_number_snapshot}
                </span>
                <span className="text-slate-500 truncate ml-2">{row.equipment?.equipment_type}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="pt-2">
        <Link to="/relationships/driver-vehicle" data-testid="carrier-reassign-link" className="text-[11px] text-cyan-700 hover:underline">
          Change assignment <CaretRight size={10} className="inline" />
        </Link>
      </div>
    </ManagementCard>
  );
}

function OwnerDetailsCard({ data }) {
  const owner = data.owner;
  const dor = data.owner_relationship;
  return (
    <ManagementCard
      testid="card-owner-details"
      section="owner-details"
      title="Owner Details"
      subtitle="Read-only relationship view"
      canEdit={false}
    >
      {owner ? (
        <>
          <InlineField label="Name" value={<Link to="/registers/owners" className="text-cyan-700 hover:underline">{owner.name}</Link>} testid="field-owner-name" />
          <InlineField label="Type" value={owner.owner_type} testid="field-owner-type" />
          <InlineField label="Mobile" value={owner.contact_phone || owner.phone} testid="field-owner-mobile" />
          <InlineField label="Email" value={owner.contact_email || owner.email} testid="field-owner-email-canonical" />
          <InlineField label="Relation" value={dor?.relationship_type} testid="field-relationship-type" />
          <InlineField label="Since" value={dor?.effective_from} testid="field-relationship-since" />
          <div className="pt-2">
            <Link to="/relationships/driver-owner" data-testid="owner-change-link" className="text-[11px] text-cyan-700 hover:underline">
              Change relationship <CaretRight size={10} className="inline" />
            </Link>
          </div>
        </>
      ) : (
        <div data-testid="owner-empty" className="text-xs text-slate-400 italic">No current owner relationship.</div>
      )}
    </ManagementCard>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Row 3
// ═══════════════════════════════════════════════════════════════════════════
function AdminUtilitiesCard({ data, driverId, role }) {
  const canManage = ["Admin", "Manager"].includes(role);
  const utilities = [
    { key: "docs", label: "Open Document Library", to: `/documents?entity_type=Driver&entity_id=${driverId}`, available: true, testid: "util-open-docs" },
    { key: "upload", label: "Upload supporting document", to: `/documents?entity_type=Driver&entity_id=${driverId}&upload=1`, available: true, testid: "util-upload" },
    { key: "imports", label: "Open Import Centre", to: "/imports", available: canManage, testid: "util-imports" },
    { key: "numbering", label: "Numbering admin", to: "/administration/numbering", available: true, testid: "util-numbering" },
    { key: "notifications", label: "Driver alerts", to: `/notifications/all?entity_type=Driver&entity_id=${driverId}`, available: true, testid: "util-notifications" },
  ];
  const unavailable = [
    { key: "start_sheet", label: "Generate Driver Start Sheet" },
    { key: "export", label: "Export Driver Profile" },
  ];
  return (
    <ManagementCard
      testid="card-admin-utilities"
      section="admin"
      title="Administration & Utilities"
      subtitle="Related tools & exports"
      canEdit={false}
    >
      <ul className="space-y-1.5">
        {utilities.filter(u => u.available).map((u) => (
          <li key={u.key}>
            <Link to={u.to} data-testid={u.testid} className="text-sm text-cyan-700 hover:underline inline-flex items-center gap-1">
              <CaretRight size={11} /> {u.label}
            </Link>
          </li>
        ))}
      </ul>
      <div className="pt-2 mt-2 border-t border-slate-100">
        <div className="text-[10px] uppercase tracking-[0.15em] text-slate-500 mb-1">Coming soon</div>
        <ul className="space-y-1">
          {unavailable.map((u) => (
            <li key={u.key} className="text-xs text-slate-400 flex items-center gap-1.5">
              <span data-testid={`util-unavailable-${u.key}`}>{u.label}</span>
              <span className="text-[9px] uppercase tracking-[0.15em] border border-slate-200 rounded-full px-1.5 py-0.5">Unavailable</span>
            </li>
          ))}
        </ul>
      </div>
    </ManagementCard>
  );
}

function ActivationCard({ data }) {
  const a = data.activation || {};
  const pct = a.mandatory_total ? Math.round((a.mandatory_done / a.mandatory_total) * 100) : 0;
  const readiness = a.readiness || "Not Ready";
  const variant = readiness === "Ready" ? "ok" : readiness === "Partial" ? "warn" : "danger";
  return (
    <ManagementCard
      testid="card-activation"
      section="activation"
      title="Driver Activation Checklist"
      subtitle="Evidence-validated readiness"
      canEdit={false}
    >
      <div className="flex items-center justify-between mb-2">
        <StatusPill status={readiness} testid="activation-readiness" />
        <span className="text-[11px] text-slate-500" data-testid="activation-progress">
          {a.mandatory_done}/{a.mandatory_total} mandatory · {pct}%
        </span>
      </div>
      <div className="h-1.5 w-full bg-slate-100 rounded overflow-hidden mb-2">
        <div className={`h-full ${variant === "ok" ? "bg-emerald-500" : variant === "warn" ? "bg-amber-500" : "bg-red-500"}`} style={{ width: `${pct}%` }} />
      </div>
      <ul className="space-y-1 text-xs max-h-40 overflow-y-auto">
        {(a.items || []).slice(0, 8).map((it) => (
          <li key={it.item_key} className="flex items-start gap-2" data-testid={`activation-item-${it.item_key}`}>
            {it.complete ? (
              <CheckCircle size={13} weight="fill" className="text-emerald-500 mt-0.5 shrink-0" />
            ) : (
              <Warning size={13} weight="fill" className={`${it.mandatory ? "text-red-500" : "text-amber-500"} mt-0.5 shrink-0`} />
            )}
            <span className="min-w-0">
              <span className={`${it.complete ? "text-slate-700" : "text-slate-900"} font-medium`}>{it.label}</span>
              <div className="text-[10px] text-slate-500 truncate">{it.source} · {it.reason}</div>
            </span>
          </li>
        ))}
      </ul>
    </ManagementCard>
  );
}

function NotesCard({ data, role, driverId, onChanged }) {
  const notes = data.notes || [];
  const canWrite = role !== "ReadOnly";
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ note_type: "General", title: "", content: "", is_pinned: false });
  const [saving, setSaving] = useState(false);

  const categories = useMemo(() => {
    const base = ["General", "Operations", "Incident", "Management", "Other"];
    if (["Compliance", "Manager", "Admin"].includes(role)) base.push("Compliance");
    if (["Manager", "Admin"].includes(role)) base.push("Accounts");
    return base;
  }, [role]);

  const save = async () => {
    if (!form.content.trim()) { toast.error("Content required"); return; }
    setSaving(true);
    try {
      await api.post(`/drivers/${driverId}/notes`, form);
      toast.success("Note added");
      setAdding(false);
      setForm({ note_type: "General", title: "", content: "", is_pinned: false });
      await onChanged?.();
    } catch (err) {
      toast.error(formatApiErrorDetail(err?.response?.data?.detail) || "Could not add note");
    } finally { setSaving(false); }
  };

  return (
    <ManagementCard
      testid="card-notes"
      section="notes"
      title="Notes"
      subtitle={`${notes.length} visible`}
      canEdit={false}
    >
      {adding ? (
        <div className="space-y-2 border border-slate-200 rounded p-2 bg-slate-50">
          <select
            data-testid="note-type"
            value={form.note_type}
            onChange={(e) => setForm({ ...form, note_type: e.target.value })}
            className="w-full border border-slate-200 rounded px-2 py-1 text-sm bg-white"
          >
            {categories.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <input
            data-testid="note-title"
            placeholder="Title (optional)"
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            className="w-full border border-slate-200 rounded px-2 py-1 text-sm bg-white"
          />
          <textarea
            data-testid="note-content"
            placeholder="Content"
            value={form.content}
            onChange={(e) => setForm({ ...form, content: e.target.value })}
            className="w-full border border-slate-200 rounded px-2 py-1 text-sm bg-white h-20"
          />
          <label className="flex items-center gap-2 text-xs text-slate-700">
            <input type="checkbox" checked={form.is_pinned} onChange={(e) => setForm({ ...form, is_pinned: e.target.checked })} data-testid="note-pin" /> Pin
          </label>
          <div className="flex items-center gap-2">
            <button data-testid="note-save" disabled={saving} onClick={save} className="text-[11px] px-3 py-1 rounded bg-slate-900 text-white hover:bg-slate-800 disabled:opacity-50">{saving ? "Saving…" : "Save note"}</button>
            <button data-testid="note-cancel" onClick={() => setAdding(false)} className="text-[11px] px-3 py-1 rounded text-slate-600 hover:text-slate-900">Cancel</button>
          </div>
        </div>
      ) : (
        <>
          {notes.length === 0 ? (
            <div data-testid="notes-empty" className="text-xs text-slate-400 italic">No notes visible for your role.</div>
          ) : (
            <ul className="space-y-2 max-h-40 overflow-y-auto">
              {notes.slice(0, 4).map((n) => (
                <li key={n.driver_note_id} className="border-l-2 border-slate-200 pl-2" data-testid={`note-${n.driver_note_id}`}>
                  <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.15em] text-slate-500 mb-0.5">
                    {n.is_pinned && <PushPin size={10} weight="fill" className="text-amber-500" />}
                    <span>{n.note_type}</span>
                    <span>· {new Date(n.updated_at).toLocaleDateString()}</span>
                  </div>
                  {n.title && <div className="text-xs font-semibold text-slate-900">{n.title}</div>}
                  <div className="text-xs text-slate-700 line-clamp-2">{n.content}</div>
                </li>
              ))}
            </ul>
          )}
          {canWrite && (
            <div className="pt-2">
              <button data-testid="note-add" onClick={() => setAdding(true)} className="text-[11px] text-cyan-700 hover:underline inline-flex items-center gap-1">
                <NoteBlank size={11} /> Add note
              </button>
            </div>
          )}
        </>
      )}
    </ManagementCard>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Compliance Intelligence Layer (right column)
// ═══════════════════════════════════════════════════════════════════════════
function ComplianceOverviewCard({ data, driverId }) {
  const ci = data.compliance_intelligence || {};
  const counts = data.alert_counts || {};
  return (
    <RightCard title="Compliance Overview" testid="ci-overview" section="ci-overview">
      <div className="flex items-center justify-between">
        <StatusPill status={ci.worst_status || "Compliant"} testid="ci-worst-status" />
        <span className="text-[10px] text-slate-500">Scope: {ci.worst_scope || "driver"}</span>
      </div>
      <p className="text-[11px] text-slate-500 mt-2" data-testid="ci-worst-explanation">{ci.explanation}</p>
      <div className="grid grid-cols-3 gap-2 mt-3 text-center">
        <MiniStat label="Active" value={counts.active} variant={counts.active > 0 ? "warn" : "ok"} testid="ci-count-active" />
        <MiniStat label="Ack" value={counts.acknowledged} testid="ci-count-ack" />
        <MiniStat label="Snoozed" value={counts.snoozed} testid="ci-count-snoozed" />
      </div>
      <div className="pt-2 flex items-center justify-between text-[11px]">
        <Link to={`/notifications/all?entity_type=Driver&entity_id=${driverId}`} data-testid="ci-open-notifications" className="text-cyan-700 hover:underline">
          Open notifications <CaretRight size={10} className="inline" />
        </Link>
        <Link to="/compliance" data-testid="ci-open-compliance" className="text-cyan-700 hover:underline">
          Compliance <CaretRight size={10} className="inline" />
        </Link>
      </div>
    </RightCard>
  );
}
function MiniStat({ label, value, variant = "neutral", testid }) {
  const cls = variant === "warn" ? "border-amber-200 text-amber-800 bg-amber-50" : variant === "ok" ? "border-emerald-200 text-emerald-800 bg-emerald-50" : "border-slate-200 text-slate-800 bg-slate-50";
  return (
    <div data-testid={testid} className={`border rounded px-2 py-1.5 ${cls}`}>
      <div className="text-[9px] uppercase tracking-[0.15em] opacity-80">{label}</div>
      <div className="text-sm font-semibold">{value ?? 0}</div>
    </div>
  );
}

function LicenceCard({ data }) {
  const l = data.primary_licence;
  const s = (data.compliance_intelligence?.driver_summary?.components || []).find((c) => c.component === "primary_licence");
  return (
    <RightCard title="Driver Licence" testid="ci-licence" section="licence">
      {l ? (
        <>
          <InlineField label="Number" value={l.licence_number} testid="ci-licence-number" mono />
          <InlineField label="Class" value={l.licence_class} testid="ci-licence-class" />
          <InlineField label="State" value={l.state} testid="ci-licence-state" />
          <InlineField label="Expiry" value={l.expiry_date} testid="ci-licence-expiry" />
          <div className="pt-1"><StatusPill status={s?.status || "Compliant"} compact testid="ci-licence-status" /></div>
        </>
      ) : (
        <div data-testid="ci-licence-empty" className="text-xs text-slate-400 italic">No primary licence.</div>
      )}
    </RightCard>
  );
}

function TruckRegoCard({ data }) {
  const r = data.primary_registration;
  const vs = data.compliance_intelligence?.vehicle_summary;
  const s = (vs?.components || []).find((c) => c.component === "registration");
  return (
    <RightCard title="Truck Registration" testid="ci-registration" section="registration">
      {r ? (
        <>
          <InlineField label="Rego" value={r.registration_number} testid="ci-registration-number" mono />
          <InlineField label="State" value={r.state} testid="ci-registration-state" />
          <InlineField label="Expiry" value={r.expiry_date} testid="ci-registration-expiry" />
          <div className="pt-1"><StatusPill status={s?.status || "Compliant"} compact testid="ci-registration-status" /></div>
        </>
      ) : (
        <div data-testid="ci-registration-empty" className="text-xs text-slate-400 italic">No primary vehicle assigned.</div>
      )}
    </RightCard>
  );
}

function TruckInsuranceCard({ data }) {
  const i = data.primary_insurance;
  const s = (data.compliance_intelligence?.vehicle_summary?.components || []).find((c) => c.component === "insurance");
  return (
    <RightCard title="Truck Insurance" testid="ci-insurance" section="insurance">
      {i ? (
        <>
          <InlineField label="Insurer" value={i.insurer} testid="ci-insurance-insurer" />
          <InlineField label="Policy" value={i.policy_number} testid="ci-insurance-policy" mono />
          <InlineField label="Cover" value={i.cover_type} testid="ci-insurance-cover" />
          <InlineField label="Expiry" value={i.expiry_date} testid="ci-insurance-expiry" />
          <div className="pt-1"><StatusPill status={s?.status || "Compliant"} compact testid="ci-insurance-status" /></div>
        </>
      ) : (
        <div data-testid="ci-insurance-empty" className="text-xs text-slate-400 italic">No current policy.</div>
      )}
    </RightCard>
  );
}

function VehicleComplianceCard({ data }) {
  const vs = data.compliance_intelligence?.vehicle_summary;
  const extras = data.vehicle_compliance_extras || {};
  return (
    <RightCard title="Vehicle Compliance" testid="ci-vehicle-compliance" section="vehicle-compliance">
      {vs ? (
        <>
          <div className="pb-1"><StatusPill status={vs.overall_status || "Compliant"} compact testid="ci-vehicle-worst-status" /></div>
          <InlineField label="Last insp." value={extras.latest_inspection?.inspection_date} testid="ci-inspection-date" />
          <InlineField label="Result" value={extras.latest_inspection?.result} testid="ci-inspection-result" />
          <InlineField label="Open defects" value={(extras.open_defects || []).length} testid="ci-defects-count" />
          <InlineField label="Overdue tasks" value={(extras.overdue_maintenance || []).length} testid="ci-maintenance-count" />
          <div className="pt-1">
            <Link to="/compliance" data-testid="ci-open-vehicle-compliance" className="text-[11px] text-cyan-700 hover:underline">Open vehicle compliance <CaretRight size={10} className="inline" /></Link>
          </div>
        </>
      ) : (
        <div data-testid="ci-vehicle-empty" className="text-xs text-slate-400 italic">No vehicle to monitor.</div>
      )}
    </RightCard>
  );
}

function DocumentsCard({ data, driverId }) {
  const s = data.documents?.stats || {};
  const recent = s.recent || [];
  return (
    <RightCard title="Documents, Passes & Photos" testid="ci-documents" section="documents">
      <div className="grid grid-cols-4 gap-2 text-center mb-2">
        <MiniStat label="Total" value={s.total} testid="doc-stat-total" />
        <MiniStat label="Active" value={s.active} variant="ok" testid="doc-stat-active" />
        <MiniStat label="Review" value={s.under_review} variant={s.under_review > 0 ? "warn" : "neutral"} testid="doc-stat-review" />
        <MiniStat label="Reject" value={s.rejected} variant={s.rejected > 0 ? "warn" : "neutral"} testid="doc-stat-reject" />
      </div>
      <ul className="space-y-1 text-xs">
        {recent.slice(0, 3).map((d) => (
          <li key={d.id} className="flex items-center justify-between gap-2" data-testid={`doc-recent-${d.id}`}>
            <span className="truncate text-slate-800">{d.title || d.filename}</span>
            <span className="text-[10px] text-slate-500 truncate">{d.category || d.status}</span>
          </li>
        ))}
      </ul>
      <div className="pt-2 flex items-center justify-between text-[11px]">
        <Link to={`/documents?entity_type=Driver&entity_id=${driverId}`} data-testid="ci-open-documents" className="text-cyan-700 hover:underline">Open library <CaretRight size={10} className="inline" /></Link>
        <Link to={`/documents?entity_type=Driver&entity_id=${driverId}&status=Under Review`} data-testid="ci-open-review" className="text-cyan-700 hover:underline">Under review</Link>
      </div>
    </RightCard>
  );
}

function RightCard({ title, testid, section, children }) {
  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-4" data-testid={testid} data-section={section}>
      <div className="text-[10px] uppercase tracking-[0.22em] text-cyan-700 mb-2 flex items-center gap-1.5">
        <span className="inline-flex h-1.5 w-1.5 rounded-full bg-cyan-500" />
        {title}
      </div>
      <div className="space-y-1.5 text-sm">{children}</div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Shared status pill
// ═══════════════════════════════════════════════════════════════════════════
function statusVariant(status) {
  if (!status) return "neutral";
  const s = status.toLowerCase();
  if (["expired", "missing", "not ready", "rejected", "critical"].some((k) => s.includes(k))) return "danger";
  if (["due soon", "expiring", "partial", "under review", "on leave"].some((k) => s.includes(k))) return "warn";
  if (["compliant", "ok", "active", "ready"].some((k) => s.includes(k))) return "ok";
  return "neutral";
}
function StatusPill({ status, compact, testid }) {
  const map = {
    Compliant: "bg-emerald-50 text-emerald-700 border-emerald-200",
    Active: "bg-emerald-50 text-emerald-700 border-emerald-200",
    Ready: "bg-emerald-50 text-emerald-700 border-emerald-200",
    "Due Soon": "bg-amber-50 text-amber-700 border-amber-200",
    "On Leave": "bg-amber-50 text-amber-700 border-amber-200",
    Partial: "bg-amber-50 text-amber-700 border-amber-200",
    "Under Review": "bg-blue-50 text-blue-700 border-blue-200",
    Expired: "bg-red-50 text-red-700 border-red-200",
    Missing: "bg-red-50 text-red-700 border-red-200",
    "Not Ready": "bg-red-50 text-red-700 border-red-200",
    Rejected: "bg-red-50 text-red-700 border-red-200",
    Inactive: "bg-slate-100 text-slate-700 border-slate-200",
    Archived: "bg-slate-100 text-slate-500 border-slate-200",
    "Not Applicable": "bg-slate-50 text-slate-500 border-slate-200",
  };
  const cls = map[status] || "bg-slate-100 text-slate-700 border-slate-200";
  return (
    <span
      data-testid={testid || `pill-${status || "unknown"}`}
      className={`inline-flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-[0.15em] ${compact ? "px-2 py-0.5" : "px-3 py-1"} rounded-full border ${cls}`}
    >
      <span className="inline-flex h-1.5 w-1.5 rounded-full bg-current opacity-70" />
      {status || "Unknown"}
    </span>
  );
}
