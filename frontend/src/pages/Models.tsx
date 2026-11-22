import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, waitJob } from "../api";
import { AgentResultView, TableBlock } from "../components/Blocks";
import { Icon } from "../components/Icon";
import { TermChip } from "../components/TermChip";
import { Badge, Empty, ErrorBox, Modal, Progress, Spinner } from "../components/ui";
import { useFetch } from "../lib/context";
import { formatDate, formatValue, metricName, PCT_METRICS, PROBLEM_LABEL } from "../lib/format";
import type { AgentResult, Dict, Job } from "../types";
import { ModelDetail } from "./ProjectWorkspace";

function PredictModal({ meta, onClose }: { meta: Dict; onClose: () => void }) {
  const [text, setText] = useState("[\n  {}\n]");
  const [out, setOut] = useState<any>(null);
  const [err, setErr] = useState<unknown>(null);
  useEffect(() => {
    api.get<Dict>(`/api/models/${meta.id}`).then((m) => {
      setText(JSON.stringify([Object.fromEntries((m.features ?? []).slice(0, 8).map((f: string) => [f, null]))], null, 2));
    }).catch(setErr);
  }, [meta.id]);
  async function run() {
    setErr(null);
    try { setOut(await api.post(`/api/models/${meta.id}/predict`, { rows: JSON.parse(text) })); } catch (e) { setErr(e); }
  }
  return (
    <Modal title="Testar previsão (API REST)" subtitle={`POST /api/models/${meta.id}/predict`} onClose={onClose}
      footer={<button className="btn primary" onClick={run}><Icon name="play" size={14} />Prever</button>}>
      <div className="stack">
        <p className="small muted">Indique os valores das colunas originais. Colunas omitidas são tratadas como valores em falta (imputados como no treino). <TermChip id="scoring_online" /></p>
        <textarea className="textarea" style={{ minHeight: 200 }} value={text} onChange={(e) => setText(e.target.value)} />
        <ErrorBox error={err} />
        {out && <TableBlock block={{ type: "table", columns: Object.keys(out.predictions[0] ?? {}).map((k) => ({ key: k, label: k })), rows: out.predictions }} />}
      </div>
    </Modal>
  );
}

