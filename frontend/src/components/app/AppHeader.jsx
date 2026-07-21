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
      className="bg-slate-900 text-white border-b border-slate-800 sticky top-0 z-40 px-6 lg:px-10 py-3 flex items-center justify-between"
    >
      <div className="flex items-center gap-6">
        {showBack && !onHub && (
          <Link
            to="/"
            data-testid="back-to-hub-link"
            className="inline-flex items-center gap-2 text-sm text-slate-300 hover:text-white transition-colors"
          >
            <ArrowLeft size={16} weight="bold" />
            Back to Command Centre
          </Link>
        )}
        <Link to="/" className="flex items-center gap-3" data-testid="brand-link">
          <div className="h-9 w-9 rounded-md bg-cyan-400 text-slate-900 grid place-items-center font-display font-bold text-sm shadow-[0_0_0_1px_rgba(34,211,238,0.35)_inset]">
            DCC
          </div>
          <div className="leading-tight">
            <div className="font-display font-semibold text-white text-base tracking-tight">
              Driver Command Centre
            </div>
            <div className="text-[10px] uppercase tracking-[0.25em] text-cyan-300/80">
              ACE Car Freighters · Ops
            </div>
          </div>
        </Link>
      </div>

      <div className="flex items-center gap-4">
        {user && (
          <div className="hidden md:flex flex-col items-end leading-tight" data-testid="header-user-info">
            <span className="text-sm font-medium text-white">{user.full_name}</span>
            <span className="text-[10px] uppercase tracking-[0.25em] text-cyan-300/80">
              {user.role}
            </span>
          </div>
        )}
        <button
          onClick={logout}
          data-testid="logout-button"
          className="inline-flex items-center gap-2 text-sm text-slate-200 hover:text-white border border-slate-700 hover:border-cyan-400 rounded-lg px-3 py-1.5 transition-colors"
        >
          <SignOut size={16} weight="bold" />
          Logout
        </button>
      </div>
    </header>
  );
}
