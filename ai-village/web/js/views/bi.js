// Painel BI: indicadores calculados na BD (vistas dim_*/fact_*) + exportação CSV para Power BI/Fabric.
// Barras SVG simples, com valor escrito em cada barra (a cor nunca é a única codificação).
import { h, STATE_PT } from '../ui.js';
import { get } from '../api.js';
import { S, W } from '../state.js';

const COL = { completed: '#34d399', running: '#22d3ee', assigned: '#60a5fa', pending: '#60a5fa', draft: '#7480b3', awaiting_approval: '#a78bfa', blocked: '#fbbf24', failed: '#fb7185', cancelled: '#5a6390' };
const APR_PT = { pending: 'pendente', approved: 'aprovada', consumed: 'consumida', denied: 'negada', revoked: 'revogada', expired: 'expirada' };
const APR_COL = { pending: '#a78bfa', approved: '#60a5fa', consumed: '#34d399', denied: '#fb7185', revoked: '#fbbf24', expired: '#7480b3' };

const num = (n) => (n === null || n === undefined ? '—' : Number(n).toLocaleString('pt-PT'));
const ms = (n) => (n === null || n === undefined ? '—' : n < 1000 ? `${n} ms` : `${(n / 1000).toFixed(1)} s`);
const secs = (n) => (n === null || n === undefined ? '—' : n < 90 ? `${n} s` : n < 5400 ? `${Math.round(n / 60)} min` : `${(n / 3600).toFixed(1)} h`);

