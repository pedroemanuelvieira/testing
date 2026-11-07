// «Hoje»: leitura rápida do dia — o que correu, o que falhou e o que precisa de mim (brief do Dojo §2/§9).
// A app não corre estas rotinas: mostra registos de execução feitos noutro ambiente e calcula o que falta.
import { h, field, openModal, toast, busy, fmtShort, stateBadge } from '../ui.js';
import { get, post, patch, ApiError } from '../api.js';
import { S, W, agents, agentById, loadWorld } from '../state.js';
import { avatarEl } from '../components.js';
import { openTaskDetail, openTaskForm } from './tasks.js';

const errMsg = (e) => (e instanceof ApiError ? e.message : 'Falhou. Tenta de novo.');
export const RUN = {
  ok: { label: 'OK', icon: '✔', color: '#34d399', cls: 'ok' },
  warn: { label: 'Com avisos', icon: '⚠', color: '#f4c24a', cls: 'gold' },
  failed: { label: 'Falhou', icon: '✕', color: '#fb7185', cls: 'bad' },
  missed: { label: 'Não correu', icon: '✕', color: '#fb7185', cls: 'bad' },
  awaiting: { label: 'À espera do registo', icon: '⧗', color: '#60a5fa', cls: 'info' },
  pending: { label: 'Ainda por correr', icon: '○', color: '#a3add9', cls: 'dim' },
  none: { label: 'Sem registo ainda', icon: '–', color: '#7480b3', cls: 'dim' },
  disabled: { label: 'Desativada', icon: '‖', color: '#7480b3', cls: 'dim' },
};
export const runChip = (st) => { const r = RUN[st] || RUN.none; return h('span', { class: `badge ${r.cls}` }, h('span', { 'aria-hidden': 'true' }, r.icon), ' ', r.label); };
export const PROJ = {
  in_production: ['● Em produção', 'ok'], preparing: ['Em preparação', 'info'], blocked: ['Bloqueado', 'bad'], on_demand: ['A pedido', 'violet'],
  active: ['Ativo', 'cyan'], paused: ['Pausado', 'warn'], done: ['Concluído', 'dim'],
};
const hhmm = (iso) => new Date(iso).toLocaleTimeString('pt-PT', { timeZone: 'Europe/Lisbon', hour: '2-digit', minute: '2-digit' });
const minutesOfDay = (iso) => { const [hh, mm] = hhmm(iso).split(':').map(Number); return hh * 60 + mm; };

function timeline(data) {
  const rows = data.routines.filter((r) => r.today.length);
  if (!rows.length) return h('div', { class: 'empty' }, h('b', {}, 'Sem execuções previstas hoje'), 'As rotinas de dias úteis e semanais aparecem nos dias em que correm.');
  const ns = 'http://www.w3.org/2000/svg';
  const W_ = 1000, L = 210, rowH = 34, H_ = 36 + rows.length * rowH;
  const x = (m) => L + (m / 1440) * (W_ - L - 10);
  const el = (tag, attrs, text) => { const e = document.createElementNS(ns, tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); if (text !== undefined) e.textContent = text; return e; };
  const svg = el('svg', { viewBox: `0 0 ${W_} ${H_}`, role: 'img', 'aria-label': `Linha do tempo de hoje: ${data.slots.map((s) => `${s.title} ${hhmm(s.slot_at)} ${RUN[s.status].label}`).join('; ')}` });
  svg.style.width = '100%';
  for (let hr = 0; hr <= 24; hr += 3) {
    svg.append(el('line', { x1: x(hr * 60), x2: x(hr * 60), y1: 18, y2: H_ - 4, stroke: 'rgba(139,156,255,.15)' }));
    svg.append(el('text', { x: x(hr * 60), y: 12, 'text-anchor': 'middle', 'font-size': 11, fill: '#a3add9' }, `${String(hr).padStart(2, '0')}h`));
  }
  rows.forEach((r, i) => {
    const y = 36 + i * rowH;
    svg.append(el('text', { x: 0, y: y + 4, 'font-size': 12.5, fill: '#eef1ff' }, `${agentById(r.agent_id)?.display_name || '?'} · ${r.title}`.slice(0, 32)));
    svg.append(el('line', { x1: L, x2: W_ - 10, y1: y, y2: y, stroke: 'rgba(139,156,255,.25)' }));
    for (const s of r.today) {
      const st = RUN[s.status];
      const g = el('g', { transform: `translate(${x(minutesOfDay(s.slot_at))},${y})` });
      g.append(el('circle', { r: 10, fill: '#0b1022', stroke: st.color, 'stroke-width': 2.5 }));
      g.append(el('text', { y: 4, 'text-anchor': 'middle', 'font-size': 11, 'font-weight': 700, fill: st.color }, st.icon));
      g.append(el('title', {}, `${r.title} · ${hhmm(s.slot_at)} · ${st.label}${s.note ? ` · ${s.note}` : ''}`));
      svg.append(g);
    }
  });
  const nowX = x(minutesOfDay(data.now));
  svg.append(el('line', { x1: nowX, x2: nowX, y1: 18, y2: H_ - 4, stroke: '#ff5a4d', 'stroke-width': 2 }));
  svg.append(el('text', { x: nowX + 4, y: H_ - 6, 'font-size': 11, fill: '#ff8a80' }, `agora ${hhmm(data.now)}`));
  return h('div', { style: { overflowX: 'auto' } }, h('div', { style: { minWidth: '640px' } }, svg),
    h('div', { class: 'legend' }, ['ok', 'warn', 'failed', 'missed', 'awaiting', 'pending'].map((k) => runChip(k))));
}

