import React from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";

export default function ProtectedRoute({ children }) {
  const { user } = useAuth();
  if (user === undefined) {
    return (
      <div
        data-testid="auth-loading"
        className="min-h-screen flex items-center justify-center bg-white text-gray-500 text-sm tracking-wide"
      >
        Loading ACE Driver Hub…
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  return children;
}
