import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { TruckTrailer } from "@phosphor-icons/react";

export default function Login() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (user) navigate("/", { replace: true });
  }, [user, navigate]);

  const onSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    const res = await login(email.trim(), password);
    setSubmitting(false);
    if (!res.ok) {
      setError(res.error);
    } else {
      navigate("/", { replace: true });
    }
  };

  return (
    <div className="min-h-screen w-full bg-slate-50 flex" data-testid="login-page">
      {/* Left visual / brand panel */}
      <div className="hidden lg:flex w-1/2 bg-slate-900 text-white p-12 flex-col justify-between relative overflow-hidden">
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-md bg-cyan-400 text-slate-900 grid place-items-center font-display font-bold text-sm">
            DCC
          </div>
          <div>
            <div className="font-display font-semibold tracking-tight">Driver Command Centre</div>
            <div className="text-[10px] uppercase tracking-[0.25em] text-cyan-300/80">
              ACE Car Freighters
            </div>
          </div>
        </div>

        <div className="relative">
          <TruckTrailer
            size={220}
            weight="thin"
            className="absolute -right-6 -top-10 text-cyan-500/20"
          />
          <h1 className="font-display text-4xl xl:text-5xl font-semibold tracking-tight leading-[1.05] max-w-md">
            Transport operations,<br />
            <span className="text-cyan-400">under one command.</span>
          </h1>
          <p className="mt-6 text-slate-400 max-w-md text-sm leading-relaxed">
            Drivers, licences, vehicles, equipment, maintenance and compliance —
            all from a single command centre built for the people who run the road.
          </p>
        </div>

        <div className="grid grid-cols-3 gap-6 text-xs uppercase tracking-[0.2em] text-slate-500">
          <div>
            <div className="text-white font-display text-xl mb-1">8</div>
            Operational Modules
          </div>
          <div>
            <div className="text-white font-display text-xl mb-1">24/7</div>
            Built for Dispatch
          </div>
          <div>
            <div className="text-white font-display text-xl mb-1">100%</div>
            Compliance Ready
          </div>
        </div>
      </div>

      {/* Right form panel */}
      <div className="flex-1 flex items-center justify-center px-6 py-12 bg-white">
        <div className="w-full max-w-sm">
          <div className="lg:hidden flex items-center gap-3 mb-10">
            <div className="h-8 w-8 rounded-md bg-cyan-400 text-slate-900 grid place-items-center font-display font-bold text-xs">
              DCC
            </div>
            <div className="font-display font-semibold text-slate-900">Driver Command Centre</div>
          </div>

          <div className="mb-8">
            <div className="text-[10px] uppercase tracking-[0.25em] text-slate-500 mb-3 flex items-center gap-2">
              <span className="inline-flex h-1.5 w-1.5 rounded-full bg-cyan-500" />
              Sign in
            </div>
            <h2 className="font-display text-3xl font-semibold text-slate-900 tracking-tight">
              Operations access
            </h2>
            <p className="text-sm text-slate-500 mt-2">
              Enter your credentials to access the Driver Command Centre.
            </p>
          </div>

          <form onSubmit={onSubmit} className="space-y-5" data-testid="login-form">
            <div>
              <label className="block text-xs uppercase tracking-[0.2em] font-semibold text-slate-500 mb-2">
                Email
              </label>
              <input
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                data-testid="login-email-input"
                className="w-full border border-slate-200 rounded-lg px-4 py-3 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-cyan-500/20 focus:border-cyan-500 transition-colors"
                placeholder="you@acecarfreighters.com"
              />
            </div>

            <div>
              <label className="block text-xs uppercase tracking-[0.2em] font-semibold text-slate-500 mb-2">
                Password
              </label>
              <input
                type="password"
                required
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                data-testid="login-password-input"
                className="w-full border border-slate-200 rounded-lg px-4 py-3 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-cyan-500/20 focus:border-cyan-500 transition-colors"
                placeholder="••••••••"
              />
            </div>

            {error && (
              <div
                data-testid="login-error"
                className="text-sm text-red-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2"
              >
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={submitting}
              data-testid="login-submit-button"
              className="w-full bg-slate-900 text-white hover:bg-slate-800 rounded-lg px-6 py-3 font-medium text-sm transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {submitting ? "Signing in…" : "Sign in to DCC"}
            </button>
          </form>

          <div className="mt-10 border border-slate-200 rounded-lg p-4 bg-slate-50">
            <div className="text-[10px] uppercase tracking-[0.2em] font-semibold text-slate-500 mb-2">
              Prototype Seeded Admin
            </div>
            <div className="text-xs text-slate-700 font-mono leading-relaxed">
              admin@acedriverhub.com<br />Admin@123
            </div>
            <div className="text-[11px] text-slate-500 mt-2 leading-relaxed">
              For prototype testing only. Replace seeded credentials before
              real-world deployment.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