export function openRunForm(routine, onDone) {
  const status = h('select', { 'data-autofocus': '' }, [['ok', '✔ OK'], ['warn', '⚠ Com avisos'], ['failed', '✕ Falhou']].map(([v, l]) => h('option', { value: v }, l)));
  const note = h('input', { type: 'text', maxLength: 300, placeholder: 'ex.: 6 de 7 modelos prontos (só dados fictícios/higienizados)' });
  const err = h('div', { class: 'note bad hide', role: 'alert' });
  const ok = h('button', { class: 'btn primary' }, 'Registar');
  const m = openModal({ title: `Registar execução · ${routine.title}`, body: h('div', {},
    h('p', { class: 'muted', style: { marginBottom: '10px' } }, 'Fica ligada ao slot agendado mais recente ainda sem registo. A app não executou esta rotina: estás a registar o que aconteceu no ambiente onde ela corre.'),
    field('Resultado', status), field('Nota', note), err), actions: [h('button', { class: 'btn', onclick: () => m.close() }, 'Cancelar'), ok] });
  ok.addEventListener('click', () => busy(ok, async () => {
    try { await post(`${W()}/routines/${routine.id}/runs`, { status: status.value, note: note.value }); toast('Execução registada.'); m.close(); onDone?.(); }
    catch (e) { err.textContent = errMsg(e); err.classList.remove('hide'); }
  }));
}

export function openRoutineForm(projects, onDone) {
  const f = {
    title: h('input', { type: 'text', maxLength: 120, 'data-autofocus': '' }),
    agent: h('select', {}, agents().filter((a) => a.lifecycle_status !== 'archived').map((a) => h('option', { value: a.id }, a.display_name))),
    kind: h('select', {}, [['weekdays', 'Dias úteis'], ['daily', 'Todos os dias'], ['weekly', 'Semanal'], ['monthly', 'Mensal']].map(([v, l]) => h('option', { value: v }, l))),
    times: h('input', { type: 'text', value: '09:00', placeholder: '09:00, 15:00' }),
    weekday: h('select', {}, ['domingo', 'segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado'].map((l, i) => h('option', { value: i, selected: i === 1 }, l))),
    day: h('input', { type: 'number', min: 1, max: 28, value: 1 }),
    project: h('select', {}, h('option', { value: '' }, '— sem projeto —'), projects.map((p) => h('option', { value: p.id }, `${p.number ? `${p.number} · ` : ''}${p.title}`))),
  };
  const err = h('div', { class: 'note bad hide', role: 'alert' });
  const ok = h('button', { class: 'btn primary' }, 'Criar rotina');
  const m = openModal({ title: 'Nova rotina agendada', body: h('div', {}, field('Nome', f.title), h('div', { class: 'grid2' }, field('Agente', f.agent), field('Projeto', f.project)),
    h('div', { class: 'grid2' }, field('Cadência', f.kind), field('Horas (Lisboa)', f.times, 'separadas por vírgula')), h('div', { class: 'grid2' }, field('Dia da semana (semanal)', f.weekday), field('Dia do mês (mensal)', f.day)), err),
  actions: [h('button', { class: 'btn', onclick: () => m.close() }, 'Cancelar'), ok] });
  ok.addEventListener('click', () => busy(ok, async () => {
    const schedule = { kind: f.kind.value, times: f.times.value.split(',').map((x) => x.trim()).filter(Boolean) };
    if (schedule.kind === 'weekly') schedule.weekday = Number(f.weekday.value);
    if (schedule.kind === 'monthly') schedule.day = Number(f.day.value);
    try { await post(`${W()}/routines`, { title: f.title.value, agent_id: f.agent.value, project_id: f.project.value || undefined, schedule }); toast('Rotina criada.'); m.close(); onDone?.(); }
    catch (e) { err.textContent = errMsg(e); err.classList.remove('hide'); }
  }));
}

