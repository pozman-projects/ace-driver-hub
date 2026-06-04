import React from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";
import { ArrowLeft, SignOut } from "@phosphor-icons/react";

export default function AppHeader({ showBack = false }) {
  const { user, logout } = useAuth();
  const location = useLocation();
  const onHub = location.pathname === "/";

  return (
    <header
      data-testid="app-header"
      className="bg-white border-b border-gray-200 sticky top-0 z-40 px-6 lg:px-12 py-3 flex items-center justify-between"
    >
      <div className="flex items-center gap-6">
        {showBack && !onHub && (
          <Link
            to="/"
            data-testid="back-to-hub-link"
            className="inline-flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900 transition-colors"
          >
            <ArrowLeft size={16} weight="bold" />
            Back to Hub
          </Link>
        )}
        <Link to="/" className="flex items-center gap-3" data-testid="brand-link">
          <div className="h-8 w-8 rounded-md bg-gray-900 text-white grid place-items-center font-display font-bold text-sm">
            A
          </div>
          <div className="leading-tight">
            <div className="font-display font-semibold text-gray-900 text-base">
              ACE Driver Hub
            </div>
            <div className="text-[10px] uppercase tracking-[0.2em] text-gray-500">
              Operations Control
            </div>
          </div>
        </Link>
      </div>

      <div className="flex items-center gap-4">
        {user && (
          <div className="hidden md:flex flex-col items-end leading-tight" data-testid="header-user-info">
            <span className="text-sm font-medium text-gray-900">{user.full_name}</span>
            <span className="text-[10px] uppercase tracking-[0.2em] text-gray-500">
              {user.role}
            </span>
          </div>
        )}
        <button
          onClick={logout}
          data-testid="logout-button"
          className="inline-flex items-center gap-2 text-sm text-gray-700 hover:text-gray-900 border border-gray-200 hover:border-gray-300 rounded-lg px-3 py-1.5 transition-colors"
        >
          <SignOut size={16} weight="bold" />
          Logout
        </button>
      </div>
    </header>
  );
}
