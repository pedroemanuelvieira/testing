// Tarefas: criação, delegação, máquina de estados e tentativas (RF02, RF04, CA12).
// Todas as transições são validadas AQUI (servidor), nunca no browser.
import { newId, clock, digestOf, json, parseJson, bad, conflict, forbidden, notFound, unprocessable, HttpError } from '../lib/util.js';
import { tx } from '../lib/db.js';
import { str, int, requireBody, updateVersioned, mustGet, denial, runWithDenials } from './common.js';
import { audit } from './audit.js';
import { CAPABILITIES, kindForCapability, executableCapability } from './capabilities.js';
import { authorizeDelegation, OWNER } from './policy.js';
import { getSettings } from './settings.js';
import { createArtifact, createEvidence, assertTaskHasEvidence, listEvidence, artifactMeta } from './artifacts.js';
import { sha256 } from '../lib/util.js';

export const TERMINAL = new Set(['completed', 'cancelled']);
export const EDGES = {
  draft: ['pending', 'assigned', 'cancelled'],
  pending: ['assigned', 'blocked', 'cancelled'],
  assigned: ['running', 'pending', 'blocked', 'cancelled'],
  running: ['completed', 'failed', 'blocked', 'awaiting_approval', 'cancelled'],
  awaiting_approval: ['running', 'blocked', 'cancelled'],
  blocked: ['pending', 'cancelled'],
  failed: ['assigned', 'cancelled'],
  completed: [],
  cancelled: [],
};
// Destinos que a API pública NÃO aceita directamente: têm endpoints/rotinas próprias com prova.
const INTERNAL_ONLY = new Set(['running', 'completed', 'failed']);

const out = (t) => t && ({
  ...t,
  input_refs: parseJson(t.input_refs, []), acceptance_refs: parseJson(t.acceptance_refs, []),
  config: parseJson(t.config, {}), result_refs: parseJson(t.result_refs, []),
});

export function getTask(w, id) { return out(mustGet(w, 'tasks', id, 'Tarefa')); }

export function listTasks(w, { state, agent_id, kind, project_id, limit = 200 } = {}) {
  const where = ['world_id = ?', 'account_id = ?']; const args = [w.id, w.accountId];
  if (state) { where.push('state = ?'); args.push(state); }
  if (agent_id) { where.push('assigned_agent_id = ?'); args.push(agent_id); }
  if (kind) { where.push('kind = ?'); args.push(kind); }
  if (project_id) { where.push('project_id = ?'); args.push(project_id); }
  return w.db.prepare(`SELECT * FROM tasks WHERE ${where.join(' AND ')} ORDER BY updated_at DESC LIMIT ${Math.min(Number(limit) || 200, 500)}`)
    .all(...args).map(out);
}

export function taskDetail(w, id) {
  const t = getTask(w, id);
  const attempts = w.db.prepare('SELECT * FROM execution_attempts WHERE task_id=? ORDER BY attempt_no').all(id)
    .map((a) => ({ ...a, checkpoint: parseJson(a.checkpoint, {}) }));
  const children = w.db.prepare('SELECT id,title,state,assigned_agent_id FROM tasks WHERE parent_task_id=? ORDER BY created_at').all(id);
  const intents = w.db.prepare('SELECT id,operation,state,payload_digest FROM action_intents WHERE task_id=? ORDER BY created_at').all(id);
  const history = w.db.prepare(`SELECT event_sequence,actor_ref,action,result,reason_code,occurred_at FROM audit_events
                                WHERE resource_ref=? ORDER BY event_sequence ASC`).all(id);
  const inputs = t.input_refs.map((ref) => { try { return artifactMeta(w, ref); } catch { return { id: ref, missing: true }; } });
  return { ...t, attempts, children, intents, history, inputs, evidence: listEvidence(w, { taskId: id }) };
}

function activeLoad(w, agentId) {
  return w.db.prepare("SELECT COUNT(*) c FROM tasks WHERE assigned_agent_id=? AND state IN ('assigned','running','awaiting_approval')").get(agentId).c;
}

