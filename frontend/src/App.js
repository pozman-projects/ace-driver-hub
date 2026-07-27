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
import RegisterPage from "./pages/RegisterPage";
import RelationshipPage from "./pages/RelationshipPage";
import CompliancePage from "./pages/CompliancePage";
import DocumentLibrary from "./pages/DocumentLibrary";
import ImportCentre from "./pages/ImportCentre";
import ImportWizard from "./pages/ImportWizard";
import NotificationsCentre from "./pages/NotificationsCentre";

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
                  <DriverProfile />
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
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          <Toaster position="top-right" richColors closeButton />
        </BrowserRouter>
      </AuthProvider>
    </div>
  );
}

export default App;
