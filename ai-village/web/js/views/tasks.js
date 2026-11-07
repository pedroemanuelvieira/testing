// Tarefas: formulário (delegação), detalhe com tentativas/prova/histórico, e visualizador de prova.
import { h, field, openModal, toast, stateBadge, STATE_PT, fmtTime, fmtShort, busy, confirmDialog, promptDialog, selectDialog } from '../ui.js';
import { get, post, ApiError } from '../api.js';
import { S, W, agents, agentById, capById, designOnly, loadWorld } from '../state.js';
import { avatarEl, shortHash, modeTag } from '../components.js';

const errMsg = (e) => (e instanceof ApiError ? e.message : 'Falhou. Tenta de novo.');

function parseHeader(text) {
  const first = (text || '').replace(/^﻿/, '').split(/\r?\n/, 1)[0] || '';
  const delim = [',', ';', '\t'].map((d) => [d, first.split(d).length]).sort((a, b) => b[1] - a[1])[0][0];
  return first.split(delim).map((s) => s.trim().replace(/^"|"$/g, '')).filter(Boolean);
}

export function openTaskForm({ agentId, capability, title, conversationId, parentTaskId, projectId, onDone } = {}) {
  const caps = (S.overview?.capabilities || []);
  const form = {
    title: h('input', { type: 'text', maxLength: 160, value: title || '', 'data-autofocus': '', required: true }),
    objective: h('textarea', { maxLength: 1500, placeholder: 'O que deve ficar feito e como saber que está bom?' }),
    capability: h('select', {}, h('option', { value: '' }, 'Trabalho manual (sem executor — registas o resultado com nota)'),
      caps.map((c) => h('option', { value: c.id, selected: c.id === capability }, `${c.label}${c.auto_execute ? ' ⚙ executa no worker' : ''}`))),
    agent: h('select', {}),
    priority: h('select', {}, [1, 2, 3, 4, 5].map((p) => h('option', { value: p, selected: p === 3 }, `${p}${p === 1 ? ' (mais alta)' : p === 5 ? ' (mais baixa)' : ''}`))),
    project: h('select', {}, h('option', { value: '' }, '— sem projeto —')),
    by: h('select', {}, h('option', { value: '' }, 'Pedro (direto)'), agents().filter((a) => a.lifecycle_status === 'active').map((a) => h('option', { value: a.id }, `${a.display_name} (delega em nome de…)`))),
    csv: h('textarea', { placeholder: 'registo,grupo,quantidade\nS01,A,2\n…', style: { fontFamily: 'var(--mono)', minHeight: '110px' }, spellcheck: false }),
    file: h('input', { type: 'file', accept: '.csv,text/csv,text/plain' }),
    col: h('select', {}),
  };
  const csvBox = h('div', {},
    h('div', { class: 'note warn', style: { marginBottom: '10px' } }, 'Só dados FICTÍCIOS/sintéticos (regra D1). Se detetarmos emails, IBAN, NIF, cartões ou credenciais, o ficheiro é recusado e nada é guardado.'),
    field('Ficheiro CSV (UTF-8, até 1 MB / 10 000 linhas)', form.file), field('…ou cola o conteúdo', form.csv),
    h('div', { class: 'field', 'data-for': 'csv.validate' }, h('label', {}, 'Coluna numérica a somar'), form.col));

  const refreshAgents = () => {
    const cap = caps.find((c) => c.id === form.capability.value);
    const cur = form.agent.value || agentId;
    form.agent.replaceChildren(...agents().filter((a) => a.lifecycle_status === 'active' && (!cap?.auto_execute || a.capability_ids.includes(cap.id)))
      .map((a) => h('option', { value: a.id, selected: a.id === cur }, `${a.display_name} — ${a.title || 'agente'}${a.activity_status === 'ocupado' ? ' (ocupado)' : ''}`)));
    csvBox.classList.toggle('hide', !cap?.needs_input);
    csvBox.querySelector('[data-for="csv.validate"]').classList.toggle('hide', cap?.id !== 'csv.validate');
    hint.textContent = cap ? (cap.auto_execute ? 'Executa no worker do backend e devolve relatório + prova.' : 'Sem executor automático: ficará atribuída e registas tu o resultado, com nota (prova manual).') : 'Trabalho manual: registas o resultado com nota (prova manual).';
  };
  const hint = h('span', { class: 'hint' });
  const loadCols = (text) => {
    const cols = parseHeader(text);
    form.col.replaceChildren(...cols.map((c, i) => h('option', { value: c, selected: /quant|valor|total|qtd|soma/i.test(c) || (i === cols.length - 1 && !cols.some((x) => /quant|valor|total|qtd|soma/i.test(x))) }, c)));
  };
  form.capability.addEventListener('change', refreshAgents);
  form.file.addEventListener('change', async () => {
    const f = form.file.files[0]; if (!f) return;
    if (f.size > 1_000_000) { toast('Ficheiro acima de 1 MB.', 'error'); form.file.value = ''; return; }
    form.csv.value = await f.text(); loadCols(form.csv.value);
    if (!form.title.value) form.title.value = `Validar ${f.name}`;
  });
  form.csv.addEventListener('input', () => loadCols(form.csv.value));
  get(`${W()}/projects`).then((ps) => {
    form.project.append(...ps.map((p) => h('option', { value: p.id, selected: p.id === projectId }, `${p.number ? `${p.number} · ` : ''}${p.title}`)));
  }).catch(() => {});
  if (agentId) form.agent.value = agentId;
  refreshAgents();

  const err = h('div', { class: 'note bad hide', role: 'alert' });
  const submit = h('button', { class: 'btn primary' }, 'Criar tarefa');
  const m = openModal({
    title: parentTaskId ? 'Delegar subtarefa' : 'Nova tarefa', wide: true,
    body: h('div', {}, field('Título', form.title), field('Objetivo', form.objective),
      h('div', { class: 'grid2' }, field('Capacidade', form.capability, null), field('Atribuir a', form.agent)), hint,
      h('div', { class: 'grid2', style: { marginTop: '10px' } }, field('Prioridade proposta', form.priority, 'A prioridade final é aprovada por ti (D6).'),
        field('Criar em nome de', form.by, 'Se escolheres um agente, o servidor só aceita com permissão de delegação explícita.')),
      field('Projeto', form.project),
      csvBox, err),
    actions: [h('button', { class: 'btn', onclick: () => m.close() }, 'Cancelar'), submit],
  });
  submit.addEventListener('click', () => busy(submit, async () => {
    err.classList.add('hide');
    try {
      const cap = caps.find((c) => c.id === form.capability.value);
      const body = {
        title: form.title.value, objective: form.objective.value, capability: cap?.id || undefined, assigned_agent_id: form.agent.value || undefined,
        proposed_priority: Number(form.priority.value), delegated_by: form.by.value || undefined, parent_task_id: parentTaskId, conversation_id: conversationId, project_id: form.project.value || undefined,
      };
      if (cap?.needs_input) {
        if (!form.csv.value.trim()) throw new ApiError(400, { error: { message: 'Carrega ou cola o CSV sintético.' } });
        const art = await post(`${W()}/artifacts`, { name: form.file.files[0]?.name || 'colado.csv', kind: 'csv', media_type: 'text/csv', content: form.csv.value });
        body.input_refs = [art.id];
        if (cap.id === 'csv.validate') body.config = { numeric_column: form.col.value };
      }
      const t = await post(`${W()}/tasks`, body);
      toast(`Tarefa criada: ${t.title}`);
      m.close(); await loadWorld(); onDone?.(t);
    } catch (e) { err.textContent = errMsg(e); err.classList.remove('hide'); }
  }));
  return m;
}