function resolveAssignee(w, id, capability) {
  const a = mustGet(w, 'agents', id, 'Agente atribuído');
  if (a.lifecycle_status !== 'active') throw unprocessable('O agente não está activo (desativado/arquivado): não recebe novos trabalhos.', 'agent_inactive');
  if (capability && executableCapability(capability)) {
    if (!parseJson(a.capability_ids, []).includes(capability)) {
      throw unprocessable(`O agente «${a.display_name}» não tem a capacidade ${capability}.`, 'agent_lacks_capability');
    }
  }
  return a;
}

/**
 * Cria uma tarefa. `actor` = owner (Pedro). Se `delegated_by` vier preenchido, o pedido é uma
 * delegação em nome desse agente e só passa se existir Permission explícita (negado por omissão).
 */
export function createTask(w, actor, body) {
  requireBody(body);
  const st = getSettings(w);
  const title = str(body.title, 'title', { required: true, max: 160 });
  const capability = body.capability ? str(body.capability, 'capability', { max: 60 }) : null;
  if (capability && !CAPABILITIES[capability]) throw bad(`Capacidade desconhecida: ${capability}`, 'unknown_capability');
  const spec = capability ? CAPABILITIES[capability] : null;
  const kind = capability ? kindForCapability(capability) : 'manual';
  const inputRefs = Array.isArray(body.input_refs) ? body.input_refs.map(String) : [];
  const config = body.config && typeof body.config === 'object' ? body.config : {};
  if (spec?.needsInput && inputRefs.length !== 1) throw unprocessable('Esta capacidade exige exactamente um artefacto de entrada.', 'input_required');
  if (capability === 'csv.validate' && typeof config.numeric_column !== 'string') throw unprocessable('Indica a coluna numérica (config.numeric_column).', 'config_invalid');
  for (const ref of inputRefs) {
    const a = w.db.prepare('SELECT id, purged_at FROM artifacts WHERE id=? AND world_id=?').get(ref, w.id);
    if (!a) throw bad('Artefacto de entrada inválido para este mundo.', 'invalid_reference', { field: 'input_refs' });
    if (a.purged_at) throw unprocessable('Artefacto de entrada expurgado.', 'artifact_purged');
  }

  let parent = null, depth = 0;
  if (body.parent_task_id) {
    parent = mustGet(w, 'tasks', body.parent_task_id, 'Tarefa-mãe');
    if (TERMINAL.has(parent.state)) throw unprocessable('A tarefa-mãe já está terminada.', 'parent_terminal');
    depth = parent.depth + 1;
    if (depth > st.max_delegation_depth) throw forbidden('Profundidade máxima de delegação excedida.', 'delegation_depth_exceeded');
  }

  const assignee = body.assigned_agent_id ? resolveAssignee(w, body.assigned_agent_id, capability) : null;
  const projectId = body.project_id ? mustGet(w, 'projects', body.project_id, 'Projeto').id : null;

  // Delegação por um agente: avaliada pela política, nunca pelo cargo.
  let permissionRef = null;
  if (body.delegated_by) {
    const delegator = mustGet(w, 'agents', body.delegated_by, 'Agente delegante');
    if (delegator.lifecycle_status !== 'active') throw forbidden('O delegante não está activo.', 'delegator_inactive');
    if (!assignee) throw unprocessable('Uma delegação precisa de um agente destino.', 'assignee_required');
    try { permissionRef = authorizeDelegation(w, delegator.id, assignee, Math.max(depth, 1)).id; }
    catch (e) {
      audit(w, { actor: `agent:${delegator.id}`, action: 'task.delegate', result: 'denied', reason: e.code, resource: assignee.id });
      throw e;
    }
  }
  if (assignee && activeLoad(w, assignee.id) >= st.max_active_tasks_per_agent) {
    throw new HttpError(429, 'concurrency_limit', 'O agente atingiu o limite de tarefas em simultâneo.');
  }

  const payload = { title, objective: body.objective || '', capability, assigned: assignee?.id || null, input_refs: inputRefs, config, parent: parent?.id || null, delegated_by: body.delegated_by || null, project: projectId };
  const payloadDigest = digestOf(payload);
  const idem = body.idempotency_key ? str(body.idempotency_key, 'idempotency_key', { max: 80 }) : null;
  if (idem) {
    const prev = w.db.prepare('SELECT * FROM tasks WHERE account_id=? AND idempotency_key=?').get(w.accountId, idem);
    if (prev) {
      if (prev.payload_digest !== payloadDigest) throw conflict('Mesma chave de idempotência com payload diferente.', 'idempotency_key_reuse');
      return { ...out(prev), idempotent_replay: true };
    }
  }

  const id = newId('task'), now = clock.iso();
  const state = body.draft ? 'draft' : assignee ? 'assigned' : 'pending';
  const priority = int(body.proposed_priority, 'proposed_priority', { min: 1, max: 5 }) ?? 3;
  tx(w.db, () => {
    w.db.prepare(`INSERT INTO tasks(id,world_id,account_id,title,objective,kind,capability,input_refs,config,expected_output,acceptance_refs,owner_id,
        assigned_agent_id,delegated_by,parent_task_id,scope_ref,proposed_priority,state,idempotency_key,payload_digest,depth,due_at,created_at,updated_at)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`).run(id, w.id, w.accountId, title, str(body.objective, 'objective', { max: 1500 }) || '',
      kind, capability, json(inputRefs), json(config), str(body.expected_output, 'expected_output', { max: 500 }) || '', json([]), actor.id,
      assignee?.id || null, body.delegated_by || null, parent?.id || null, permissionRef, priority, state, idem, payloadDigest, depth, body.due_at || null, now, now);
    if (projectId) w.db.prepare('UPDATE tasks SET project_id=? WHERE id=?').run(projectId, id);
    audit(w, { actor: body.delegated_by ? `agent:${body.delegated_by}` : actor.ref, action: body.delegated_by ? 'task.delegate' : 'task.create',
      resource: id, digest: payloadDigest, reason: permissionRef ? `perm:${permissionRef}` : undefined });
  });
  return getTask(w, id);
}

