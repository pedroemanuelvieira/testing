import { useNavigate } from "react-router-dom";
import { Icon } from "../components/Icon";
import { Badge, Progress } from "../components/ui";
import { useApp, useFetch } from "../lib/context";
import { PROBLEM_LABEL, relativeTime } from "../lib/format";
import type { AgentCard, Area, ProjectSummary, WorkflowStep } from "../types";

export default function Home() {
  const nav = useNavigate();
  const { meta, openChat } = useApp();
  const areas = useFetch<Area[]>("/api/knowledge/areas");
  const steps = useFetch<WorkflowStep[]>("/api/knowledge/workflow");
  const projects = useFetch<ProjectSummary[]>("/api/projects");
  const agents = useFetch<{ agents: AgentCard[] }>("/api/agents");
  const k = meta?.knowledge;
  return (
    <div className="stack" style={{ gap: 20 }}>
      <section className="hero">
        <div className="row" style={{ gap: 8, marginBottom: 10 }}>
          <Badge tone="purple"><Icon name="sparkles" size={12} />Agentes especializados</Badge>
          <Badge tone="blue"><Icon name="database" size={12} />Ligado ao Power BI Service</Badge>
        </div>
        <h1>Do Power BI à previsão — com um agente para cada etapa</h1>
        <p>
          Enquadre o problema de negócio, ligue-se aos modelos semânticos, prepare os dados, escolha e afine modelos com
          aconselhamento especializado, avalie em euros, explique, cumpra o RGPD/AI Act e publique as previsões de volta no
          Power BI. Tudo guiado, passo a passo, com glossário e assistente sempre à mão.
        </p>
        <div className="row" style={{ marginTop: 16, gap: 10 }}>
          <button className="btn accent" onClick={() => nav("/casos-de-uso")}><Icon name="play" size={15} />Começar por um caso de uso</button>
          <button className="btn" style={{ background: "rgba(255,255,255,.1)", color: "#fff", borderColor: "rgba(255,255,255,.25)" }}
            onClick={() => nav("/glossario?tab=guias&guia=guia_primeiro_projeto")}><Icon name="map" size={15} />Primeiro projeto em 30 min</button>
          <button className="btn" style={{ background: "rgba(255,255,255,.1)", color: "#fff", borderColor: "rgba(255,255,255,.25)" }}
            onClick={() => openChat()}><Icon name="message-circle" size={15} />Tirar uma dúvida</button>
        </div>
        <div className="row" style={{ marginTop: 20, gap: 10 }}>
          {[["Casos de uso", k?.use_cases], ["Áreas de negócio", k?.areas], ["Modelos", k?.models], ["Termos no glossário", k?.terms],
            ["Agentes", (agents.data?.agents.length ?? 0) || undefined], ["Passos guiados", k?.workflow_steps]].map(([l, v]) => (
            <div key={l as string} className="stat"><b>{v ?? "…"}</b><span className="tiny">{l}</span></div>
          ))}
        </div>
      </section>

      <section className="card">
        <div className="card-title"><h3>O percurso de um projeto — 13 passos, 13 agentes</h3>
          <button className="btn ghost sm" onClick={() => nav("/glossario?tab=percurso")}>Ver guia completo<Icon name="chevron-right" size={14} /></button></div>
        <div className="flow">
          {(steps.data ?? []).map((s) => (
            <div key={s.id} className="flow-step" title={s.objective}>
              <div className="n">PASSO {s.order}</div>
              <div style={{ fontWeight: 650, fontSize: ".86rem", lineHeight: 1.25 }}>{s.title}</div>
              <div className="tiny muted" style={{ marginTop: 4 }}>{s.agent_name}</div>
            </div>
          ))}
        </div>
      </section>

      <div className="grid cols-2" style={{ alignItems: "start" }}>
        <section className="card">
          <div className="card-title"><h3>Áreas de negócio</h3><button className="btn ghost sm" onClick={() => nav("/casos-de-uso")}>Todos os casos<Icon name="chevron-right" size={14} /></button></div>
          <div className="grid auto-sm">
            {(areas.data ?? []).map((a) => (
              <div key={a.id} className="card flat area-card" style={{ borderLeftColor: a.color, padding: 12 }} onClick={() => nav(`/casos-de-uso?area=${a.id}`)}>
                <div className="row" style={{ gap: 8 }}><span style={{ color: a.color }}><Icon name={a.icon} size={18} /></span><b className="small">{a.name}</b></div>
                <div className="tiny muted" style={{ marginTop: 4 }}>{a.use_cases} casos de uso · {a.kpis.slice(0, 2).join(", ")}</div>
              </div>
            ))}
          </div>
        </section>
        <section className="card">
          <div className="card-title"><h3>Projetos recentes</h3><button className="btn primary sm" onClick={() => nav("/projetos?novo=1")}><Icon name="plus" size={14} />Novo projeto</button></div>
          {projects.data && projects.data.length === 0 && (
            <div className="empty" style={{ padding: 20 }}>
              <Icon name="projects" size={28} />
              <p className="small" style={{ marginTop: 8 }}>Ainda não há projetos. Crie o primeiro a partir de um caso de uso — os dados de demonstração permitem experimentar tudo.</p>
              <button className="btn primary sm" onClick={() => nav("/casos-de-uso")}>Explorar casos de uso</button>
            </div>
          )}
          <div className="stack tight">
            {(projects.data ?? []).slice(0, 6).map((p) => (
              <div key={p.id} className="card flat" style={{ padding: 10, cursor: "pointer" }} onClick={() => nav(`/projetos/${p.id}`)}>
                <div className="row between"><b className="small">{p.name}</b><span className="tiny muted">{relativeTime(p.updated_at)}</span></div>
                <div className="row" style={{ marginTop: 4 }}>
                  <Badge>{PROBLEM_LABEL[p.problem_type]}</Badge>
                  {p.production_version_id && <Badge tone="ok">em produção</Badge>}
                  <div style={{ flex: 1, minWidth: 80 }}><Progress value={p.progress} /></div>
                  <span className="tiny muted">{Math.round(p.progress * 100)}%</span>
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>

      <section className="card">
        <div className="card-title"><h3>Agentes especializados</h3><button className="btn ghost sm" onClick={() => nav("/agentes")}>Ver todos<Icon name="chevron-right" size={14} /></button></div>
        <div className="grid auto-sm">
          {(agents.data?.agents ?? []).slice(0, 12).map((a) => (
            <div key={a.id} className="card flat" style={{ padding: 12 }}>
              <div className="row" style={{ gap: 8 }}><span style={{ color: "var(--primary-2)" }}><Icon name={a.icon} size={18} /></span><b className="small">{a.component}</b></div>
              <div className="tiny muted" style={{ marginTop: 4 }}>{a.name}</div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
