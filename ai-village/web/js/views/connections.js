// Vista «Ligações»: inventário HONESTO. «Ligada» só com prova datada nesta app; o resto diz o que falta.
import { h, toast, busy, confirmDialog, fmtTime } from '../ui.js';
import { get, post, patch, ApiError } from '../api.js';
import { S, W, designOnly, loadWorld } from '../state.js';

const errMsg = (e) => (e instanceof ApiError ? e.message : 'Falhou. Tenta de novo.');
const ST = {
  planned: ['dim', 'Planeada · não verificada'], demo: ['gold', 'Demo (local)'], pending: ['warn', 'Pendente de verificação'], connected: ['ok', 'Ligada · verificada'],
  degraded: ['warn', 'Degradada · reverificar'], blocked: ['bad', 'Bloqueada'], disconnected: ['dim', 'Desligada'], revoked: ['bad', 'Revogada'],
};
const SCOPE_PT = { chat: 'conversa (chat)', read: 'leitura', write: 'escrita' };

export async function connectionsView(root) {
  root.append(h('div', { class: 'view-head' }, h('div', {}, h('div', { class: 'kanji' }, '繋 · LIGAÇÕES'), h('h1', {}, 'Contas, modelos e fontes'))));
  const body = h('div', { class: 'col' });
  root.append(body);
  let sig = '';

  const how = h('div', { class: 'card' }, h('h3', {}, '🔌 Como funciona a ligação das tuas contas'),
    h('ol', { style: { margin: 0, paddingLeft: '20px', display: 'grid', gap: '6px' } },
      h('li', {}, [h('b', {}, 'Mundo pessoal: '), 'só dados fictícios/sintéticos (regra D1). Contas reais entram por importação manual higienizada, nunca por sincronização automática.']),
      h('li', {}, [h('b', {}, 'Mundo profissional: '), 'nesta conta é só desenho. Dados, segredos e contas reais ficam exclusivamente no ambiente profissional aprovado (G3).']),
      h('li', {}, [h('b', {}, 'Segredos: '), 'ficam no servidor (variável de ambiente). Nunca aparecem aqui, em prompts, logs ou exportações.']),
      h('li', {}, [h('b', {}, 'Estado honesto: '), '«ligada» só depois de um diagnóstico read-only com prova datada. Ter uma subscrição de chat não dá API; um conector noutro ambiente não conta.']),
      h('li', {}, [h('b', {}, 'Modelo real (G2): '), 'define ANTHROPIC_API_KEY no servidor, verifica, concede o âmbito «chat» e cria uma conversa em modo real. Sem isto, tudo é DEMO.'])));

  function card(c) {
    const [cls, label] = ST[c.status] || ['dim', c.status];
    const row = h('div', { class: 'row' });
    const act = (txt, cls2, fn, ok) => { const b = h('button', { class: `btn sm ${cls2}` }, txt); b.addEventListener('click', () => busy(b, async () => { try { await fn(); if (ok) toast(ok); await refresh(true); await loadWorld(); } catch (e) { if (e instanceof ApiError && e.status === 0) return; toast(errMsg(e), 'error'); await refresh(true); } })); row.append(b); };
    if (c.adapter_implemented && !['revoked', 'disconnected'].includes(c.status)) act(c.status === 'connected' ? '↻ Reverificar' : '✔ Verificar ligação', 'primary', () => post(`${W()}/connections/${c.id}/verify`), 'Diagnóstico concluído.');
    for (const s of c.available_scopes) {
      if (c.status === 'connected' && c.provider_id === 'anthropic-api' || c.status === 'demo') {
        const on = c.granted_scopes.includes(s);
        act(`${on ? '✔ ' : ''}${SCOPE_PT[s] || s}`, on ? 'sakura' : '', () => patch(`${W()}/connections/${c.id}`, { granted_scopes: on ? c.granted_scopes.filter((x) => x !== s) : [...c.granted_scopes, s] }), on ? 'Âmbito retirado.' : 'Âmbito concedido.');
      }
    }
    if (['connected', 'degraded', 'pending'].includes(c.status)) {
      act('Desligar', '', async () => { if (!(await confirmDialog('Desligar? Novos pedidos e contexto são negados e as tarefas dependentes ficam bloqueadas.', { okLabel: 'Desligar' }))) throw new ApiError(0, {}); await post(`${W()}/connections/${c.id}/disconnect`, {}); }, 'Ligação desligada.');
      act('Revogar', 'danger', async () => { if (!(await confirmDialog('Revogar remove a referência do segredo e a prova, e bloqueia os trabalhos dependentes. A revogação no fornecedor é manual.', { danger: true, okLabel: 'Revogar' }))) throw new ApiError(0, {}); await post(`${W()}/connections/${c.id}/disconnect`, { revoke: true }); }, 'Ligação revogada.');
    }
    return h('article', { class: 'card', 'aria-label': c.label },
      h('div', { class: 'row' }, h('h3', { style: { margin: 0 } }, c.label), h('span', { class: `badge ${cls}` }, label), c.stale ? h('span', { class: 'badge warn' }, 'prova expirada') : null, c.secret_ref ? h('span', { class: 'chip mono', title: 'Referência (não é o segredo)' }, c.secret_ref) : null),
      h('p', { class: 'muted', style: { margin: '8px 0' } }, c.notes),
      h('table', {}, h('tbody', {},
        h('tr', {}, h('td', { class: 'muted' }, 'Âmbitos concedidos'), h('td', {}, c.granted_scopes.length ? c.granted_scopes.map((s) => h('span', { class: 'chip on', style: { marginRight: '4px' } }, SCOPE_PT[s] || s)) : 'nenhum')),
        h('tr', {}, h('td', { class: 'muted' }, 'Última prova'), h('td', {}, c.verified_at ? `${fmtTime(c.verified_at)}${c.proof?.http_status ? ` · HTTP ${c.proof.http_status}` : ''}` : 'sem prova nesta app')),
        c.proof?.error_code ? h('tr', {}, h('td', { class: 'muted' }, 'Último erro'), h('td', {}, c.proof.error_code)) : null,
        h('tr', {}, h('td', { class: 'muted' }, 'Adaptador'), h('td', {}, c.adapter_implemented ? 'implementado (v1)' : 'por implementar')))),
      row.children.length ? h('div', { style: { marginTop: '10px' } }, row) : null);
  }

  async function refresh(force) {
    const list = await get(`${W()}/connections`);
    const s = JSON.stringify(list); if (!force && s === sig) return; sig = s;
    const models = list.filter((c) => c.category === 'model'), sources = list.filter((c) => c.category !== 'model');
    body.replaceChildren(
      designOnly() ? h('div', { class: 'note warn' }, 'Mundo profissional (desenho): nenhuma ligação real é permitida nesta conta; a verificação está desativada.') : null,
      h('h2', {}, 'Modelos de conversa'), h('div', { class: 'cols2' }, models.map(card)),
      h('h2', { style: { marginTop: '10px' } }, 'Fontes de informação'), h('div', { class: 'cols2' }, sources.map(card)), how);
  }
  await refresh(true);
  return { tick: () => refresh(false) };
}
