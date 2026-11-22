import { useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { Icon } from "../components/Icon";
import { TermList } from "../components/TermChip";
import { Badge, Callout, CodeBlock, ErrorBox, Modal, Spinner, Stars } from "../components/ui";
import { useFetch } from "../lib/context";
import { formatValue, metricName, PROBLEM_LABEL } from "../lib/format";
import type { Area, ProblemType, ProjectView, UseCase } from "../types";

const RISK_TONE: Record<string, "crit" | "warn" | "ok"> = { alto: "crit", limitado: "warn", mínimo: "ok" };

function UseCaseDetail({ id, onClose, areas }: { id: string; onClose: () => void; areas: Record<string, Area> }) {
  const { data: uc, error } = useFetch<UseCase>(`/api/knowledge/use-cases/${id}`);
  const nav = useNavigate();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  async function create() {
    setBusy(true);
    try {
      const v = await api.post<ProjectView>("/api/projects", { use_case_id: id });
      nav(`/projetos/${v.project.id}`);
    } catch (e) { setErr(e); } finally { setBusy(false); }
  }
  return (
    <Modal title={uc?.name ?? "…"} subtitle={uc ? `${areas[uc.area]?.name ?? uc.area} · ${PROBLEM_LABEL[uc.problem_type]} · maturidade ${uc.maturity}` : undefined}
      onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Fechar</button>
        <button className="btn primary" disabled={busy || !uc} onClick={create}>{busy ? <Spinner /> : <Icon name="plus" size={15} />}Criar projeto com este caso</button></>}>
      <ErrorBox error={error || err} />
      {!uc ? <Spinner /> : (
        <div className="stack">
          <Callout level="info" title={uc.business_question}>{uc.decision}</Callout>
          <div className="grid cols-2">
            <div className="card flat">
              <h4>Alvo e horizonte</h4>
              <p className="small"><b>{uc.target.column ?? "Sem alvo (não supervisionado)"}</b> — {uc.target.definition}</p>
              <p className="small muted">Unidade: {uc.unit}{uc.horizon && uc.horizon !== "n/a" ? ` · Horizonte: ${uc.horizon}` : ""}</p>
              <h4 style={{ marginTop: 10 }}>Métricas</h4>
              <div className="row"><Badge tone="blue">{metricName(uc.metrics.primary)} (principal)</Badge>{uc.metrics.secondary.map((m) => <Badge key={m}>{metricName(m)}</Badge>)}</div>
              <p className="small" style={{ marginTop: 6 }}><b>Métrica de negócio:</b> {uc.metrics.business}</p>
            </div>
            <div className="card flat">
              <h4>Features típicas</h4>
              <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>{uc.typical_features.map((f) => <li key={f}>{f}</li>)}</ul>
              <h4 style={{ marginTop: 10 }}>Requisitos de dados</h4>
              <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>{uc.data_requirements.map((f) => <li key={f}>{f}</li>)}</ul>
            </div>
          </div>
          <div className="card flat">
            <h4>Modelos recomendados para este caso</h4>
            <div className="grid cols-3">
              {(uc.models ?? []).map((m, i) => (
                <div key={m.id} className="card flat" style={{ padding: 10 }}>
                  <div className="row between"><b className="small">{i + 1}. {m.name}</b><Stars n={m.interpretability} /></div>
                  <div className="tiny muted" style={{ marginTop: 4 }}>{m.why}</div>
                </div>
              ))}
            </div>
          </div>
          <div className="grid cols-2">
            {uc.business_costs && (
              <div className="card flat">
                <h4>Matriz de custo-benefício (pré-definida)</h4>
                <div className="kpis">
                  <div className="kpi"><div className="kpi-label">Custo FP</div><div className="kpi-value">{formatValue(uc.business_costs.cost_fp, "money")}</div></div>
                  <div className="kpi"><div className="kpi-label">Benefício VP</div><div className="kpi-value">{formatValue(uc.business_costs.benefit_tp, "money")}</div></div>
                  <div className="kpi"><div className="kpi-label">Custo FN</div><div className="kpi-value">{formatValue(uc.business_costs.cost_fn, "money")}</div></div>
                </div>
                {uc.business_costs.note && <p className="tiny muted" style={{ marginTop: 6 }}>{uc.business_costs.note}</p>}
              </div>
            )}
            <div className="card flat">
              <h4>Armadilhas a evitar</h4>
              <div className="stack tight">{uc.pitfalls.map((p) => <Callout key={p} level="warning">{p}</Callout>)}</div>
            </div>
          </div>
          {uc.powerbi_output && (
            <div className="card flat">
              <h4>Saída para o Power BI — tabela <code>{uc.powerbi_output.table}</code></h4>
              <div className="row" style={{ marginBottom: 8 }}>{uc.powerbi_output.columns.map((c) => <Badge key={c}>{c}</Badge>)}</div>
              <div className="grid cols-2">
                <div><b className="small">Visuais recomendados</b><ul className="small" style={{ paddingLeft: 18 }}>{uc.powerbi_output.visuals.map((v) => <li key={v}>{v}</li>)}</ul></div>
                <CodeBlock language="dax" code={uc.powerbi_output.measures.map((m) => m.dax).join("\n\n")} />
              </div>
            </div>
          )}
          <div className="row">
            <Badge tone={RISK_TONE[uc.ai_act_risk] ?? "ok"}><Icon name="scale" size={12} />AI Act: risco {uc.ai_act_risk}</Badge>
            {uc.sensitive_attributes.length > 0 && <Badge tone="warn">Atributos sensíveis: {uc.sensitive_attributes.join(", ")}</Badge>}
            {uc.demo?.table && <Badge tone="blue"><Icon name="database" size={12} />Dados de demo: {uc.demo.table}</Badge>}
          </div>
          <div><b className="small">Conceitos-chave: </b><TermList ids={uc.terms} /></div>
        </div>
      )}
    </Modal>
  );
}