// ---------- prova ----------
function metric(label, value, sub) { return h('div', { class: 'kpi' }, h('div', { class: 'v' }, String(value)), h('div', { class: 'l' }, label), sub ? h('div', { class: 's' }, sub) : null); }

function reportView(ev) {
  const r = ev.report;
  if (!r || typeof r !== 'object') return h('div', { class: 'note' }, ev.integrity === 'expurgado' ? 'Relatório expurgado pela política de retenção.' : 'Sem relatório.');
  if (ev.kind === 'csv_validation') {
    return h('div', {},
      h('div', { class: 'kpis' }, metric('Linhas lidas', r.rows_read), metric('Válidas (numérico)', r.valid_numeric), metric('Inválidas', r.invalid_numeric), metric('Duplicados exatos', r.duplicates_exact, 'além da 1.ª ocorrência'), metric(`Soma «${r.numeric_column}»`, r.sum_numeric, `sem deduplicar · dedup: ${r.sum_numeric_deduplicated}`)),
      r.formula_like_cells ? h('div', { class: 'note warn' }, `${r.formula_like_cells} célula(s) com aspeto de fórmula foram tratadas como TEXTO e nunca executadas.`) : null,
      r.issues?.length ? h('div', { class: 'table-wrap', style: { marginTop: '10px' } }, h('table', {}, h('thead', {}, h('tr', {}, ['Linha', 'Problema', 'Detalhe'].map((x) => h('th', {}, x)))),
        h('tbody', {}, r.issues.map((i) => h('tr', {}, h('td', {}, i.line), h('td', {}, i.code), h('td', {}, i.detail)))))) : null);
  }
  if (ev.kind === 'csv_profile') {
    return h('div', { class: 'table-wrap' }, h('table', {}, h('thead', {}, h('tr', {}, ['Coluna', 'Tipo', 'Preenchidos', 'Vazios', 'Distintos', 'Min', 'Máx', 'Média', 'Top'].map((x) => h('th', {}, x)))),
      h('tbody', {}, r.columns.map((c) => h('tr', {}, h('td', {}, c.name), h('td', {}, c.inferred_type), h('td', {}, c.non_empty), h('td', {}, c.empty), h('td', {}, c.distinct), h('td', {}, c.min ?? '—'), h('td', {}, c.max ?? '—'), h('td', {}, c.mean ?? '—'), h('td', {}, c.top_values.map((t) => `${t.value} (${t.count})`).join(', ')))))));
  }
  return h('pre', { class: 'json' }, JSON.stringify(r, null, 2));
}

