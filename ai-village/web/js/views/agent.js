// Gaveta do agente: Conversa (histórico no backend), Tarefas e Perfil. Também a gaveta da unidade.
import { h, openDrawer, toast, stateBadge, activityBadge, fmtShort, busy, confirmDialog, selectDialog } from '../ui.js';
import { get, post, ApiError } from '../api.js';
import { S, W, agents, agentById, unitById, roleById, capById, designOnly, loadWorld } from '../state.js';
import { avatarEl, modeTag } from '../components.js';
import { openTaskForm, openTaskDetail } from './tasks.js';
import { openAgentEditor } from './editors.js';

const errMsg = (e) => (e instanceof ApiError ? e.message : 'Falhou. Tenta de novo.');

export function openAgentDrawer(agentId, tab = 'conversa') {
  let agent = agentById(agentId);
  if (!agent) { toast('Agente não encontrado.', 'error'); return null; }
  const head = h('div', { class: 'row', style: { flex: 1 } });
  const body = h('div', { class: 'col', style: { flex: 1, minHeight: 0 } });
  const drawer = openDrawer({ title: agent.display_name, header: head, body, label: `Agente ${agent.display_name}` });
  drawer.bodyEl.style.gap = '12px';
  drawer.bodyEl.replaceChildren(body);
  let current = tab;

  const tabs = h('div', { class: 'tabs', role: 'tablist' });
  const pane = h('div', { class: 'col', style: { flex: 1, minHeight: 0 } });
  const paintHead = () => {
    agent = agentById(agentId) || agent;
    head.replaceChildren(avatarEl(agent, 'lg'), h('div', {},
      h('h2', {}, agent.display_name), h('div', { class: 'muted' }, agent.title || 'Agente'),
      h('div', { class: 'row', style: { marginTop: '4px' } }, activityBadge(agent.activity_status),
        agent.orchestrator_flag ? h('span', { class: 'badge gold' }, '★ Orquestrador') : null,
        agent.origin === 'ecosystem_ref' ? h('span', { class: 'badge dim hide-sm', title: 'Entidade da app que reflete a ficha do ecossistema; não é o bot original.' }, 'ecossistema') : null,
        unitById(agent.org_unit_id) ? h('span', { class: 'chip hide-sm' }, unitById(agent.org_unit_id).name) : null)));
  };
  const paintTabs = () => {
    tabs.replaceChildren(...[['conversa', 'Conversa'], ['tarefas', 'Tarefas'], ['perfil', 'Perfil']].map(([id, label]) =>
      h('button', { role: 'tab', 'aria-selected': String(current === id), onclick: () => { current = id; paintTabs(); paintPane(); } }, label)));
  };
  const paintPane = () => {
    pane.replaceChildren();
    pane.style.overflow = current === 'conversa' ? 'hidden' : 'auto';
    if (current === 'conversa') chatPane(pane, agent);
    else if (current === 'tarefas') tasksPane(pane, agent);
    else profilePane(pane, agent, () => { paintHead(); paintPane(); }, drawer);
  };
  body.append(tabs, pane);
  paintHead(); paintTabs(); paintPane();
  return drawer;
}

