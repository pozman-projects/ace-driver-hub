import React, { useEffect, useState } from "react";
import { useParams, Link, Navigate } from "react-router-dom";
import AppHeader from "../components/app/AppHeader";
import api, { formatApiErrorDetail } from "../lib/api";
import { findModule, humanLabel } from "../lib/modules";
import { toast } from "sonner";
import NotificationBadge from "../components/app/NotificationBadge";
import {
  User,
  ArrowUpRight,
  Phone,
  EnvelopeSimple,
  MapPin,
  IdentificationCard,
} from "@phosphor-icons/react";

const SECTIONS = [
  "licences",
  "truck-rego",
  "insurance",
  "equipment",
  "maintenance",
  "tilt-trays",
  "onboarding",
];

export default function DriverProfile() {
  const { driverId } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [canonical, setCanonical] = useState({ owner: null, vehicle: null, equipment: [], ownerRow: null, vehicleRow: null });
  const [complianceSummary, setComplianceSummary] = useState(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    Promise.allSettled([
      api.get(`/drivers/${driverId}/profile`),
      api.get(`/driver-owner-relationships`, { params: { driver_id: driverId, is_current: true } }),
      api.get(`/driver-vehicle-assignments`, { params: { driver_id: driverId, is_active: true, is_primary: true } }),
      api.get(`/driver-equipment-assignments`, { params: { driver_id: driverId, is_active: true } }),
      api.get(`/owners`),
      api.get(`/vehicles`),
      api.get(`/equipment`),
      api.get(`/compliance/drivers/${driverId}`),
    ]).then(([profileR, dorR, dvaR, deaR, oR, vR, eR, csR]) => {
      if (!active) return;
      if (profileR.status === "fulfilled") setData(profileR.value.data);
      else if (profileR.reason?.response?.status === 404) setNotFound(true);
      else toast.error(formatApiErrorDetail(profileR.reason?.response?.data?.detail));

      const owners = oR.status === "fulfilled" ? oR.value.data || [] : [];
      const vehicles = vR.status === "fulfilled" ? vR.value.data || [] : [];
      const equipment = eR.status === "fulfilled" ? eR.value.data || [] : [];
      const ownersById = Object.fromEntries(owners.map((o) => [o.id, o]));
      const vehiclesById = Object.fromEntries(vehicles.map((v) => [v.id, v]));
      const equipmentById = Object.fromEntries(equipment.map((e) => [e.id, e]));
      const dor = dorR.status === "fulfilled" ? (dorR.value.data || [])[0] : null;
      const dva = dvaR.status === "fulfilled" ? (dvaR.value.data || [])[0] : null;
      const dea = deaR.status === "fulfilled" ? deaR.value.data || [] : [];
      setCanonical({
        ownerRow: dor,
        owner: dor ? ownersById[dor.owner_id] : null,
        vehicleRow: dva,
        vehicle: dva ? vehiclesById[dva.vehicle_id] : null,
        equipment: dea.map((a) => ({ assignment: a, item: equipmentById[a.equipment_id] })).filter((x) => x.item),
      });
      if (csR.status === "fulfilled") setComplianceSummary(csR.value.data);
    }).finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [driverId]);

  if (notFound) return <Navigate to="/m/drivers" replace />;

  const driver = data?.driver;
  const linked = data?.linked || {};
  const totalLinked = SECTIONS.reduce(
    (sum, s) => sum + (linked[s]?.length || 0),
    0
  );

  return (
    <div className="min-h-screen bg-slate-50" data-testid="driver-profile-page">
      <AppHeader showBack />

      <main className="max-w-[1600px] mx-auto w-full px-6 lg:px-12 py-10">
        {/* Header */}
        <section className="mb-10">
          <div className="text-[10px] uppercase tracking-[0.25em] text-gray-500 mb-2">
            <Link to="/m/drivers" className="hover:text-gray-900 transition-colors">
              Driver Hub
            </Link>
            <span className="mx-2">/</span>
            <span>Profile</span>
          </div>

          {loading ? (
            <h1 className="font-display text-3xl text-gray-400">Loading driver…</h1>
          ) : driver ? (
            <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-6">
              <div className="flex items-start gap-5">
                <div className="h-16 w-16 rounded-xl bg-gray-900 text-white grid place-items-center font-display font-semibold text-2xl">
                  {(driver.name || "?").slice(0, 1).toUpperCase()}
                </div>
                <div>
                  <h1
                    data-testid="driver-name"
                    className="font-display text-3xl sm:text-4xl lg:text-5xl font-semibold tracking-tight text-gray-900"
                  >
                    {driver.name}
                  </h1>
                  <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-gray-500">
                    {driver.driver_number && (
                      <span className="inline-flex items-center gap-1.5 text-[10px] uppercase tracking-[0.2em] font-medium text-gray-700 border border-gray-200 rounded-full px-2 py-1 bg-white">
                        <User size={12} weight="bold" />
                        {driver.driver_number}
                      </span>
                    )}
                    {driver.company && <span>{driver.company}</span>}
                    {driver.status && (
                      <span className="inline-flex items-center gap-1.5">
                        <span
                          className={`inline-flex h-1.5 w-1.5 rounded-full ${
                            driver.status === "Active"
                              ? "bg-emerald-500"
                              : driver.status === "On Leave"
                              ? "bg-amber-500"
                              : "bg-gray-400"
                          }`}
                        />
                        {driver.status}
                      </span>
                    )}
                  </div>

                  <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-gray-600">
                    {driver.phone && (
                      <span className="inline-flex items-center gap-2">
                        <Phone size={14} className="text-gray-400" />
                        {driver.phone}
                      </span>
                    )}
                    {driver.email && (
                      <span className="inline-flex items-center gap-2">
                        <EnvelopeSimple size={14} className="text-gray-400" />
                        {driver.email}
                      </span>
                    )}
                    {driver.base && (
                      <span className="inline-flex items-center gap-2">
                        <MapPin size={14} className="text-gray-400" />
                        {driver.base}
                      </span>
                    )}
                    {driver.licence_number && (
                      <span className="inline-flex items-center gap-2">
                        <IdentificationCard size={14} className="text-gray-400" />
                        {driver.licence_number}
                      </span>
                    )}
                  </div>
                </div>
              </div>

              <div className="bg-white border border-gray-200 rounded-xl px-5 py-4 lg:min-w-[200px]">
                <div className="text-[10px] uppercase tracking-[0.2em] text-gray-500 mb-1.5">
                  Linked Records
                </div>
                <div
                  className="font-display text-3xl font-semibold text-gray-900"
                  data-testid="driver-linked-total"
                >
                  {totalLinked}
                </div>
                <div className="text-xs text-gray-500 mt-1">
                  Across {SECTIONS.length} modules
                </div>
              </div>
            </div>
          ) : null}
        </section>

        {/* Numbering identifiers (EB-08) */}
        <IdentifierCard driver={driver} />

        {/* Canonical Relationships & Assignments (EB-03) */}
        <section className="mb-6 grid grid-cols-1 lg:grid-cols-3 gap-4" data-testid="driver-canonical-widgets">
          <CanonicalWidget
            testid="driver-widget-current-owner"
            label="Current Owner"
            emptyLabel="No current owner"
            openTo="/relationships/driver-owner"
            loading={loading}
            active={!!canonical.owner || !!canonical.ownerRow}
          >
            {canonical.owner || canonical.ownerRow ? (
              <>
                <div className="text-sm font-semibold text-slate-900 truncate">
                  {canonical.owner?.name || canonical.owner?.trading_name || canonical.ownerRow?.owner_name_snapshot || "—"}
                </div>
                {(canonical.owner?.abn || canonical.owner?.owner_code) && (
                  <div className="text-[11px] text-slate-500 mt-0.5">
                    {canonical.owner?.owner_code}
                    {canonical.owner?.owner_code && canonical.owner?.abn && " · "}
                    {canonical.owner?.abn && `ABN ${canonical.owner.abn}`}
                  </div>
                )}
                {canonical.ownerRow?.effective_from && (
                  <div className="text-[10px] uppercase tracking-[0.15em] text-slate-400 mt-2">
                    Since {canonical.ownerRow.effective_from}
                  </div>
                )}
              </>
            ) : null}
          </CanonicalWidget>

          <CanonicalWidget
            testid="driver-widget-vehicle"
            label="Vehicle Assignment"
            emptyLabel="No active vehicle assignment"
            openTo="/relationships/driver-vehicle"
            loading={loading}
            active={!!canonical.vehicle || !!canonical.vehicleRow}
          >
            {canonical.vehicle || canonical.vehicleRow ? (
              <>
                <div className="text-sm font-semibold text-slate-900 truncate">
                  {canonical.vehicle?.registration_number || canonical.vehicleRow?.vehicle_registration_snapshot || "—"}
                </div>
                {(canonical.vehicle?.make || canonical.vehicle?.model) && (
                  <div className="text-[11px] text-slate-500 mt-0.5 truncate">
                    {[canonical.vehicle?.make, canonical.vehicle?.model].filter(Boolean).join(" ")}
                  </div>
                )}
                {canonical.vehicleRow?.is_primary && (
                  <div className="text-[10px] uppercase tracking-[0.15em] text-emerald-700 mt-2 inline-flex items-center gap-1">
                    <span className="inline-flex h-1 w-1 rounded-full bg-emerald-500" />
                    Primary
                  </div>
                )}
              </>
            ) : null}
          </CanonicalWidget>

          <CanonicalWidget
            testid="driver-widget-equipment"
            label="Equipment Assignments"
            emptyLabel="No active equipment"
            openTo="/relationships/driver-equipment"
            loading={loading}
            active={canonical.equipment.length > 0}
            count={canonical.equipment.length}
          >
            {canonical.equipment.length > 0 && (
              <ul className="space-y-1.5">
                {canonical.equipment.slice(0, 3).map(({ assignment, item }) => (
                  <li key={assignment.id} className="flex items-baseline justify-between gap-3">
                    <span className="text-sm font-medium text-slate-900 truncate">
                      {item?.equipment_number || assignment.equipment_number_snapshot || "—"}
                    </span>
                    {item?.equipment_type && (
                      <span className="text-[10px] uppercase tracking-[0.15em] text-slate-500 truncate">
                        {item.equipment_type}
                      </span>
                    )}
                  </li>
                ))}
                {canonical.equipment.length > 3 && (
                  <li className="text-[11px] text-slate-500">+ {canonical.equipment.length - 3} more</li>
                )}
              </ul>
            )}
          </CanonicalWidget>
        </section>

        {/* Active Notifications (EB-07b) */}
        <section className="mb-6 bg-white border border-slate-200 rounded-xl p-4 shadow-sm" data-testid="driver-alerts-card">
          <div className="flex items-center justify-between mb-2">
            <div className="text-[10px] uppercase tracking-[0.25em] text-cyan-600 flex items-center gap-2">
              <span className="inline-flex h-1.5 w-1.5 rounded-full bg-cyan-500" />
              Active alerts
            </div>
            <Link
              to={`/notifications/all?entity_type=Driver&entity_id=${driverId}`}
              data-testid="driver-alerts-open"
              className="inline-flex items-center gap-1 text-xs text-cyan-700 hover:text-cyan-900"
            >
              Open Centre <ArrowUpRight size={11} weight="bold" />
            </Link>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            <NotificationBadge entityType="Driver" entityId={driverId}
              testid="driver-alert-badge"
              linkTo={`/notifications/all?entity_type=Driver&entity_id=${driverId}`} />
            <span className="text-xs text-slate-500">Acknowledgement and snooze do not change source compliance status.</span>
          </div>
        </section>

        {/* Canonical Compliance Summary (EB-04) */}
        {complianceSummary && (
          <section className="mb-6 bg-white border border-slate-200 rounded-xl p-5 shadow-sm" data-testid="driver-compliance-summary">
            <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3 mb-3">
              <div>
                <div className="text-[10px] uppercase tracking-[0.25em] text-cyan-600 mb-1 flex items-center gap-2">
                  <span className="inline-flex h-1.5 w-1.5 rounded-full bg-cyan-500" />
                  Canonical Compliance
                </div>
                <div className="font-display text-lg font-semibold text-slate-900">Driver Compliance</div>
              </div>
              <ComplianceStatusPill status={complianceSummary.overall_status} />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {complianceSummary.components.map((c) => (
                <div key={c.component} className="border border-slate-200 rounded-lg px-4 py-3 flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500">{c.label}</div>
                    <div className="text-xs text-slate-600 truncate">{c.reason}</div>
                  </div>
                  <ComplianceStatusPill status={c.status} compact />
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Sections */}
        <section className="space-y-6" data-testid="driver-profile-sections">
          {SECTIONS.map((slug) => (
            <ProfileSection
              key={slug}
              slug={slug}
              rows={linked[slug] || []}
              loading={loading}
            />
          ))}
        </section>
      </main>
    </div>
  );
}

function ProfileSection({ slug, rows, loading }) {
  const mod = findModule(slug);
  if (!mod) return null;
  const columns = mod.columns.filter((c) => c !== "driver"); // hide redundant driver col

  return (
    <div
      className="bg-white border border-gray-200 rounded-xl overflow-hidden"
      data-testid={`profile-section-${slug}`}
    >
      <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="text-[10px] uppercase tracking-[0.2em] font-semibold text-gray-500">
            {mod.title}
          </div>
          <span
            className="text-[11px] text-gray-700 bg-gray-100 rounded-full px-2 py-0.5"
            data-testid={`profile-section-${slug}-count`}
          >
            {rows.length}
          </span>
        </div>
        <Link
          to={`/m/${slug}`}
          data-testid={`profile-section-${slug}-open`}
          className="inline-flex items-center gap-1 text-xs text-gray-600 hover:text-gray-900 transition-colors"
        >
          Open module
          <ArrowUpRight size={12} weight="bold" />
        </Link>
      </div>

      {loading ? (
        <div className="px-6 py-10 text-center text-sm text-gray-400">Loading…</div>
      ) : rows.length === 0 ? (
        <div className="px-6 py-10 text-center text-sm text-gray-400">
          No {mod.title.toLowerCase()} linked to this driver yet.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                {columns.map((c) => (
                  <th
                    key={c}
                    className="text-left px-6 py-3 text-[10px] uppercase tracking-[0.2em] font-semibold text-gray-500"
                  >
                    {humanLabel(c)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.id}
                  data-testid={`profile-row-${row.id}`}
                  className="border-b border-gray-100 last:border-0 hover:bg-gray-50 transition-colors"
                >
                  {columns.map((c) => (
                    <td key={c} className="px-6 py-4 text-gray-800">
                      {row[c] || <span className="text-gray-300">—</span>}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}


function IdentifierCard({ driver }) {
  const [history, setHistory] = React.useState([]);
  React.useEffect(() => {
    if (!driver?.id) return;
    let alive = true;
    api.get(`/numbering/drivers/${driver.id}/history`)
      .then(({ data }) => alive && setHistory(data || []))
      .catch(() => alive && setHistory([]));
    return () => { alive = false; };
  }, [driver?.id]);
  if (!driver) return null;
  const disp = driver.dispatch_number;
  const dispNum = disp ? parseInt(String(disp), 10) : NaN;
  const isInactive = !Number.isNaN(dispNum) && dispNum >= 100 && dispNum <= 999
    && (driver.driver_status === "Inactive" || driver.driver_status === "Archived");
  const dcEvent = history.find((h) => h.identifier_type === "Driver Code");
  const isImported = !!driver._import_job_id || driver._source === "import";
  const source = dcEvent
    ? (dcEvent.automatic ? "Automatic" : dcEvent.manual_override ? "Manual" : "System")
    : (isImported ? "Imported" : "Manual");
  return (
    <section className="mb-6 bg-white border border-slate-200 rounded-xl p-4 shadow-sm" data-testid="driver-identifier-card">
      <div className="flex items-center justify-between mb-3">
        <div className="text-[10px] uppercase tracking-[0.25em] text-cyan-600 flex items-center gap-2">
          <span className="inline-flex h-1.5 w-1.5 rounded-full bg-cyan-500" />
          Identifiers
        </div>
        <Link
          to={`/administration/numbering`}
          data-testid="driver-identifier-open-admin"
          className="inline-flex items-center gap-1 text-xs text-cyan-700 hover:text-cyan-900"
        >
          Numbering admin <ArrowUpRight size={11} weight="bold" />
        </Link>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-sm">
        <div>
          <div className="text-[10px] uppercase tracking-[0.15em] text-slate-500">Driver Code</div>
          <div className="font-display text-lg font-semibold text-slate-900" data-testid="driver-identifier-code">
            {driver.driver_code || "—"}
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">
            Source: <span data-testid="driver-identifier-source">{source}</span>
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-[0.15em] text-slate-500">Dispatch Number</div>
          <div className="font-display text-lg font-semibold text-slate-900" data-testid="driver-identifier-dispatch">
            {disp || "—"}
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">
            {disp ? (isInactive ? "Inactive (operational)" : "Active (operational)") : "None allocated"}
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-[0.15em] text-slate-500">Allocation history</div>
          <div className="text-sm text-slate-800" data-testid="driver-identifier-history-count">
            {history.length} {history.length === 1 ? "event" : "events"}
          </div>
          <div className="text-[10px] text-slate-400 mt-0.5">Full audit in Numbering admin</div>
        </div>
      </div>
    </section>
  );
}


function CanonicalWidget({ testid, label, emptyLabel, openTo, loading, active, count, children }) {
  return (
    <div
      data-testid={testid}
      className={`relative bg-white border rounded-xl px-5 py-4 shadow-sm transition-colors ${
        active ? "border-slate-200" : "border-dashed border-slate-200"
      }`}
    >
      <div className="flex items-center justify-between gap-3 mb-2">
        <div className="text-[10px] uppercase tracking-[0.25em] text-slate-500 flex items-center gap-2">
          <span className={`inline-flex h-1.5 w-1.5 rounded-full ${active ? "bg-emerald-500" : "bg-slate-300"}`} />
          {label}
          {typeof count === "number" && (
            <span
              className="ml-1 text-[10px] font-medium text-slate-700 bg-slate-100 border border-slate-200 rounded-full px-1.5 py-0.5"
              data-testid={`${testid}-count`}
            >
              {count}
            </span>
          )}
        </div>
        {openTo && (
          <Link
            to={openTo}
            data-testid={`${testid}-open`}
            className="inline-flex items-center gap-1 text-[11px] text-slate-500 hover:text-slate-900"
          >
            Open <ArrowUpRight size={11} weight="bold" />
          </Link>
        )}
      </div>
      <div className="min-h-[38px]">
        {loading ? (
          <div className="text-xs text-slate-400">Loading…</div>
        ) : active ? (
          children
        ) : (
          <div className="text-xs text-slate-400" data-testid={`${testid}-empty`}>{emptyLabel}</div>
        )}
      </div>
    </div>
  );
}

function ComplianceStatusPill({ status, compact }) {
  const map = {
    Compliant: "bg-emerald-50 text-emerald-700 border-emerald-200",
    "Due Soon": "bg-amber-50 text-amber-700 border-amber-200",
    Expired: "bg-red-50 text-red-700 border-red-200",
    Missing: "bg-red-50 text-red-700 border-red-200",
    Incomplete: "bg-slate-100 text-slate-700 border-slate-200",
    "Under Review": "bg-blue-50 text-blue-700 border-blue-200",
    "Not Applicable": "bg-slate-50 text-slate-500 border-slate-200",
    Archived: "bg-slate-100 text-slate-500 border-slate-200",
  };
  const dots = {
    Compliant: "bg-emerald-500",
    "Due Soon": "bg-amber-500",
    Expired: "bg-red-500",
    Missing: "bg-red-500",
    Incomplete: "bg-slate-400",
    "Under Review": "bg-blue-500",
    "Not Applicable": "bg-slate-300",
    Archived: "bg-slate-400",
  };
  const cls = map[status] || map.Incomplete;
  const dot = dots[status] || dots.Incomplete;
  return (
    <span
      data-testid={`compliance-pill-${status || "Unknown"}`}
      className={`inline-flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-[0.15em] ${compact ? "px-2 py-0.5" : "px-3 py-1"} rounded-full border ${cls}`}
    >
      <span className={`inline-flex h-1.5 w-1.5 rounded-full ${dot}`} />
      {status || "Unknown"}
    </span>
  );
}
