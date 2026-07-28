import React from "react";
import { Link } from "react-router-dom";
import { IdentificationCard, Buildings } from "@phosphor-icons/react";
import { HeaderBadge, StatusPill, statusVariant } from "./driverCCUtils";

export default function DriverCCHeader({ driver, data, loading, driverId }) {
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
