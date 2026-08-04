import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Users,
  IdentificationCard,
  Truck,
  ShieldCheck,
  Wrench,
  Toolbox,
  TruckTrailer,
  UserPlus,
  ArrowUpRight,
  Warning,
  CheckCircle,
  Clock,
  Files,
  ArrowsDownUp,
} from "@phosphor-icons/react";
import AppHeader from "../components/app/AppHeader";
import { MODULES } from "../lib/modules";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { SEVERITY_DOT } from "../lib/notifications";

const ICONS = {
  Users,
  IdentificationCard,
  Truck,
  ShieldCheck,
  Wrench,
  Toolbox,
  Trailer: TruckTrailer,
  UserPlus,
};

export default function Hub() {
  const { user } = useAuth();
  const [stats, setStats] = useState({});
  const [loaded, setLoaded] = useState(false);
  const [compliance, setCompliance] = useState(null);

  useEffect(() => {
    let active = true;
    Promise.allSettled([
      api.get("/stats/overview"),
      api.get("/compliance/expiring"),
    ])
      .then(([s, c]) => {
        if (!active) return;
        if (s.status === "fulfilled") setStats(s.value.data || {});
        if (c.status === "fulfilled") setCompliance(c.value.data || null);
      })
      .finally(() => active && setLoaded(true));
    return () => {
      active = false;
    };
  }, []);

  const now = new Date();
  const dateLabel = now.toLocaleDateString("en-AU", {
    weekday: "long",
    day: "2-digit",
    month: "short",
    year: "numeric",
  });

  return (
    <div className="min-h-screen bg-slate-50" data-testid="hub-page">
      <AppHeader />

      <main className="max-w-[1600px] mx-auto w-full px-6 lg:px-12 py-5 lg:py-6">
        {/* Hero / status bar */}
        <section className="mb-5 flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4">
          <div>
            <div className="text-[10px] uppercase tracking-[0.25em] text-slate-500 mb-2 flex items-center gap-2">
              <span className="inline-flex h-1.5 w-1.5 rounded-full bg-cyan-500" />
              Driver Command Centre · Ops Console
            </div>
            <h1 className="font-display text-2xl lg:text-3xl font-semibold tracking-tight text-slate-900 leading-tight">
              Welcome back,{" "}
              <span className="text-slate-500">
                {user?.full_name || "Operator"}.
              </span>
            </h1>
            <p className="mt-1.5 text-sm text-slate-500 max-w-xl leading-snug">
              Select a module to manage drivers, fleet compliance and equipment.
            </p>
          </div>

          <div className="grid grid-cols-3 gap-3 lg:min-w-[380px]">
            <StatTile label="Drivers" value={stats.drivers ?? 0} loaded={loaded} />
            <StatTile label="Active Licences" value={stats.licences ?? 0} loaded={loaded} />
            <StatTile label="Vehicles" value={stats["truck-rego"] ?? 0} loaded={loaded} />
          </div>
        </section>

        {/* Status strip */}
        <section className="mb-4 flex items-center justify-between border-y border-gray-200 py-2 text-xs text-gray-500">
          <div className="flex items-center gap-3">
            <span className="inline-flex h-2 w-2 rounded-full bg-emerald-500" />
            <span className="uppercase tracking-[0.2em]">System Online</span>
          </div>
          <div className="hidden sm:block uppercase tracking-[0.2em]">
            {dateLabel}
          </div>
          <div className="uppercase tracking-[0.2em]">
            Modules · <span className="text-gray-900 font-medium">{MODULES.length}</span>
          </div>
        </section>

        {/* Notification strip (EB-07b) */}
        <NotificationStrip />

        {/* Compliance widget */}
        <ComplianceWidget data={compliance} loaded={loaded} />

        {/* Foundation Registers (EB-02) */}
        <section className="mb-4" data-testid="foundation-registers-section">
          <div className="mb-3 flex items-baseline justify-between">
            <div className="flex items-center gap-3">
              <span className="text-[10px] uppercase tracking-[0.25em] text-cyan-600 flex items-center gap-2">
                <span className="inline-flex h-1.5 w-1.5 rounded-full bg-cyan-500" />
                Foundation Registers
              </span>
              <span className="text-[10px] uppercase tracking-[0.2em] text-slate-400">
                Canonical master records
              </span>
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
            {[
              { slug: "drivers", title: "Drivers", desc: "Identity, contact, payroll and status.", icon: Users },
              { slug: "owners", title: "Owners", desc: "Owners of vehicles and equipment.", icon: IdentificationCard },
              { slug: "vehicles", title: "Vehicles", desc: "Rego, VIN, ownership and status.", icon: Truck },
              { slug: "equipment", title: "Equipment", desc: "Trays, trailers and other assets.", icon: Toolbox },
            ].map((r) => {
              const Icon = r.icon;
              return (
                <Link
                  key={r.slug}
                  to={`/registers/${r.slug}`}
                  data-testid={`register-card-${r.slug}`}
                  className="ace-fade-up bg-white border border-slate-200 rounded-xl p-4 shadow-sm hover:shadow-md hover:-translate-y-0.5 hover:border-cyan-300 transition-all duration-300 group flex items-center gap-3"
                >
                  <div className="p-2.5 bg-cyan-50 text-cyan-700 rounded-lg group-hover:bg-cyan-500 group-hover:text-white transition-colors">
                    <Icon size={20} weight="regular" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="font-display font-semibold text-slate-900 text-sm leading-tight">
                      {r.title}
                    </div>
                    <div className="text-[11px] text-slate-500 truncate">{r.desc}</div>
                  </div>
                  <ArrowUpRight size={14} weight="bold" className="text-slate-300 group-hover:text-slate-900 transition-colors" />
                </Link>
              );
            })}
          </div>
        </section>

        {/* Relationships & Assignments (EB-03) */}
        <section className="mb-4" data-testid="relationships-section">
          <div className="mb-3 flex items-baseline justify-between">
            <div className="flex items-center gap-3">
              <span className="text-[10px] uppercase tracking-[0.25em] text-cyan-600 flex items-center gap-2">
                <span className="inline-flex h-1.5 w-1.5 rounded-full bg-cyan-500" />
                Relationships &amp; Assignments
              </span>
              <span className="text-[10px] uppercase tracking-[0.2em] text-slate-400">
                Dated links between master records
              </span>
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {[
              { slug: "driver-owner", title: "Driver – Owner", desc: "Current ownership context per driver.", icon: IdentificationCard },
              { slug: "driver-vehicle", title: "Driver – Vehicle", desc: "Active primary driver per vehicle.", icon: Truck },
              { slug: "driver-equipment", title: "Driver – Equipment", desc: "Trays / trailers allocation.", icon: Toolbox },
            ].map((r) => {
              const Icon = r.icon;
              return (
                <Link
                  key={r.slug}
                  to={`/relationships/${r.slug}`}
                  data-testid={`relationship-card-${r.slug}`}
                  className="ace-fade-up bg-white border border-slate-200 rounded-xl p-4 shadow-sm hover:shadow-md hover:-translate-y-0.5 hover:border-cyan-300 transition-all duration-300 group flex items-center gap-3"
                >
                  <div className="p-2.5 bg-cyan-50 text-cyan-700 rounded-lg group-hover:bg-cyan-500 group-hover:text-white transition-colors">
                    <Icon size={20} weight="regular" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="font-display font-semibold text-slate-900 text-sm leading-tight">{r.title}</div>
                    <div className="text-[11px] text-slate-500 truncate">{r.desc}</div>
                  </div>
                  <ArrowUpRight size={14} weight="bold" className="text-slate-300 group-hover:text-slate-900 transition-colors" />
                </Link>
              );
            })}
          </div>
        </section>

        {/* Documents & Evidence (EB-05) */}
        <section className="mb-4" data-testid="documents-section">
          <div className="mb-3 flex items-baseline justify-between">
            <div className="flex items-center gap-3">
              <span className="text-[10px] uppercase tracking-[0.25em] text-cyan-600 flex items-center gap-2">
                <span className="inline-flex h-1.5 w-1.5 rounded-full bg-cyan-500" />
                Documents &amp; Evidence
              </span>
              <span className="text-[10px] uppercase tracking-[0.2em] text-slate-400">
                Private evidence store · versioned · audited
              </span>
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <Link
              to="/documents"
              data-testid="documents-library-card"
              className="ace-fade-up bg-white border border-slate-200 rounded-xl p-4 shadow-sm hover:shadow-md hover:-translate-y-0.5 hover:border-cyan-300 transition-all duration-300 group flex items-center gap-3"
            >
              <div className="p-2.5 bg-cyan-50 text-cyan-700 rounded-lg group-hover:bg-cyan-500 group-hover:text-white transition-colors">
                <Files size={20} weight="regular" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="font-display font-semibold text-slate-900 text-sm leading-tight">Document Library</div>
                <div className="text-[11px] text-slate-500 truncate">Search, upload, preview, version every file.</div>
              </div>
              <ArrowUpRight size={14} weight="bold" className="text-slate-300 group-hover:text-slate-900 transition-colors" />
            </Link>
            <Link
              to="/documents?status=Under+Review"
              data-testid="documents-review-card"
              className="ace-fade-up bg-white border border-slate-200 rounded-xl p-4 shadow-sm hover:shadow-md hover:-translate-y-0.5 hover:border-cyan-300 transition-all duration-300 group flex items-center gap-3"
            >
              <div className="p-2.5 bg-amber-50 text-amber-700 rounded-lg group-hover:bg-amber-500 group-hover:text-white transition-colors">
                <Clock size={20} weight="regular" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="font-display font-semibold text-slate-900 text-sm leading-tight">Under Review</div>
                <div className="text-[11px] text-slate-500 truncate">Files awaiting validation before activation.</div>
              </div>
              <ArrowUpRight size={14} weight="bold" className="text-slate-300 group-hover:text-slate-900 transition-colors" />
            </Link>
            <Link
              to="/documents?archived=true"
              data-testid="documents-archived-card"
              className="ace-fade-up bg-white border border-slate-200 rounded-xl p-4 shadow-sm hover:shadow-md hover:-translate-y-0.5 hover:border-cyan-300 transition-all duration-300 group flex items-center gap-3"
            >
              <div className="p-2.5 bg-slate-100 text-slate-500 rounded-lg group-hover:bg-slate-700 group-hover:text-white transition-colors">
                <Files size={20} weight="regular" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="font-display font-semibold text-slate-900 text-sm leading-tight">Archived Documents</div>
                <div className="text-[11px] text-slate-500 truncate">Retained history — restorable by Admin/Manager.</div>
              </div>
              <ArrowUpRight size={14} weight="bold" className="text-slate-300 group-hover:text-slate-900 transition-colors" />
            </Link>
          </div>
        </section>

        {/* Data Import & Migration (EB-06) */}
        <section className="mb-4" data-testid="imports-section">
          <div className="mb-3 flex items-baseline justify-between">
            <div className="flex items-center gap-3">
              <span className="text-[10px] uppercase tracking-[0.25em] text-cyan-600 flex items-center gap-2">
                <span className="inline-flex h-1.5 w-1.5 rounded-full bg-cyan-500" />
                Data Import &amp; Migration
              </span>
              <span className="text-[10px] uppercase tracking-[0.2em] text-slate-400">
                Guided XLSX / XLSM / CSV import · dry-run · reversible
              </span>
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <Link
              to="/imports"
              data-testid="imports-centre-card"
              className="ace-fade-up bg-white border border-slate-200 rounded-xl p-4 shadow-sm hover:shadow-md hover:-translate-y-0.5 hover:border-cyan-300 transition-all duration-300 group flex items-center gap-3"
            >
              <div className="p-2.5 bg-cyan-50 text-cyan-700 rounded-lg group-hover:bg-cyan-500 group-hover:text-white transition-colors">
                <ArrowsDownUp size={20} weight="regular" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="font-display font-semibold text-slate-900 text-sm leading-tight">Import Centre</div>
                <div className="text-[11px] text-slate-500 truncate">Load ACE spreadsheets into canonical registers.</div>
              </div>
              <ArrowUpRight size={14} weight="bold" className="text-slate-300 group-hover:text-slate-900 transition-colors" />
            </Link>
            <Link
              to="/migration-preparation"
              data-testid="migration-prep-card"
              className="ace-fade-up bg-white border border-slate-200 rounded-xl p-4 shadow-sm hover:shadow-md hover:-translate-y-0.5 hover:border-cyan-300 transition-all duration-300 group flex items-center gap-3"
            >
              <div className="p-2.5 bg-indigo-50 text-indigo-700 rounded-lg group-hover:bg-indigo-500 group-hover:text-white transition-colors">
                <ArrowsDownUp size={20} weight="regular" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="font-display font-semibold text-slate-900 text-sm leading-tight">Migration Preparation</div>
                <div className="text-[11px] text-slate-500 truncate">Dry-run mapping, matching, reconciliation & Go/No-Go.</div>
              </div>
              <ArrowUpRight size={14} weight="bold" className="text-slate-300 group-hover:text-slate-900 transition-colors" />
            </Link>
            <Link
              to="/administration/storage"
              data-testid="storage-admin-card"
              className="ace-fade-up bg-white border border-slate-200 rounded-xl p-4 shadow-sm hover:shadow-md hover:-translate-y-0.5 hover:border-cyan-300 transition-all duration-300 group flex items-center gap-3"
            >
              <div className="p-2.5 bg-indigo-50 text-indigo-700 rounded-lg group-hover:bg-indigo-500 group-hover:text-white transition-colors">
                <ArrowsDownUp size={20} weight="regular" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="font-display font-semibold text-slate-900 text-sm leading-tight">Storage Administration</div>
                <div className="text-[11px] text-slate-500 truncate">Private object storage, retention, reconciliation & migration.</div>
              </div>
              <ArrowUpRight size={14} weight="bold" className="text-slate-300 group-hover:text-slate-900 transition-colors" />
            </Link>
            <Link
              to="/migration-commit"
              data-testid="migration-commit-card"
              className="ace-fade-up bg-white border border-slate-200 rounded-xl p-4 shadow-sm hover:shadow-md hover:-translate-y-0.5 hover:border-cyan-300 transition-all duration-300 group flex items-center gap-3"
            >
              <div className="p-2.5 bg-rose-50 text-rose-700 rounded-lg group-hover:bg-rose-500 group-hover:text-white transition-colors">
                <ArrowsDownUp size={20} weight="regular" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="font-display font-semibold text-slate-900 text-sm leading-tight">Migration Commit</div>
                <div className="text-[11px] text-slate-500 truncate">Approved commit, rollback & legacy backfill.</div>
              </div>
              <ArrowUpRight size={14} weight="bold" className="text-slate-300 group-hover:text-slate-900 transition-colors" />
            </Link>
            <Link
              to="/administration/automation"
              data-testid="automation-hub-card"
              className="ace-fade-up bg-white border border-slate-200 rounded-xl p-4 shadow-sm hover:shadow-md hover:-translate-y-0.5 hover:border-cyan-300 transition-all duration-300 group flex items-center gap-3"
            >
              <div className="p-2.5 bg-emerald-50 text-emerald-700 rounded-lg group-hover:bg-emerald-500 group-hover:text-white transition-colors">
                <ArrowsDownUp size={20} weight="regular" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="font-display font-semibold text-slate-900 text-sm leading-tight">Automation & Delivery</div>
                <div className="text-[11px] text-slate-500 truncate">Scheduler jobs, deliveries, providers & templates.</div>
              </div>
              <ArrowUpRight size={14} weight="bold" className="text-slate-300 group-hover:text-slate-900 transition-colors" />
            </Link>
          </div>
        </section>
        <section className="mb-4" data-testid="canonical-compliance-section">
          <div className="mb-3 flex items-baseline justify-between">
            <div className="flex items-center gap-3">
              <span className="text-[10px] uppercase tracking-[0.25em] text-cyan-600 flex items-center gap-2">
                <span className="inline-flex h-1.5 w-1.5 rounded-full bg-cyan-500" />
                Canonical Compliance
              </span>
              <span className="text-[10px] uppercase tracking-[0.2em] text-slate-400">
                Records monitoring master records
              </span>
            </div>
            <Link
              to="/compliance"
              data-testid="canonical-compliance-overview-link"
              className="inline-flex items-center gap-1 text-[11px] text-slate-500 hover:text-slate-900 uppercase tracking-[0.2em]"
            >
              Open overview
              <ArrowUpRight size={12} weight="bold" />
            </Link>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
            {[
              { slug: "driver-licences", title: "Driver Licences", desc: "Primary licence per driver.", icon: IdentificationCard },
              { slug: "vehicle-registrations", title: "Vehicle Registration", desc: "Current registration per vehicle.", icon: Truck },
              { slug: "vehicle-insurance", title: "Vehicle Insurance", desc: "Current policy per cover type.", icon: ShieldCheck },
              { slug: "vehicle-inspections", title: "Vehicle Inspections", desc: "Roadworthy & scheduled inspections.", icon: ShieldCheck },
              { slug: "vehicle-defects", title: "Vehicle Defects", desc: "Defect register with severity.", icon: Warning },
              { slug: "vehicle-maintenance-tasks", title: "Vehicle Maintenance", desc: "Scheduled + overdue tasks.", icon: Wrench },
              { slug: "equipment-compliance", title: "Equipment Compliance", desc: "Cert, inspection, insurance.", icon: Toolbox },
            ].map((r) => {
              const Icon = r.icon;
              return (
                <Link
                  key={r.slug}
                  to={`/compliance/records/${r.slug}`}
                  data-testid={`compliance-card-${r.slug}`}
                  className="ace-fade-up bg-white border border-slate-200 rounded-xl p-4 shadow-sm hover:shadow-md hover:-translate-y-0.5 hover:border-cyan-300 transition-all duration-300 group flex items-center gap-3"
                >
                  <div className="p-2.5 bg-cyan-50 text-cyan-700 rounded-lg group-hover:bg-cyan-500 group-hover:text-white transition-colors">
                    <Icon size={20} weight="regular" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="font-display font-semibold text-slate-900 text-sm leading-tight">{r.title}</div>
                    <div className="text-[11px] text-slate-500 truncate">{r.desc}</div>
                  </div>
                  <ArrowUpRight size={14} weight="bold" className="text-slate-300 group-hover:text-slate-900 transition-colors" />
                </Link>
              );
            })}
          </div>
        </section>

        {/* Legacy Prototype section label */}
        <div className="mt-5 mb-3 flex items-baseline justify-between">
          <div className="flex items-center gap-3">
            <span className="text-[10px] uppercase tracking-[0.25em] text-slate-500 flex items-center gap-2">
              <span className="inline-flex h-1.5 w-1.5 rounded-full bg-slate-400" />
              Legacy Prototype Modules
            </span>
            <span className="text-[10px] uppercase tracking-[0.2em] text-slate-400">
              Preserved from Phase 1
            </span>
          </div>
        </div>

        {/* Module grid — Control Room Grid */}
        <section
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4"
          data-testid="module-grid"
        >
          {MODULES.map((mod, i) => {
            const Icon = ICONS[mod.icon] || Users;
            const count = stats[mod.slug];
            return (
              <Link
                key={mod.slug}
                to={`/m/${mod.slug}`}
                data-testid={`module-card-${mod.slug}`}
                className="ace-fade-up bg-white border border-gray-200 rounded-xl p-4 lg:p-5 shadow-sm hover:shadow-lg hover:-translate-y-1 hover:border-gray-300 transition-all duration-300 group cursor-pointer flex flex-col items-start text-left h-full"
                style={{ animationDelay: `${i * 40}ms` }}
              >
                <div className="flex items-start justify-between w-full mb-3">
                  <div className="p-2.5 bg-gray-50 rounded-lg text-gray-700 group-hover:bg-gray-900 group-hover:text-white transition-colors duration-300">
                    <Icon size={22} weight="regular" />
                  </div>
                  <ArrowUpRight
                    size={16}
                    weight="bold"
                    className="text-gray-300 group-hover:text-gray-900 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-all duration-300"
                  />
                </div>

                <div className="text-[10px] uppercase tracking-[0.25em] text-gray-400 mb-1">
                  Module 0{i + 1}
                </div>
                <h3 className="font-display text-base lg:text-lg font-semibold text-gray-900 leading-tight mb-1.5">
                  {mod.title}
                </h3>
                <p className="text-xs text-gray-500 leading-snug mb-3 line-clamp-2">
                  {mod.description}
                </p>

                <div className="mt-auto pt-3 border-t border-gray-100 w-full flex items-center justify-between">
                  <span className="text-[10px] uppercase tracking-[0.2em] text-gray-400">
                    Records
                  </span>
                  <span
                    className="font-display text-base font-semibold text-gray-900"
                    data-testid={`module-count-${mod.slug}`}
                  >
                    {count ?? "—"}
                  </span>
                </div>
              </Link>
            );
          })}
        </section>

        <footer className="mt-5 pt-3 border-t border-slate-200 flex items-center justify-between text-[11px] text-slate-400">
          <div
            className="uppercase tracking-[0.2em] text-slate-500"
            data-testid="hub-version-stamp"
          >
            DCC · Phase 2 Foundation · EB-06
          </div>
          <div className="uppercase tracking-[0.2em]">Built for transport operations</div>
        </footer>
      </main>
    </div>
  );
}

