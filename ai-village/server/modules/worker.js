// Worker durável: executa tarefas reais com leases, recuperação e prova (RF05, RF12, CA14).
// O browser nunca produz resultados oficiais — só este módulo (num processo à parte em produção).
import { clock, addMs, json, parseJson, newId, sha256 } from '../lib/util.js';
import { tx } from '../lib/db.js';
import { audit } from './audit.js';
import { CAPABILITIES } from './capabilities.js';
import { getSettings } from './settings.js';
import { openAttempt, setState } from './tasks.js';
import { createArtifact, createEvidence, readArtifact } from './artifacts.js';
import { kpis } from './bi.js';

const EXECUTABLE = Object.entries(CAPABILITIES).filter(([, c]) => c.executor).map(([id]) => id);
const WORKER_REF = (cap) => `worker:${cap}@1`;

/** Reserva a próxima tarefa executável (atribuída, agente activo). Transacção única = um só vencedor. */
export function claimNext(w) {
  const st = getSettings(w);
  if (st.jobs_suspended) return null;
  const ph = EXECUTABLE.map(() => '?').join(',');
  return tx(w.db, () => {
    const t = w.db.prepare(`SELECT t.* FROM tasks t JOIN agents a ON a.id = t.assigned_agent_id
      WHERE t.world_id = ? AND t.state = 'assigned' AND t.capability IN (${ph}) AND a.lifecycle_status = 'active'
      ORDER BY COALESCE(t.approved_priority, t.proposed_priority) ASC, t.created_at ASC LIMIT 1`).get(w.id, ...EXECUTABLE);
    if (!t) return null;
    const tries = w.db.prepare('SELECT COUNT(*) c FROM execution_attempts WHERE task_id=?').get(t.id).c;
    if (tries >= st.max_attempts) {
      setState(w, t, 'blocked', { error_code: 'max_attempts' }, { skipEdges: true });
      audit(w, { actor: 'worker', action: 'task.blocked', resource: t.id, result: 'denied', reason: 'max_attempts' });
      return null;
    }
    const attemptId = openAttempt(w, t, WORKER_REF(t.capability), { leaseSeconds: st.lease_seconds });
    setState(w, t, 'running');
    audit(w, { actor: 'worker', action: 'attempt.start', resource: t.id, reason: attemptId });
    return { task: t, attemptId };
  });
}

export function heartbeat(w, attemptId) {
  const st = getSettings(w);
  const now = clock.iso();
  w.db.prepare("UPDATE execution_attempts SET heartbeat_at=?, lease_expires_at=?, updated_at=? WHERE id=? AND state='running'")
    .run(now, addMs(now, st.lease_seconds * 1000), now, attemptId);
}

/**
 * Executa o executor da capacidade e grava resultado + prova NUMA transacção.
 * `fault` (só testes): simula crash antes de gravar → fica tentativa com lease por recuperar.
 */
export function executeAttempt(w, { task, attemptId }, { fault } = {}) {
  const cap = CAPABILITIES[task.capability];
  const steps = [];
  const step = (name) => steps.push({ step: name, at: clock.iso() });
  const config = parseJson(task.config, {});
  const inputIds = parseJson(task.input_refs, []);
  let inputDigest = null, text = null;
  try {
    step('claim_task');
    if (cap.needsInput) {
      step('read_input_verified');
      const art = readArtifact(w, inputIds[0]); // verifica digest antes de usar
      text = art.content; inputDigest = art.digest;
    }
    const result = cap.executor({ text, config, step, kpiSnapshot: () => kpis(w) });
    heartbeat(w, attemptId);
    if (fault === 'before_commit') throw new Error('FAULT_INJECTED_before_commit');
    step('write_report_and_evidence');
    return tx(w.db, () => {
      const reportJson = JSON.stringify(result.report);
      const art = createArtifact(w, { ref: 'worker' }, { name: `relatorio-${task.id}.json`, kind: 'report', media_type: 'application/json', content: reportJson, skipD1: true });
      const now = clock.iso();
      const updated = w.db.prepare("UPDATE execution_attempts SET state='succeeded', ended_at=?, updated_at=?, result_ref=?, record_version=record_version+1 WHERE id=? AND state='running'").run(now, now, art.id, attemptId);
      if (Number(updated.changes) !== 1) throw new Error('attempt_no_longer_running'); // cancelada entretanto
      createEvidence(w, {
        task_id: task.id, attempt_id: attemptId, kind: cap.taskKind, input_digest: inputDigest, artifact_id: art.id, output_digest: art.digest,
        executor_ref: WORKER_REF(task.capability), steps, source_ref: inputIds[0] || 'backend:db', source_version: inputDigest || art.digest,
        limitations: cap.limitations || [], summary: result.summary, mode: 'real_execution',
      });
      const cur = w.db.prepare('SELECT * FROM tasks WHERE id=?').get(task.id);
      setState(w, cur, 'completed', { result_refs: json([art.id]), error_code: null });
      audit(w, { actor: 'worker', action: 'task.completed', resource: task.id, digest: art.digest, reason: attemptId });
      return { ok: true, report: result.report };
    });
  } catch (e) {
    if (String(e.message).startsWith('FAULT_INJECTED')) throw e; // crash simulado: não limpa nada
    return failAttempt(w, task, attemptId, e);
  }
}

