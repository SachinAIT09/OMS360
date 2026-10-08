import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, ApiError, tokenStore } from "../api/client";
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
    // A free-tier server that was asleep answers 502/503 or not at all while it boots: keep trying for about a minute.
    const deadline = Date.now() + 60_000;
    let r: { token: string; user: User };
    for (;;) {
      try { r = await api.post<{ token: string; user: User }>("/auth/login", { email, password }); break; }
      catch (e) {
        if (!(e instanceof ApiError && [0, 502, 503, 504].includes(e.status)) || Date.now() > deadline) throw e;
        await new Promise(res => setTimeout(res, 3000));
      }
    }
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