export function approvePriority(w, actor, id, body) {
  if (actor.type !== 'owner') throw forbidden('Só o dono aprova prioridades (D6).', 'owner_only');
  mustGet(w, 'tasks', id, 'Tarefa');
  const p = int(body.approved_priority, 'approved_priority', { min: 1, max: 5, required: true });
  tx(w.db, () => {
    updateVersioned(w, 'tasks', id, body.expected_version, { approved_priority: p });
    audit(w, { actor: actor.ref, action: 'task.priority_approved', resource: id, reason: `p${p}` });
  });
  return getTask(w, id);
}

function setState(w, t, to, extra = {}, { skipEdges = false } = {}) {
  if (!skipEdges && !EDGES[t.state].includes(to)) throw unprocessable(`Transição inválida: ${t.state} → ${to}`, 'invalid_transition', { from: t.state, to });
  const now = clock.iso();
  const sets = { state: to, ...extra };
  const cols = Object.keys(sets);
  const r = w.db.prepare(`UPDATE tasks SET ${cols.map((c) => `${c}=?`).join(',')}, updated_at=?, record_version=record_version+1
                          WHERE id=? AND world_id=? AND state=?`).run(...cols.map((c) => sets[c]), now, t.id, w.id, t.state);
  if (Number(r.changes) === 0) throw conflict('O estado da tarefa mudou entretanto.', 'stale_state');
}