export default function UseCases() {
  const [params, setParams] = useSearchParams();
  const area = params.get("area") ?? "";
  const pt = params.get("tipo") ?? "";
  const selected = params.get("caso");
  const [q, setQ] = useState("");
  const areas = useFetch<Area[]>("/api/knowledge/areas");
  const pts = useFetch<ProblemType[]>("/api/knowledge/problem-types");
  const ucs = useFetch<UseCase[]>(`/api/knowledge/use-cases?${new URLSearchParams({ ...(area && { area }), ...(pt && { problem_type: pt }) })}`);
  const areaMap = useMemo(() => Object.fromEntries((areas.data ?? []).map((a) => [a.id, a])), [areas.data]);
  const list = (ucs.data ?? []).filter((u) => !q || `${u.name} ${u.summary} ${u.business_question}`.toLowerCase().includes(q.toLowerCase()));
  const set = (k: string, v: string | null) => { const p = new URLSearchParams(params); if (v) p.set(k, v); else p.delete(k); setParams(p); };
  return (
    <div className="stack">
      <div className="page-head">
        <div><h1>Casos de uso de negócio</h1>
          <p>Cada caso especializa os agentes: pergunta de negócio, alvo, features, modelos recomendados, métricas, custos de erro,
            armadilhas e a tabela a publicar no Power BI. Escolha um e crie um projeto — os dados de demonstração estão prontos.</p></div>
      </div>
      <div className="card" style={{ padding: 12 }}>
        <div className="row">
          <button className={`chip ${!area ? "active" : ""}`} onClick={() => set("area", null)}>Todas as áreas</button>
          {(areas.data ?? []).map((a) => (
            <button key={a.id} className={`chip ${area === a.id ? "active" : ""}`} onClick={() => set("area", a.id)}>
              <Icon name={a.icon} size={13} />{a.name} <span className="tiny">({a.use_cases})</span>
            </button>
          ))}
        </div>
        <div className="row" style={{ marginTop: 10 }}>
          <select className="select" style={{ maxWidth: 260 }} value={pt} onChange={(e) => set("tipo", e.target.value || null)}>
            <option value="">Todos os tipos de problema</option>
            {(pts.data ?? []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <input className="input" style={{ maxWidth: 320 }} placeholder="Pesquisar casos…" value={q} onChange={(e) => setQ(e.target.value)} />
          <span className="muted small">{list.length} caso(s)</span>
        </div>
      </div>
      <ErrorBox error={ucs.error} />
      <div className="grid auto">
        {list.map((u) => {
          const a = areaMap[u.area];
          return (
            <div key={u.id} className="card uc-card" onClick={() => set("caso", u.id)}>
              <div className="row between">
                <Badge tone="blue"><Icon name={a?.icon ?? "briefcase"} size={12} />{a?.name ?? u.area}</Badge>
                <Badge>{PROBLEM_LABEL[u.problem_type]}</Badge>
              </div>
              <h3 style={{ margin: 0 }}>{u.name}</h3>
              <div className="small muted">{u.summary}</div>
              <div className="small"><b>Pergunta:</b> {u.business_question}</div>
              <div className="row" style={{ marginTop: "auto" }}>
                {u.recommended_models.slice(0, 3).map((m) => <Badge key={m.model}>{m.model.replace(/_/g, " ")}</Badge>)}
                <span className="spacer" />
                <Badge tone={RISK_TONE[u.ai_act_risk]}>{u.maturity}</Badge>
              </div>
            </div>
          );
        })}
      </div>
      {selected && <UseCaseDetail id={selected} areas={areaMap} onClose={() => set("caso", null)} />}
    </div>
  );
}
