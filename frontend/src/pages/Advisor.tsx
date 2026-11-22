import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Icon } from "../components/Icon";
import { ParamEditor } from "../components/ParamEditor";
import { TermChip } from "../components/TermChip";
import { Badge, Callout, Stars } from "../components/ui";
import { useFetch } from "../lib/context";
import { PROBLEM_LABEL } from "../lib/format";
import type { ModelSpec, ProjectSummary, UseCase } from "../types";

const IMB = (r: number) => { const m = Math.min(r, 1 - r); return m < 0.02 ? "extremo" : m < 0.1 ? "forte" : m < 0.3 ? "moderado" : "nenhum"; };

export default function Advisor() {
  const [params, setParams] = useSearchParams();
  const ucs = useFetch<UseCase[]>("/api/knowledge/use-cases");
  const models = useFetch<ModelSpec[]>("/api/knowledge/models");
  const projects = useFetch<ProjectSummary[]>("/api/projects");
  const [ucId, setUcId] = useState(params.get("caso") ?? "churn_clientes");
  const [modelId, setModelId] = useState(params.get("modelo") ?? "lightgbm");
  const [projectId, setProjectId] = useState(params.get("projeto") ?? "");
  const [goal, setGoal] = useState("");
  const [rows, setRows] = useState(20000);
  const [feats, setFeats] = useState(25);
  const [pos, setPos] = useState(0.15);
  const uc = ucs.data?.find((u) => u.id === ucId);
  const project = projects.data?.find((p) => p.id === projectId);
  const task = project?.problem_type ?? uc?.problem_type ?? "binary_classification";
  const candidates = (models.data ?? []).filter((m) => m.tasks.includes(task));
  const spec = models.data?.find((m) => m.id === modelId);

  useEffect(() => {
    if (candidates.length && !candidates.some((m) => m.id === modelId)) setModelId(candidates[0].id);
  }, [candidates, modelId]);
  useEffect(() => { if (project?.use_case_id) setUcId(project.use_case_id); }, [project]);
  useEffect(() => {
    const p = new URLSearchParams();
    if (modelId) p.set("modelo", modelId);
    if (ucId) p.set("caso", ucId);
    if (projectId) p.set("projeto", projectId);
    setParams(p, { replace: true });
  }, [modelId, ucId, projectId, setParams]);

  const profile = useMemo(() => (projectId ? null : {
    n_rows: rows, n_features: feats, task, ...(task === "binary_classification" ? { positive_rate: pos, imbalance: IMB(pos) } : {}),
  }), [projectId, rows, feats, pos, task]);
  const logRows = Math.log10(rows);

  return (
    <div className="stack">
      <div className="page-head">
        <div><h1>Conselheiro de hiperparâmetros</h1>
          <p>Escolha o caso de estudo e o modelo: o conselheiro recomenda cada parâmetro para esse contexto e perfil de dados,
            explica o efeito de o subir ou descer, valida as suas alterações em tempo real e estima o risco de
            <TermChip id="overfitting" /> / <TermChip id="underfitting" />. Com um projeto, pode ainda comparar configurações nos dados reais.</p></div>
      </div>
      <div className="card">
        <div className="grid cols-4">
          <label className="field">Projeto (usa o perfil real dos dados)
            <select className="select" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
              <option value="">— nenhum (perfil manual) —</option>{(projects.data ?? []).filter((p) => p.rows).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
          <label className="field">Caso de estudo
            <select className="select" value={ucId} onChange={(e) => setUcId(e.target.value)} disabled={!!project?.use_case_id}>
              {(ucs.data ?? []).map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}</select></label>
          <label className="field">Modelo ({PROBLEM_LABEL[task]})
            <select className="select" value={modelId} onChange={(e) => setModelId(e.target.value)}>
              {candidates.map((m) => <option key={m.id} value={m.id} disabled={m.available === false}>{m.name}{m.available === false ? " (indisponível)" : ""}</option>)}</select></label>
          <label className="field">Objetivo
            <select className="select" value={goal} onChange={(e) => setGoal(e.target.value)}>
              <option value="">do caso de uso{uc?.profile?.goal ? ` (${uc.profile.goal})` : ""}</option>
              {["equilibrado", "performance", "interpretabilidade", "rapidez"].map((g) => <option key={g}>{g}</option>)}</select></label>
        </div>
        {!projectId && (
          <div className="grid cols-3" style={{ marginTop: 12 }}>
            <label className="field">Nº de linhas: <b>{rows.toLocaleString("pt-PT")}</b>
              <input type="range" min={2.5} max={7} step={0.05} value={logRows} onChange={(e) => setRows(Math.round(10 ** Number(e.target.value)))} /></label>
            <label className="field">Nº de variáveis: <b>{feats}</b>
              <input type="range" min={2} max={300} value={feats} onChange={(e) => setFeats(Number(e.target.value))} /></label>
            {task === "binary_classification" && (
              <label className="field">Taxa de positivos: <b>{(pos * 100).toFixed(1)}%</b> <Badge tone={IMB(pos) === "nenhum" ? "ok" : IMB(pos) === "moderado" ? "warn" : "crit"}>desequilíbrio {IMB(pos)}</Badge>
                <input type="range" min={-3} max={-0.31} step={0.01} value={Math.log10(pos)} onChange={(e) => setPos(Number((10 ** Number(e.target.value)).toFixed(4)))} /></label>
            )}
          </div>
        )}
      </div>
      {spec && (
        <div className="card">
          <div className="row between">
            <div><h3 style={{ margin: 0 }}>{spec.name}</h3><div className="small muted">{spec.description}</div></div>
            <div className="row"><span className="small">Interpretabilidade <Stars n={spec.interpretability} /></span><span className="small">Rapidez <Stars n={spec.speed} /></span></div>
          </div>
          <div className="grid cols-3" style={{ marginTop: 10 }}>
            <div className="small"><b>Como funciona:</b> {spec.how_it_works}</div>
            <div className="small"><b>Pontos fortes:</b> {spec.strengths.join("; ")}</div>
            <div className="small"><b>Limitações:</b> {spec.weaknesses.join("; ")}</div>
          </div>
          <div className="row" style={{ marginTop: 8 }}>
            {spec.needs_scaling && <Badge tone="info"><Icon name="ruler" size={12} />precisa de normalização (automática)</Badge>}
            {spec.handles_missing && <Badge tone="ok">trata valores em falta</Badge>}
            <Badge>{spec.library}</Badge>
          </div>
        </div>
      )}
      {uc && uc.recommended_models.length > 0 && !uc.recommended_models.some((r) => r.model === modelId) && (
        <Callout level="info" title="Modelos recomendados para este caso">{uc.recommended_models.map((r) => r.model.replace(/_/g, " ")).join(", ")}</Callout>
      )}
      {modelId && (spec?.tasks.includes(task)) && (
        <ParamEditor key={`${modelId}-${projectId}-${ucId}`} modelId={modelId} useCaseId={ucId} projectId={projectId || null} profile={profile} goal={goal || undefined} />
      )}
    </div>
  );
}
