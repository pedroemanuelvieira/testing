// Vista «Trabalho»: quadro de tarefas, aprovações (simuladas), provas e painel BI.
import { h, field, openModal, toast, busy, stateBadge, STATE_PT, fmtShort, fmtTime, debounce } from '../ui.js';
import { get, post, ApiError } from '../api.js';
import { S, W, agentById, agents, loadWorld, designOnly, pref } from '../state.js';
import { avatarEl, shortHash } from '../components.js';
import { openTaskForm, openTaskDetail, openEvidence } from './tasks.js';
import { biPanel } from './bi.js';

const errMsg = (e) => (e instanceof ApiError ? e.message : 'Falhou. Tenta de novo.');
const LANES = [
  ['Fila', ['draft', 'pending', 'assigned']], ['Em execução / espera', ['running', 'awaiting_approval']],
  ['Precisam de atenção', ['blocked', 'failed']], ['Terminadas', ['completed', 'cancelled']],
];

export function workView(root, sub = 'tarefas') {
  const tabs = h('div', { class: 'tabs', role: 'tablist' });
  const pane = h('div', {});
  const head = h('div', { class: 'view-head' }, h('div', {}, h('div', { class: 'kanji' }, '仕事 · TRABALHO'), h('h1', {}, 'Tarefas, provas e aprovações')), h('span', { class: 'grow' }),
    h('button', { class: 'btn primary', onclick: () => openTaskForm({ onDone: () => tick(true) }) }, '＋ Nova tarefa'));
  root.append(head, tabs, pane);
  let current = ['tarefas', 'aprovacoes', 'provas', 'painel'].includes(sub) ? sub : 'tarefas';
  let sig = '';
  const NAMES = { tarefas: 'Tarefas', aprovacoes: 'Aprovações', provas: 'Provas', painel: 'Painel BI' };
  const paintTabs = () => tabs.replaceChildren(...Object.entries(NAMES).map(([id, l]) => h('button', { role: 'tab', 'aria-selected': String(current === id), onclick: () => { current = id; sig = ''; location.hash = `#/trabalho/${id}`; paintTabs(); tick(true); } },
    l, id === 'aprovacoes' && S.overview?.pending_approvals ? h('span', { class: 'badge violet', style: { marginLeft: '6px' } }, S.overview.pending_approvals) : null)));

  async function tick(force) {
    paintTabs();
    try {
      if (current === 'tarefas') await tasksPane(pane, force);
      else if (current === 'aprovacoes') await approvalsPane(pane, force);
      else if (current === 'provas') await evidencePane(pane, force);
      else await biPanel(pane, force);
    } catch (e) { pane.replaceChildren(h('div', { class: 'note bad' }, errMsg(e))); }
  }
  const sigOf = (x) => JSON.stringify(x);
  const keep = { sig: '' };

  async function tasksPane(el, force) {
    const ts = await get(`${W()}/tasks?limit=300`);
    const s = sigOf([ts.map((t) => [t.id, t.state, t.record_version]), agents().map((a) => [a.id, a.activity_status])]);
    if (!force && s === keep.sig) return; keep.sig = s;
    if (!ts.length) {
      el.replaceChildren(h('div', { class: 'empty' }, h('b', {}, 'Ainda não há tarefas'), 'Cria uma tarefa ou executa o cenário guiado F01 na Vila.', h('div', { style: { marginTop: '10px' } }, h('button', { class: 'btn primary', onclick: () => openTaskForm({ onDone: () => tick(true) }) }, '＋ Nova tarefa'))));
      return;
    }
    el.replaceChildren(h('div', { class: 'board' }, LANES.map(([title, states]) => {
      const items = ts.filter((t) => states.includes(t.state));
      return h('section', { class: 'lane', 'aria-label': title }, h('h3', {}, title, h('span', { class: 'badge dim' }, items.length)),
        items.map((t) => { const a = agentById(t.assigned_agent_id); return h('button', { class: 'tcard', onclick: () => openTaskDetail(t.id, () => tick(true)) },
          h('b', {}, t.title), h('div', { class: 'row' }, stateBadge(t.state), a ? h('span', { class: 'faint' }, a.display_name) : null, t.capability?.startsWith('csv') || t.capability === 'report.village_kpis' ? h('span', { class: 'chip on' }, '⚙ worker') : null),
          h('div', { class: 'faint' }, `${fmtShort(t.updated_at)} · prioridade ${t.approved_priority ?? t.proposed_priority}${t.approved_priority ? '' : ' (proposta)'}`)); }));
    })));
  }

  async function evidencePane(el, force) {
    const [ev, ts] = await Promise.all([get(`${W()}/evidence`), get(`${W()}/tasks?limit=300`)]);
    const s = sigOf(ev.map((e) => e.id)); if (!force && s === keep.sig) return; keep.sig = s;
    const title = (id) => ts.find((t) => t.id === id)?.title || id;
    el.replaceChildren(ev.length ? h('div', { class: 'card flat table-wrap' }, h('table', {}, h('thead', {}, h('tr', {}, ['Tarefa', 'Tipo', 'Modo', 'Executor', 'Digest de saída', 'Captada', ''].map((x) => h('th', {}, x)))),
      h('tbody', {}, ev.map((e) => h('tr', {}, h('td', {}, title(e.task_id)), h('td', {}, e.kind), h('td', {}, h('span', { class: `badge ${e.mode === 'real_execution' ? 'cyan' : 'gold'}` }, e.mode === 'real_execution' ? 'worker' : 'manual')), h('td', { class: 'mono' }, e.executor_ref), h('td', { class: 'mono' }, shortHash(e.output_digest)), h('td', {}, fmtShort(e.captured_at)),
        h('td', {}, h('button', { class: 'btn sm', onclick: () => openEvidence(e.id) }, 'Abrir prova'))))))) : h('div', { class: 'empty' }, h('b', {}, 'Sem provas'), 'As provas aparecem quando uma tarefa conclui — executada pelo worker ou registada manualmente.'));
  }

  async function approvalsPane(el, force) {
    const list = await get(`${W()}/approvals`);
    const s = sigOf(list.map((a) => [a.id, a.state])); if (!force && s === keep.sig) return; keep.sig = s;
    const act = (btn, path, ok, body) => btn.addEventListener('click', () => busy(btn, async () => { try { await post(`${W()}/approvals/${path}`, body || {}); toast(ok); await loadWorld(); tick(true); } catch (e) { toast(errMsg(e), 'error'); tick(true); } }));
    const card = (a) => {
      const exp = Date.parse(a.expires_at), left = Math.round((exp - Date.now()) / 60000);
      const actions = h('div', { class: 'row' });
      if (a.state === 'pending') { const ap = h('button', { class: 'btn primary' }, 'Aprovar esta ação exata'); act(ap, `${a.id}/approve`, 'Aprovada (ainda não executada).'); const dn = h('button', { class: 'btn danger' }, 'Negar'); act(dn, `${a.id}/deny`, 'Negada.', { reason: 'negada pelo dono' }); actions.append(ap, dn); }
      if (a.state === 'approved') { const ex = h('button', { class: 'btn sakura' }, '▶ Executar simulação (uso único)'); act(ex, `${a.id}/execute`, 'Simulação executada — nada saiu da app.'); const rv = h('button', { class: 'btn danger' }, 'Revogar'); act(rv, `${a.id}/revoke`, 'Revogada.', { reason: 'revogada pelo dono' }); actions.append(ex, rv); }
      if (a.state === 'expired' || a.state === 'revoked') { const rq = h('button', { class: 'btn' }, 'Pedir nova aprovação'); rq.addEventListener('click', () => busy(rq, async () => { try { await post(`${W()}/intents/${a.intent_id}/request-approval`); toast('Novo pedido criado.'); tick(true); } catch (e) { toast(errMsg(e), 'error'); } })); actions.append(rq); }
      const badge = { pending: 'violet', approved: 'info', consumed: 'ok', denied: 'bad', revoked: 'warn', expired: 'dim' }[a.state] || 'dim';
      const PT = { pending: 'pendente', approved: 'aprovada', consumed: 'consumida', denied: 'negada', revoked: 'revogada', expired: 'expirada' };
      return h('article', { class: 'card', 'aria-label': a.summary }, h('div', { class: 'row' }, h('h3', { style: { margin: 0 } }, a.summary), h('span', { class: `badge ${badge}` }, PT[a.state] || a.state), h('span', { class: 'badge gold' }, 'SIMULAÇÃO')),
        h('div', { class: 'cols2', style: { marginTop: '10px' } },
          h('table', {}, h('tbody', {}, [['Destino', a.destination], ['Efeito', a.effect], ['Payload v' + a.payload_version, shortHash(a.payload_digest)], ['Mundo / conta', `${S.world} · conta sintética`], ['Pedida', fmtShort(a.requested_at)], ['Expira', a.state === 'pending' || a.state === 'approved' ? `${fmtShort(a.expires_at)} (${left > 0 ? `em ${left} min` : 'a expirar'})` : fmtShort(a.expires_at)]]
            .map(([k, v]) => h('tr', {}, h('td', { class: 'muted' }, k), h('td', { class: 'mono' }, v))))), h('pre', { class: 'json', 'aria-label': 'Payload exato' }, JSON.stringify(a.payload, null, 2))),
        a.intent_result ? h('div', { class: 'note ok', style: { marginTop: '8px' } }, `Executada em ${fmtTime(a.intent_result.executed_at)} — ${a.intent_result.note}`) : null, h('div', { style: { marginTop: '10px' } }, actions));
    };
    el.replaceChildren(h('div', { class: 'row', style: { marginBottom: '12px' } }, h('div', { class: 'note grow' }, 'Nesta fase só existem ações SIMULADAS (sem saída de rede). Aprovar vincula este payload exato; alterar payload, destino, conta ou mundo invalida a aprovação.'),
      h('button', { class: 'btn primary', onclick: () => openIntentForm() }, '＋ Nova ação simulada')),
      list.length ? h('div', { class: 'col' }, list.map(card)) : h('div', { class: 'empty' }, h('b', {}, 'Sem pedidos de aprovação'), 'Propõe uma ação simulada para ver o circuito: pré-visualizar → aprovar → executar uma só vez.'));
  }

  function openIntentForm(taskId) {
    const f = {
      op: h('select', {}, [['simulated.send_report', 'Enviar relatório (simulado)'], ['simulated.publish_note', 'Publicar nota interna (simulado)']].map(([v, l]) => h('option', { value: v }, l))),
      dest: h('input', { type: 'text', value: 'simulado://interno/relatorio-semanal' }),
      payload: h('textarea', { style: { fontFamily: 'var(--mono)' }, spellcheck: false }, JSON.stringify({ assunto: 'Resumo F01', linhas_lidas: 4, soma: 8 }, null, 2)),
    };
    const err = h('div', { class: 'note bad hide', role: 'alert' });
    const go = h('button', { class: 'btn primary' }, 'Pedir aprovação');
    const m = openModal({ title: 'Nova ação simulada', body: h('div', {}, h('div', { class: 'note warn', style: { marginBottom: '10px' } }, 'Só destinos simulado://… e só dados fictícios. Nada é enviado para fora.'), field('Operação', f.op), field('Destino', f.dest), field('Payload (JSON)', f.payload), err),
      actions: [h('button', { class: 'btn', onclick: () => m.close() }, 'Cancelar'), go] });
    go.addEventListener('click', () => busy(go, async () => {
      try {
        let payload; try { payload = JSON.parse(f.payload.value); } catch { throw new ApiError(400, { error: { message: 'Payload não é JSON válido.' } }); }
        await post(`${W()}/intents`, { operation: f.op.value, destination: f.dest.value, payload, idempotency_key: `ui-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`, task_id: taskId });
        toast('Pedido criado: aguarda a tua decisão.'); m.close(); await loadWorld(); location.hash = '#/trabalho/aprovacoes'; tick(true);
      } catch (e) { err.textContent = errMsg(e); err.classList.remove('hide'); }
    }));
  }
  const onIntent = (e) => openIntentForm(e.detail?.taskId);
  window.addEventListener('village:new-intent', onIntent);

  paintTabs(); tick(true);
  void designOnly; void pref; void STATE_PT; void avatarEl; void debounce;
  return { tick: () => tick(false), destroy: () => window.removeEventListener('village:new-intent', onIntent) };
}
