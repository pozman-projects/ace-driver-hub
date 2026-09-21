import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem("ace_token")}` } });

const HEX_RE = /^#[0-9A-Fa-f]{6}$/;

function useMe() {
  const [me, setMe] = useState(null);
  useEffect(() => {
    axios.get(`${API}/auth/me`, auth()).then((r) => setMe(r.data)).catch(() => setMe(null));
  }, []);
  return me;
}

function useThemePref() {
  const [theme, setTheme] = useState("light");
  const [loading, setLoading] = useState(true);
  const load = async () => {
    try {
      const r = await axios.get(`${API}/user-preferences/theme`, auth());
      setTheme(r.data?.theme || "light");
    } catch { setTheme("light"); } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);
  const save = async (next) => {
    setTheme(next);
    try {
      await axios.put(`${API}/user-preferences/theme`, { theme: next }, auth());
      toast.success(next === "dark"
        ? "Dark preference saved. Full visual Dark Mode is coming in the dedicated Dark Mode rollout."
        : "Light preference saved.");
    } catch (err) {
      toast.error(`Could not save preference: ${err.response?.data?.detail || err.message}`);
      load();
    }
  };
  return { theme, loading, save };
}

function useSkin() {
  const [skin, setSkin] = useState({ accent_colour: null, has_logo: false });
  const [loading, setLoading] = useState(true);
  const load = async () => {
    try {
      const r = await axios.get(`${API}/settings/skin`, auth());
      setSkin(r.data || {});
    } catch { setSkin({ accent_colour: null, has_logo: false }); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);
  return { skin, loading, reload: load };
}

function ThemeSection({ initialSection }) {
  const { theme, loading, save } = useThemePref();
  return (
    <section id="theme" data-testid="appearance-theme-section"
             className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-baseline justify-between mb-4">
        <div>
          <div className="text-[10px] uppercase tracking-[0.18em] text-slate-500">
            Section 1 · Personal preference
          </div>
          <h2 className="text-lg font-semibold text-slate-900" data-testid="theme-title">
            Theme
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Your own light/dark preference. Saved to your account.
          </p>
        </div>
        <span className="text-[10px] text-slate-400 uppercase tracking-[0.14em]"
              data-testid="theme-current">
          Current · {loading ? "…" : theme}
        </span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <label data-testid="theme-option-light"
               className={`flex items-start gap-3 rounded-lg border px-3 py-3 cursor-pointer transition-colors ${theme === "light" ? "border-cyan-500 bg-cyan-50" : "border-slate-200 hover:border-slate-300"}`}>
          <input type="radio" name="theme" value="light" checked={theme === "light"}
                 onChange={() => save("light")} className="mt-1"
                 data-testid="theme-radio-light" disabled={loading}/>
          <span>
            <span className="block text-sm font-medium text-slate-900">Light</span>
            <span className="block text-xs text-slate-500 mt-0.5">Available</span>
          </span>
        </label>
        <label data-testid="theme-option-dark"
               className={`flex items-start gap-3 rounded-lg border px-3 py-3 cursor-pointer transition-colors ${theme === "dark" ? "border-cyan-500 bg-cyan-50" : "border-slate-200 hover:border-slate-300"}`}>
          <input type="radio" name="theme" value="dark" checked={theme === "dark"}
                 onChange={() => save("dark")} className="mt-1"
                 data-testid="theme-radio-dark" disabled={loading}/>
          <span>
            <span className="block text-sm font-medium text-slate-900">Dark</span>
            <span className="block text-xs text-slate-500 mt-0.5" data-testid="theme-dark-note">
              Preference can be saved. Full visual Dark Mode is coming in the
              dedicated Dark Mode rollout.
            </span>
          </span>
        </label>
      </div>
      {initialSection === "theme" && (
        <div className="mt-3 text-[10px] uppercase tracking-[0.14em] text-cyan-600"
             data-testid="theme-anchor-active">Section link opened</div>
      )}
    </section>
  );
}

function SkinSection({ me, initialSection }) {
  const canManage = me && ["Admin", "Manager"].includes(me.role);
  const { skin, loading, reload } = useSkin();
  const fileRef = useRef(null);
  const [accent, setAccent] = useState("");
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);

  useEffect(() => { if (skin?.accent_colour) setAccent(skin.accent_colour); }, [skin?.accent_colour]);

  const hexValid = accent === "" || HEX_RE.test(accent);
  const previewAccent = hexValid && accent ? accent : (skin?.accent_colour || "#0EA5E9");

  const logoUrl = useMemo(() => (
    skin?.has_logo ? `${API}/settings/skin/logo?t=${skin?.updated_at || ""}` : null
  ), [skin?.has_logo, skin?.updated_at]);

  const saveAccent = async () => {
    if (!hexValid) { toast.error("Accent must be a #RRGGBB hex value"); return; }
    setSaving(true);
    try {
      await axios.put(`${API}/settings/skin`, { accent_colour: accent || null }, auth());
      toast.success("Skin accent saved");
      reload();
    } catch (err) {
      toast.error(`Save failed: ${err.response?.data?.detail || err.message}`);
    } finally { setSaving(false); }
  };

  const uploadLogo = async (file) => {
    if (!file) return;
    if (!["image/png", "image/jpeg"].includes(file.type)) {
      toast.error("Logo must be PNG or JPEG"); return;
    }
    setUploading(true);
    const fd = new FormData();
    fd.append("file", file);
    try {
      await axios.post(`${API}/settings/skin/logo`, fd, {
        ...auth(),
        headers: { ...auth().headers, "Content-Type": "multipart/form-data" },
      });
      toast.success("Logo uploaded");
      reload();
    } catch (err) {
      toast.error(`Upload failed: ${err.response?.data?.detail || err.message}`);
    } finally { setUploading(false); }
  };

  const removeLogo = async () => {
    try {
      await axios.delete(`${API}/settings/skin/logo`, auth());
      toast.success("Logo removed. ACE text branding restored.");
      reload();
    } catch (err) {
      toast.error(`Remove failed: ${err.response?.data?.detail || err.message}`);
    }
  };

  return (
    <section id="skin" data-testid="appearance-skin-section"
             className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-baseline justify-between mb-4">
        <div>
          <div className="text-[10px] uppercase tracking-[0.18em] text-slate-500">
            Section 2 · Global brand
          </div>
          <h2 className="text-lg font-semibold text-slate-900" data-testid="skin-title">Skin</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            One organisation-wide logo and accent colour. Applies to Driver PDFs and brand surfaces.
          </p>
        </div>
        {!canManage && (
          <span className="text-[10px] text-slate-400 uppercase tracking-[0.14em]"
                data-testid="skin-readonly-badge">Read-only</span>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* LOGO COLUMN */}
        <div>
          <div className="text-[10px] uppercase tracking-[0.16em] text-slate-500 mb-2">Logo</div>
          <div data-testid="skin-logo-preview"
               className="h-24 rounded-lg border border-dashed border-slate-300 bg-slate-50 flex items-center justify-center overflow-hidden">
            {loading ? (
              <span className="text-xs text-slate-400">Loading…</span>
            ) : logoUrl ? (
              <img src={logoUrl} alt="Skin logo" className="max-h-20 max-w-full object-contain"
                   data-testid="skin-logo-img"/>
            ) : (
              <span className="text-xs text-slate-500" data-testid="skin-logo-fallback">
                ACE Driver Command Centre (default text branding)
              </span>
            )}
          </div>
          {canManage && (
            <div className="mt-2 flex items-center gap-2">
              <input ref={fileRef} type="file" accept="image/png,image/jpeg"
                     className="hidden" onChange={(e) => uploadLogo(e.target.files?.[0])}
                     data-testid="skin-logo-file-input"/>
              <button className="text-xs px-2.5 py-1.5 rounded-md border border-slate-200 hover:border-cyan-400 hover:bg-cyan-50"
                      onClick={() => fileRef.current?.click()} disabled={uploading}
                      data-testid="skin-logo-upload-btn">
                {uploading ? "Uploading…" : (skin?.has_logo ? "Replace Logo" : "Upload Logo")}
              </button>
              {skin?.has_logo && (
                <button className="text-xs px-2.5 py-1.5 rounded-md border border-rose-200 text-rose-700 hover:bg-rose-50"
                        onClick={removeLogo} data-testid="skin-logo-remove-btn">Remove</button>
              )}
              <span className="text-[10px] text-slate-500">PNG or JPEG · max 512 KB</span>
            </div>
          )}
        </div>

        {/* ACCENT COLUMN */}
        <div>
          <div className="text-[10px] uppercase tracking-[0.16em] text-slate-500 mb-2">Accent colour</div>
          <div className="flex items-center gap-2">
            <input type="color" value={accent || previewAccent}
                   onChange={(e) => setAccent(e.target.value.toUpperCase())}
                   className="h-10 w-14 rounded border border-slate-200 cursor-pointer"
                   disabled={!canManage}
                   data-testid="skin-accent-color"/>
            <input type="text" value={accent} placeholder="#RRGGBB"
                   onChange={(e) => setAccent(e.target.value.trim().toUpperCase())}
                   maxLength={7}
                   className={`h-10 flex-1 px-2 rounded border text-sm font-mono ${hexValid ? "border-slate-200" : "border-rose-400"}`}
                   disabled={!canManage}
                   data-testid="skin-accent-hex"/>
            {canManage && (
              <button onClick={saveAccent} disabled={saving || !hexValid}
                      className="text-xs px-3 py-2 rounded-md bg-slate-900 text-white disabled:opacity-50"
                      data-testid="skin-accent-save">
                {saving ? "Saving…" : "Save"}
              </button>
            )}
          </div>
          {!hexValid && (
            <div className="mt-1 text-[10px] text-rose-600" data-testid="skin-accent-error">
              Must be a valid #RRGGBB hex value
            </div>
          )}

          {/* Small branding preview */}
          <div className="mt-3 rounded-lg border border-slate-200 overflow-hidden"
               data-testid="skin-preview">
            <div style={{ backgroundColor: "#0F172A" }} className="px-3 py-2 flex items-center gap-2">
              {logoUrl
                ? <img src={logoUrl} alt="" className="h-4 max-w-[80px] object-contain"/>
                : <span className="text-[10px] uppercase tracking-[0.18em]"
                        style={{ color: previewAccent }}>ACE Car Freighters</span>}
              <span className="text-white text-xs">Driver Command Centre</span>
            </div>
            <div className="px-3 py-2 flex items-center gap-2 bg-white">
              <button style={{ backgroundColor: previewAccent }}
                      className="text-white text-xs px-3 py-1.5 rounded-md">
                Sample brand button
              </button>
              <span className="text-[10px] text-slate-500">Accent applied to branding surfaces only</span>
            </div>
          </div>
        </div>
      </div>
      {initialSection === "skin" && (
        <div className="mt-3 text-[10px] uppercase tracking-[0.14em] text-cyan-600"
             data-testid="skin-anchor-active">Section link opened</div>
      )}
    </section>
  );
}

export default function AppearancePage() {
  const me = useMe();
  const { hash, search } = useLocation();
  const initialSection = useMemo(() => {
    const q = new URLSearchParams(search).get("section");
    if (q === "theme" || q === "skin") return q;
    if (hash === "#theme" || hash === "#skin") return hash.slice(1);
    return null;
  }, [search, hash]);

  useEffect(() => {
    if (initialSection) {
      const el = document.getElementById(initialSection);
      if (el) el.scrollIntoView({ block: "start", behavior: "smooth" });
    }
  }, [initialSection]);

  return (
    <div className="min-h-screen bg-slate-50" data-testid="appearance-page">
      <div className="max-w-4xl mx-auto px-6 py-8">
        <div className="mb-6 flex items-baseline justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.18em] text-slate-500">Administration</div>
            <h1 className="text-2xl font-semibold text-slate-900">Appearance</h1>
            <p className="text-sm text-slate-500 mt-1">
              Personal Theme preference and global Skin branding.
            </p>
          </div>
          <Link to="/hub" className="text-xs text-slate-600 underline"
                data-testid="appearance-back-link">← Back to hub</Link>
        </div>

        <div className="space-y-6">
          <ThemeSection initialSection={initialSection}/>
          <SkinSection me={me} initialSection={initialSection}/>
        </div>
      </div>
    </div>
  );
}
