import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import AppHeader from "../components/app/AppHeader";
import api, { formatApiErrorDetail } from "../lib/api";
import { StatusBadge } from "./CompliancePage";
import { STATUS_STYLES, STATUS_DOT, COMPLIANCE_TYPES } from "../lib/compliance";
import {
  Warning,
  Clock,
  CheckCircle,
  ArrowUpRight,
  IdentificationCard,
  Truck,
  Toolbox,
} from "@phosphor-icons/react";
import { toast } from "sonner";
import NotificationBadge from "../components/app/NotificationBadge";

const LEGACY_LABELS = {
  licences: "Driver Licences",
  "truck-rego": "Driver Truck Rego",
  insurance: "Driver Insurance",
};

export default function Compliance() {
  const [tab, setTab] = useState("canonical"); // canonical | legacy
  return (
    <div className="min-h-screen bg-slate-50" data-testid="compliance-page">
      <AppHeader showBack />

      <main className="max-w-[1600px] mx-auto w-full px-6 lg:px-12 py-6">
        <section className="mb-5">
          <div className="text-[10px] uppercase tracking-[0.25em] text-cyan-600 mb-1 flex items-center gap-2">
            <span className="inline-flex h-1.5 w-1.5 rounded-full bg-cyan-500" />
            Compliance Intelligence
          </div>
          <h1 className="font-display text-2xl lg:text-3xl font-semibold tracking-tight text-slate-900 leading-tight">
            Fleet Compliance Overview
          </h1>
          <p className="mt-1.5 text-sm text-slate-500 max-w-2xl leading-snug">
            Canonical worst-status-wins summary across drivers, vehicles and equipment.
            Legacy prototype view remains accessible for reference until Phase 3.
          </p>
        </section>

        <div className="mb-5 inline-flex items-center rounded-lg border border-slate-200 bg-white p-1 shadow-sm">
          <button
            type="button"
            onClick={() => setTab("canonical")}
            data-testid="compliance-tab-canonical"
            className={`px-4 py-1.5 text-xs uppercase tracking-[0.2em] rounded-md font-medium transition-colors ${
              tab === "canonical" ? "bg-slate-900 text-white" : "text-slate-500 hover:text-slate-900"
            }`}
          >
            Canonical
          </button>
          <button
            type="button"
            onClick={() => setTab("legacy")}
            data-testid="compliance-tab-legacy"
            className={`px-4 py-1.5 text-xs uppercase tracking-[0.2em] rounded-md font-medium transition-colors ${
              tab === "legacy" ? "bg-slate-900 text-white" : "text-slate-500 hover:text-slate-900"
            }`}
          >
            Legacy Prototype
          </button>
        </div>

        {tab === "canonical" ? <CanonicalOverview /> : <LegacyOverview />}
      </main>
    </div>
  );
}

