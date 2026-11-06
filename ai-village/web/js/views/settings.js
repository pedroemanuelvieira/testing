// Vista «Configuração»: organização (CRUD), permissões, definições/retenção, auditoria, capacidades e backup.
import { h, field, toast, busy, confirmDialog, fmtTime, fmtShort } from '../ui.js';
import { get, post, patch, ApiError } from '../api.js';
import { S, W, units, roles, agents, agentById, unitById, loadWorld } from '../state.js';
import { avatarEl } from '../components.js';
import { openAgentEditor, openUnitEditor, openRoleEditor, THEMES } from './editors.js';
import { openAgentDrawer } from './agent.js';

const errMsg = (e) => (e instanceof ApiError ? e.message : 'Falhou. Tenta de novo.');
const TABS = [['org', 'Organização'], ['perm', 'Permissões'], ['def', 'Definições'], ['audit', 'Auditoria'], ['caps', 'Capacidades'], ['backup', 'Backup']];

export function settingsView(root, sub = 'org') {
  let current = TABS.some(([id]) => id === sub) ? sub : 'org';
  const tabs = h('div', { class: 'tabs', role: 'tablist' });
  const pane = h('div', {});
  root.append(h('div', { class: 'view-head' }, h('div', {}, h('div', { class: 'kanji' }, '設定 · CONFIGURAÇÃO'), h('h1', {}, 'Organização e regras'))), tabs, pane);
  const paintTabs = () => tabs.replaceChildren(...TABS.map(([id, l]) => h('button', { role: 'tab', 'aria-selected': String(current === id), onclick: () => { current = id; location.hash = `#/config/${id}`; paintTabs(); paint(); } }, l)));
  const guard = (fn) => async (...a) => { try { await fn(...a); } catch (e) { if (e instanceof ApiError && e.status === 0) return; toast(errMsg(e), 'error'); } };

  const PANES = {
    org() {
      const repaint = async () => { await loadWorld(); paint(); };
      const unitRows = units().filter((u) => u.lifecycle_status === 'active').map((u) => h('tr', {}, h('td', {}, h('span', { style: { color: 'var(--vermilion)' } }, u.kanji), ' ', h('b', {}, u.name)), h('td', {}, THEMES.find(([v]) => v === u.theme)?.[1] || u.theme), h('td', {}, agentById(u.responsible_agent_id)?.display_name || '—'), h('td', {}, agents().filter((a) => a.org_unit_id === u.id).length),
        h('td', {}, h('div', { class: 'row' }, h('button', { class: 'btn sm', onclick: () => openUnitEditor(u, { onSaved: repaint }) }, 'Editar'), h('button', { class: 'btn sm danger', onclick: guard(async () => { if (!(await confirmDialog(`Arquivar a unidade «${u.name}»?`, { danger: true, okLabel: 'Arquivar' }))) return; await post(`${W()}/units/${u.id}/archive`, { expected_version: u.record_version }); toast('Unidade arquivada.'); repaint(); }) }, 'Arquivar')))));
      const roleRows = roles().filter((r) => r.lifecycle_status === 'active').map((r) => h('tr', {}, h('td', {}, h('b', {}, r.name)), h('td', {}, r.tier), h('td', { class: 'muted' }, r.mission), h('td', {}, h('div', { class: 'row' }, h('button', { class: 'btn sm', onclick: () => openRoleEditor(r, { onSaved: repaint }) }, 'Editar'), h('button', { class: 'btn sm danger', onclick: guard(async () => { if (!(await confirmDialog(`Arquivar a função «${r.name}»?`, { danger: true, okLabel: 'Arquivar' }))) return; await post(`${W()}/roles/${r.id}/archive`, { expected_version: r.record_version }); toast('Função arquivada.'); repaint(); }) }, 'Arquivar')))));
      const agentRows = agents().map((a) => h('tr', {}, h('td', {}, h('div', { class: 'row' }, avatarEl(a), h('div', {}, h('b', {}, a.display_name, a.orchestrator_flag ? ' ★' : ''), h('div', { class: 'faint' }, a.title)))), h('td', {}, unitById(a.org_unit_id)?.name || '—'), h('td', {}, agentById(a.manager_agent_id)?.display_name || '—'), h('td', { class: 'faint' }, a.capability_ids.length),
        h('td', {}, h('div', { class: 'row' }, h('button', { class: 'btn sm', onclick: () => openAgentEditor(a, { onSaved: repaint }) }, 'Editar'), h('button', { class: 'btn sm', onclick: () => openAgentDrawer(a.id, 'perfil') }, 'Abrir')))));
      const tbl = (heads, rows, empty) => rows.length ? h('div', { class: 'table-wrap' }, h('table', {}, h('thead', {}, h('tr', {}, heads.map((x) => h('th', {}, x)))), h('tbody', {}, rows))) : h('div', { class: 'empty' }, empty);
      return h('div', { class: 'col' },
        h('div', { class: 'note' }, 'Acrescentar funções, agentes e unidades não exige código. O servidor impede ciclos, um segundo orquestrador e arquivar agentes com tarefas ativas sem reencaminhar. CEO e diretores são cargos da app — não orquestradores.'),
        h('div', { class: 'card flat' }, h('div', { class: 'row' }, h('h3', { style: { margin: 0 } }, 'Unidades (edifícios)'), h('span', { class: 'grow' }), h('button', { class: 'btn sm primary', onclick: () => openUnitEditor(null, { onSaved: repaint }) }, '＋ Unidade')), tbl(['Unidade', 'Edifício', 'Responsável', 'Agentes', ''], unitRows, 'Sem unidades.')),
        h('div', { class: 'card flat' }, h('div', { class: 'row' }, h('h3', { style: { margin: 0 } }, 'Funções (cargos)'), h('span', { class: 'grow' }), h('button', { class: 'btn sm primary', onclick: () => openRoleEditor(null, { onSaved: repaint }) }, '＋ Função')), tbl(['Função', 'Nível', 'Missão', ''], roleRows, 'Sem funções.')),
        h('div', { class: 'card flat' }, h('div', { class: 'row' }, h('h3', { style: { margin: 0 } }, 'Agentes'), h('span', { class: 'grow' }), h('button', { class: 'btn sm primary', onclick: () => openAgentEditor(null, { onSaved: repaint }) }, '＋ Agente')), tbl(['Agente', 'Unidade', 'Reporta a', 'Capacidades', ''], agentRows, 'Sem agentes.')));
    },

    async perm() {
      const perms = await get(`${W()}/permissions`);
      const who = h('select', {}, agents().filter((a) => a.lifecycle_status === 'active').map((a) => h('option', { value: a.id }, a.display_name)));
      const scope = h('select', {}, h('option', { value: '*' }, 'Todos os agentes do mundo'), units().filter((u) => u.lifecycle_status === 'active').map((u) => h('option', { value: `unit:${u.id}` }, `Unidade: ${u.name}`)), agents().filter((a) => a.lifecycle_status === 'active').map((a) => h('option', { value: `agent:${a.id}` }, `Agente: ${a.display_name}`)));
      const depth = h('select', {}, [1, 2, 3].map((n) => h('option', { value: n }, `${n} nível(eis)`)));
      const add = h('button', { class: 'btn primary' }, 'Conceder delegação');
      add.addEventListener('click', () => busy(add, guard(async () => { await post(`${W()}/permissions`, { principal_id: who.value, resource_scope: scope.value, allowed_actions: ['delegate'], delegation_limit: Number(depth.value) }); toast('Permissão concedida.'); paint(); })));
      return h('div', { class: 'col' },
        h('div', { class: 'note' }, 'Negado por omissão. Só tu concedes. Um diretor/CEO não delega por título: precisa de uma permissão explícita para o destino e a profundidade. O servidor avalia isto em cada delegação.'),
        h('div', { class: 'card flat' }, h('h3', {}, 'Nova permissão de delegação'), h('div', { class: 'grid2' }, field('Quem delega', who), field('Para quem (escopo)', scope)), h('div', { class: 'row' }, field('Profundidade máxima', depth), add)),
        h('div', { class: 'card flat table-wrap' }, h('h3', {}, 'Permissões'), h('table', {}, h('thead', {}, h('tr', {}, ['Quem', 'Escopo', 'Profundidade', 'Concedida', 'Estado', ''].map((x) => h('th', {}, x)))),
          h('tbody', {}, perms.map((p) => h('tr', {}, h('td', {}, agentById(p.principal_id)?.display_name || p.principal_id),
            h('td', {}, p.resource_scope === '*' ? 'todos' : p.resource_scope.startsWith('unit:') ? `unidade ${unitById(p.resource_scope.slice(5))?.name || '?'}` : `agente ${agentById(p.resource_scope.slice(6))?.display_name || '?'}`), h('td', {}, p.delegation_limit), h('td', {}, fmtShort(p.created_at)),
            h('td', {}, p.revoked_at ? h('span', { class: 'badge bad' }, 'revogada') : h('span', { class: 'badge ok' }, 'ativa')),
            h('td', {}, p.revoked_at ? null : h('button', { class: 'btn sm danger', onclick: guard(async () => { await post(`${W()}/permissions/${p.id}/revoke`); toast('Revogada.'); paint(); }) }, 'Revogar'))))))));
    },

    async def() {
      const st = await get(`${W()}/settings`);
      const defs = [['retention_content_days', 'Retenção de conteúdo/provas (dias)', 'H08 proposta: 30'], ['retention_audit_days', 'Retenção da auditoria (dias)', 'H08 proposta: 90'], ['backup_retention_days', 'Retenção de backups (dias)', 'H08 proposta: 7'],
        ['approval_ttl_minutes', 'Validade das aprovações (min)', ''], ['lease_seconds', 'Lease do worker (s)', 'tempo até uma tentativa ser dada como perdida'], ['max_attempts', 'Máx. tentativas por tarefa', ''], ['max_active_tasks_per_agent', 'Máx. tarefas simultâneas por agente', ''], ['max_delegation_depth', 'Profundidade máx. de delegação', '']];
      const inputs = Object.fromEntries(defs.map(([k]) => [k, h('input', { type: 'number', min: 1, value: st[k] })]));
      const susp = h('input', { type: 'checkbox', checked: st.jobs_suspended });
      const save = h('button', { class: 'btn primary' }, 'Guardar definições');
      save.addEventListener('click', () => busy(save, guard(async () => { await patch(`${W()}/settings`, { ...Object.fromEntries(defs.map(([k]) => [k, Number(inputs[k].value)])), jobs_suspended: susp.checked }); toast('Definições guardadas.'); await loadWorld(); paint(); })));
      const sweep = h('button', { class: 'btn' }, 'Executar expurgo de retenção agora');
      sweep.addEventListener('click', () => busy(sweep, guard(async () => { const r = await post(`${W()}/retention/sweep`); toast(`Expurgo: ${r.artifacts} artefactos, ${r.messages} mensagens, ${r.audit_events} eventos de auditoria.`); })));
      return h('div', { class: 'col' }, h('div', { class: 'note' }, 'Valores por defeito = hipóteses H06/H07/H08 do documento de requisitos: propostas, reversíveis e a confirmar por ti.'),
        h('div', { class: 'card flat' }, h('div', { class: 'grid2' }, defs.map(([k, l, hint]) => field(l, inputs[k], hint))), h('label', { class: 'row' }, susp, 'Suspender jobs do worker (ex.: depois de um restauro)'), h('div', { class: 'row', style: { marginTop: '12px' } }, save, sweep)),
        h('div', { class: 'card flat' }, h('h3', {}, 'Limites do CSV (H06)'), h('p', { class: 'muted' }, `UTF-8, até ${st.csv_max_bytes.toLocaleString('pt-PT')} bytes e ${st.csv_max_rows.toLocaleString('pt-PT')} linhas de dados. Fórmulas nunca são executadas.`)));
    },

    async audit() {
      const [rows, ver] = await Promise.all([get(`${W()}/audit?limit=150`), get(`${W()}/audit/verify`)]);
      const verify = h('button', { class: 'btn' }, '🔍 Verificar integridade da cadeia'); verify.addEventListener('click', () => busy(verify, guard(async () => { const v = await get(`${W()}/audit/verify`); toast(v.ok ? `Cadeia íntegra (${v.checked} eventos).` : `ADULTERAÇÃO detetada no evento ${v.broken_at}!`, v.ok ? 'ok' : 'error'); })));
      return h('div', { class: 'col' }, h('div', { class: 'note ' + (ver.ok ? 'ok' : 'bad') }, ver.ok ? `Cadeia de hashes íntegra · ${ver.checked} eventos verificados.` : `Cadeia QUEBRADA no evento ${ver.broken_at}.`),
        h('div', { class: 'row' }, verify, h('span', { class: 'faint' }, 'Append-only; guarda ação, resultado e digest — nunca prompts nem conteúdo.')),
        h('div', { class: 'card flat table-wrap' }, h('table', {}, h('thead', {}, h('tr', {}, ['#', 'Quando', 'Quem', 'Ação', 'Recurso', 'Resultado', 'Motivo'].map((x) => h('th', {}, x)))),
          h('tbody', {}, rows.map((e) => h('tr', {}, h('td', { class: 'faint' }, e.event_sequence), h('td', {}, fmtShort(e.occurred_at)), h('td', { class: 'mono' }, e.actor_ref), h('td', {}, e.action), h('td', { class: 'mono' }, e.resource_ref || '—'),
            h('td', {}, h('span', { class: `badge ${e.result === 'ok' ? 'ok' : e.result === 'denied' ? 'bad' : 'warn'}` }, e.result)), h('td', { class: 'faint' }, e.reason_code || '')))))));
    },

    caps() {
      const caps = S.overview?.capabilities || [];
      return h('div', { class: 'col' },
        h('div', { class: 'card flat' }, h('h3', {}, '➕ Como acrescentar uma função nova'),
          h('ol', { style: { margin: 0, paddingLeft: '20px', display: 'grid', gap: '6px' } },
            h('li', {}, 'Organização → «＋ Função»: nome, missão, responsabilidades e limites (sem código).'),
            h('li', {}, 'Organização → «＋ Agente»: escolhe a função, a unidade e as capacidades. O retrato é editável.'),
            h('li', {}, 'Se o trabalho for manual, está pronto: cria tarefas e regista o resultado com prova.'),
            h('li', {}, 'Se precisas de execução automática, acrescenta uma entrada em server/modules/capabilities.js (com executor determinístico) e um teste — o worker passa a executá-la.'))),
        h('div', { class: 'card flat table-wrap' }, h('h3', {}, 'Catálogo de capacidades'), h('table', {}, h('thead', {}, h('tr', {}, ['Capacidade', 'Categoria', 'Execução', 'Entrada', 'Limitações'].map((x) => h('th', {}, x)))),
          h('tbody', {}, caps.map((c) => h('tr', {}, h('td', {}, h('b', {}, c.label), h('div', { class: 'mono faint' }, c.id)), h('td', {}, c.category), h('td', {}, c.auto_execute ? h('span', { class: 'badge cyan' }, '⚙ worker') : h('span', { class: 'badge gold' }, 'manual')), h('td', {}, c.needs_input ? 'ficheiro CSV' : '—'), h('td', { class: 'faint' }, c.limitations.join(' · ') || '—')))))));
    },

    async backup() {
      const list = await get('/api/admin/backups');
      const mk = h('button', { class: 'btn primary' }, '🔐 Criar backup cifrado agora');
      mk.addEventListener('click', () => busy(mk, guard(async () => { const r = await post('/api/admin/backup'); toast(`Backup criado: ${r.file}`); paint(); })));
      return h('div', { class: 'col' },
        h('div', { class: 'note' }, 'Backups AES-256-GCM com passphrase só no servidor (VILLAGE_BACKUP_PASSPHRASE). Contêm as BDs dos mundos; não contêm sessões nem o passcode. O restauro faz-se em pasta isolada e vazia, suspende os jobs e reaplica revogações/expurgos posteriores.'),
        h('div', { class: 'card flat' }, h('div', { class: 'row' }, mk), h('pre', { class: 'json', style: { marginTop: '10px' } }, '# restaurar num ambiente isolado e vazio\nVILLAGE_BACKUP_PASSPHRASE=… npm run restore -- <ficheiro.vbk> <pasta-destino> [pasta-data-com-tombstones]')),
        h('div', { class: 'card flat' }, h('h3', {}, 'Backups existentes'), list.length ? h('ul', { style: { margin: 0, paddingLeft: '18px' } }, list.map((f) => h('li', { class: 'mono' }, f))) : h('span', { class: 'muted' }, 'Ainda sem backups.')));
    },
  };

  async function paint() {
    pane.replaceChildren(h('div', { class: 'muted' }, 'A carregar…'));
    try { pane.replaceChildren(await PANES[current]()); } catch (e) { pane.replaceChildren(h('div', { class: 'note bad' }, errMsg(e))); }
  }
  paintTabs(); paint();
  void fmtTime;
  return { tick: () => {} };
}
