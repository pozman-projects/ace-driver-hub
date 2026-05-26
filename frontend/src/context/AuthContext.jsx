import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import api, { formatApiErrorDetail } from "../lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  // user: undefined = checking; null = unauthenticated; object = authenticated
  const [user, setUser] = useState(undefined);

  const refreshMe = useCallback(async () => {
    const token = localStorage.getItem("ace_token");
    if (!token) {
      setUser(null);
      return;
    }
    try {
      const { data } = await api.get("/auth/me");
      setUser(data);
      localStorage.setItem("ace_user", JSON.stringify(data));
    } catch (e) {
      localStorage.removeItem("ace_token");
      localStorage.removeItem("ace_user");
      setUser(null);
    }
  }, []);

  useEffect(() => {
    refreshMe();
  }, [refreshMe]);

  const login = async (email, password) => {
    try {
      const { data } = await api.post("/auth/login", { email, password });
      localStorage.setItem("ace_token", data.access_token);
      localStorage.setItem("ace_user", JSON.stringify(data.user));
      setUser(data.user);
      return { ok: true };
    } catch (e) {
      return {
        ok: false,
        error: formatApiErrorDetail(e?.response?.data?.detail) || "Login failed",
      };
    }
  };

  const logout = () => {
    localStorage.removeItem("ace_token");
    localStorage.removeItem("ace_user");
    setUser(null);
    window.location.href = "/login";
  };

  return (
    <AuthContext.Provider value={{ user, login, logout, refreshMe }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
