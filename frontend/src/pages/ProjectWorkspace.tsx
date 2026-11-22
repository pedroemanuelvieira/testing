import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, waitJob } from "../api";
import { AgentResultView, TableBlock } from "../components/Blocks";
import { Icon } from "../components/Icon";
import { ParamEditor } from "../components/ParamEditor";
import { TermList } from "../components/TermChip";
import { Badge, Callout, ErrorBox, Markdown, Modal, Progress, Spinner, Tabs } from "../components/ui";
import { useApp, useFetch } from "../lib/context";
import { formatDate, formatValue, metricName, PCT_METRICS, PROBLEM_LABEL, STATUS_LABEL } from "../lib/format";
import type { AgentCard, AgentResult, Dict, Job, ModelSpec, Project, ProjectView, UseCase, WorkflowStep } from "../types";

const STATUS_ICON: Record<string, string> = { done: "check", warning: "alert", error: "x-circle" };

function ColumnPicker({ columns, value, onChange, single }: { columns: string[]; value: string[]; onChange: (v: string[]) => void; single?: boolean }) {
  return (
    <div className="row" style={{ gap: 5 }}>
      {columns.map((c) => {
        const on = value.includes(c);
        return <button key={c} className={`chip ${on ? "active" : ""}`} style={{ padding: "2px 9px", fontSize: ".78rem" }}
          onClick={() => onChange(single ? (on ? [] : [c]) : on ? value.filter((x) => x !== c) : [...value, c])}>{c}</button>;
      })}
    </div>
  );
}

function useJobRunner(projectId: string, onFinished: () => void) {
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<unknown>(null);
  const run = useCallback(async (path: string, body: Dict) => {
    setError(null);
    try {
      const r = await api.post<{ job: Job }>(path, body);
      setJob(r.job);
      await waitJob(r.job.id, setJob);
    } catch (e) { setError(e); } finally { setJob(null); onFinished(); }
  }, [onFinished]);
  return { job, error, run, busy: !!job, projectId };
}

function JobBanner({ job }: { job: Job }) {
  return (
    <div className="card" style={{ borderColor: "var(--primary-2)" }}>
      <div className="row between"><div className="row"><Spinner /> <b>{job.message || "A executar…"}</b></div><span className="small muted">{Math.round(job.progress * 100)}%</span></div>
      <div style={{ marginTop: 8 }}><Progress value={job.progress} /></div>
      {job.log.length > 1 && <div className="tiny muted" style={{ marginTop: 6, maxHeight: 70, overflow: "auto" }}>{job.log.slice(-4).map((l, i) => <div key={i}>{l.msg}</div>)}</div>}
    </div>
  );
}