// ---------------- conversa ----------------
function chatPane(pane, agent) {
  const state = { conv: null, convs: [], lastSeq: 0 };
  const list = h('div', { class: 'msgs', role: 'log', 'aria-live': 'polite', 'aria-label': `Conversa com ${agent.display_name}`, tabindex: 0 });
  const input = h('textarea', { placeholder: `Escreve a ${agent.display_name}… (só dados fictícios)`, maxLength: 4000, rows: 2, 'data-autofocus': '', 'aria-label': 'Mensagem' });
  const send = h('button', { class: 'btn primary' }, 'Enviar');
  const banner = h('div', { class: 'note' });
  const sel = h('select', { 'aria-label': 'Conversa' });
  const newBtn = h('button', { class: 'btn sm' }, '＋ Nova conversa');
  const mode = h('select', { 'aria-label': 'Modo da nova conversa' }, h('option', { value: 'demo' }, 'Demo (regras fixas)'));
  const hasReal = (conns) => conns.find((c) => c.provider_id === 'anthropic-api');

  const bubble = (m) => {
    const cls = m.author_type === 'owner' ? 'owner' : m.author_type === 'agent' ? 'agent' : 'system';
    let content = m.content;
    if (m.state === 'blocked') content = '🛑 Mensagem bloqueada pela guarda D1: o conteúdo NÃO foi guardado nem resumido.';
    if (m.state === 'purged') content = '— conteúdo expurgado pela política de retenção —';
    const el = h('div', { class: `msg ${cls}${m.state === 'error' ? ' error' : ''}` }, content,
      h('div', { class: 'meta' }, fmtShort(m.created_at), modeTag(m.mode), m.provider_ref ? h('span', { class: 'mono' }, m.provider_ref) : null,
        m.task_refs?.length ? h('button', { class: 'chip', onclick: () => openTaskDetail(m.task_refs[0]) }, '↗ tarefa') : null));
    const frag = [el];
    const sg = m.meta?.suggestion;
    if (sg) {
      const target = agentById(sg.agent_id);
      frag.push(h('div', { class: 'suggest row' },
        h('button', { class: 'btn sm sakura', onclick: () => openTaskForm({ agentId: sg.agent_id, capability: sg.capability, title: sg.title, conversationId: state.conv?.id, onDone: () => loadMsgs() }) },
          `➜ Criar tarefa para ${target?.display_name || sg.agent_name}`), h('span', { class: 'faint' }, sg.auto ? '⚙ executa no worker' : 'trabalho manual')));
    }
    return frag;
  };
  const paint = (msgs) => {
    const atBottom = list.scrollHeight - list.scrollTop - list.clientHeight < 60;
    list.replaceChildren(...(msgs.length ? msgs.flatMap(bubble) : [h('div', { class: 'empty' }, h('b', {}, 'Sem mensagens ainda'), 'Diz «olá», «estado» ou descreve o que precisas (ex.: «validar um csv»).')]));
    if (atBottom || !state.lastSeq) list.scrollTop = list.scrollHeight;
    state.lastSeq = msgs.at(-1)?.sequence || 0;
  };
  async function loadMsgs() { if (!state.conv) return; paint(await get(`${W()}/conversations/${state.conv.id}/messages`)); }
  const paintBanner = () => {
    const c = state.conv;
    banner.className = `note ${c?.mode === 'real' ? 'ok' : 'warn'}`;
    banner.replaceChildren(c?.mode === 'real'
      ? h('span', {}, h('b', {}, 'Modo REAL'), ' — modelo via API; falhas aparecem como erro, nunca viram demo em silêncio.')
      : h('span', {}, h('b', {}, 'Modo DEMO'), ' — regras fixas, sem modelo de IA. Uma mensagem não prova execução: para trabalho real, cria uma tarefa.'));
  };
  async function open(conv) { state.conv = conv; state.lastSeq = 0; paintBanner(); await loadMsgs(); sel.value = conv.id; }
  async function init() {
    const [convs, conns] = await Promise.all([get(`${W()}/agents/${agent.id}/conversations`), get(`${W()}/connections`)]);
    state.convs = convs;
    const real = hasReal(conns);
    const usable = real && real.status === 'connected' && real.granted_scopes.includes('chat');
    mode.replaceChildren(h('option', { value: 'demo' }, 'Demo (regras fixas)'),
      h('option', { value: 'real', disabled: !usable, title: usable ? '' : 'Indisponível: liga e verifica o modelo em Ligações e concede o âmbito «chat».' }, usable ? 'Real (modelo via API)' : 'Real — indisponível (ver Ligações)'));
    state.realConn = usable ? real.id : null;
    sel.replaceChildren(...convs.map((c) => h('option', { value: c.id }, `${c.title} · ${c.mode.toUpperCase()} · ${fmtShort(c.updated_at)}`)));
    if (convs.length) await open(convs[0]); else { await createConv('demo'); }
  }
  async function createConv(m) {
    const c = await post(`${W()}/agents/${agent.id}/conversations`, { mode: m, connection_id: m === 'real' ? state.realConn : undefined });
    state.convs.unshift(c);
    sel.prepend(h('option', { value: c.id }, `${c.title} · ${c.mode.toUpperCase()} · agora`));
    await open(c);
  }
  sel.addEventListener('change', () => open(state.convs.find((c) => c.id === sel.value)));
  newBtn.addEventListener('click', () => busy(newBtn, async () => { try { await createConv(mode.value); } catch (e) { toast(errMsg(e), 'error'); } }));
  let ready = Promise.resolve();
  const doSend = () => busy(send, async () => {
    await ready; // a conversa carrega de forma assíncrona: não perder um Enter rápido
    const text = input.value.trim();
    if (!text) return;
    if (!state.conv) { toast('A conversa ainda não está disponível. Tenta de novo.', 'error'); return; }
    input.value = '';
    const pending = h('div', { class: 'msg owner' }, text, h('div', { class: 'meta' }, 'a enviar…'));
    list.append(pending); list.scrollTop = list.scrollHeight;
    try {
      const r = await post(`${W()}/conversations/${state.conv.id}/messages`, { content: text, request_id: `r${Date.now()}${Math.random().toString(36).slice(2, 6)}` });
      if (r.error) toast(r.error.message, 'error');
      await loadMsgs(); await loadWorld();
    } catch (e) { pending.remove(); input.value = text; toast(errMsg(e), 'error'); }
    input.focus();
  });
  send.addEventListener('click', doSend);
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); doSend(); } });
  pane.append(h('div', { class: 'row' }, sel, newBtn, mode), banner, h('div', { class: 'chat' }, list, h('div', { class: 'composer' }, input, send)));
  sel.style.cssText = 'width:auto;flex:3 1 200px'; mode.style.cssText = 'width:auto;flex:2 1 150px';
  ready = init().catch((e) => toast(errMsg(e), 'error'));
}

