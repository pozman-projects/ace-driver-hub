/**
 * EB-09 · Final Three-Row DCC Driver Command Centre Profile — page shell
 * ---------------------------------------------------------------------
 * EB-09.1 refactor: this file now only orchestrates data loading and
 * composes the extracted card components under /components/driver-cc/.
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
import React, { useCallback, useEffect, useState } from "react";
import { useParams, useSearchParams, Navigate } from "react-router-dom";
import { toast } from "sonner";
import AppHeader from "../components/app/AppHeader";
import api, { formatApiErrorDetail } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import DriverProfileLegacy from "./DriverProfile";

import { ManagementRow } from "../components/driver-cc/driverCCUtils";
import DriverCCHeader from "../components/driver-cc/DriverCCHeader";
import { SkeletonRow, SkeletonRight } from "../components/driver-cc/DriverCCLoadingState";
import DriverCCErrorState from "../components/driver-cc/DriverCCErrorState";
import DriverDetailsCard from "../components/driver-cc/DriverDetailsCard";
import AccountDetailsCard from "../components/driver-cc/AccountDetailsCard";
import DriverSetupCard from "../components/driver-cc/DriverSetupCard";
import CommunicationCard from "../components/driver-cc/CommunicationCard";
import CarrierEquipmentCard from "../components/driver-cc/CarrierEquipmentCard";
import OwnerDetailsCard from "../components/driver-cc/OwnerDetailsCard";
import AdminUtilitiesCard from "../components/driver-cc/AdminUtilitiesCard";
import ActivationChecklistCard from "../components/driver-cc/ActivationChecklistCard";
import DriverNotesCard from "../components/driver-cc/DriverNotesCard";
import ComplianceOverviewCard from "../components/driver-cc/ComplianceOverviewCard";
import DriverLicenceCard from "../components/driver-cc/DriverLicenceCard";
import TruckRegistrationCard from "../components/driver-cc/TruckRegistrationCard";
import TruckInsuranceCard from "../components/driver-cc/TruckInsuranceCard";
import VehicleComplianceCard from "../components/driver-cc/VehicleComplianceCard";
import DocumentsPassesPhotosCard from "../components/driver-cc/DocumentsPassesPhotosCard";


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
        <DriverCCHeader driver={driver} data={data} loading={loading} driverId={driverId} />

        {failed && <DriverCCErrorState onRetry={refresh} />}

        <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_420px] gap-6">
          {/* LEFT — Management Layer */}
          <div className="min-w-0 space-y-6">
            {loading ? <SkeletonRow /> : data ? (
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
                  <CarrierEquipmentCard data={data} />
                  <OwnerDetailsCard data={data} />
                </ManagementRow>
                {/* Row 3 */}
                <ManagementRow>
                  <AdminUtilitiesCard data={data} driverId={driverId} role={role} />
                  <ActivationChecklistCard data={data} />
                  <DriverNotesCard data={data} role={role} driverId={driverId} onChanged={refresh} />
                </ManagementRow>
              </>
            ) : null}
          </div>

          {/* RIGHT — Compliance Intelligence Layer (sticky on desktop) */}
          <aside className="xl:sticky xl:top-6 xl:self-start space-y-4" data-testid="compliance-intelligence-layer" data-section="compliance">
            {loading ? <SkeletonRight /> : data ? (
              <>
                <ComplianceOverviewCard data={data} driverId={driverId} />
                <DriverLicenceCard data={data} />
                <TruckRegistrationCard data={data} />
                <TruckInsuranceCard data={data} />
                <VehicleComplianceCard data={data} />
                <DocumentsPassesPhotosCard data={data} driverId={driverId} />
              </>
            ) : null}
          </aside>
        </div>
      </main>
    </div>
  );
}