function failAttempt(w, task, attemptId, e) {
  const now = clock.iso();
  const code = e.code || 'executor_error';
  const message = String(e.message || e).slice(0, 300);
  tx(w.db, () => {
    const upd = w.db.prepare("UPDATE execution_attempts SET state='failed', ended_at=?, updated_at=?, error_code=?, error_message=?, record_version=record_version+1 WHERE id=? AND state='running'").run(now, now, code, message, attemptId);
    if (Number(upd.changes) !== 1) return;
    const cur = w.db.prepare('SELECT * FROM tasks WHERE id=?').get(task.id);
    if (cur.state === 'running') setState(w, cur, 'failed', { error_code: code });
    audit(w, { actor: 'worker', action: 'attempt.failed', resource: task.id, result: 'error', reason: code, correlation: attemptId });
  });
  return { ok: false, error_code: code, message };
}

/**
 * Recupera tentativas cujo lease expirou (worker morreu). Como as capacidades automáticas são
 * determinísticas e sem efeitos externos, é seguro voltar a pô-las em fila — com a tentativa
 * anterior conservada como 'abandoned'. Excedendo max_attempts, bloqueia para reconciliação.
 */
export function recoverExpired(w) {
  const now = clock.iso();
  const st = getSettings(w);
  const stale = w.db.prepare(`SELECT x.*, t.state task_state FROM execution_attempts x JOIN tasks t ON t.id = x.task_id
    WHERE x.world_id=? AND x.state='running' AND x.lease_expires_at IS NOT NULL AND x.lease_expires_at < ?`).all(w.id, now);
  let recovered = 0;
  for (const x of stale) {
    tx(w.db, () => {
      w.db.prepare("UPDATE execution_attempts SET state='abandoned', ended_at=?, updated_at=?, error_code='lease_expired', record_version=record_version+1 WHERE id=? AND state='running'").run(now, now, x.id);
      const t = w.db.prepare('SELECT * FROM tasks WHERE id=?').get(x.task_id);
      if (t.state !== 'running') return;
      const tries = w.db.prepare('SELECT COUNT(*) c FROM execution_attempts WHERE task_id=?').get(t.id).c;
      if (tries >= st.max_attempts) {
        setState(w, t, 'blocked', { error_code: 'recovery_needs_reconciliation' }, { skipEdges: true });
        audit(w, { actor: 'worker', action: 'attempt.recovery', resource: t.id, result: 'denied', reason: 'max_attempts_reconcile', correlation: x.id });
      } else {
        setState(w, t, 'assigned', { error_code: null }, { skipEdges: true });
        audit(w, { actor: 'worker', action: 'attempt.recovery', resource: t.id, reason: 'requeued', correlation: x.id });
      }
      recovered++;
    });
  }
  return recovered;
}

/** Um ciclo do worker: recupera, depois processa até `max` tarefas. */
export function runOnce(w, { max = 10, fault } = {}) {
  let done = 0;
  recoverExpired(w);
  for (let i = 0; i < max; i++) {
    const claim = claimNext(w);
    if (!claim) break;
    executeAttempt(w, claim, { fault });
    done++;
  }
  return done;
}
