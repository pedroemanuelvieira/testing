import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, safeStorage } from "../api";
import type { Meta, Term } from "../types";

interface AppState {
  meta: Meta | null;
  terms: Record<string, Term>;
  termsLoaded: boolean;
  currentProject: { id: string; name: string } | null;
  setCurrentProject: (p: { id: string; name: string } | null) => void;
  chatOpen: boolean;
  openChat: (prefill?: string) => void;
  closeChat: () => void;
  chatPrefill: string | null;
  consumePrefill: () => string | null;
  theme: "light" | "dark" | "system";
  setTheme: (t: "light" | "dark" | "system") => void;
  refreshMeta: () => void;
}

const Ctx = createContext<AppState | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [terms, setTerms] = useState<Record<string, Term>>({});
  const [termsLoaded, setTermsLoaded] = useState(false);
  const [currentProject, setCurrentProject] = useState<{ id: string; name: string } | null>(null);
  const [chatOpen, setChatOpen] = useState(false);
  const [chatPrefill, setChatPrefill] = useState<string | null>(null);
  const [theme, setThemeState] = useState<"light" | "dark" | "system">((safeStorage("theme") as any) || "system");

  const refreshMeta = useCallback(() => {
    api.get<Meta>("/api/meta").then(setMeta).catch(() => undefined);
  }, []);

  useEffect(() => {
    refreshMeta();
    api.get<Term[]>("/api/knowledge/glossary")
      .then((list) => { setTerms(Object.fromEntries(list.map((t) => [t.id, t]))); setTermsLoaded(true); })
      .catch(() => setTermsLoaded(true));
  }, [refreshMeta]);

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);
    safeStorage("theme", theme);
  }, [theme]);

  const value = useMemo<AppState>(() => ({
    meta, terms, termsLoaded, currentProject, setCurrentProject, chatOpen,
    openChat: (prefill?: string) => { if (prefill) setChatPrefill(prefill); setChatOpen(true); },
    closeChat: () => setChatOpen(false),
    chatPrefill,
    consumePrefill: () => { const p = chatPrefill; setChatPrefill(null); return p; },
    theme, setTheme: setThemeState, refreshMeta,
  }), [meta, terms, termsLoaded, currentProject, chatOpen, chatPrefill, theme, refreshMeta]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp fora do AppProvider");
  return v;
}

/** Carrega dados de um endpoint com estado de carregamento/erro. */
export function useFetch<T>(path: string | null, deps: unknown[] = []): { data: T | null; error: unknown; loading: boolean; reload: () => void } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState<boolean>(!!path);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!path) { setLoading(false); return; }
    let alive = true;
    setLoading(true);
    api.get<T>(path)
      .then((d) => { if (alive) { setData(d); setError(null); } })
      .catch((e) => { if (alive) setError(e); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, tick, ...deps]);
  return { data, error, loading, reload: () => setTick((t) => t + 1) };
}