// ------------------------------------------------------------------ configuração por passo
function StepConfig({ step, view, onSaved }: { step: string; view: ProjectView; onSaved: () => void }) {
  const p = view.project;
  const cols: string[] = p.data_info?.column_names ?? [];
  const [draft, setDraft] = useState<Partial<Project>>({});
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const models = useFetch<ModelSpec[]>(`/api/knowledge/models?task=${p.problem_type}`);
  const ucs = useFetch<UseCase[]>(step === "enquadramento" ? "/api/knowledge/use-cases" : null);
  useEffect(() => setDraft({}), [step, p.updated_at]);
  const v = <K extends keyof Project>(k: K): Project[K] => (k in draft ? (draft as any)[k] : p[k]);
  const set = (k: keyof Project, val: any) => setDraft((d) => ({ ...d, [k]: val }));
  async function save() {
    setSaving(true); setErr(null);
    try { await api.patch(`/api/projects/${p.id}`, draft); setDraft({}); onSaved(); } catch (e) { setErr(e); } finally { setSaving(false); }
  }
  const dirty = Object.keys(draft).length > 0;
  const saveBar = dirty && (
    <div className="row"><button className="btn primary sm" onClick={save} disabled={saving}>{saving ? <Spinner size={13} /> : <Icon name="check" size={13} />}Guardar configuração</button>
      <button className="btn sm ghost" onClick={() => setDraft({})}>Descartar</button></div>
  );
  let body: React.ReactNode = null;
  if (step === "enquadramento") {
    const costs = v("business_costs") || {};
    const pt = p.problem_type;
    body = (
      <div className="stack">
        <div className="grid cols-2">
          <label className="field">Caso de uso
            <select className="select" value={v("use_case_id") ?? ""} onChange={(e) => set("use_case_id", e.target.value || null)}>
              <option value="">— personalizado —</option>{(ucs.data ?? []).map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
            </select></label>
          <label className="field">Objetivo do conselheiro
            <select className="select" value={v("goal")} onChange={(e) => set("goal", e.target.value)}>
              {["equilibrado", "performance", "interpretabilidade", "rapidez"].map((g) => <option key={g}>{g}</option>)}</select></label>
        </div>
        {cols.length > 0 && ["binary_classification", "multiclass_classification", "regression"].includes(pt) && (
          <div className="grid cols-2">
            <label className="field">Alvo (target)
              <select className="select" value={v("target") ?? ""} onChange={(e) => set("target", e.target.value || null)}>
                <option value="">—</option>{cols.map((c) => <option key={c}>{c}</option>)}</select></label>
            {pt === "binary_classification" && <label className="field">Classe positiva<input className="input" value={v("positive_class") ?? ""} onChange={(e) => set("positive_class", e.target.value === "" ? null : isNaN(Number(e.target.value)) ? e.target.value : Number(e.target.value))} placeholder="ex.: 1" /></label>}
            <label className="field">Coluna temporal (divisão temporal, opcional)
              <select className="select" value={v("time_column") ?? ""} onChange={(e) => set("time_column", e.target.value || null)}>
                <option value="">—</option>{cols.map((c) => <option key={c}>{c}</option>)}</select></label>
          </div>
        )}
        {cols.length > 0 && pt === "forecasting" && (
          <div className="grid cols-3">
            <label className="field">Coluna temporal<select className="select" value={v("time_column") ?? ""} onChange={(e) => set("time_column", e.target.value)}>{cols.map((c) => <option key={c}>{c}</option>)}</select></label>
            <label className="field">Valor a prever<select className="select" value={v("value_column") ?? ""} onChange={(e) => set("value_column", e.target.value)}>{cols.map((c) => <option key={c}>{c}</option>)}</select></label>
            <label className="field">Agregação<select className="select" value={v("aggregation")} onChange={(e) => set("aggregation", e.target.value)}>{["sum", "mean", "count"].map((c) => <option key={c}>{c}</option>)}</select></label>
            <label className="field">Frequência<select className="select" value={v("freq") ?? ""} onChange={(e) => set("freq", e.target.value || null)}><option value="">automática</option><option value="D">diária</option><option value="W">semanal</option><option value="M">mensal</option></select></label>
            <label className="field">Horizonte (períodos)<input className="input" type="number" value={v("horizon") ?? ""} onChange={(e) => set("horizon", Number(e.target.value) || null)} /></label>
          </div>
        )}
        {cols.length > 0 && pt === "forecasting" && <label className="field">Séries (uma previsão por valor destas colunas)<ColumnPicker columns={cols} value={v("series_columns")} onChange={(x) => set("series_columns", x)} /></label>}
        {cols.length > 0 && pt === "association_rules" && (
          <div className="grid cols-2">
            <label className="field">Coluna da transação<select className="select" value={v("transaction_column") ?? ""} onChange={(e) => set("transaction_column", e.target.value)}>{cols.map((c) => <option key={c}>{c}</option>)}</select></label>
            <label className="field">Coluna do item<select className="select" value={v("item_column") ?? ""} onChange={(e) => set("item_column", e.target.value)}>{cols.map((c) => <option key={c}>{c}</option>)}</select></label>
          </div>
        )}
        {cols.length > 0 && ["clustering", "anomaly_detection"].includes(pt) && (
          <label className="field">Variáveis a usar (vazio = automático)<ColumnPicker columns={cols} value={v("features")} onChange={(x) => set("features", x)} /></label>
        )}
        {cols.length > 0 && pt === "anomaly_detection" && (
          <label className="field">Coluna com rótulos de validação (opcional)<select className="select" value={v("label_column") ?? ""} onChange={(e) => set("label_column", e.target.value || null)}><option value="">—</option>{cols.map((c) => <option key={c}>{c}</option>)}</select></label>
        )}
        {cols.length > 0 && <label className="field">Identificadores (ligam as previsões ao Power BI)<ColumnPicker columns={cols} value={v("id_columns")} onChange={(x) => set("id_columns", x)} /></label>}
        {pt === "binary_classification" && (
          <div className="stack tight">
            <b className="small">Matriz de custo-benefício (face a não agir) <TermList ids={["matriz_custo_beneficio"]} /></b>
            <div className="grid cols-3">
              {[["cost_fp", "Custo de um falso positivo (€)"], ["benefit_tp", "Benefício de um verdadeiro positivo (€)"], ["cost_fn", "Valor perdido por falso negativo (€)"]].map(([k, l]) => (
                <label key={k} className="field">{l}<input className="input" type="number" value={costs[k] ?? ""} onChange={(e) => set("business_costs", { ...costs, [k]: Number(e.target.value) })} /></label>
              ))}
            </div>
          </div>
        )}
        {!cols.length && <Callout level="info">Carregue os dados (passo 2) para escolher colunas.</Callout>}
        {saveBar}
      </div>
    );
  } else if (step === "dados") {
    const src = p.source;
    body = (
      <div className="stack">
        {src ? (
          <div className="kpis">
            <div className="kpi"><div className="kpi-label">Conector</div><div className="kpi-value text">{src.connector_id}</div></div>
            <div className="kpi"><div className="kpi-label">Workspace</div><div className="kpi-value text">{src.workspace_id ?? "—"}</div></div>
            <div className="kpi"><div className="kpi-label">Modelo semântico</div><div className="kpi-value text">{src.dataset_id ?? "—"}</div></div>
            <div className="kpi"><div className="kpi-label">Tabela</div><div className="kpi-value text">{src.table ?? "consulta DAX"}</div></div>
          </div>
        ) : <Callout level="warning" title="Sem fonte de dados">Escolha uma tabela na página <a href="/dados">Dados (Power BI)</a> e crie o projeto a partir dela, ou execute o agente para obter sugestões.</Callout>}
        {src && (
          <div className="grid cols-2">
            <label className="field">Máx. de linhas (vazio = todas)<input className="input" type="number" value={(v("source") as any)?.top ?? ""} onChange={(e) => set("source", { ...src, ...(v("source") as any), top: Number(e.target.value) || null })} /></label>
            <label className="field">Consulta DAX personalizada (opcional)<textarea className="textarea" value={(v("source") as any)?.query ?? ""} placeholder="EVALUATE ..." onChange={(e) => set("source", { ...src, ...(v("source") as any), query: e.target.value || null })} /></label>
          </div>
        )}
        {saveBar}
      </div>
    );
  } else if (step === "qualidade" || step === "features") {
    body = cols.length ? (
      <div className="stack">
        <label className="field">Colunas excluídas do treino (clique para incluir/excluir) <ColumnPicker columns={cols.filter((c) => c !== p.target)} value={v("excluded_columns")} onChange={(x) => set("excluded_columns", x)} /></label>
        {saveBar}
      </div>
    ) : null;
  } else if (step === "modelos") {
    body = (
      <div className="stack">
        <div className="grid auto-sm">
          {(models.data ?? []).map((m) => {
            const on = v("selected_models").includes(m.id);
            return (
              <label key={m.id} className="card flat" style={{ padding: 10, cursor: m.available === false ? "not-allowed" : "pointer", opacity: m.available === false ? 0.5 : 1, borderColor: on ? "var(--primary-2)" : undefined }}>
                <div className="row"><input type="checkbox" checked={on} disabled={m.available === false}
                  onChange={() => set("selected_models", on ? v("selected_models").filter((x) => x !== m.id) : [...v("selected_models"), m.id])} /><b className="small">{m.name}</b></div>
                <div className="tiny muted" style={{ marginTop: 4 }}>{m.when_to_use}</div>
              </label>
            );
          })}
        </div>
        {saveBar}
      </div>
    );
  } else if (step === "treino" && ["binary_classification", "multiclass_classification", "regression"].includes(p.problem_type)) {
    const t = v("tuning");
    body = (
      <div className="stack">
        <div className="grid cols-3">
          <label className="checkbox"><input type="checkbox" checked={t.enabled} onChange={(e) => set("tuning", { ...t, enabled: e.target.checked })} />Afinação automática de hiperparâmetros <TermList ids={["tuning"]} /></label>
          <label className="field">Tentativas<input className="input" type="number" min={3} max={100} value={t.n_iter} onChange={(e) => set("tuning", { ...t, n_iter: Number(e.target.value) })} /></label>
          <label className="field">Método<select className="select" value={t.method} onChange={(e) => set("tuning", { ...t, method: e.target.value })}><option value="random">Random search</option><option value="optuna">Otimização bayesiana (Optuna)</option></select></label>
          <label className="field">Folds de validação cruzada<input className="input" type="number" min={3} max={10} value={v("cv_folds")} onChange={(e) => set("cv_folds", Number(e.target.value))} /></label>
        </div>
        {saveBar}
      </div>
    );
  }
  return body ? <div className="card"><h4 className="row"><Icon name="settings" size={15} />Configuração deste passo</h4><ErrorBox error={err} />{body}</div> : null;
}

function RunParams({ step, values, onChange, problemType }: { step: string; values: Dict; onChange: (v: Dict) => void; problemType: string }) {
  if (step === "enquadramento") return <label className="field">Pergunta de negócio (opcional — o agente sugere casos de uso)<input className="input" value={values.question ?? ""} onChange={(e) => onChange({ ...values, question: e.target.value })} placeholder="ex.: que clientes vão deixar de comprar nos próximos meses?" /></label>;
  if (step === "avaliacao" && problemType === "binary_classification") return (
    <div className="grid cols-2">
      <label className="field">Limiar manual (vazio = ótimo por custo-benefício)<input className="input" type="number" step="0.01" min={0.01} max={0.99} value={values.threshold ?? ""} onChange={(e) => onChange({ ...values, threshold: e.target.value === "" ? undefined : Number(e.target.value), capacity: undefined })} /></label>
      <label className="field">Ou capacidade (nº de casos a tratar na população)<input className="input" type="number" value={values.capacity ?? ""} onChange={(e) => onChange({ ...values, capacity: e.target.value === "" ? undefined : Number(e.target.value), threshold: undefined })} /></label>
    </div>
  );
  if (step === "implementacao") return (
    <label className="field">Publicar<select className="select" value={values.publish ?? "both"} onChange={(e) => onChange({ ...values, publish: e.target.value })}>
      <option value="both">Power BI (se o conector permitir) + ficheiros</option><option value="powerbi">Só Power BI</option><option value="export">Só ficheiros (CSV/Excel/Parquet)</option></select></label>
  );
  if (step === "monitorizacao") return <label className="checkbox"><input type="checkbox" checked={!!values.simulate_drift} onChange={(e) => onChange({ ...values, simulate_drift: e.target.checked })} />Simular drift (formação)</label>;
  if (step === "treino" && problemType === "clustering") return <label className="field">Nº de segmentos (vazio = recomendado)<input className="input" type="number" value={values.n_clusters ?? ""} onChange={(e) => onChange({ ...values, n_clusters: e.target.value === "" ? undefined : Number(e.target.value) })} /></label>;
  if (step === "treino" && problemType === "forecasting") return <label className="field">Horizonte (vazio = configuração do projeto)<input className="input" type="number" value={values.horizon ?? ""} onChange={(e) => onChange({ ...values, horizon: e.target.value === "" ? undefined : Number(e.target.value) })} /></label>;
  return null;
}

// ------------------------------------------------------------------ página
export default function ProjectWorkspace() {
  const { id = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const nav = useNavigate();
  const { setCurrentProject, openChat } = useApp();
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  const view = useFetch<ProjectView>(`/api/projects/${id}`, [tick]);
  const latest = useFetch<Record<string, AgentResult>>(`/api/projects/${id}/latest`, [tick]);
  const workflow = useFetch<WorkflowStep[]>("/api/knowledge/workflow");
  const agents = useFetch<{ agents: AgentCard[] }>("/api/agents");
  const runner = useJobRunner(id, reload);
  const [tab, setTab] = useState<"percurso" | "modelos" | "historico">("percurso");
  const [autoOpen, setAutoOpen] = useState(false);
  const [runParams, setRunParams] = useState<Dict>({});
  const [guideOpen, setGuideOpen] = useState(true);
  const v = view.data;
  const stepId = params.get("passo") ?? v?.steps.find((s) => s.status === "pending")?.id ?? v?.steps[0]?.id ?? "enquadramento";
  const step = v?.steps.find((s) => s.id === stepId);
  const wf = workflow.data?.find((w) => w.id === stepId);
  const card = agents.data?.agents.find((a) => a.id === step?.agent_id);
  const result = step ? latest.data?.[step.agent_id] : undefined;

  useEffect(() => {
    if (v) setCurrentProject({ id: v.project.id, name: v.project.name });
    return () => setCurrentProject(null);
  }, [v, setCurrentProject]);
  useEffect(() => setRunParams({}), [stepId]);

  if (view.error) return <ErrorBox error={view.error} />;
  if (!v) return <Spinner />;
  const p = v.project;
  const champ = v.champion;
  const pm = champ?.primary_metric;
  const goStep = (s: string) => { const q = new URLSearchParams(params); q.set("passo", s); setParams(q); setTab("percurso"); };

  return (
    <div className="stack">
      <div className="page-head">
        <div style={{ minWidth: 0 }}>
          <div className="row"><Badge tone="blue">{PROBLEM_LABEL[p.problem_type]}</Badge>{v.use_case && <Badge>{v.use_case.name}</Badge>}
            {p.production_version_id && <Badge tone="ok"><Icon name="rocket" size={12} />em produção</Badge>}</div>
          <h1 style={{ marginTop: 6 }}>{p.name}</h1>
          <div className="row" style={{ maxWidth: 520 }}><div style={{ flex: 1 }}><Progress value={v.progress} /></div><span className="small muted">{Math.round(v.progress * 100)}% do percurso</span></div>
        </div>
        <div className="row">
          {champ && (
            <div className="kpi" style={{ minWidth: 200 }}>
              <div className="kpi-label">Modelo campeão</div>
              <div style={{ fontWeight: 650 }}>{champ.model_name}</div>
              {pm && champ.metrics_test?.[pm] !== undefined && <div className="small">{metricName(pm)}: <b>{formatValue(champ.metrics_test[pm], PCT_METRICS.has(pm) ? "pct" : "num")}</b></div>}
            </div>
          )}
          <button className="btn accent" onClick={() => setAutoOpen(true)} disabled={runner.busy}><Icon name="wand" size={15} />Piloto automático</button>
          <button className="btn" onClick={() => runner.run(`/api/projects/${id}/agents/reporting/run`, { params: {} }).then(() => goStep(stepId))} disabled={runner.busy}><Icon name="file-text" size={15} />Relatório</button>
          <button className="btn ghost" onClick={() => openChat("Qual é o próximo passo neste projeto e porquê?")}><Icon name="message-circle" size={15} />Ajuda</button>
          <button className="icon-btn danger" title="Apagar projeto" onClick={async () => { if (window.confirm("Apagar este projeto e os seus modelos?")) { await api.del(`/api/projects/${id}`); nav("/projetos"); } }}><Icon name="trash" size={17} /></button>
        </div>
      </div>
      {runner.job && <JobBanner job={runner.job} />}
      <ErrorBox error={runner.error} />
      <Tabs value={tab} onChange={setTab} tabs={[{ id: "percurso", label: "Percurso guiado" }, { id: "modelos", label: "Versões do modelo" }, { id: "historico", label: "Histórico de execuções" }]} />

      {tab === "percurso" && (
        <div className="workspace">
          <nav className="stepper">
            {v.steps.map((s) => (
              <button key={s.id} className={`step ${s.status} ${s.id === stepId ? "active" : ""}`} onClick={() => goStep(s.id)}>
                <span className="step-num">{STATUS_ICON[s.status] ? <Icon name={STATUS_ICON[s.status]} size={14} /> : s.order}</span>
                <span style={{ minWidth: 0 }}><div className="step-title">{s.title}</div><div className="step-agent">{s.agent_name}</div></span>
              </button>
            ))}
            {latest.data?.reporting && (
              <button className={`step ${stepId === "relatorio" ? "active" : ""}`} onClick={() => goStep("relatorio")}>
                <span className="step-num"><Icon name="file-text" size={14} /></span><span><div className="step-title">Relatório executivo</div><div className="step-agent">Agente de Relatórios</div></span>
              </button>
            )}
          </nav>
          <div className="stack" style={{ minWidth: 0 }}>
            {stepId === "relatorio" && latest.data?.reporting ? (
              <div className="card"><AgentResultView result={latest.data.reporting} /></div>
            ) : step && (
              <>
                <div className="card">
                  <div className="card-title">
                    <div><div className="tiny muted">PASSO {step.order} · {STATUS_LABEL[step.status] ?? step.status}</div><h2 style={{ margin: 0 }}>{step.title}</h2></div>
                    <button className="btn ghost sm" onClick={() => setGuideOpen((g) => !g)}><Icon name="book-open" size={14} />{guideOpen ? "Esconder guia" : "Mostrar guia"}</button>
                  </div>
                  {wf && guideOpen && (
                    <div className="grid cols-2">
                      <div className="stack tight">
                        <div><b>Objetivo:</b> {wf.objective}</div>
                        <div className="small muted"><b>Porque importa:</b> {wf.why}</div>
                        <div className="small"><b>Como fazer:</b><ol style={{ margin: "4px 0", paddingLeft: 18 }}>{wf.how.map((h) => <li key={h}>{h}</li>)}</ol></div>
                      </div>
                      <div className="stack tight">
                        <div className="small"><b>Checklist:</b>{wf.checklist.map((c) => <div key={c}>☐ {c}</div>)}</div>
                        <div className="small"><b>Erros comuns:</b>{wf.mistakes.map((m) => <div key={m} style={{ color: "var(--warn)" }}>⚠ {m}</div>)}</div>
                        <div><TermList ids={wf.terms} /></div>
                      </div>
                    </div>
                  )}
                </div>
                <StepConfig step={step.id} view={v} onSaved={reload} />
                {step.id === "parametros" && p.selected_models.length > 0 && <ParamsStep project={p} onApplied={reload} />}
                <div className="card">
                  <div className="card-title">
                    <div className="row"><span style={{ color: "var(--primary-2)" }}><Icon name={card?.icon ?? "bot"} size={20} /></span>
                      <div><h3 style={{ margin: 0 }}>{step.agent_name}</h3><div className="tiny muted">{card?.role}</div></div></div>
                    <button className="btn primary" disabled={runner.busy || (card?.requires_data && !v.has_data && step.agent_id !== "connector")}
                      onClick={() => runner.run(`/api/projects/${id}/agents/${step.agent_id}/run`, { params: runParams })}>
                      {runner.busy ? <Spinner size={14} /> : <Icon name="play" size={15} />}{result ? "Executar novamente" : "Executar agente"}</button>
                  </div>
                  <p className="small muted">{card?.description}</p>
                  <RunParams step={step.id} values={runParams} onChange={setRunParams} problemType={p.problem_type} />
                  {card?.requires_data && !v.has_data && step.agent_id !== "connector" && <Callout level="warning">Carregue primeiro os dados (passo 2).</Callout>}
                </div>
                {result ? <div className="card"><h3>Resultado</h3><AgentResultView result={result} />
                  {result.next_step && result.next_step !== step.id && (
                    <div className="row" style={{ marginTop: 14 }}><button className="btn primary" onClick={() => goStep(result.next_step!)}>Seguir para o próximo passo<Icon name="chevron-right" size={15} /></button></div>
                  )}</div>
                  : <div className="card"><div className="empty" style={{ padding: 24 }}><Icon name="bot" size={28} /><p className="small">Este agente ainda não foi executado neste projeto.</p></div></div>}
              </>
            )}
          </div>
        </div>
      )}
      {tab === "modelos" && <ModelsTab projectId={id} onChange={reload} />}
      {tab === "historico" && <HistoryTab projectId={id} tick={tick} />}
      {autoOpen && <AutopilotModal onClose={() => setAutoOpen(false)} onRun={(opts) => { setAutoOpen(false); runner.run(`/api/projects/${id}/autopilot`, opts); }} />}
    </div>
  );
}

function ParamsStep({ project, onApplied }: { project: Project; onApplied: () => void }) {
  const [model, setModel] = useState(project.selected_models[0]);
  useEffect(() => { if (!project.selected_models.includes(model)) setModel(project.selected_models[0]); }, [project.selected_models, model]);
  return (
    <div className="card">
      <h3 className="row"><Icon name="sliders" size={17} />Conselheiro interativo</h3>
      <p className="small muted">Ajuste os parâmetros de cada modelo: as recomendações são específicas deste caso de uso e do perfil dos seus dados; as validações e o risco de overfitting atualizam-se em tempo real.</p>
      <Tabs value={model} onChange={setModel} tabs={project.selected_models.map((m) => ({ id: m, label: <>{m.replace(/_/g, " ")}{project.params_locked.includes(m) && <Icon name="lock" size={12} />}</> }))} />
      {model && <ParamEditor key={model} modelId={model} projectId={project.id} useCaseId={project.use_case_id} goal={project.goal}
        initial={project.model_params[model]} locked={project.params_locked.includes(model)} onApplied={onApplied} />}
    </div>
  );
}

function AutopilotModal({ onClose, onRun }: { onClose: () => void; onRun: (o: Dict) => void }) {
  const [dep, setDep] = useState(false);
  const [tune, setTune] = useState(false);
  return (
    <Modal size="sm" title="Piloto automático" subtitle="Os agentes executam o percurso em sequência" onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancelar</button><button className="btn accent" onClick={() => onRun({ include_deployment: dep, tune })}><Icon name="wand" size={15} />Executar</button></>}>
      <div className="stack">
        <p className="small">Enquadramento → dados → perfil → qualidade → features → modelos → parâmetros → treino → avaliação → explicabilidade → governança → relatório.</p>
        <label className="checkbox"><input type="checkbox" checked={tune} onChange={(e) => setTune(e.target.checked)} />Afinação automática de hiperparâmetros (mais lento)</label>
        <label className="checkbox"><input type="checkbox" checked={dep} onChange={(e) => setDep(e.target.checked)} />Incluir implementação (promover e publicar previsões)</label>
        <Callout level="info">Pode rever e ajustar cada passo depois; os resultados ficam no histórico.</Callout>
      </div>
    </Modal>
  );
}

function ModelsTab({ projectId, onChange }: { projectId: string; onChange: () => void }) {
  const { data, reload } = useFetch<Dict[]>(`/api/projects/${projectId}/models`);
  const [detail, setDetail] = useState<Dict | null>(null);
  async function act(path: string) { await api.post(path); reload(); onChange(); }
  if (!data) return <Spinner />;
  if (!data.length) return <div className="card"><div className="empty">Ainda não há modelos treinados.</div></div>;
  return (
    <div className="card" style={{ padding: 0 }}>
      <div className="table-wrap" style={{ border: 0, maxHeight: "none" }}>
        <table className="tbl">
          <thead><tr><th>Versão</th><th>Modelo</th><th>Estado</th><th>Métrica</th><th>Criado</th><th></th></tr></thead>
          <tbody>
            {data.map((m) => (
              <tr key={m.id}>
                <td><b>v{m.version}</b>{m.is_champion && <> <Badge tone="purple">campeão</Badge></>}</td>
                <td>{m.model_name}{m.tuned && <> <Badge tone="info">afinado</Badge></>}</td>
                <td><Badge tone={m.stage === "produção" ? "ok" : m.stage === "arquivado" ? undefined : "blue"}>{m.stage}</Badge></td>
                <td className="num">{m.primary_metric && m.metrics_test?.[m.primary_metric] !== undefined ? `${metricName(m.primary_metric)} ${formatValue(m.metrics_test[m.primary_metric], PCT_METRICS.has(m.primary_metric) ? "pct" : "num")}` : "—"}</td>
                <td className="small muted">{formatDate(m.created_at)}</td>
                <td><div className="row" style={{ justifyContent: "flex-end" }}>
                  {!m.is_champion && <button className="btn sm" onClick={() => act(`/api/models/${m.id}/champion`)}>Tornar campeão</button>}
                  {m.stage !== "produção" && <button className="btn sm" onClick={() => act(`/api/models/${m.id}/promote`)}><Icon name="rocket" size={12} />Promover</button>}
                  <button className="btn sm ghost" onClick={() => api.get<Dict>(`/api/models/${m.id}`).then(setDetail)}>Detalhe</button>
                </div></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {detail && <ModelDetail meta={detail} onClose={() => setDetail(null)} />}
    </div>
  );
}

export function ModelDetail({ meta, onClose }: { meta: Dict; onClose: () => void }) {
  const [t, setT] = useState<"resumo" | "card" | "json">("resumo");
  const metrics = Object.entries(meta.metrics_test ?? {}).filter(([, x]) => typeof x === "number");
  return (
    <Modal title={`${meta.model_name} — v${meta.version}`} subtitle={meta.id} onClose={onClose}>
      <Tabs value={t} onChange={setT} tabs={[{ id: "resumo", label: "Resumo" }, { id: "card", label: "Ficha do modelo" }, { id: "json", label: "Metadados" }]} />
      {t === "resumo" && (
        <div className="stack">
          <div className="kpis">{metrics.slice(0, 12).map(([k, x]) => (
            <div key={k} className="kpi"><div className="kpi-label">{metricName(k)}</div><div className="kpi-value">{formatValue(x, PCT_METRICS.has(k) ? "pct" : "num")}</div>
              {meta.baseline_metrics?.[k] !== undefined && <div className="kpi-hint">baseline {formatValue(meta.baseline_metrics[k], PCT_METRICS.has(k) ? "pct" : "num")}</div>}</div>))}</div>
          <TableBlock block={{ type: "table", columns: [{ key: "k", label: "Parâmetro" }, { key: "v", label: "Valor" }], rows: Object.entries(meta.params ?? {}).map(([k, x]) => ({ k, v: String(x) })) }} />
          {meta.last_scoring && <Callout level="info" title="Último scoring">{formatDate(meta.last_scoring.at)} · {meta.last_scoring.rows} registos · tabela {meta.last_scoring.table}</Callout>}
          {(meta.monitoring ?? []).length > 0 && <Callout level="info" title="Última monitorização">{meta.monitoring.at(-1).estado} · PSI máx. {formatValue(meta.monitoring.at(-1).max_psi, "num")}</Callout>}
        </div>
      )}
      {t === "card" && (meta.model_card ? <Markdown text={meta.model_card} /> : <Callout level="info">Execute o Agente de Governança para gerar a ficha do modelo.</Callout>)}
      {t === "json" && <pre className="codeblock">{JSON.stringify(meta, null, 2)}</pre>}
    </Modal>
  );
}

function HistoryTab({ projectId, tick }: { projectId: string; tick: number }) {
  const { data } = useFetch<Dict[]>(`/api/projects/${projectId}/runs`, [tick]);
  const [open, setOpen] = useState<AgentResult | null>(null);
  const rows = useMemo(() => data ?? [], [data]);
  return (
    <div className="card" style={{ padding: 0 }}>
      <div className="table-wrap" style={{ border: 0, maxHeight: "none" }}>
        <table className="tbl">
          <thead><tr><th>Quando</th><th>Agente</th><th>Estado</th><th>Resumo</th><th>Duração</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.run_id} className="clickable" onClick={() => api.get<AgentResult>(`/api/projects/${projectId}/runs/${r.run_id}`).then(setOpen)}>
                <td className="small">{formatDate(r.created_at)}</td><td><b className="small">{r.title}</b></td>
                <td><Badge tone={r.status === "ok" ? "ok" : "warn"}>{r.status}</Badge></td>
                <td className="small" style={{ maxWidth: 520 }}>{r.summary?.replace(/\*\*/g, "")}</td>
                <td className="num small">{(r.duration_ms / 1000).toFixed(1)} s</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {open && <Modal title={open.title} subtitle={formatDate(open.created_at)} onClose={() => setOpen(null)}><AgentResultView result={open} /></Modal>}
    </div>
  );
}