export async function openEvidence(id) {
  let ev;
  try { ev = await get(`${W()}/evidence/${id}`); } catch (e) { toast(errMsg(e), 'error'); return; }
  const integ = ev.integrity === 'ok' ? h('span', { class: 'badge ok' }, '✔ integridade verificada') : ev.integrity === 'FALHA' ? h('span', { class: 'badge bad' }, '✖ FALHA de integridade') : h('span', { class: 'badge dim' }, ev.integrity);
  openModal({
    title: 'Prova (Evidence)', wide: true,
    body: h('div', { class: 'col' },
      h('div', { class: 'row' }, integ, h('span', { class: 'badge info' }, ev.kind), h('span', { class: `badge ${ev.mode === 'real_execution' ? 'cyan' : 'gold'}` }, ev.mode === 'real_execution' ? 'execução real no worker' : 'registo manual'), h('span', { class: 'badge dim' }, ev.classification)),
      reportView(ev),
      h('div', { class: 'cols2' },
        h('div', { class: 'card flat' }, h('h3', {}, 'Origem e digests'), h('table', {}, h('tbody', {},
          ...[['Executor', ev.executor_ref], ['Fonte', ev.source_ref], ['Input digest', ev.input_digest], ['Output digest', ev.output_digest], ['Captada em', fmtTime(ev.captured_at)], ['Retenção até', fmtShort(ev.retention_until)]]
            .map(([k, v]) => h('tr', {}, h('td', { class: 'muted' }, k), h('td', { class: 'mono', title: v || '' }, k.includes('digest') ? shortHash(v) : (v || '—'))))))),
        h('div', { class: 'card flat' }, h('h3', {}, 'Passos realmente executados'), h('ol', { class: 'timeline' }, ev.executed_steps.map((s) => h('li', {}, h('b', {}, s.step), h('span', { class: 'faint' }, ` · ${fmtTime(s.at)}`)))))),
      h('div', { class: 'card flat' }, h('h3', {}, 'Limitações'), h('ul', { style: { margin: 0, paddingLeft: '18px' } }, ev.limitations.map((l) => h('li', {}, l))))),
  });
}

