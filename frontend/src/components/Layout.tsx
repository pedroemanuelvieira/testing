import { useEffect, useRef, useState, type ReactNode } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useApp } from "../lib/context";
import { Chatbot } from "./Chatbot";
import { Icon } from "./Icon";
import { Badge } from "./ui";

const NAV: { section: string; items: { to: string; label: string; icon: string }[] }[] = [
  { section: "Começar", items: [
    { to: "/", label: "Início", icon: "home" },
    { to: "/casos-de-uso", label: "Casos de uso", icon: "briefcase" },
  ] },
  { section: "Construir", items: [
    { to: "/dados", label: "Dados (Power BI)", icon: "database" },
    { to: "/projetos", label: "Projetos", icon: "projects" },
    { to: "/conselheiro", label: "Conselheiro de parâmetros", icon: "sliders" },
  ] },
  { section: "Operar", items: [
    { to: "/modelos", label: "Modelos & monitorização", icon: "rocket" },
    { to: "/agentes", label: "Agentes", icon: "bot" },
  ] },
  { section: "Aprender", items: [
    { to: "/glossario", label: "Glossário & guias", icon: "book-open" },
  ] },
];

const KIND_LABEL: Record<string, string> = { term: "Glossário", use_case: "Caso de uso", model: "Modelo", guide: "Guia", faq: "FAQ", step: "Passo", area: "Área" };

function GlobalSearch() {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<any[]>([]);
  const [open, setOpen] = useState(false);
  const nav = useNavigate();
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (q.trim().length < 2) { setResults([]); return; }
    const t = setTimeout(() => api.get<any[]>(`/api/knowledge/search?q=${encodeURIComponent(q)}&k=10`).then(setResults).catch(() => setResults([])), 200);
    return () => clearTimeout(t);
  }, [q]);
  useEffect(() => {
    const onDoc = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);
  function go(r: any) {
    setOpen(false); setQ("");
    const routes: Record<string, string> = {
      term: `/glossario/${r.id}`, use_case: `/casos-de-uso?caso=${r.id}`, model: `/conselheiro?modelo=${r.id}`,
      guide: `/glossario?tab=guias&guia=${r.id}`, faq: `/glossario?tab=faq`, step: `/glossario?tab=percurso&passo=${r.id}`,
      area: `/casos-de-uso?area=${r.id}`,
    };
    nav(routes[r.kind] ?? "/");
  }
  return (
    <div ref={box} style={{ position: "relative", flex: 1, maxWidth: 560 }}>
      <div className="row" style={{ gap: 0 }}>
        <span style={{ position: "absolute", left: 10, top: 9, color: "var(--text-3)" }}><Icon name="search" size={16} /></span>
        <input className="input" style={{ paddingLeft: 34 }} placeholder="Pesquisar termos, casos de uso, modelos, guias…" value={q}
          onChange={(e) => { setQ(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)}
          onKeyDown={(e) => { if (e.key === "Enter" && results[0]) go(results[0]); }} />
      </div>
      {open && results.length > 0 && (
        <div className="search-results">
          {results.map((r) => (
            <div key={`${r.kind}-${r.id}`} className="search-item" onClick={() => go(r)}>
              <Badge tone="blue">{KIND_LABEL[r.kind] ?? r.kind}</Badge>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontWeight: 600 }}>{r.title}</div>
                <div className="tiny muted" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 420 }}>{r.snippet}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function Layout({ children }: { children: ReactNode }) {
  const { meta, theme, setTheme, openChat } = useApp();
  const [menu, setMenu] = useState(false);
  const loc = useLocation();
  useEffect(() => setMenu(false), [loc.pathname]);
  const connectorOk = meta?.connectors.some((c) => c.status === "ok" && c.kind !== "files");
  const internal = meta?.connectors.find((c) => c.kind === "internal");
  return (
    <div className="app">
      <aside className={`sidebar ${menu ? "open" : ""}`}>
        <NavLink to="/" className="brand">
          <div className="brand-logo"><Icon name="trending-up" size={19} /></div>
          <div><div className="brand-name">BI ML Studio</div><div className="brand-sub">Machine learning para equipas de BI</div></div>
        </NavLink>
        <nav className="nav">
          {NAV.map((s) => (
            <div key={s.section}>
              <div className="nav-section">{s.section}</div>
              {s.items.map((i) => (
                <NavLink key={i.to} to={i.to} end={i.to === "/"} className={({ isActive }) => (isActive ? "active" : "")}>
                  <Icon name={i.icon} size={17} />{i.label}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="row"><span className={`dot ${internal ? (internal.status === "ok" ? "ok" : "crit") : connectorOk ? "warn" : "crit"}`} />
            {internal ? (internal.status === "ok" ? "Conector interno Power BI ativo" : "Conector interno com erro") : "Dados de demonstração"}</div>
          <div className="row"><span className={`dot ${meta?.assistant.mode === "llm" ? "ok" : "warn"}`} />
            Assistente {meta?.assistant.mode === "llm" ? "IA ativo" : "em modo offline"}</div>
          <div className="tiny">v{meta?.version ?? "…"} · {meta?.knowledge.terms ?? "…"} termos · {meta?.knowledge.use_cases ?? "…"} casos</div>
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <button className="icon-btn menu-btn" onClick={() => setMenu((m) => !m)} aria-label="Menu"><Icon name="layers" size={20} /></button>
          <GlobalSearch />
          <div className="spacer" />
          <button className="btn ghost sm" onClick={() => openChat()}><Icon name="sparkles" size={15} /><span className="hide-mobile">Perguntar ao assistente</span></button>
          <button className="icon-btn" title="Tema" onClick={() => setTheme(theme === "dark" ? "light" : theme === "light" ? "system" : "dark")}>
            <Icon name={theme === "dark" ? "moon" : theme === "light" ? "sun" : "settings"} size={18} />
          </button>
        </header>
        <main className="content">{children}</main>
      </div>
      <Chatbot />
    </div>
  );
}
