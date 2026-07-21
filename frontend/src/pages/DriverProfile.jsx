import React, { useEffect, useState } from "react";
import { useParams, Link, Navigate } from "react-router-dom";
import AppHeader from "../components/app/AppHeader";
import api, { formatApiErrorDetail } from "../lib/api";
import { findModule, humanLabel } from "../lib/modules";
import { toast } from "sonner";
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