// ---------------- tarefas ----------------
function tasksPane(pane, agent) {
  const box = h('div', { class: 'col' });
  const del = h('button', { class: 'btn primary' }, '＋ Delegar tarefa a este agente');
  del.addEventListener('click', () => openTaskForm({ agentId: agent.id, onDone: load }));
  pane.append(del, box);
  async function load() {
    const ts = await get(`${W()}/tasks?agent_id=${agent.id}`);
    box.replaceChildren(...(ts.length ? ts.map((t) => h('button', { class: 'tcard', onclick: () => openTaskDetail(t.id, load) }, h('b', {}, t.title), h('div', { class: 'row' }, stateBadge(t.state), h('span', { class: 'faint' }, fmtShort(t.updated_at)), t.capability ? h('span', { class: 'chip' }, t.capability) : null)))
      : [h('div', { class: 'empty' }, h('b', {}, 'Sem tarefas'), `${agent.display_name} está sem trabalho atribuído.`)]));
  }
  load().catch((e) => toast(errMsg(e), 'error'));
}

// ---------------- perfil ----------------
function profilePane(pane, agent, repaint, drawer) {
  const roles = agent.role_ids.map(roleById).filter(Boolean);
  const mgr = agentById(agent.manager_agent_id);
  const team = agents().filter((a) => a.manager_agent_id === agent.id);
  const actions = h('div', { class: 'row' });
  actions.append(h('button', { class: 'btn', onclick: () => openAgentEditor(agent, { onSaved: async () => { await loadWorld(); repaint(); } }) }, '✎ Editar'));
  actions.append(h('button', { class: 'btn', onclick: async () => {
    try { await (await import('../api.js')).patch(`${W()}/agents/${agent.id}`, { lifecycle_status: agent.lifecycle_status === 'active' ? 'deactivated' : 'active', expected_version: agent.record_version }); await loadWorld(); repaint(); toast('Estado atualizado.'); } catch (e) { toast(errMsg(e), 'error'); }
  } }, agent.lifecycle_status === 'active' ? '‖ Desativar' : '▶ Reativar'));
  actions.append(h('button', { class: 'btn danger', onclick: async () => {
    try {
      await post(`${W()}/agents/${agent.id}/archive`, { expected_version: agent.record_version });
    } catch (e) {
      if (e.code === 'agent_has_active_tasks') {
        const others = agents().filter((a) => a.id !== agent.id && a.lifecycle_status === 'active').map((a) => ({ value: a.id, label: a.display_name }));
        const dest = await selectDialog(`«${agent.display_name}» tem tarefas ativas. Reencaminhar para`, [{ value: '', label: '— cancelar as tarefas —' }, ...others], { okLabel: 'Arquivar' });
        if (dest === null) return;
        try { await post(`${W()}/agents/${agent.id}/archive`, dest ? { reassign_to: dest } : { cancel_active: true }); } catch (e2) { toast(errMsg(e2), 'error'); return; }
      } else { toast(errMsg(e), 'error'); return; }
    }
    toast('Agente arquivado (histórico preservado).'); await loadWorld(); drawer.close();
  } }, '🗄 Arquivar'));
  pane.append(
    h('div', { class: 'card flat' }, h('h3', {}, 'Missão'), h('p', {}, agent.description || '—')),
    roles.length ? h('div', { class: 'card flat' }, h('h3', {}, 'Funções'), roles.map((r) => h('div', { style: { marginBottom: '8px' } }, h('b', {}, r.name), h('div', { class: 'muted' }, r.mission),
      r.limits.length ? h('div', { class: 'faint' }, 'Limites: ' + r.limits.join(' · ')) : null))) : null,
    h('div', { class: 'card flat' }, h('h3', {}, 'Capacidades'), h('div', { class: 'row' }, agent.capability_ids.length ? agent.capability_ids.map((c) => h('span', { class: `chip ${capById(c)?.auto_execute ? 'on' : ''}`, title: capById(c)?.auto_execute ? 'Executa no worker' : 'Trabalho manual' }, `${capById(c)?.auto_execute ? '⚙ ' : ''}${capById(c)?.label || c}`)) : h('span', { class: 'muted' }, 'Nenhuma.')),
      h('p', { class: 'hint faint', style: { marginTop: '6px' } }, 'Cargo e função não concedem acesso: as capacidades e permissões são explícitas.')),
    h('div', { class: 'card flat' }, h('h3', {}, 'Hierarquia'), h('p', {}, mgr ? ['Reporta a ', h('button', { class: 'chip', onclick: () => { drawer.close(); openAgentDrawer(mgr.id, 'perfil'); } }, mgr.display_name)] : 'Sem superior direto.'),
      team.length ? h('div', { class: 'row', style: { marginTop: '6px' } }, 'Equipa: ', team.map((a) => h('button', { class: 'chip', onclick: () => { drawer.close(); openAgentDrawer(a.id, 'perfil'); } }, a.display_name))) : null),
    actions);
  void designOnly;
}

export function openUnitDrawer(unitId) {
  const u = unitById(unitId); if (!u) return;
  const members = agents().filter((a) => a.org_unit_id === u.id);
  const resp = agentById(u.responsible_agent_id);
  const d = openDrawer({
    title: u.name, label: `Unidade ${u.name}`,
    header: h('div', {}, h('div', { class: 'kanji', style: { color: 'var(--vermilion)', letterSpacing: '.3em' } }, u.kanji), h('h2', {}, u.name), h('div', { class: 'muted' }, u.purpose)),
    body: h('div', { class: 'col' }, resp ? h('div', { class: 'note' }, `Responsável: ${resp.display_name} (${resp.title})`) : null,
      members.length ? members.map((a) => h('button', { class: 'agent-row', style: { textAlign: 'left', cursor: 'pointer', width: '100%' }, onclick: () => { d.close(); openAgentDrawer(a.id); } },
        avatarEl(a), h('div', { class: 'meta' }, h('b', {}, a.display_name), h('span', {}, a.title)), activityBadge(a.activity_status))) : h('div', { class: 'empty' }, h('b', {}, 'Unidade vazia'), 'Cria um agente em Configuração → Organização.')),
  });
  return d;
}