// ---------- detalhe ----------
export async function openTaskDetail(id, onChange) {
  let t;
  try { t = await get(`${W()}/tasks/${id}`); } catch (e) { toast(errMsg(e), 'error'); return; }
  const agent = agentById(t.assigned_agent_id);
  const cap = capById(t.capability);
  const auto = Boolean(cap?.auto_execute);
  const m = openModal({ title: t.title, wide: true, body: h('div', {}), onClose: () => onChange?.() });
  const root = m.box.children[1];
  const reload = async () => { m.close(); await loadWorld(); await openTaskDetail(id, onChange); };
  const act = (btn, fn, ok) => btn.addEventListener('click', () => busy(btn, async () => { try { await fn(); if (ok) toast(ok); await reload(); } catch (e) { if (e instanceof ApiError && e.status === 0) return; toast(errMsg(e), 'error'); } }));

  const actions = h('div', { class: 'row' });
  const noteBox = h('textarea', { placeholder: 'Resultado / nota (fica como prova manual). Só dados fictícios.', maxLength: 4000 });
  const mk = (label, cls, fn, ok) => { const b = h('button', { class: `btn ${cls}` }, label); act(b, fn, ok); actions.append(b); return b; };
  const ask = async (q) => { const v = await promptDialog(q); if (v === null) throw new ApiError(0, { error: { message: 'cancelado' } }); return v; };
  if (t.state === 'assigned' && auto) {
    mk('⚙ Executar worker agora', 'primary', async () => { if (designOnly()) throw new ApiError(403, { error: { message: 'Mundo só de desenho.' } }); await post(`${W()}/worker/run`); });
    root.append(h('div', { class: 'note' }, S.overview?.worker?.online ? 'O worker (processo separado) vai apanhar esta tarefa dentro de segundos.' : 'O processo do worker não está a reportar. Podes executar agora: corre o mesmo código no backend.'));
  }
  if (t.state === 'assigned' && !auto) mk('Iniciar (manual)', 'primary', () => post(`${W()}/tasks/${id}/start-manual`), 'Tarefa iniciada: há agora uma tentativa ativa.');
  if (t.state === 'failed') mk('↻ Repetir (nova tentativa)', 'primary', () => post(`${W()}/tasks/${id}/retry`), 'Nova tentativa criada; a falha anterior fica registada.');
  if (t.state === 'blocked') mk('Desbloquear', '', async () => post(`${W()}/tasks/${id}/transition`, { to: 'pending', note: await ask('Motivo do desbloqueio (fica registado)') }));
  if (t.state === 'pending') mk('Atribuir…', '', async () => {
      const opts = agents().filter((a) => a.lifecycle_status === 'active' && (!auto || a.capability_ids.includes(t.capability))).map((a) => ({ value: a.id, label: `${a.display_name} — ${a.title}` }));
      const aid = await selectDialog('Atribuir a', opts); if (!aid) throw new ApiError(0, { error: { message: 'cancelado' } });
      await post(`${W()}/tasks/${id}/transition`, { to: 'assigned', assigned_agent_id: aid });
    });
  if (!['completed', 'cancelled'].includes(t.state)) {
    if (['assigned', 'pending', 'running', 'awaiting_approval'].includes(t.state)) mk('Bloquear', '', async () => post(`${W()}/tasks/${id}/transition`, { to: 'blocked', note: await ask('Motivo do bloqueio (fica registado)') }));
    mk('Cancelar tarefa', 'danger', async () => { if (!(await confirmDialog('Cancelar esta tarefa? Não volta a ser executada sem nova intenção.', { danger: true, okLabel: 'Cancelar tarefa' }))) throw new ApiError(0, { error: { message: 'Cancelado.' } }); await post(`${W()}/tasks/${id}/transition`, { to: 'cancelled', note: 'cancelada pelo dono' }); });
    const sub = h('button', { class: 'btn', onclick: () => { m.close(); openTaskForm({ parentTaskId: id, onDone: () => openTaskDetail(id, onChange) }); } }, '⤵ Delegar subtarefa');
    actions.append(sub);
  }
  if (t.state === 'running' && !auto) {
    root.append(field('Concluir com resultado', noteBox));
    const done = h('button', { class: 'btn primary' }, 'Concluir com nota'); act(done, () => post(`${W()}/tasks/${id}/complete-manual`, { note: noteBox.value }), 'Tarefa concluída com prova manual.');
    actions.append(done);
    actions.append(h('button', { class: 'btn sakura', onclick: () => { m.close(); window.dispatchEvent(new CustomEvent('village:new-intent', { detail: { taskId: id } })); } }, 'Propor ação simulada…'));
  }
  if (t.state === 'awaiting_approval') actions.append(h('button', { class: 'btn sakura', onclick: () => { m.close(); location.hash = '#/trabalho/aprovacoes'; } }, 'Ir às aprovações'));

  const prio = h('select', {}, [1, 2, 3, 4, 5].map((p) => h('option', { value: p, selected: p === (t.approved_priority ?? t.proposed_priority) }, p)));
  const prioBtn = h('button', { class: 'btn sm' }, 'Aprovar prioridade'); act(prioBtn, () => post(`${W()}/tasks/${id}/priority`, { approved_priority: Number(prio.value), expected_version: t.record_version }), 'Prioridade aprovada.');

  root.append(
    h('div', { class: 'row' }, stateBadge(t.state), auto ? h('span', { class: 'badge cyan' }, '⚙ worker') : h('span', { class: 'badge gold' }, 'manual'),
      agent ? h('span', { class: 'row' }, avatarEl(agent), h('span', {}, h('b', {}, agent.display_name), h('div', { class: 'faint' }, agent.title))) : h('span', { class: 'muted' }, 'sem agente'),
      t.error_code ? h('span', { class: 'badge bad' }, `erro: ${t.error_code}`) : null),
    t.objective ? h('p', { class: 'muted', style: { margin: '10px 0' } }, t.objective) : null,
    h('div', { class: 'cols2', style: { marginTop: '10px' } },
      h('div', { class: 'card flat' }, h('h3', {}, 'Delegação e prioridade'), h('table', {}, h('tbody', {},
        h('tr', {}, h('td', { class: 'muted' }, 'Origem'), h('td', {}, t.delegated_by ? `delegada por ${agentById(t.delegated_by)?.display_name || t.delegated_by}` : 'Pedro (direto)')),
        h('tr', {}, h('td', { class: 'muted' }, 'Tarefa-mãe'), h('td', {}, t.parent_task_id || '—')),
        h('tr', {}, h('td', { class: 'muted' }, 'Profundidade'), h('td', {}, t.depth)),
        h('tr', {}, h('td', { class: 'muted' }, 'Prioridade proposta'), h('td', {}, t.proposed_priority)),
        h('tr', {}, h('td', { class: 'muted' }, 'Prioridade aprovada'), h('td', {}, t.approved_priority ?? 'por aprovar')))),
        h('div', { class: 'row', style: { marginTop: '8px' } }, prio, prioBtn)),
      h('div', { class: 'card flat' }, h('h3', {}, 'Entradas'), t.inputs.length ? h('table', {}, h('tbody', {}, t.inputs.map((i) => h('tr', {}, h('td', {}, i.name || i.id), h('td', { class: 'mono', title: i.digest }, shortHash(i.digest)), h('td', { class: 'faint' }, i.purged_at ? 'expurgado' : `${i.size_bytes} B`))))) : h('span', { class: 'muted' }, 'Sem artefactos de entrada.'),
        t.kind !== 'manual' ? h('div', { class: 'faint', style: { marginTop: '6px' } }, `Config: ${JSON.stringify(t.config)}`) : null)),
    h('div', { style: { margin: '12px 0' } }, actions),
    h('div', { class: 'cols2' },
      h('div', { class: 'card flat' }, h('h3', {}, `Tentativas (${t.attempts.length})`), t.attempts.length ? h('div', { class: 'table-wrap' }, h('table', {}, h('thead', {}, h('tr', {}, ['#', 'Estado', 'Executor', 'Início', 'Fim', 'Erro'].map((x) => h('th', {}, x)))),
        h('tbody', {}, t.attempts.map((a) => h('tr', {}, h('td', {}, a.attempt_no), h('td', {}, h('span', { class: `badge ${a.state === 'succeeded' ? 'ok' : a.state === 'running' ? 'cyan' : a.state === 'failed' ? 'bad' : 'warn'}` }, a.state)), h('td', { class: 'mono' }, a.executor_ref), h('td', {}, fmtShort(a.started_at)), h('td', {}, fmtShort(a.ended_at)), h('td', {}, a.error_code || '—')))))) : h('span', { class: 'muted' }, 'Ainda sem tentativas de execução: nada a correr.')),
      h('div', { class: 'card flat' }, h('h3', {}, `Prova (${t.evidence.length})`), t.evidence.length ? h('div', { class: 'col' }, t.evidence.map((e) => h('button', { class: 'btn', onclick: () => openEvidence(e.id) }, `Ver prova · ${e.kind} · ${fmtShort(e.captured_at)}`))) : h('span', { class: 'muted' }, 'Sem prova ainda: a tarefa só conclui com resultado + prova.'))),
    t.children.length ? h('div', { class: 'card flat', style: { marginTop: '12px' } }, h('h3', {}, 'Subtarefas'), h('div', { class: 'col' }, t.children.map((c) => h('button', { class: 'tcard', onclick: () => { m.close(); openTaskDetail(c.id, onChange); } }, h('b', {}, c.title), stateBadge(c.state))))) : null,
    h('div', { class: 'card flat', style: { marginTop: '12px' } }, h('h3', {}, 'Histórico (auditoria)'), h('ol', { class: 'timeline' },
      t.history.map((e) => h('li', { class: e.result === 'denied' ? 'denied' : e.result === 'error' ? 'error' : '' }, h('b', {}, e.action), ' ', h('span', { class: 'faint' }, `${e.actor_ref} · ${fmtTime(e.occurred_at)}${e.reason_code ? ` · ${e.reason_code}` : ''}${e.result !== 'ok' ? ` · ${e.result}` : ''}`))))));
  void STATE_PT; void modeTag;
}