export async function todayPane(el, { refresh }) {
  const [data, projects] = await Promise.all([get(`${W()}/today`), get(`${W()}/projects`)]);
  const k = data.kpis;
  const kp = (v, l, s, cls) => h('div', { class: `kpi ${cls || ''}` }, h('div', { class: 'v' }, String(v)), h('div', { class: 'l' }, l), s ? h('div', { class: 's' }, s) : null);
  const goNeed = (n) => (n.kind === 'task' ? openTaskDetail(n.id, refresh) : n.kind === 'approval' ? (location.hash = '#/trabalho/aprovacoes') : document.getElementById(`rot-${n.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }));
  const ORDER = ['failed', 'missed', 'warn', 'awaiting', 'pending', 'none', 'ok', 'disabled']; // problemas primeiro
  const rows = [...data.routines].sort((a, b) => ORDER.indexOf(a.chip) - ORDER.indexOf(b.chip) || a.title.localeCompare(b.title));
  const prodProjects = projects.filter((p) => p.kind === 'ml' && p.state === 'in_production');
  const otherMl = projects.filter((p) => p.kind === 'ml' && p.state !== 'in_production');
  el.replaceChildren(
    h('div', { class: 'row', style: { marginBottom: '10px' } }, h('div', { class: 'grow' }, h('b', {}, `Hoje · ${new Date(data.now).toLocaleDateString('pt-PT', { timeZone: 'Europe/Lisbon', weekday: 'long', day: 'numeric', month: 'long' })}`), h('span', { class: 'faint' }, ` · ${hhmm(data.now)} Lisboa`)),
      h('button', { class: 'btn sm', onclick: () => openRoutineForm(projects, refresh) }, '＋ Nova rotina')),
    h('div', { class: 'kpis' }, kp(k.scheduled, 'Previstas hoje'), kp(k.recorded, 'Registadas', k.with_warnings ? `${k.with_warnings} com avisos` : 'sem avisos'),
      kp(k.failed_or_missed, 'Falharam ou não correram', null, k.failed_or_missed ? 'kpi-bad' : ''), kp(k.pending + k.awaiting, 'Por correr', k.awaiting ? `${k.awaiting} à espera do registo` : null)),
    h('div', { class: 'cols2' },
      h('section', { class: 'card', 'aria-label': 'Precisa de mim' }, h('h3', {}, '⚑ Precisa de mim'),
        data.needs_me.length ? h('div', { class: 'col' }, data.needs_me.map((n) => h('button', { class: 'tcard', onclick: () => goNeed(n) }, h('b', {}, n.title),
          h('div', { class: 'row' }, n.kind === 'routine' ? runChip(n.status) : n.kind === 'task' ? stateBadge(n.status) : h('span', { class: 'badge violet' }, 'aprovação pendente'), h('span', { class: 'faint' }, { routine: 'rotina', task: 'tarefa', approval: 'aprovação' }[n.kind])))))
          : h('div', { class: 'empty' }, h('b', {}, 'Nada à tua espera'), 'Sem falhas, bloqueios ou aprovações pendentes.')),
      h('section', { class: 'card', 'aria-label': 'Projetos ML' }, h('h3', {}, 'ML · em produção'),
        prodProjects.length ? h('div', { class: 'col', style: { gap: '6px' } }, prodProjects.map((p) => h('div', { class: 'row' }, h('b', { class: 'mono' }, p.number), h('span', { class: 'grow' }, p.title), h('span', { class: 'faint' }, p.cadence),
          p.last_point_status !== 'none' ? runChip(p.last_point_status) : null))) : h('div', { class: 'muted' }, 'Nenhum.'),
        otherMl.length ? h('div', { class: 'row', style: { marginTop: '10px' } }, otherMl.map((p) => h('span', { class: `badge ${PROJ[p.state][1]}`, title: p.next_step }, `${p.number} ${p.title} · ${PROJ[p.state][0]}`))) : null)),
    h('section', { class: 'card', style: { marginTop: '14px' }, 'aria-label': 'Linha do tempo de hoje' }, h('h3', {}, 'Linha do tempo de hoje (0h–24h)'), timeline(data)),
    h('section', { class: 'card', style: { marginTop: '14px' }, 'aria-label': 'Rotinas da equipa' }, h('h3', {}, `Rotinas da equipa (${rows.length})`),
      h('div', { class: 'note', style: { marginBottom: '10px' } }, 'A app não corre estas rotinas: regista execuções feitas onde elas correm (manual ou importação, sempre higienizado) e calcula o que estava previsto. «Não correu» = passou mais de 1 h do slot sem registo.'),
      rows.length ? h('div', { class: 'table-wrap' }, h('table', {}, h('thead', {}, h('tr', {}, ['Agente', 'Rotina', 'Cadência', 'Próxima', 'Última execução', 'Estado', ''].map((x) => h('th', {}, x)))),
        h('tbody', {}, rows.map((r) => { const a = agentById(r.agent_id); return h('tr', { id: `rot-${r.id}` },
          h('td', {}, a ? h('div', { class: 'row', style: { flexWrap: 'nowrap' } }, avatarEl(a, 'xs'), a.display_name) : '?'), h('td', {}, h('b', {}, r.title)), h('td', { class: 'faint' }, r.cadence),
          h('td', {}, r.next_run_at ? fmtShort(r.next_run_at) : '—'),
          h('td', {}, r.last_run ? [h('div', {}, `${fmtShort(r.last_run.slot_at || r.last_run.recorded_at)} · ${RUN[r.last_run.status].label}`), r.last_run.note ? h('div', { class: 'faint' }, r.last_run.note) : null] : h('span', { class: 'faint' }, '—')),
          h('td', {}, runChip(r.chip)),
          h('td', {}, h('div', { class: 'row', style: { flexWrap: 'nowrap' } }, h('button', { class: 'btn sm', onclick: () => openRunForm(r, refresh) }, 'Registar'),
            h('button', { class: 'btn sm', 'aria-label': r.enabled ? `Desativar ${r.title}` : `Ativar ${r.title}`, onclick: async () => { try { await patch(`${W()}/routines/${r.id}`, { enabled: !r.enabled, expected_version: r.record_version }); refresh(); } catch (e) { toast(errMsg(e), 'error'); } } }, r.enabled ? 'Pausar' : 'Ativar')))); })))) : h('div', { class: 'empty' }, h('b', {}, 'Sem rotinas'), 'Cria a primeira em «＋ Nova rotina».')));
  void loadWorld; void openTaskForm; void S;
}

export async function projectsPane(el, { refresh }) {
  const projects = await get(`${W()}/projects`);
  const card = (p) => h('article', { class: 'card', 'aria-label': p.title },
    h('div', { class: 'row' }, p.number ? h('b', { class: 'mono' }, p.number) : null, h('h3', { style: { margin: 0 } }, p.title), h('span', { class: `badge ${PROJ[p.state][1]}` }, PROJ[p.state][0]), p.kind === 'ml' ? h('span', { class: 'chip' }, 'ML') : null),
    h('table', { style: { marginTop: '8px' } }, h('tbody', {},
      h('tr', {}, h('td', { class: 'muted' }, 'Dono'), h('td', {}, agentById(p.owner_agent_id)?.display_name || '—')),
      p.cadence ? h('tr', {}, h('td', { class: 'muted' }, 'Cadência'), h('td', {}, p.cadence)) : null,
      p.last_point ? h('tr', {}, h('td', { class: 'muted' }, 'Último ponto'), h('td', {}, p.last_point_status !== 'none' ? [runChip(p.last_point_status), ' '] : null, p.last_point)) : null,
      p.next_step ? h('tr', {}, h('td', { class: 'muted' }, 'Próximo passo'), h('td', {}, p.next_step)) : null,
      h('tr', {}, h('td', { class: 'muted' }, 'Tarefas'), h('td', {}, `${p.open_tasks} abertas de ${p.total_tasks}`)))),
    h('div', { class: 'row', style: { marginTop: '10px' } }, h('button', { class: 'btn sm primary', onclick: () => openTaskForm({ projectId: p.id, onDone: refresh }) }, '＋ Tarefa'),
      h('button', { class: 'btn sm', onclick: () => openProject(p.id, refresh) }, 'Abrir'), h('button', { class: 'btn sm', onclick: () => openProjectForm(p, refresh) }, 'Ponto de situação')));
  const ml = projects.filter((p) => p.kind === 'ml'), gen = projects.filter((p) => p.kind !== 'ml');
  el.replaceChildren(h('div', { class: 'row', style: { marginBottom: '12px' } }, h('span', { class: 'grow muted' }, `${projects.length} projeto(s)`), h('button', { class: 'btn primary', onclick: () => openProjectForm(null, refresh) }, '＋ Novo projeto')),
    projects.length ? [ml.length ? h('h2', {}, 'Projetos ML') : null, h('div', { class: 'cols2' }, ml.map(card)), gen.length ? h('h2', { style: { marginTop: '14px' } }, 'Outros projetos') : null, h('div', { class: 'cols2' }, gen.map(card))]
      : h('div', { class: 'empty' }, h('b', {}, 'Sem projetos'), 'Agrupa tarefas e rotinas num projeto.'));
}

async function openProject(id, refresh) {
  let p; try { p = await get(`${W()}/projects/${id}`); } catch (e) { toast(errMsg(e), 'error'); return; }
  const m = openModal({ title: `${p.number ? `${p.number} · ` : ''}${p.title}`, wide: true, body: h('div', { class: 'col' },
    h('div', { class: 'row' }, h('span', { class: `badge ${PROJ[p.state][1]}` }, PROJ[p.state][0]), p.last_point ? h('span', { class: 'muted' }, `Último ponto: ${p.last_point}`) : null),
    h('h3', {}, 'Tarefas'), p.tasks.length ? p.tasks.map((t) => h('button', { class: 'tcard', onclick: () => { m.close(); openTaskDetail(t.id, refresh); } }, h('b', {}, t.title), h('div', { class: 'row' }, stateBadge(t.state), h('span', { class: 'faint' }, agentById(t.assigned_agent_id)?.display_name || '')))) : h('span', { class: 'muted' }, 'Sem tarefas.'),
    h('h3', {}, 'Rotinas'), p.routines.length ? h('ul', {}, p.routines.map((r) => h('li', {}, r.title))) : h('span', { class: 'muted' }, 'Sem rotinas.')) });
}

function openProjectForm(p, refresh) {
  const isNew = !p;
  const f = {
    number: h('input', { type: 'text', maxLength: 12, value: p?.number || '' }), title: h('input', { type: 'text', maxLength: 120, value: p?.title || '', 'data-autofocus': '' }),
    kind: h('select', {}, [['ml', 'ML'], ['general', 'Geral']].map(([v, l]) => h('option', { value: v, selected: v === (p?.kind || 'general') }, l))),
    state: h('select', {}, Object.entries(PROJ).map(([v, [l]]) => h('option', { value: v, selected: v === (p?.state || 'active') }, l))),
    cadence: h('input', { type: 'text', maxLength: 60, value: p?.cadence || '' }), last: h('input', { type: 'text', maxLength: 300, value: p?.last_point || '' }),
    lastStatus: h('select', {}, [['none', '—'], ['ok', '✔ OK / estável'], ['warn', '⚠ Com avisos'], ['failed', '✕ Falhou']].map(([v, l]) => h('option', { value: v, selected: v === (p?.last_point_status || 'none') }, l))),
    next: h('input', { type: 'text', maxLength: 300, value: p?.next_step || '' }),
    owner: h('select', {}, h('option', { value: '' }, '—'), agents().map((a) => h('option', { value: a.id, selected: a.id === p?.owner_agent_id }, a.display_name))),
  };
  const err = h('div', { class: 'note bad hide', role: 'alert' });
  const ok = h('button', { class: 'btn primary' }, isNew ? 'Criar projeto' : 'Guardar ponto de situação');
  const m = openModal({ title: isNew ? 'Novo projeto' : `Ponto de situação · ${p.title}`, body: h('div', {}, h('div', { class: 'grid2' }, field('Nº', f.number), field('Título', f.title)),
    h('div', { class: 'grid2' }, field('Tipo', f.kind), field('Estado', f.state)), h('div', { class: 'grid2' }, field('Cadência', f.cadence), field('Dono', f.owner)),
    h('div', { class: 'grid2' }, field('Último ponto', f.last), field('Estado do último ponto', f.lastStatus)), field('Próximo passo', f.next), err),
  actions: [h('button', { class: 'btn', onclick: () => m.close() }, 'Cancelar'), ok] });
  ok.addEventListener('click', () => busy(ok, async () => {
    const body = { number: f.number.value, title: f.title.value, kind: f.kind.value, state: f.state.value, cadence: f.cadence.value, last_point: f.last.value, last_point_status: f.lastStatus.value, next_step: f.next.value, owner_agent_id: f.owner.value || null };
    try { if (isNew) await post(`${W()}/projects`, body); else await patch(`${W()}/projects/${p.id}`, { ...body, expected_version: p.record_version }); toast('Projeto guardado.'); m.close(); refresh(); }
    catch (e) { err.textContent = errMsg(e); err.classList.remove('hide'); }
  }));
}