export default function Models() {
  const nav = useNavigate();
  const { data, error, reload } = useFetch<Dict[]>("/api/models");
  const [detail, setDetail] = useState<Dict | null>(null);
  const [predict, setPredict] = useState<Dict | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [mon, setMon] = useState<AgentResult | null>(null);
  const [err, setErr] = useState<unknown>(null);
  async function monitor(m: Dict, simulate: boolean) {
    setErr(null);
    try {
      const r = await api.post<{ job: Job }>(`/api/projects/${m.project_id}/agents/monitoring/run`, { params: { version_id: m.id, simulate_drift: simulate } });
      setJob(r.job);
      const done = await waitJob(r.job.id, setJob);
      setMon(done.result);
      reload();
    } catch (e) { setErr(e); } finally { setJob(null); }
  }
  async function promote(m: Dict) { await api.post(`/api/models/${m.id}/promote`); reload(); }
  const prod = (data ?? []).filter((m) => m.stage === "produção");
  const others = (data ?? []).filter((m) => m.stage !== "produção");
  const metricCell = (m: Dict) => m.primary_metric && m.metrics_test?.[m.primary_metric] !== undefined
    ? `${metricName(m.primary_metric)} ${formatValue(m.metrics_test[m.primary_metric], PCT_METRICS.has(m.primary_metric) ? "pct" : "num")}` : "—";
  return (
    <div className="stack">
      <div className="page-head">
        <div><h1>Modelos & monitorização</h1>
          <p>Registo de todas as versões treinadas, com estado (<TermChip id="champion_challenger" />), métricas, scoring e saúde em
            produção (<TermChip id="drift_dados" />, <TermChip id="psi" />).</p></div>
      </div>
      <ErrorBox error={error || err} />
      {job && <div className="card"><div className="row"><Spinner /> {job.message}</div><div style={{ marginTop: 8 }}><Progress value={job.progress} /></div></div>}
      <section className="card">
        <h3 className="row"><Icon name="rocket" size={17} />Em produção</h3>
        {!prod.length ? <Empty icon="rocket" title="Nenhum modelo em produção">Promova um modelo no passo de Implementação de um projeto.</Empty> : (
          <div className="grid auto">
            {prod.map((m) => {
              const last = m.monitoring?.[0];
              return (
                <div key={m.id} className="card flat stack tight">
                  <div className="row between"><b>{m.project_name}</b><Badge tone="ok">produção</Badge></div>
                  <div className="small">{m.model_name} · v{m.version} · {PROBLEM_LABEL[m.problem_type]}</div>
                  <div className="small">{metricCell(m)}</div>
                  {m.last_scoring && <div className="tiny muted">Último scoring: {formatDate(m.last_scoring.at)} · {m.last_scoring.rows} registos → {m.last_scoring.table}</div>}
                  <div className="row">Saúde: {last ? <Badge tone={last.estado === "estável" ? "ok" : last.estado === "atenção" ? "warn" : "crit"}>{last.estado}</Badge> : <Badge>por avaliar</Badge>}
                    {last && <span className="tiny muted">PSI máx. {formatValue(last.max_psi, "num")} · {formatDate(last.data)}</span>}</div>
                  <div className="row">
                    <button className="btn sm primary" onClick={() => monitor(m, false)} disabled={!!job}><Icon name="activity" size={13} />Monitorizar</button>
                    <button className="btn sm" onClick={() => monitor(m, true)} disabled={!!job} title="Para formação: desloca distribuições">Simular drift</button>
                    {m.kind === "supervised" && <button className="btn sm ghost" onClick={() => setPredict(m)}>Testar API</button>}
                    <button className="btn sm ghost" onClick={() => nav(`/projetos/${m.project_id}`)}>Projeto</button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>
      <section className="card" style={{ padding: 0 }}>
        <div style={{ padding: "14px 18px 0" }}><h3>Todas as versões</h3></div>
        {!others.length && !prod.length ? <Empty icon="cpu" title="Ainda não há modelos treinados" /> : (
          <div className="table-wrap" style={{ border: 0, maxHeight: "none" }}>
            <table className="tbl">
              <thead><tr><th>Projeto</th><th>Modelo</th><th>Tipo</th><th>Estado</th><th>Métrica (teste)</th><th>Criado</th><th></th></tr></thead>
              <tbody>
                {(data ?? []).map((m) => (
                  <tr key={m.id}>
                    <td><a onClick={() => nav(`/projetos/${m.project_id}`)} style={{ cursor: "pointer" }}>{m.project_name}</a></td>
                    <td>{m.model_name} <span className="tiny muted">v{m.version}</span> {m.is_champion && <Badge tone="purple">campeão</Badge>}</td>
                    <td><Badge>{PROBLEM_LABEL[m.problem_type]}</Badge></td>
                    <td><Badge tone={m.stage === "produção" ? "ok" : m.stage === "arquivado" ? undefined : "blue"}>{m.stage}</Badge></td>
                    <td className="num">{metricCell(m)}</td>
                    <td className="small muted">{formatDate(m.created_at)}</td>
                    <td><div className="row" style={{ justifyContent: "flex-end" }}>
                      {m.stage !== "produção" && <button className="btn sm" onClick={() => promote(m)}>Promover</button>}
                      <button className="btn sm ghost" onClick={() => api.get<Dict>(`/api/models/${m.id}`).then(setDetail)}>Detalhe</button>
                    </div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {detail && <ModelDetail meta={detail} onClose={() => setDetail(null)} />}
      {predict && <PredictModal meta={predict} onClose={() => setPredict(null)} />}
      {mon && <Modal title="Relatório de monitorização" onClose={() => setMon(null)}><AgentResultView result={mon} /></Modal>}
    </div>
  );
}