/** Transição pedida via API. running/completed/failed são rejeitadas (têm caminho próprio com prova). */
export function transitionTask(w, actor, id, to, { note, assigned_agent_id, expected_version } = {}) {
  const t = mustGet(w, 'tasks', id, 'Tarefa');
  if (expected_version !== undefined && Number(expected_version) !== t.record_version) {
    throw conflict('Versão desactualizada.', 'stale_version', { current_version: t.record_version });
  }
  if (INTERNAL_ONLY.has(to)) {
    audit(w, { actor: actor.ref, action: 'task.transition', resource: id, result: 'denied', reason: `forbidden_target:${to}` });
    throw unprocessable(
      to === 'completed' ? 'Conclusão exige resultado e prova: usa o worker ou «concluir manualmente com nota».'
        : `O estado «${to}» só pode ser definido pela execução real (tentativa ativa).`, 'transition_not_allowed');
  }
  return runWithDenials(() => tx(w.db, () => {
    const cur = mustGet(w, 'tasks', id);
    if (!EDGES[cur.state].includes(to)) {
      throw denial(unprocessable(`Transição inválida: ${cur.state} → ${to}`, 'invalid_transition', { from: cur.state, to }),
        () => audit(w, { actor: actor.ref, action: 'task.transition', resource: id, result: 'denied', reason: `invalid:${cur.state}->${to}` }));
    }
    const extra = {};
    if (to === 'assigned') {
      const agentId = assigned_agent_id || cur.assigned_agent_id;
      if (!agentId) throw unprocessable('Indica o agente a atribuir.', 'assignee_required');
      const a = resolveAssignee(w, agentId, cur.capability);
      if (activeLoad(w, a.id) >= getSettings(w).max_active_tasks_per_agent) throw new HttpError(429, 'concurrency_limit', 'O agente atingiu o limite de tarefas em simultâneo.');
      extra.assigned_agent_id = a.id;
    }
    if (to === 'blocked' || (cur.state === 'blocked' && to === 'pending')) {
      if (!note) throw bad('Indica o motivo (nota) — fica registado.', 'note_required');
    }
    if (to === 'blocked') extra.error_code = 'blocked_by_owner';
    if (cur.state === 'blocked' && to === 'pending') extra.error_code = null;
    if (cur.state === 'awaiting_approval' && to === 'running') {
      const ok = w.db.prepare("SELECT COUNT(*) c FROM approvals p JOIN action_intents i ON i.id=p.intent_id WHERE i.task_id=? AND p.state IN ('approved','consumed')").get(id).c;
      if (!ok) throw unprocessable('Não é possível saltar a aprovação: ainda não existe aprovação válida.', 'approval_required');
    }
    if (to === 'awaiting_approval') {
      const pend = w.db.prepare("SELECT COUNT(*) c FROM approvals p JOIN action_intents i ON i.id=p.intent_id WHERE i.task_id=? AND p.state='pending'").get(id).c;
      if (!pend) throw unprocessable('Sem aprovação pendente ligada a esta tarefa.', 'approval_missing');
    }
    if (to === 'cancelled') cancelActiveAttempt(w, id, 'cancelled_by_owner');
    setState(w, cur, to, extra);
    audit(w, { actor: actor.ref, action: `task.${to}`, resource: id, reason: note ? `note:${note.slice(0, 80)}` : undefined });
    return getTask(w, id);
  }));
}

export function cancelActiveAttempt(w, taskId, code) {
  const now = clock.iso();
  w.db.prepare("UPDATE execution_attempts SET state='cancelled', ended_at=?, updated_at=?, error_code=?, record_version=record_version+1 WHERE task_id=? AND state='running'").run(now, now, code, taskId);
}

// ---- tentativas ----
export function nextAttemptNo(w, taskId) {
  return w.db.prepare('SELECT COALESCE(MAX(attempt_no),0)+1 n FROM execution_attempts WHERE task_id=?').get(taskId).n;
}

export function openAttempt(w, task, executorRef, { leaseSeconds } = {}) {
  const id = newId('att'), now = clock.iso();
  const prev = w.db.prepare('SELECT id FROM execution_attempts WHERE task_id=? ORDER BY attempt_no DESC LIMIT 1').get(task.id);
  const lease = leaseSeconds ? new Date(Date.parse(now) + leaseSeconds * 1000).toISOString() : null;
  w.db.prepare(`INSERT INTO execution_attempts(id,world_id,account_id,task_id,attempt_no,state,executor_ref,lease_expires_at,heartbeat_at,started_at,retry_of,created_at,updated_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)`).run(id, w.id, w.accountId, task.id, nextAttemptNo(w, task.id), 'running', executorRef, lease, now, now, prev?.id || null, now, now);
  return id;
}

