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
} from "@phosphor-icons/react";
import AppHeader from "../components/app/AppHeader";
import { MODULES } from "../lib/modules";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";

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
    <div className="min-h-screen bg-white" data-testid="hub-page">
      <AppHeader />

      <main className="max-w-[1600px] mx-auto w-full px-6 lg:px-12 py-10 lg:py-14">
        {/* Hero / status bar */}
        <section className="mb-10 lg:mb-14 flex flex-col lg:flex-row lg:items-end lg:justify-between gap-6">
          <div>
            <div className="text-[10px] uppercase tracking-[0.25em] text-gray-500 mb-3">
              Operations Control Hub
            </div>
            <h1 className="font-display text-4xl sm:text-5xl lg:text-6xl font-semibold tracking-tight text-gray-900 leading-[1.02]">
              Welcome back,
              <br />
              <span className="text-gray-500">
                {user?.full_name || "Operator"}.
              </span>
            </h1>
            <p className="mt-4 text-gray-600 max-w-xl leading-relaxed">
              Select a module to manage drivers, fleet compliance and equipment.
              All data flows into the unified ACE operations database.
            </p>
          </div>

          <div className="grid grid-cols-3 gap-4 lg:gap-6 lg:min-w-[420px]">
            <StatTile label="Drivers" value={stats.drivers ?? 0} loaded={loaded} />
            <StatTile label="Active Licences" value={stats.licences ?? 0} loaded={loaded} />
            <StatTile label="Vehicles" value={stats["truck-rego"] ?? 0} loaded={loaded} />
          </div>
        </section>

        {/* Status strip */}
        <section className="mb-8 flex items-center justify-between border-y border-gray-200 py-3 text-xs text-gray-500">
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

        {/* Compliance widget */}
        <ComplianceWidget data={compliance} loaded={loaded} />

        {/* Module grid — Control Room Grid */}
        <section
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 lg:gap-8"
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
                className="ace-fade-up bg-white border border-gray-200 rounded-xl p-6 lg:p-7 shadow-sm hover:shadow-lg hover:-translate-y-1 hover:border-gray-300 transition-all duration-300 group cursor-pointer flex flex-col items-start text-left h-full"
                style={{ animationDelay: `${i * 40}ms` }}
              >
                <div className="flex items-start justify-between w-full mb-8">
                  <div className="p-3 bg-gray-50 rounded-lg text-gray-700 group-hover:bg-gray-900 group-hover:text-white transition-colors duration-300">
                    <Icon size={28} weight="regular" />
                  </div>
                  <ArrowUpRight
                    size={18}
                    weight="bold"
                    className="text-gray-300 group-hover:text-gray-900 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-all duration-300"
                  />
                </div>

                <div className="text-[10px] uppercase tracking-[0.25em] text-gray-400 mb-2">
                  Module 0{i + 1}
                </div>
                <h3 className="font-display text-xl font-semibold text-gray-900 leading-tight mb-2">
                  {mod.title}
                </h3>
                <p className="text-sm text-gray-500 leading-relaxed mb-6">
                  {mod.description}
                </p>

                <div className="mt-auto pt-4 border-t border-gray-100 w-full flex items-center justify-between">
                  <span className="text-[10px] uppercase tracking-[0.2em] text-gray-400">
                    Records
                  </span>
                  <span
                    className="font-display text-lg font-semibold text-gray-900"
                    data-testid={`module-count-${mod.slug}`}
                  >
                    {count ?? "—"}
                  </span>
                </div>
              </Link>
            );
          })}
        </section>

        <footer className="mt-16 pt-6 border-t border-gray-200 flex items-center justify-between text-xs text-gray-400">
          <div className="uppercase tracking-[0.2em]">ACE Driver Hub · v1.0 Prototype</div>
          <div className="uppercase tracking-[0.2em]">Built for transport operations</div>
        </footer>
      </main>
    </div>
  );
}

function StatTile({ label, value, loaded }) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl px-5 py-4">
      <div className="text-[10px] uppercase tracking-[0.2em] text-gray-500 mb-1.5">
        {label}
      </div>
      <div className="font-display text-2xl font-semibold text-gray-900">
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
      className="ace-fade-up mb-10 lg:mb-12 group block bg-white border border-gray-200 rounded-xl p-6 lg:p-8 shadow-sm hover:shadow-lg hover:-translate-y-0.5 hover:border-gray-300 transition-all duration-300"
    >
      <div className="flex flex-col lg:flex-row lg:items-center gap-8 lg:gap-12">
        {/* Headline */}
        <div className="flex items-start gap-5 lg:min-w-[280px]">
          <div className={`p-3 rounded-lg border ${t.badge}`}>
            <ToneIcon size={28} weight="regular" />
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-[0.25em] text-gray-500 mb-2 flex items-center gap-2">
              <span className={`inline-flex h-1.5 w-1.5 rounded-full ${t.dot}`} />
              Compliance · Next 30 Days
            </div>
            <div className="font-display text-3xl font-semibold text-gray-900 leading-none mb-1">
              Expiring Soon
            </div>
            <div className="text-sm text-gray-500 mt-2" data-testid="compliance-status-label">
              {loaded ? t.label : "Loading compliance risk…"}
            </div>
          </div>
        </div>

        {/* Big total */}
        <div className="lg:border-l lg:border-gray-200 lg:pl-12 flex items-end gap-6">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] text-gray-500 mb-2">
              Total At Risk
            </div>
            <div
              className={`font-display text-5xl lg:text-6xl font-semibold leading-none ${t.number}`}
              data-testid="compliance-total"
            >
              {loaded ? totalAtRisk : "—"}
            </div>
          </div>
          <div className="pb-1 text-xs text-gray-500 leading-relaxed">
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
        <div className="flex-1 grid grid-cols-3 gap-3 lg:gap-4">
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
                className="border border-gray-200 rounded-lg px-4 py-3 group-hover:border-gray-300 transition-colors"
              >
                <div className="flex items-center gap-2 mb-2">
                  <span className={`inline-flex h-1.5 w-1.5 rounded-full ${subStyles.dot}`} />
                  <span className="text-[10px] uppercase tracking-[0.2em] text-gray-500">
                    {m.label}
                  </span>
                </div>
                <div className="flex items-baseline justify-between">
                  <span className={`font-display text-2xl font-semibold ${subStyles.number}`}>
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
        <div className="hidden xl:flex items-center text-sm text-gray-600 group-hover:text-gray-900 transition-colors">
          View list
          <ArrowUpRight
            size={16}
            weight="bold"
            className="ml-1 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform"
          />
        </div>
      </div>
    </Link>
  );
}

