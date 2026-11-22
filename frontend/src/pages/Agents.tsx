import { Icon } from "../components/Icon";
import { Badge, Spinner } from "../components/ui";
import { useFetch } from "../lib/context";
import { PROBLEM_LABEL } from "../lib/format";
import type { AgentCard } from "../types";

export default function Agents() {
  const { data } = useFetch<{ agents: AgentCard[]; flows: Record<string, string[]>; trainers: Record<string, string> }>("/api/agents");
  if (!data) return <Spinner />;
  const byId = Object.fromEntries(data.agents.map((a) => [a.id, a]));
  return (
    <div className="stack">
      <div className="page-head">
        <div><h1>Agentes especializados</h1>
          <p>Cada componente de ML tem um agente dedicado, com conhecimento próprio, e todos se especializam pelo caso de uso e pela
            área de negócio. O orquestrador encadeia-os num percurso adaptado ao tipo de problema.</p></div>
      </div>
      <section className="card">
        <h3>Percursos por tipo de problema (piloto automático)</h3>
        <div className="stack tight">
          {Object.entries(data.flows).map(([pt, flow]) => (
            <div key={pt} className="row" style={{ alignItems: "flex-start" }}>
              <div style={{ width: 190, flexShrink: 0 }}><Badge tone="blue">{PROBLEM_LABEL[pt]}</Badge></div>
              <div className="pipeline">
                {flow.map((a, i) => (
                  <span key={a} className="row" style={{ gap: 6 }}>
                    <span className="node" title={byId[a]?.description}>{byId[a]?.component ?? a}</span>
                    {i < flow.length - 1 && <Icon name="chevron-right" size={13} />}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>
      <div className="grid auto">
        {data.agents.map((a) => (
          <div key={a.id} className="card stack tight">
            <div className="row">
              <span style={{ width: 38, height: 38, borderRadius: 10, display: "grid", placeItems: "center", background: "var(--primary-soft)", color: "var(--primary-text)" }}>
                <Icon name={a.icon} size={20} /></span>
              <div style={{ minWidth: 0 }}><b>{a.name}</b><div className="tiny muted">{a.component} · {a.role}</div></div>
            </div>
            <p className="small" style={{ color: "var(--text-2)" }}>{a.description}</p>
            <div className="row" style={{ gap: 4 }}>{a.capabilities.map((c) => <Badge key={c}>{c}</Badge>)}</div>
            <div className="grid cols-2 small" style={{ marginTop: 4 }}>
              <div><b>Entradas</b>{a.inputs.map((i) => <div key={i} className="muted">• {i}</div>)}</div>
              <div><b>Saídas</b>{a.outputs.map((i) => <div key={i} className="muted">• {i}</div>)}</div>
            </div>
            {a.problem_types.length > 0 && <div className="row">{a.problem_types.map((p) => <Badge key={p} tone="purple">{PROBLEM_LABEL[p]}</Badge>)}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}
