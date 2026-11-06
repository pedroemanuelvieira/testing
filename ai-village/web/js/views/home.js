// Vista «Vila»: KPIs honestos, primeiros passos, mapa (SVG) e lista equivalente.
import { h, toast, busy, activityBadge } from '../ui.js';
import { post, ApiError } from '../api.js';
import { S, W, pref, agents, units, orchestrator, designOnly, loadWorld, subscribe } from '../state.js';
import { avatarEl } from '../components.js';
import { renderVillage, bindVillage } from '../village.js';
import { openAgentDrawer, openUnitDrawer } from './agent.js';
import { openAgentEditor, openUnitEditor } from './editors.js';

const kpi = (label, value, sub) => h('div', { class: 'kpi' }, h('div', { class: 'v' }, String(value)), h('div', { class: 'l' }, label), sub ? h('div', { class: 's' }, sub) : null);

export function homeView(root) {
  let mode = pref.get('map', window.innerWidth < 720 ? 'list' : 'mapa');
  let lastSig = '';
  const kpis = h('div', { class: 'kpis' });
  const first = h('div');
  const stage = h('div');
  const toggle = h('div', { class: 'world-switch', role: 'group', 'aria-label': 'Modo de visualização' });
  const head = h('div', { class: 'view-head' }, h('div', {}, h('div', { class: 'kanji' }, '村 · VILA'), h('h1', {}, S.overview?.world?.name || 'Vila')), h('span', { class: 'grow' }), toggle,
    h('button', { class: 'btn', onclick: () => openUnitEditor(null) }, '＋ Unidade'), h('button', { class: 'btn primary', onclick: () => openAgentEditor(null) }, '＋ Agente'));
  root.append(head, kpis, first, stage);

  const paintToggle = () => toggle.replaceChildren(...[['mapa', '🗺 Mapa'], ['list', '☰ Lista']].map(([id, l]) => h('button', { 'aria-pressed': String(mode === id), onclick: () => { mode = id; pref.set('map', id); lastSig = ''; render(); } }, l)));

  function paintKpis() {
    const k = S.overview.kpis, st = k.tasks_by_state;
    const open = (st.assigned || 0) + (st.running || 0) + (st.awaiting_approval || 0) + (st.pending || 0);
    const busyN = agents().filter((a) => a.activity_status === 'ocupado').length;
    kpis.replaceChildren(
      kpi('Agentes', k.agents.by_lifecycle.active || 0, `${busyN} a executar agora`), kpi('Tarefas abertas', open, `${(st.blocked || 0) + (st.failed || 0)} a precisar de atenção`),
      kpi('Concluídas', st.completed || 0, k.evidence_coverage === null ? 'sem dados' : `${k.evidence_coverage}% com prova`), kpi('Aprovações pendentes', S.overview.pending_approvals, 'simuladas — sem envio externo'),
      kpi('Worker', S.overview.worker.online ? 'online' : 'offline', S.overview.worker.queued ? `${S.overview.worker.queued} na fila` : 'fila vazia'));
  }

  function paintFirst() {
    const k = S.overview.kpis;
    const orch = orchestrator();
    const items = [];
    if (designOnly()) {
      items.push(h('div', { class: 'note warn' }, h('b', {}, 'Mundo profissional — só desenho. '), 'Nesta conta não entram dados reais nem há execução: aqui desenhas a organização que será implementada no ambiente profissional aprovado (G3). Só o blueprint higienizado atravessa mundos, pela Ponte.'));
    } else if (k.tasks_total < 2) {
      const run = h('button', { class: 'btn primary' }, '▶ Executar cenário guiado F01');
      run.addEventListener('click', () => busy(run, async () => {
        try { const r = await post(`${W()}/demo/f01`); toast(`Tarefa criada para ${r.agent.name}. O worker vai validar o CSV…`); await loadWorld(); location.hash = '#/trabalho/tarefas'; } catch (e) { toast(e instanceof ApiError ? e.message : 'Falhou', 'error'); }
      }));
      items.push(h('div', { class: 'card' }, h('h3', {}, '🚀 Primeiros passos'), h('ol', { style: { margin: 0, paddingLeft: '20px', display: 'grid', gap: '8px' } },
        h('li', {}, orch ? ['Fala com o orquestrador ', h('button', { class: 'chip on', onclick: () => openAgentDrawer(orch.id) }, orch.display_name), ' — diz «ajuda» ou «preciso de validar um csv».'] : 'Cria um orquestrador.'),
        h('li', {}, ['Vê trabalho REAL a acontecer: ', run, h('span', { class: 'muted' }, ' valida uma fixture CSV sintética no worker e devolve prova (4 · 3 · 1 · 1 · soma 8).')]),
        h('li', {}, 'Abre a prova em Trabalho → Provas e confirma passos, digests e limitações.'),
        h('li', {}, 'Cria a tua função e o teu agente em «＋ Agente» — sem código.'))));
    }
    first.replaceChildren(...items);
  }

  function renderMap() {
    const wrap = h('div', { class: 'village-wrap' });
    const scroll = h('div', { class: 'village-scroll', tabindex: 0, 'aria-label': 'Mapa da vila (desliza para ver tudo)' });
    scroll.innerHTML = renderVillage({ units: units(), agents: agents(), world: S.world });
    bindVillage(scroll, { onAgent: (id) => openAgentDrawer(id), onUnit: (id) => openUnitDrawer(id) });
    wrap.append(scroll, h('div', { class: 'village-hud' },
      h('span', { class: 'chip' }, S.overview.world.policy.label), h('span', { class: 'chip' }, 'retratos provisórios')));
    stage.replaceChildren(wrap, h('div', { class: 'legend' },
      h('span', {}, h('span', { class: 'badge ok' }, '● disponível')), h('span', {}, h('span', { class: 'badge cyan' }, '⚙ ocupado'), ' só com tentativa real em curso'),
      h('span', {}, h('span', { class: 'badge warn' }, '! bloqueado')), h('span', {}, h('span', { class: 'badge dim' }, '⏸ inativo')), h('span', {}, h('span', { class: 'badge gold' }, '★ orquestrador')),
      h('span', { class: 'faint' }, 'Clica num edifício ou num agente. A lista tem as mesmas ações.')));
  }

  function renderList() {
    const byUnit = units().filter((u) => u.lifecycle_status === 'active').map((u) => ({ u, members: agents().filter((a) => a.org_unit_id === u.id) }));
    const loose = agents().filter((a) => !a.org_unit_id);
    const card = (u, members) => h('section', { class: 'card unit-card', 'aria-label': u?.name || 'Sem unidade' },
      h('h3', {}, u ? [h('span', { class: 'kanji' }, u.kanji), u.name] : 'Sem unidade', u ? h('button', { class: 'btn sm', style: { marginLeft: 'auto' }, onclick: () => openUnitDrawer(u.id) }, 'Abrir') : null),
      u?.purpose ? h('p', { class: 'muted', style: { marginBottom: '10px' } }, u.purpose) : null,
      members.length ? members.map((a) => h('div', { class: 'agent-row' }, avatarEl(a), h('div', { class: 'meta' }, h('b', {}, a.display_name, a.orchestrator_flag ? ' ★' : ''), h('span', {}, a.title)), h('div', { class: 'acts' }, activityBadge(a.activity_status),
        h('button', { class: 'btn sm primary', onclick: () => openAgentDrawer(a.id, 'conversa') }, 'Conversar'), h('button', { class: 'btn sm', onclick: () => openAgentDrawer(a.id, 'tarefas') }, 'Tarefas'))))
        : h('div', { class: 'muted' }, 'Sem agentes.'));
    stage.replaceChildren(h('div', { class: 'org-list', style: { gridTemplateColumns: 'repeat(auto-fit,minmax(min(100%,480px),1fr))' } }, byUnit.map(({ u, members }) => card(u, members)), loose.length ? card(null, loose) : null));
  }

  function render() {
    paintToggle(); paintKpis(); paintFirst();
    const sig = JSON.stringify([mode, units().map((u) => [u.id, u.name, u.theme, u.kanji, u.plot, u.lifecycle_status]), agents().map((a) => [a.id, a.display_name, a.title, a.org_unit_id, a.activity_status, a.orchestrator_flag, a.appearance, a.lifecycle_status])]);
    if (sig === lastSig) return;
    lastSig = sig;
    if (mode === 'mapa') renderMap(); else renderList();
  }
  render();
  const unsub = subscribe(render); // reage logo a qualquer alteração do backend (ex.: novo agente)
  return { tick: render, destroy: unsub };
}