// ---------------------------------------------------------------- CANONICAL
function CanonicalOverview() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("all");
  const [entityFilter, setEntityFilter] = useState("all"); // all | driver | vehicle | equipment
  const [dueWithin, setDueWithin] = useState("all");

  useEffect(() => {
    let alive = true;
    setLoading(true);
    const params = {};
    if (statusFilter !== "all") params.status = statusFilter;
    if (entityFilter !== "all") params.entity_type = entityFilter;
    if (dueWithin !== "all") params.due_within_days = parseInt(dueWithin, 10);
    api
      .get("/compliance/overview", { params })
      .then((r) => alive && setData(r.data))
      .catch((e) => toast.error(formatApiErrorDetail(e?.response?.data?.detail)))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [statusFilter, entityFilter, dueWithin]);

  const totals = data?.totals || { drivers: {}, vehicles: {}, equipment: {} };

  return (
    <div>
      {/* Type tiles */}
      <section className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6" data-testid="compliance-canonical-tiles">
        <EntityTile
          label="Drivers"
          icon={IdentificationCard}
          totals={totals.drivers}
          items={data?.drivers || []}
          loading={loading}
          testid="canonical-tile-drivers"
          openBase="/drivers/"
          idKey="driver_id"
          nameKey="driver_name"
        />
        <EntityTile
          label="Vehicles"
          icon={Truck}
          totals={totals.vehicles}
          items={data?.vehicles || []}
          loading={loading}
          testid="canonical-tile-vehicles"
          openBase="/registers/vehicles"
          idKey="vehicle_id"
          nameKey="registration_number"
        />
        <EntityTile
          label="Equipment"
          icon={Toolbox}
          totals={totals.equipment}
          items={data?.equipment || []}
          loading={loading}
          testid="canonical-tile-equipment"
          openBase="/registers/equipment"
          idKey="equipment_id"
          nameKey="equipment_number"
        />
      </section>

      {/* Filters */}
      <section className="mb-4 flex flex-wrap items-center gap-3">
        <span className="text-[10px] uppercase tracking-[0.2em] text-slate-500 mr-2">Filter</span>
        <select value={entityFilter} onChange={(e) => setEntityFilter(e.target.value)}
          data-testid="canonical-filter-entity"
          className="border border-slate-200 rounded-lg px-3 py-2 text-sm bg-white">
          <option value="all">All entities</option>
          <option value="driver">Drivers only</option>
          <option value="vehicle">Vehicles only</option>
          <option value="equipment">Equipment only</option>
        </select>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
          data-testid="canonical-filter-status"
          className="border border-slate-200 rounded-lg px-3 py-2 text-sm bg-white">
          <option value="all">All statuses</option>
          {Object.keys(STATUS_STYLES).map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={dueWithin} onChange={(e) => setDueWithin(e.target.value)}
          data-testid="canonical-filter-due"
          className="border border-slate-200 rounded-lg px-3 py-2 text-sm bg-white">
          <option value="all">Any expiry</option>
          <option value="30">Due within 30d</option>
          <option value="90">Due within 90d</option>
        </select>
        <div className="text-[11px] text-slate-400 ml-auto">Window: {data?.warning_window_days ?? 30}d</div>
      </section>

      {/* Combined table */}
      <section className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm" data-testid="canonical-overview-table">
        <div className="px-6 py-3 border-b border-slate-200 flex items-center justify-between text-xs text-slate-500">
          <div className="uppercase tracking-[0.2em] font-semibold">At-risk records</div>
          <div className="text-[11px]">{loading ? "Loading…" : "Worst-status-wins"}</div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200">
                {["Entity", "Reference", "Status", "Worst Component", "Reason", ""].map((h) => (
                  <th key={h} className="text-left px-6 py-3 text-[10px] uppercase tracking-[0.2em] font-semibold text-slate-500">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr><td colSpan={6} className="px-6 py-14 text-center text-sm text-slate-400">Loading…</td></tr>
              )}
              {!loading && [
                ...(data?.drivers || []).map((r) => ({ ...r, _entity: "driver" })),
                ...(data?.vehicles || []).map((r) => ({ ...r, _entity: "vehicle" })),
                ...(data?.equipment || []).map((r) => ({ ...r, _entity: "equipment" })),
              ].length === 0 && (
                <tr><td colSpan={6} className="px-6 py-14 text-center text-sm text-slate-500" data-testid="canonical-empty">No records match this filter.</td></tr>
              )}
              {!loading &&
                [
                  ...(data?.drivers || []).map((r) => ({ ...r, _entity: "driver" })),
                  ...(data?.vehicles || []).map((r) => ({ ...r, _entity: "vehicle" })),
                  ...(data?.equipment || []).map((r) => ({ ...r, _entity: "equipment" })),
                ]
                  .sort((a, b) => (b.severity || 0) - (a.severity || 0))
                  .map((r) => (
                    <CanonicalRow key={`${r._entity}-${r.driver_id || r.vehicle_id || r.equipment_id}`} row={r} />
                  ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function EntityTile({ label, icon: Icon, totals, items, loading, testid, openBase, idKey, nameKey }) {
  const total = Object.values(totals || {}).reduce((s, n) => s + n, 0);
  const bad = (totals?.Expired || 0) + (totals?.Missing || 0);
  const warn = (totals?.["Due Soon"] || 0);
  const ok = (totals?.Compliant || 0);
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm" data-testid={testid}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-cyan-50 text-cyan-700 rounded-lg">
            <Icon size={20} weight="regular" />
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-[0.25em] text-slate-500">{label}</div>
            <div className="font-display text-2xl font-semibold text-slate-900">{loading ? "…" : total}</div>
          </div>
        </div>
        <div className="flex items-center gap-2 text-[11px]">
          <span className="inline-flex items-center gap-1 text-red-600 font-medium">
            <span className="inline-flex h-1.5 w-1.5 rounded-full bg-red-500" />
            {bad}
          </span>
          <span className="inline-flex items-center gap-1 text-amber-600 font-medium">
            <span className="inline-flex h-1.5 w-1.5 rounded-full bg-amber-500" />
            {warn}
          </span>
          <span className="inline-flex items-center gap-1 text-emerald-700 font-medium">
            <span className="inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
            {ok}
          </span>
        </div>
      </div>
      {items.length > 0 && (
        <div className="text-[11px] text-slate-400 mt-2">{items.length} in current view</div>
      )}
      <div className="mt-3 pt-3 border-t border-slate-100 flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-[0.2em] text-slate-500">Active alerts</span>
        <NotificationBadge
          entityType={label === "Drivers" ? "Driver" : label === "Vehicles" ? "Vehicle" : "Equipment"}
          testid={`${testid}-alerts`}
          linkTo={`/notifications/all?entity_type=${label === "Drivers" ? "Driver" : label === "Vehicles" ? "Vehicle" : "Equipment"}`}
        />
      </div>
    </div>
  );
}

function CanonicalRow({ row }) {
  const linkTo =
    row._entity === "driver"
      ? `/drivers/${row.driver_id}`
      : row._entity === "vehicle"
      ? `/registers/vehicles`
      : `/registers/equipment`;
  const nameLabel =
    row._entity === "driver"
      ? row.driver_name || "Driver"
      : row._entity === "vehicle"
      ? row.registration_number || row.vehicle_id
      : row.equipment_number || row.equipment_id;
  const worstComp = row.components?.find((c) => c.component === row.worst_component) || null;
  return (
    <tr className="border-b border-slate-100 last:border-0 hover:bg-slate-50 transition-colors">
      <td className="px-6 py-3.5">
        <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500">{row._entity}</div>
      </td>
      <td className="px-6 py-3.5 font-medium text-slate-900">
        <Link to={linkTo} className="hover:underline">{nameLabel}</Link>
      </td>
      <td className="px-6 py-3.5"><StatusBadge status={row.overall_status} /></td>
      <td className="px-6 py-3.5 text-slate-700 text-sm capitalize">{row.worst_component || "—"}</td>
      <td className="px-6 py-3.5 text-slate-500 text-sm">{worstComp?.reason || "—"}</td>
      <td className="px-6 py-3.5 text-right">
        <Link to={linkTo} className="inline-flex items-center gap-1 text-xs text-slate-600 hover:text-slate-900">
          Open <ArrowUpRight size={12} weight="bold" />
        </Link>
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------- LEGACY
function LegacyOverview() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");
  const [moduleFilter, setModuleFilter] = useState("all");

  useEffect(() => {
    let active = true;
    setLoading(true);
    api
      .get("/compliance/expiring")
      .then((r) => active && setData(r.data))
      .catch((e) => toast.error(formatApiErrorDetail(e?.response?.data?.detail)))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, []);

  const records = data?.records || [];
  const totals = data?.totals || { expired: 0, expiring: 0, ok: 0 };
  const modules = data?.modules || {};

  const filtered = useMemo(() => {
    return records.filter((r) => {
      if (filter !== "all" && r.status !== filter) return false;
      if (moduleFilter !== "all" && r.module !== moduleFilter) return false;
      return true;
    });
  }, [records, filter, moduleFilter]);

  const tone = totals.expired > 0 ? "red" : totals.expiring > 0 ? "amber" : "green";
  const HeroIcon = tone === "red" ? Warning : tone === "amber" ? Clock : CheckCircle;

  return (
    <div data-testid="legacy-overview">
      <div className="mb-6 flex items-start gap-4">
        <div className={`p-3 rounded-lg border ${
          tone === "red" ? "text-red-600 bg-red-50 border-red-200"
          : tone === "amber" ? "text-amber-600 bg-amber-50 border-amber-200"
          : "text-emerald-700 bg-emerald-50 border-emerald-200"
        }`}>
          <HeroIcon size={22} />
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500">Legacy Prototype Compliance</div>
          <div className="font-display text-lg font-semibold text-slate-900">Expiring Soon — Phase 1 prototype view</div>
          <div className="text-xs text-slate-500 max-w-lg">Preserved intact from the Phase 1 baseline. Powered by the original <code>/api/compliance/expiring</code> endpoint.</div>
        </div>
      </div>

      <section className="mb-4 flex flex-wrap items-center gap-2 lg:gap-3">
        <span className="text-[10px] uppercase tracking-[0.2em] text-slate-500 mr-2">Filter</span>
        {[{key:"all", label:"All At Risk"},{key:"expired",label:"Expired"},{key:"expiring",label:"Due 30d"}].map((f) => (
          <FilterChip key={f.key} label={f.label} active={filter === f.key} onClick={() => setFilter(f.key)} testid={`legacy-filter-status-${f.key}`} />
        ))}
        <div className="mx-3 h-5 w-px bg-slate-200 hidden sm:block" />
        <FilterChip label="All Modules" active={moduleFilter === "all"} onClick={() => setModuleFilter("all")} testid="legacy-filter-module-all" />
        {Object.keys(LEGACY_LABELS).map((slug) => (
          <FilterChip key={slug} label={LEGACY_LABELS[slug]} active={moduleFilter === slug} onClick={() => setModuleFilter(slug)} testid={`legacy-filter-module-${slug}`} />
        ))}
      </section>

      <section className="mb-6 grid grid-cols-1 md:grid-cols-3 gap-4">
        {Object.keys(LEGACY_LABELS).map((slug) => {
          const mod = modules[slug] || { expired: 0, expiring: 0, ok: 0, total: 0 };
          return (
            <Link
              key={slug}
              to={`/m/${slug}`}
              data-testid={`legacy-module-link-${slug}`}
              className="bg-white border border-slate-200 rounded-xl p-4 hover:shadow-md hover:border-slate-300 transition-all group flex items-center justify-between"
            >
              <div>
                <div className="text-[10px] uppercase tracking-[0.25em] text-slate-500 mb-1">{LEGACY_LABELS[slug]}</div>
                <div className="font-display text-xl font-semibold text-slate-900">{mod.total} records</div>
                <div className="text-xs text-slate-500 mt-1">
                  <span className="text-red-600 font-medium">{mod.expired}</span> expired ·
                  <span className="text-amber-600 font-medium ml-1">{mod.expiring}</span> within 30d
                </div>
              </div>
              <ArrowUpRight size={16} weight="bold" className="text-slate-300 group-hover:text-slate-900 transition-colors" />
            </Link>
          );
        })}
      </section>

      <section className="bg-white border border-slate-200 rounded-xl overflow-hidden" data-testid="legacy-table-wrapper">
        <div className="px-6 py-3 border-b border-slate-200 flex items-center justify-between">
          <div className="text-xs uppercase tracking-[0.2em] font-semibold text-slate-500">At-Risk Records · {filtered.length}</div>
          <div className="text-[11px] text-slate-400">{loading ? "Loading…" : `Showing ${filtered.length} of ${records.length}`}</div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="legacy-table">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200">
                {["Status", "Module", "Driver", "Reference", "Expiry Date", "Days", ""].map((h) => (
                  <th key={h} className="text-left px-6 py-3 text-[10px] uppercase tracking-[0.2em] font-semibold text-slate-500">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 && !loading && (
                <tr><td colSpan={7} className="px-6 py-14 text-center text-sm text-slate-500">No records match this filter.</td></tr>
              )}
              {filtered.map((r) => (
                <tr key={`${r.module}-${r.id}`} className="border-b border-slate-100 last:border-0 hover:bg-slate-50 transition-colors">
                  <td className="px-6 py-3.5"><LegacyStatusBadge status={r.status} /></td>
                  <td className="px-6 py-3.5 text-slate-700">{LEGACY_LABELS[r.module]}</td>
                  <td className="px-6 py-3.5 text-slate-900 font-medium">
                    {r.driver_id ? (
                      <Link to={`/drivers/${r.driver_id}`} className="hover:underline">{r.driver_name || r.title}</Link>
                    ) : (r.driver_name || r.title)}
                  </td>
                  <td className="px-6 py-3.5 text-slate-600">{r.subtitle || "—"}</td>
                  <td className="px-6 py-3.5 text-slate-700">{r.expiry_date || "—"}</td>
                  <td className="px-6 py-3.5">
                    {r.days_until == null ? (<span className="text-slate-300">—</span>)
                      : r.days_until < 0 ? (<span className="text-red-600 font-medium">{Math.abs(r.days_until)}d ago</span>)
                      : (<span className="text-amber-600 font-medium">in {r.days_until}d</span>)}
                  </td>
                  <td className="px-6 py-3.5 text-right">
                    <Link to={`/m/${r.module}`} className="inline-flex items-center gap-1 text-xs text-slate-600 hover:text-slate-900">
                      Open <ArrowUpRight size={12} weight="bold" />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function FilterChip({ label, active, onClick, testid }) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testid}
      className={
        active
          ? "px-3 py-1.5 rounded-full text-xs font-medium bg-slate-900 text-white border border-slate-900"
          : "px-3 py-1.5 rounded-full text-xs font-medium bg-white text-slate-600 border border-slate-200 hover:border-slate-400 hover:text-slate-900"
      }
    >
      {label}
    </button>
  );
}

function LegacyStatusBadge({ status }) {
  if (status === "expired") {
    return (
      <span className="inline-flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-[0.15em] px-2.5 py-1 rounded-full bg-red-50 text-red-700 border border-red-200">
        <span className="inline-flex h-1.5 w-1.5 rounded-full bg-red-500" /> Expired
      </span>
    );
  }
  if (status === "expiring") {
    return (
      <span className="inline-flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-[0.15em] px-2.5 py-1 rounded-full bg-amber-50 text-amber-700 border border-amber-200">
        <span className="inline-flex h-1.5 w-1.5 rounded-full bg-amber-500" /> Due Soon
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-[0.15em] px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
      <span className="inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" /> OK
    </span>
  );
}

// keep alias export for existing imports
export { COMPLIANCE_TYPES };
