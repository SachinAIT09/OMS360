import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, tokenStore } from "../api/client";
import type { User } from "../api/types";

interface Auth {
  user: User | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  can: (permission: string) => boolean;
}

const Ctx = createContext<Auth | null>(null);
export const useAuth = () => {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAuth outside AuthProvider");
  return c;
};

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const qc = useQueryClient();

  useEffect(() => {
    if (!tokenStore.get()) { setReady(true); return; }
    api.get<User>("/auth/me").then(setUser).catch(() => tokenStore.set(null)).finally(() => setReady(true));
  }, []);

  useEffect(() => {
    const h = () => { setUser(null); qc.clear(); };
    window.addEventListener("oms360:signed-out", h);
    return () => window.removeEventListener("oms360:signed-out", h);
  }, [qc]);

  const login = useCallback(async (email: string, password: string) => {
    const r = await api.post<{ token: string; user: User }>("/auth/login", { email, password });
    tokenStore.set(r.token);
    setUser(r.user);
  }, []);

  const logout = useCallback(async () => {
    try { await api.post("/auth/logout"); } catch { /* already gone */ }
    tokenStore.set(null);
    setUser(null);
    qc.clear();
  }, [qc]);

  const can = useCallback((p: string) => !!user?.permissions.includes(p), [user]);

  return <Ctx.Provider value={{ user, ready, login, logout, can }}>{children}</Ctx.Provider>;
}
