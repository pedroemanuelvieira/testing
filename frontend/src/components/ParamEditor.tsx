import { useEffect, useMemo, useRef, useState } from "react";
import { api, waitJob } from "../api";
import { formatValue } from "../lib/format";
import type { Assessment, Dict, ParamDetail, Recommendation, Validation } from "../types";
import { Icon } from "./Icon";
import { TermChip } from "./TermChip";
import { Badge, Callout, ErrorBox, Progress, Spinner } from "./ui";

function Gauge({ label, value, level, term }: { label: string; value: number; level: string; term?: string }) {
  const tone = level === "alto" ? "crit" : level === "médio" ? "warn" : "ok";
  return (
    <div className="gauge">
      <div className="row between small"><span style={{ fontWeight: 600 }}>{label} {term && <TermChip id={term} label="?" />}</span><Badge tone={tone}>{level}</Badge></div>
      <div className="gauge-bar"><div className="gauge-marker" style={{ left: `${Math.max(2, Math.min(98, value))}%` }} /></div>
    </div>
  );
}

export function AssessmentPanel({ a }: { a: Assessment }) {
  return (
    <div className="stack tight">
      <Gauge label="Risco de overfitting" value={a.overfit_risk} level={a.overfit_level} term="overfitting" />
      <Gauge label="Risco de underfitting" value={a.underfit_risk} level={a.underfit_level} term="underfitting" />
      <Gauge label="Custo de treino" value={a.training_cost} level={a.training_cost_level} />
      <div className="small"><b>Complexidade:</b> {a.complexity}/100</div>
      <Progress value={a.complexity / 100} />
      <div className="tiny muted">{a.explanation}</div>
    </div>
  );
}

const toPos = (d: ParamDetail, v: number) => {
  const min = d.min ?? 0, max = d.max ?? 1;
  if (d.log && min > 0) return (1000 * (Math.log(Math.max(v, min)) - Math.log(min))) / (Math.log(max) - Math.log(min));
  return (1000 * (v - min)) / (max - min || 1);
};
const fromPos = (d: ParamDetail, p: number) => {
  const min = d.min ?? 0, max = d.max ?? 1;
  let v = d.log && min > 0 ? Math.exp(Math.log(min) + (p / 1000) * (Math.log(max) - Math.log(min))) : min + (p / 1000) * (max - min);
  if (d.type === "int") v = Math.round(v);
  else v = Number(v.toPrecision(3));
  return v;
};

function ParamControl({ d, value, onChange, issues }: { d: ParamDetail; value: any; onChange: (v: any) => void; issues: Validation["issues"] }) {
  const changed = String(value) !== String(d.value);
  const mine = issues.filter((i) => i.param === d.name);
  return (
    <div className={`param ${changed ? "changed" : ""}`}>
      <div className="param-head">
        <div>
          <span className="param-name">{d.label}</span> <span className="param-code">{d.name}</span>{" "}
          {d.term && <TermChip id={d.term} label="?" />}
        </div>
        <div className="row" style={{ gap: 6 }}>
          <Badge tone={d.importance === "alta" ? "crit" : d.importance === "média" ? "warn" : undefined}>{d.importance}</Badge>
          {changed && <button className="btn ghost sm" onClick={() => onChange(d.value)} title="Repor valor recomendado"><Icon name="refresh" size={12} />{String(d.value)}</button>}
        </div>
      </div>
      <div style={{ marginTop: 8 }}>
        {d.type === "choice" ? (
          <select className="select" value={String(value)} onChange={(e) => onChange(e.target.value)}>
            {d.choices.map((c) => <option key={String(c)} value={String(c)}>{String(c)}</option>)}
          </select>
        ) : d.type === "bool" ? (
          <label className="checkbox"><input type="checkbox" checked={value === true || value === "true"} onChange={(e) => onChange(e.target.checked)} />{value === true || value === "true" ? "ativo" : "inativo"}</label>
        ) : (
          <div className="row" style={{ flexWrap: "nowrap" }}>
            {d.min != null && d.max != null && (
              <input type="range" min={0} max={1000} value={toPos(d, Number(value))} onChange={(e) => onChange(fromPos(d, Number(e.target.value)))} />
            )}
            <input className="input" style={{ width: 110 }} type="number" step={d.type === "int" ? 1 : "any"} value={value ?? ""}
              onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))} />
          </div>
        )}
      </div>
      <div className="param-reason"><b>Recomendação:</b> {String(d.value)} — {d.reason}</div>
      {(d.increase && d.increase !== "n/a") && (
        <div className="param-effects"><div>↑ {d.increase}</div><div>↓ {d.decrease}</div></div>
      )}
      {mine.map((i, k) => <div key={k} style={{ marginTop: 6 }}><Callout level={i.level === "error" ? "critical" : i.level === "warning" ? "warning" : "info"}>{i.message}</Callout></div>)}
    </div>
  );
}

