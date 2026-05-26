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

  useEffect(() => {
    let active = true;
    api
      .get("/stats/overview")
      .then((r) => {
        if (active) setStats(r.data || {});
      })
      .catch(() => {})
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