function NotificationStrip() {
  const [overview, setOverview] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  React.useEffect(() => {
    let alive = true;
    api.get("/notifications/overview")
      .then(({ data }) => alive && setOverview(data))
      .catch(() => alive && setOverview(null))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, []);
  if (loading || !overview) return null;
  const active = overview.by_status?.Active ?? 0;
  const critical = overview.by_severity?.Critical ?? 0;
  const high = overview.by_severity?.High ?? 0;
  const failed = overview.delivery_failures ?? 0;
  const anything = active + critical + high + failed;
  if (anything === 0) return null;
  const items = [
    { label: "Active alerts", value: active, dot: SEVERITY_DOT.Medium, to: "/notifications/all?status=Active" },
    { label: "Critical", value: critical, dot: SEVERITY_DOT.Critical, to: "/notifications/critical?severity=Critical" },
    { label: "High", value: high, dot: SEVERITY_DOT.High, to: "/notifications/critical?severity=High" },
    { label: "Delivery failures", value: failed, dot: "bg-red-500", to: "/notifications/failed" },
  ];
  return (
    <section
      data-testid="hub-notification-strip"
      className="mb-4 bg-white border border-slate-200 rounded-xl px-5 py-3 shadow-sm"
    >
      <div className="flex flex-wrap items-center gap-3 justify-between">
        <div className="text-[10px] uppercase tracking-[0.25em] text-slate-500 inline-flex items-center gap-2">
          <span className="inline-flex h-1.5 w-1.5 rounded-full bg-cyan-500" />
          Active alert summary
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {items.map((i) => (
            <Link key={i.label} to={i.to}
              data-testid={`hub-alert-${i.label.toLowerCase().replace(/\s+/g, "-")}`}
              className="inline-flex items-center gap-1.5 text-xs text-slate-700 hover:text-slate-900">
              <span className={`inline-flex h-1.5 w-1.5 rounded-full ${i.dot}`} />
              <span>{i.label}</span>
              <span className="font-semibold text-slate-900">{i.value}</span>
            </Link>
          ))}
          <Link to="/notifications/all" data-testid="hub-alert-open" className="text-[10px] uppercase tracking-[0.15em] text-cyan-700 hover:text-cyan-900 font-semibold">
            Open Centre →
          </Link>
        </div>
      </div>
    </section>
  );
}

function StatTile({ label, value, loaded }) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg px-4 py-2.5">
      <div className="text-[10px] uppercase tracking-[0.2em] text-gray-500 mb-0.5">
        {label}
      </div>
      <div className="font-display text-xl font-semibold text-gray-900 leading-tight">
        {loaded ? value : "—"}
      </div>
    </div>
  );
}