function hbars(rows, { max, unit = '' } = {}) {
  const top = max ?? Math.max(1, ...rows.map((r) => r.value));
  return h('div', { class: 'bars', role: 'list' }, rows.map((r) => h('div', { class: 'bar', role: 'listitem', 'aria-label': `${r.label}: ${r.value}${unit}` },
    h('span', { title: r.label, style: { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }, r.label),
    h('span', { class: 'track' }, (r.parts || [{ value: r.value, color: r.color }]).map((p) => h('i', { style: { width: `${(p.value / top) * 100}%`, background: p.color }, title: p.title || '' }))),
    h('b', { style: { textAlign: 'right' } }, `${r.value}${unit}`))));
}

function columns(rows) {
  if (!rows.length) return h('div', { class: 'empty' }, 'Sem tarefas concluídas nos últimos 14 dias.');
  const max = Math.max(1, ...rows.map((r) => r.completed)), W_ = 380, H_ = 150, bw = Math.min(34, (W_ - 40) / rows.length - 8);
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg'); svg.setAttribute('viewBox', `0 0 ${W_} ${H_ + 30}`); svg.setAttribute('role', 'img'); svg.setAttribute('aria-label', `Tarefas concluídas por dia: ${rows.map((r) => `${r.day}: ${r.completed}`).join('; ')}`); svg.style.width = '100%';
  rows.forEach((r, i) => {
    const x = 30 + i * ((W_ - 40) / rows.length), hh = (r.completed / max) * (H_ - 28);
    const rect = document.createElementNS(ns, 'rect'); Object.entries({ x, y: H_ - hh, width: bw, height: hh, rx: 4, fill: '#22d3ee' }).forEach(([k, v]) => rect.setAttribute(k, v)); svg.append(rect);
    const t = document.createElementNS(ns, 'text'); Object.entries({ x: x + bw / 2, y: H_ - hh - 6, 'text-anchor': 'middle', 'font-size': 12, 'font-weight': 700, fill: '#eef1ff' }).forEach(([k, v]) => t.setAttribute(k, v)); t.textContent = r.completed; svg.append(t);
    const d = document.createElementNS(ns, 'text'); Object.entries({ x: x + bw / 2, y: H_ + 16, 'text-anchor': 'middle', 'font-size': 10.5, fill: '#a3add9' }).forEach(([k, v]) => d.setAttribute(k, v)); d.textContent = r.day.slice(5); svg.append(d);
  });
  const base = document.createElementNS(ns, 'line'); Object.entries({ x1: 24, x2: W_, y1: H_, y2: H_, stroke: 'rgba(139,156,255,.4)' }).forEach(([k, v]) => base.setAttribute(k, v)); svg.append(base);
  return svg;
}

const TABLES = [
  ['fact_task', 'Tarefas (1 linha por tarefa): estado, agente, tentativas, tempo de ciclo'], ['fact_attempt', 'Tentativas de execução: duração, erro, executor'],
  ['fact_approval', 'Aprovações: estado, tempo até decisão'], ['fact_message', 'Mensagens (só metadados: modo, autor, nº de caracteres)'],
  ['fact_audit', 'Auditoria minimizada (ação, resultado, motivo)'], ['dim_agent', 'Dimensão agentes (+ funções, unidade, superior)'], ['dim_unit', 'Dimensão unidades'], ['dim_role', 'Dimensão funções/cargos'],
];

export async function biPanel(el) {
  const k = await get(`${W()}/bi/kpis`);
  const st = k.tasks_by_state, total = k.tasks_total;
  const done = st.completed || 0;
  const stateRows = Object.entries(st).sort((a, b) => b[1] - a[1]).map(([s, v]) => ({ label: `${STATE_PT[s] || s}`, value: v, color: COL[s] || '#7480b3' }));
  const work = k.workload.filter((w) => w.open_tasks + w.completed_tasks + w.problem_tasks > 0).slice(0, 10).map((w) => ({
    label: w.display_name, value: w.open_tasks + w.completed_tasks + w.problem_tasks,
    parts: [{ value: w.open_tasks, color: '#22d3ee', title: 'abertas' }, { value: w.completed_tasks, color: '#34d399', title: 'concluídas' }, { value: w.problem_tasks, color: '#fbbf24', title: 'problemas' }],
  }));
  const apr = Object.entries(k.approvals_by_state).map(([s, v]) => ({ label: APR_PT[s] || s, value: v, color: APR_COL[s] || '#7480b3' }));
  const kp = (l, v, s) => h('div', { class: 'kpi' }, h('div', { class: 'v' }, v), h('div', { class: 'l' }, l), s ? h('div', { class: 's' }, s) : null);
  el.replaceChildren(
    h('div', { class: 'kpis' }, kp('Tarefas', num(total)), kp('Taxa de conclusão', total ? `${Math.round((done / total) * 100)}%` : '—', `${done} concluídas`), kp('Cobertura de prova', k.evidence_coverage === null ? '—' : `${k.evidence_coverage}%`, 'concluídas com Evidence'),
      kp('Execução p50 / p95', `${ms(k.attempt_duration_ms.p50)} / ${ms(k.attempt_duration_ms.p95)}`, `${k.attempt_duration_ms.n} tentativas bem-sucedidas`), kp('Tempo de ciclo p50', secs(k.lead_time_seconds.p50), `${k.lead_time_seconds.n} tarefas terminadas`), kp('Eventos de auditoria', num(k.audit_events))),
    h('div', { class: 'cols2' },
      h('div', { class: 'card' }, h('h3', {}, 'Tarefas por estado'), stateRows.length ? hbars(stateRows) : h('div', { class: 'empty' }, 'Sem tarefas.')),
      h('div', { class: 'card' }, h('h3', {}, 'Carga por agente'), work.length ? [hbars(work), h('div', { class: 'legend' }, h('span', {}, h('span', { class: 'dot', style: { color: '#22d3ee' } }), 'abertas'), h('span', {}, h('span', { class: 'dot', style: { color: '#34d399' } }), 'concluídas'), h('span', {}, h('span', { class: 'dot', style: { color: '#fbbf24' } }), 'problemas'))] : h('div', { class: 'empty' }, 'Ainda nenhum agente tem tarefas.')),
      h('div', { class: 'card' }, h('h3', {}, 'Concluídas por dia (14 dias)'), columns(k.completed_per_day)),
      h('div', { class: 'card' }, h('h3', {}, 'Aprovações (funil)'), apr.length ? hbars(apr) : h('div', { class: 'empty' }, 'Sem pedidos de aprovação.'))),
    h('div', { class: 'card', style: { marginTop: '14px' } }, h('h3', {}, '📤 Dados para Power BI / Fabric'),
      h('p', { class: 'muted', style: { marginBottom: '10px' } }, 'Modelo em estrela (dimensões + factos), já calculado na base de dados. Descarrega os CSV (UTF-8 com BOM, separador vírgula) e liga com «Obter dados → Texto/CSV». Chaves: agent_id, unit_id, role_id, task_id, attempt_id, approval_id. Só metadados — nunca conteúdo de mensagens, notas ou ficheiros.'),
      h('div', { class: 'table-wrap' }, h('table', {}, h('thead', {}, h('tr', {}, h('th', {}, 'Tabela'), h('th', {}, 'Conteúdo'), h('th', {}, ''))),
        h('tbody', {}, TABLES.map(([t, d]) => h('tr', {}, h('td', { class: 'mono' }, t), h('td', {}, d), h('td', {}, h('a', { class: 'btn sm', href: `/api/w/${S.world}/bi/export/${t}.csv`, download: `${S.world}_${t}.csv` }, '⬇ CSV'))))))),
      h('p', { class: 'hint faint', style: { marginTop: '8px' } }, `Gerado em ${new Date(k.generated_at).toLocaleString('pt-PT', { timeZone: 'Europe/Lisbon' })} (Lisboa). Células que começam por = + - @ são prefixadas com apóstrofo para evitar injeção de fórmulas.`)));
}
