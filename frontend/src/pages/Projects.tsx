import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { Icon } from "../components/Icon";
import { Badge, Empty, ErrorBox, Modal, Progress, Spinner } from "../components/ui";
import { useFetch } from "../lib/context";
import { formatValue, PROBLEM_LABEL, relativeTime } from "../lib/format";
import type { ProblemType, ProjectSummary, ProjectView, UseCase } from "../types";

function NewProject({ onClose }: { onClose: () => void }) {
  const nav = useNavigate();
  const ucs = useFetch<UseCase[]>("/api/knowledge/use-cases");
  const pts = useFetch<ProblemType[]>("/api/knowledge/problem-types");
  const [mode, setMode] = useState<"uc" | "custom">("uc");
  const [uc, setUc] = useState("churn_clientes");
  const [name, setName] = useState("");
  const [pt, setPt] = useState("binary_classification");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  async function create() {
    setBusy(true);
    try {
      const body = mode === "uc" ? { use_case_id: uc, name: name || undefined } : { name: name || "Novo projeto", problem_type: pt };
      const v = await api.post<ProjectView>("/api/projects", body);
      nav(`/projetos/${v.project.id}`);
    } catch (e) { setErr(e); } finally { setBusy(false); }
  }
  return (
    <Modal size="sm" title="Novo projeto" onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancelar</button><button className="btn primary" onClick={create} disabled={busy}>{busy && <Spinner />}Criar projeto</button></>}>
      <div className="stack">
        <ErrorBox error={err} />
        <div className="row">
          <button className={`chip ${mode === "uc" ? "active" : ""}`} onClick={() => setMode("uc")}>A partir de um caso de uso</button>
          <button className={`chip ${mode === "custom" ? "active" : ""}`} onClick={() => setMode("custom")}>Projeto personalizado</button>
        </div>
        {mode === "uc" ? (
          <label className="field">Caso de uso
            <select className="select" value={uc} onChange={(e) => setUc(e.target.value)}>
              {(ucs.data ?? []).map((u) => <option key={u.id} value={u.id}>{u.name} — {PROBLEM_LABEL[u.problem_type]}</option>)}
            </select>
            <span className="tiny muted">A fonte de dados de demonstração e a configuração do caso são preenchidas automaticamente.</span>
          </label>
        ) : (
          <label className="field">Tipo de problema
            <select className="select" value={pt} onChange={(e) => setPt(e.target.value)}>{(pts.data ?? []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
            <span className="tiny muted">Depois escolha a fonte de dados no passo 2 (ou crie o projeto a partir da página Dados).</span>
          </label>
        )}
        <label className="field">Nome (opcional)<input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="ex.: Churn — clientes particulares Q4" /></label>
      </div>
    </Modal>
  );
}

export default function Projects() {
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const { data, error, loading } = useFetch<ProjectSummary[]>("/api/projects");
  const open = params.get("novo") === "1";
  return (
    <div className="stack">
      <div className="page-head">
        <div><h1>Projetos</h1><p>Cada projeto percorre os passos do enquadramento à monitorização, com um agente por etapa.</p></div>
        <button className="btn primary" onClick={() => setParams({ novo: "1" })}><Icon name="plus" size={15} />Novo projeto</button>
      </div>
      <ErrorBox error={error} />
      {loading && <Spinner />}
      {data && data.length === 0 && (
        <div className="card"><Empty icon="projects" title="Sem projetos">Crie um projeto a partir de um caso de uso para começar com dados de demonstração.</Empty></div>
      )}
      {data && data.length > 0 && (
        <div className="card" style={{ padding: 0 }}>
          <div className="table-wrap" style={{ border: 0, maxHeight: "none" }}>
            <table className="tbl">
              <thead><tr><th>Projeto</th><th>Tipo</th><th>Caso de uso</th><th>Progresso</th><th>Linhas</th><th>Estado</th><th>Atualizado</th></tr></thead>
              <tbody>
                {data.map((p) => (
                  <tr key={p.id} className="clickable" onClick={() => nav(`/projetos/${p.id}`)}>
                    <td><b>{p.name}</b><div className="tiny muted">{p.id}</div></td>
                    <td><Badge>{PROBLEM_LABEL[p.problem_type]}</Badge></td>
                    <td className="small">{p.use_case_name ?? "Personalizado"}</td>
                    <td style={{ minWidth: 140 }}><Progress value={p.progress} /><span className="tiny muted">{Math.round(p.progress * 100)}%</span></td>
                    <td className="num">{formatValue(p.rows, "int")}</td>
                    <td>{p.production_version_id ? <Badge tone="ok">em produção</Badge> : p.champion_version_id ? <Badge tone="blue">modelo treinado</Badge> : <Badge>em curso</Badge>}</td>
                    <td className="small muted">{relativeTime(p.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {open && <NewProject onClose={() => setParams({})} />}
    </div>
  );
}