export function ParamEditor({ modelId, useCaseId, projectId, profile, goal, initial, locked, onApplied }: {
  modelId: string; useCaseId?: string | null; projectId?: string | null; profile?: Dict | null; goal?: string;
  initial?: Dict | null; locked?: boolean; onApplied?: () => void;
}) {
  const [rec, setRec] = useState<Recommendation | null>(null);
  const [values, setValues] = useState<Dict>({});
  const [val, setVal] = useState<Validation | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const [compare, setCompare] = useState<any>(null);
  const [cmpProgress, setCmpProgress] = useState<number | null>(null);
  const [applied, setApplied] = useState<string | null>(null);
  const [showLow, setShowLow] = useState(false);
  const timer = useRef<number>();

  const body = useMemo(() => ({ model_id: modelId, use_case_id: useCaseId || undefined, project_id: projectId || undefined,
    profile: profile || undefined, goal: goal || undefined }), [modelId, useCaseId, projectId, profile, goal]);

  useEffect(() => {
    setRec(null); setErr(null); setCompare(null); setApplied(null);
    api.post<Recommendation>("/api/advisor/recommend", body).then((r) => {
      setRec(r);
      setValues({ ...r.params, ...(initial ?? {}) });
    }).catch(setErr);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [body]);

  useEffect(() => {
    if (!rec) return;
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      api.post<Validation>("/api/advisor/validate", { ...body, params: values }).then(setVal).catch(setErr);
    }, 250);
    return () => window.clearTimeout(timer.current);
  }, [values, rec, body]);

  async function runCompare() {
    if (!projectId) return;
    setCompare(null); setCmpProgress(0); setErr(null);
    try {
      const r = await api.post<any>("/api/advisor/compare", { ...body, params: values });
      const job = await waitJob(r.job.id, (j) => setCmpProgress(j.progress));
      setCompare(job.result);
    } catch (e) { setErr(e); } finally { setCmpProgress(null); }
  }
  async function apply(lock: boolean) {
    if (!projectId) return;
    try {
      await api.post("/api/advisor/apply", { project_id: projectId, model_id: modelId, params: values, lock });
      setApplied(lock ? "Parâmetros aplicados e bloqueados — o conselheiro não os vai substituir." : "Parâmetros aplicados ao projeto.");
      onApplied?.();
    } catch (e) { setErr(e); }
  }

  if (err && !rec) return <ErrorBox error={err} />;
  if (!rec) return <div className="row"><Spinner /> A calcular recomendação…</div>;
  const issues = val?.issues ?? [];
  const general = issues.filter((i) => !i.param);
  const details = rec.details.filter((d) => showLow || d.importance !== "baixa");
  const changedCount = rec.details.filter((d) => String(values[d.name]) !== String(d.value)).length;
  return (
    <div className="grid" style={{ gridTemplateColumns: "minmax(0, 1fr) 300px", alignItems: "start" }}>
      <div className="stack">
        <ErrorBox error={err} />
        <Callout level="info" title={`${rec.model_name} — objetivo: ${rec.goal}`}>
          {rec.goal_description}
          {rec.notes.map((n, i) => <div key={i}>• {n}</div>)}
        </Callout>
        {locked && <Callout level="warning" title="Parâmetros bloqueados">Este modelo usa parâmetros definidos manualmente no projeto.</Callout>}
        {details.map((d) => (
          <ParamControl key={d.name} d={d} value={values[d.name]} issues={issues} onChange={(v) => setValues((s) => ({ ...s, [d.name]: v }))} />
        ))}
        <button className="btn ghost sm" onClick={() => setShowLow((s) => !s)}>{showLow ? "Esconder" : "Mostrar"} parâmetros de importância baixa</button>
      </div>
      <div className="stack" style={{ position: "sticky", top: 0 }}>
        <div className="card">
          <h4>Avaliação da configuração</h4>
          {val ? <AssessmentPanel a={val.assessment} /> : <Spinner />}
          {general.map((i, k) => <div key={k} style={{ marginTop: 8 }}><Callout level={i.level === "error" ? "critical" : i.level}>{i.message}</Callout></div>)}
          <div className="tiny muted" style={{ marginTop: 8 }}>{changedCount} parâmetro(s) alterado(s) face à recomendação.</div>
          <div className="row" style={{ marginTop: 10 }}>
            <button className="btn sm" onClick={() => setValues({ ...rec.params })}><Icon name="refresh" size={13} />Repor recomendação</button>
          </div>
        </div>
        {projectId && (
          <div className="card">
            <h4>Testar nos dados do projeto</h4>
            <p className="small muted">Validação cruzada rápida (3 folds) da sua configuração vs a recomendada.</p>
            <button className="btn sm primary" onClick={runCompare} disabled={cmpProgress !== null}>
              {cmpProgress !== null ? <Spinner size={13} /> : <Icon name="flask" size={13} />}Comparar com recomendado</button>
            {cmpProgress !== null && <div style={{ marginTop: 8 }}><Progress value={cmpProgress} /></div>}
            {compare && (
              <div className="stack tight" style={{ marginTop: 10 }}>
                {(["recommended", "custom"] as const).map((k) => {
                  const c = compare[k];
                  const gap = c.train - c.cv;
                  return (
                    <div key={k} className="kpi">
                      <div className="kpi-label">{k === "recommended" ? "Recomendada" : "A sua configuração"}</div>
                      <div className="kpi-value">{formatValue(c.cv, "num")}</div>
                      <div className="kpi-hint">{c.metric_name} (CV) ± {formatValue(c.cv_std, "num")} · treino {formatValue(c.train, "num")} · gap {formatValue(gap, "num")} · {c.seconds}s</div>
                    </div>
                  );
                })}
                <div className="small">{compare.custom.cv > compare.recommended.cv
                  ? "✅ A sua configuração é melhor na validação cruzada."
                  : "ℹ️ A recomendação mantém-se melhor ou equivalente."}</div>
              </div>
            )}
            <div className="divider" />
            <div className="row">
              <button className="btn sm" onClick={() => apply(false)}><Icon name="check" size={13} />Aplicar</button>
              <button className="btn sm" onClick={() => apply(true)}><Icon name="lock" size={13} />Aplicar e bloquear</button>
            </div>
            {applied && <div style={{ marginTop: 8 }}><Callout level="success">{applied}</Callout></div>}
          </div>
        )}
      </div>
    </div>
  );
}
