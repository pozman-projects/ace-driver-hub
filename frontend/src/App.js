import React from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider } from "./context/AuthContext";
import ProtectedRoute from "./components/app/ProtectedRoute";
import Login from "./pages/Login";
import Hub from "./pages/Hub";
import ModulePage from "./pages/ModulePage";
import Compliance from "./pages/Compliance";
import DriverProfile from "./pages/DriverProfile";
import DriverCommandCentre from "./pages/DriverCommandCentre";
import RegisterPage from "./pages/RegisterPage";
import RelationshipPage from "./pages/RelationshipPage";
import CompliancePage from "./pages/CompliancePage";
import DocumentLibrary from "./pages/DocumentLibrary";
import ImportCentre from "./pages/ImportCentre";
import ImportWizard from "./pages/ImportWizard";
import NotificationsCentre from "./pages/NotificationsCentre";
import NumberingAdmin from "./pages/NumberingAdmin";
import DriverActivationPage from "./pages/DriverActivationPage";
import ActivationTemplatesPage from "./pages/ActivationTemplatesPage";
import ActivationTemplateDetailPage from "./pages/ActivationTemplateDetailPage";
import ActivationJobsPage from "./pages/ActivationJobsPage";
import DriverExportsPage from "./pages/DriverExportsPage";
import ExportVerificationPage from "./pages/ExportVerificationPage";
import MigrationPreparationHub from "./pages/MigrationPreparationHub";
import MigrationWorkbooksPage from "./pages/MigrationWorkbooksPage";
import MigrationMappingsPage from "./pages/MigrationMappingsPage";
import MigrationDryRunsPage from "./pages/MigrationDryRunsPage";
import StorageAdmin from "./pages/StorageAdmin";
import MigrationCommitHub from "./pages/MigrationCommitHub";
import MigrationDryRunDetailPage from "./pages/MigrationDryRunDetailPage";

function App() {
  return (
    <div className="App">
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route
              path="/"
              element={
                <ProtectedRoute>
                  <Hub />
                </ProtectedRoute>
              }
            />
            <Route
              path="/m/:slug"
              element={
                <ProtectedRoute>
                  <ModulePage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/compliance"
              element={
                <ProtectedRoute>
                  <Compliance />
                </ProtectedRoute>
              }
            />
            <Route
              path="/drivers/:driverId"
              element={
                <ProtectedRoute>
                  <DriverCommandCentre />
                </ProtectedRoute>
              }
            />
            <Route
              path="/registers/:slug"
              element={
                <ProtectedRoute>
                  <RegisterPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/relationships/:slug"
              element={
                <ProtectedRoute>
                  <RelationshipPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/compliance/records/:slug"
              element={
                <ProtectedRoute>
                  <CompliancePage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/documents"
              element={
                <ProtectedRoute>
                  <DocumentLibrary />
                </ProtectedRoute>
              }
            />
            <Route
              path="/imports"
              element={
                <ProtectedRoute>
                  <ImportCentre />
                </ProtectedRoute>
              }
            />
            <Route
              path="/imports/:jobId"
              element={
                <ProtectedRoute>
                  <ImportWizard />
                </ProtectedRoute>
              }
            />
            <Route
              path="/notifications"
              element={<Navigate to="/notifications/my" replace />}
            />
            <Route
              path="/notifications/:view"
              element={
                <ProtectedRoute>
                  <NotificationsCentre />
                </ProtectedRoute>
              }
            />
            <Route
              path="/administration/numbering"
              element={
                <ProtectedRoute>
                  <NumberingAdmin />
                </ProtectedRoute>
              }
            />
            <Route
              path="/administration/storage"
              element={
                <ProtectedRoute>
                  <StorageAdmin />
                </ProtectedRoute>
              }
            />
            <Route
              path="/migration-commit"
              element={
                <ProtectedRoute>
                  <MigrationCommitHub />
                </ProtectedRoute>
              }
            />
            <Route
              path="/drivers/:driverId/activation"
              element={
                <ProtectedRoute>
                  <DriverActivationPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/administration/activation-templates"
              element={
                <ProtectedRoute>
                  <ActivationTemplatesPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/administration/activation-templates/:templateId"
              element={
                <ProtectedRoute>
                  <ActivationTemplateDetailPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/administration/activation-jobs"
              element={
                <ProtectedRoute>
                  <ActivationJobsPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/drivers/:driverId/exports"
              element={
                <ProtectedRoute>
                  <DriverExportsPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/exports/verify/:reference"
              element={
                <ProtectedRoute>
                  <ExportVerificationPage />
                </ProtectedRoute>
              }
            />
            <Route path="/migration-preparation" element={<ProtectedRoute><MigrationPreparationHub /></ProtectedRoute>} />
            <Route path="/migration-preparation/workbooks" element={<ProtectedRoute><MigrationWorkbooksPage /></ProtectedRoute>} />
            <Route path="/migration-preparation/mappings" element={<ProtectedRoute><MigrationMappingsPage /></ProtectedRoute>} />
            <Route path="/migration-preparation/dry-runs" element={<ProtectedRoute><MigrationDryRunsPage /></ProtectedRoute>} />
            <Route path="/migration-preparation/dry-runs/:dryRunId" element={<ProtectedRoute><MigrationDryRunDetailPage /></ProtectedRoute>} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          <Toaster position="top-right" richColors closeButton />
        </BrowserRouter>
      </AuthProvider>
    </div>
  );
}

export default App;