function ComplianceWidget({ data, loaded }) {
  const totals = data?.totals || { expired: 0, expiring: 0, ok: 0, unknown: 0 };
  const modules = data?.modules || {};
  const expired = totals.expired || 0;
  const expiring = totals.expiring || 0;
  const totalAtRisk = expired + expiring;

  // Status: red if any expired, amber if any expiring, green otherwise
  const tone =
    expired > 0 ? "red" : expiring > 0 ? "amber" : "green";

  const toneStyles = {
    red: {
      badge: "bg-red-50 text-red-700 border-red-200",
      dot: "bg-red-500",
      number: "text-red-600",
      icon: Warning,
      label: "Action Required",
    },
    amber: {
      badge: "bg-amber-50 text-amber-700 border-amber-200",
      dot: "bg-amber-500",
      number: "text-amber-600",
      icon: Clock,
      label: "Attention Needed",
    },
    green: {
      badge: "bg-emerald-50 text-emerald-700 border-emerald-200",
      dot: "bg-emerald-500",
      number: "text-emerald-700",
      icon: CheckCircle,
      label: "All Clear",
    },
  };
  const t = toneStyles[tone];
  const ToneIcon = t.icon;

  const subModules = [
    { slug: "licences", label: "Licences" },
    { slug: "truck-rego", label: "Truck Rego" },
    { slug: "insurance", label: "Insurance" },
  ];

  return (
    <Link
      to="/compliance"
      data-testid="compliance-widget"
      className="ace-fade-up mb-4 group block bg-white border border-gray-200 rounded-xl p-4 lg:p-5 shadow-sm hover:shadow-lg hover:-translate-y-0.5 hover:border-gray-300 transition-all duration-300"
    >
      <div className="flex flex-col lg:flex-row lg:items-center gap-4 lg:gap-8">
        {/* Headline */}
        <div className="flex items-center gap-3 lg:min-w-[260px]">
          <div className={`p-2.5 rounded-lg border ${t.badge}`}>
            <ToneIcon size={22} weight="regular" />
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-[0.25em] text-gray-500 mb-1 flex items-center gap-2">
              <span className={`inline-flex h-1.5 w-1.5 rounded-full ${t.dot}`} />
              Compliance · Next 30 Days
            </div>
            <div className="flex items-baseline gap-3">
              <div className="font-display text-xl font-semibold text-gray-900 leading-none">
                Expiring Soon
              </div>
              <div className="text-xs text-gray-500" data-testid="compliance-status-label">
                {loaded ? t.label : "Loading…"}
              </div>
            </div>
          </div>
        </div>

        {/* Big total */}
        <div className="lg:border-l lg:border-gray-200 lg:pl-8 flex items-end gap-4">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] text-gray-500 mb-0.5">
              Total At Risk
            </div>
            <div
              className={`font-display text-3xl lg:text-4xl font-semibold leading-none ${t.number}`}
              data-testid="compliance-total"
            >
              {loaded ? totalAtRisk : "—"}
            </div>
          </div>
          <div className="pb-0.5 text-[11px] text-gray-500 leading-tight">
            <div>
              <span className="font-medium text-red-600" data-testid="compliance-expired">
                {loaded ? expired : 0}
              </span>{" "}
              expired
            </div>
            <div>
              <span className="font-medium text-amber-600" data-testid="compliance-expiring">
                {loaded ? expiring : 0}
              </span>{" "}
              within 30d
            </div>
          </div>
        </div>

        {/* Per-module split */}
        <div className="flex-1 grid grid-cols-3 gap-2 lg:gap-3">
          {subModules.map((m) => {
            const mod = modules[m.slug] || { expired: 0, expiring: 0 };
            const sub = (mod.expired || 0) + (mod.expiring || 0);
            const subTone =
              mod.expired > 0 ? "red" : mod.expiring > 0 ? "amber" : "green";
            const subStyles = toneStyles[subTone];
            return (
              <div
                key={m.slug}
                data-testid={`compliance-sub-${m.slug}`}
                className="border border-gray-200 rounded-lg px-3 py-2 group-hover:border-gray-300 transition-colors"
              >
                <div className="flex items-center gap-2 mb-1">
                  <span className={`inline-flex h-1.5 w-1.5 rounded-full ${subStyles.dot}`} />
                  <span className="text-[10px] uppercase tracking-[0.2em] text-gray-500">
                    {m.label}
                  </span>
                </div>
                <div className="flex items-baseline justify-between">
                  <span className={`font-display text-lg font-semibold ${subStyles.number}`}>
                    {loaded ? sub : "—"}
                  </span>
                  <span className="text-[10px] uppercase tracking-[0.2em] text-gray-400">
                    {mod.expired || 0}R · {mod.expiring || 0}A
                  </span>
                </div>
              </div>
            );
          })}
        </div>

        {/* CTA */}
        <div className="hidden xl:flex items-center text-xs text-gray-600 group-hover:text-gray-900 transition-colors">
          View list
          <ArrowUpRight
            size={14}
            weight="bold"
            className="ml-1 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform"
          />
        </div>
      </div>
    </Link>
  );
}