/** Retry: cria nova tentativa ligada à anterior e conserva a falha (CA12). */
export function retryTask(w, actor, id) {
  return tx(w.db, () => {
    const t = mustGet(w, 'tasks', id, 'Tarefa');
    if (t.state !== 'failed') throw unprocessable('Só tarefas falhadas podem ser repetidas.', 'invalid_transition');
    if (!t.assigned_agent_id) throw unprocessable('A tarefa não tem agente atribuído.', 'assignee_required');
    resolveAssignee(w, t.assigned_agent_id, t.capability);
    const tries = w.db.prepare('SELECT COUNT(*) c FROM execution_attempts WHERE task_id=?').get(id).c;
    if (tries >= getSettings(w).max_attempts) throw unprocessable('Limite de tentativas atingido: bloqueia e investiga.', 'max_attempts');
    setState(w, t, 'assigned', { error_code: null });
    audit(w, { actor: actor.ref, action: 'task.retry', resource: id, reason: `attempt:${tries + 1}` });
    return getTask(w, id);
  });
}

// ---- trabalho manual (agentes sem executor): Pedro regista o resultado, com prova ----
export function startManual(w, actor, id) {
  return tx(w.db, () => {
    const t = mustGet(w, 'tasks', id, 'Tarefa');
    if (t.state !== 'assigned') throw unprocessable('Só tarefas atribuídas podem ser iniciadas.', 'invalid_transition');
    if (executableCapability(t.capability)) throw unprocessable('Esta tarefa é executada pelo worker; não é de trabalho manual.', 'auto_executor');
    const att = openAttempt(w, t, 'owner:manual');
    setState(w, t, 'running');
    audit(w, { actor: actor.ref, action: 'task.start_manual', resource: id, reason: att });
    return getTask(w, id);
  });
}

export function completeManual(w, actor, id, body) {
  requireBody(body);
  const note = str(body.note, 'note', { required: true, max: 4000 });
  return tx(w.db, () => {
    const t = mustGet(w, 'tasks', id, 'Tarefa');
    if (t.state !== 'running') throw unprocessable('A tarefa tem de estar em execução (tentativa activa).', 'invalid_transition');
    if (executableCapability(t.capability)) throw unprocessable('Esta tarefa é executada pelo worker.', 'auto_executor');
    const att = w.db.prepare("SELECT * FROM execution_attempts WHERE task_id=? AND state='running'").get(id);
    if (!att) throw unprocessable('Sem tentativa activa.', 'no_active_attempt');
    // O texto da nota passa pela guarda D1 (lança 422 e não guarda se detetar conteúdo proibido).
    const art = createArtifact(w, actor, { name: `nota-${id}.txt`, kind: 'note', content: note });
    const now = clock.iso();
    w.db.prepare("UPDATE execution_attempts SET state='succeeded', ended_at=?, updated_at=?, result_ref=? WHERE id=?").run(now, now, art.id, att.id);
    createEvidence(w, {
      task_id: id, attempt_id: att.id, kind: 'manual_note', artifact_id: art.id, output_digest: art.digest, executor_ref: 'owner:manual',
      steps: [{ step: 'owner_recorded_result', at: now }], mode: 'manual',
      limitations: ['Resultado registado manualmente pelo dono; não foi executado nem verificado por um agente de IA.'],
      summary: { note_chars: note.length },
    });
    setState(w, t, 'completed', { result_refs: json([art.id]) });
    audit(w, { actor: actor.ref, action: 'task.completed', resource: id, digest: art.digest, reason: 'manual' });
    return getTask(w, id);
  });
}

export function assertCompletable(w, taskId) { assertTaskHasEvidence(w, taskId); }
export { setState, activeLoad, resolveAssignee, sha256 };
