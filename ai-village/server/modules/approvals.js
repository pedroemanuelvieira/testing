// Ações consequentes: ActionIntent → Approval → execução SIMULADA (RF06, RF07).
// Nesta fase não existe saída de rede: o "efeito" é um registo interno (H09).
// Garantias: aprovação exata (digest + versão + conta + mundo + destino), uso único e atómico,
// revogação/expiração/alteração invalidam, retry devolve o resultado existente.
import { newId, clock, addMs, digestOf, json, parseJson, bad, conflict, forbidden, notFound, unprocessable } from '../lib/util.js';
import { tx } from '../lib/db.js';
import { str, requireBody, mustGet, denial, runWithDenials } from './common.js';
import { audit } from './audit.js';
import { classifyD1, d1Notice } from './d1.js';
import { getSettings } from './settings.js';
import { setState } from './tasks.js';

export const OPERATIONS = {
  'simulated.send_report': { label: 'Enviar relatório (simulado)', destinationPrefix: 'simulado://' },
  'simulated.publish_note': { label: 'Publicar nota interna (simulado)', destinationPrefix: 'simulado://' },
};

function digestFor(w, { operation, destination, payload, version }) {
  return digestOf({ world: w.id, account: w.accountId, operation, destination, payload, payload_version: version });
}

function describe(op, destination, payload) {
  return `${OPERATIONS[op].label} → ${destination} · ${Object.keys(payload).length} campo(s)`;
}

// Expira lazy-mente aprovações vencidas (chamado antes de qualquer leitura/decisão).
export function expireDue(w) {
  const now = clock.iso();
  const due = w.db.prepare("SELECT id, intent_id FROM approvals WHERE state IN ('pending','approved') AND expires_at <= ?").all(now);
  for (const a of due) {
    w.db.prepare("UPDATE approvals SET state='expired', updated_at=?, record_version=record_version+1 WHERE id=? AND state IN ('pending','approved')").run(now, a.id);
    w.db.prepare("UPDATE action_intents SET state='invalidated', updated_at=?, record_version=record_version+1 WHERE id=? AND state IN ('pending_approval','approved')").run(now, a.intent_id);
    audit(w, { actor: 'system:clock', action: 'approval.expired', resource: a.id, approval: a.id, result: 'denied', reason: 'expired' });
    syncTaskAfterNegative(w, a.intent_id, 'approval_expired');
  }
  return due.length;
}

function syncTaskAfterNegative(w, intentId, code) {
  const i = w.db.prepare('SELECT task_id FROM action_intents WHERE id=?').get(intentId);
  if (!i?.task_id) return;
  const t = w.db.prepare('SELECT * FROM tasks WHERE id=?').get(i.task_id);
  if (t && t.state === 'awaiting_approval') setState(w, t, 'blocked', { error_code: code });
}

function newApproval(w, intent, ttlMinutes) {
  const id = newId('apr'), now = clock.iso();
  const op = OPERATIONS[intent.operation];
  w.db.prepare(`INSERT INTO approvals(id,world_id,account_id,intent_id,payload_version,payload_digest,summary,effect,state,requested_at,expires_at,created_at,updated_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)`).run(id, w.id, w.accountId, intent.id, intent.payload_version, intent.payload_digest,
    describe(intent.operation, intent.destination, parseJson(intent.payload, {})), 'SIMULAÇÃO — não envia nada para fora da app', 'pending', now,
    addMs(now, ttlMinutes * 60000), now, now);
  w.db.prepare("UPDATE action_intents SET approval_id=?, state='pending_approval', updated_at=?, record_version=record_version+1 WHERE id=?").run(id, now, intent.id);
  void op;
  return id;
}

export function createIntent(w, actor, body) {
  requireBody(body);
  expireDue(w);
  const operation = str(body.operation, 'operation', { required: true, max: 60 });
  if (!OPERATIONS[operation]) throw bad(`Operação não suportada: ${operation}`, 'unknown_operation', { allowed: Object.keys(OPERATIONS) });
  const destination = str(body.destination, 'destination', { required: true, max: 200 });
  if (!destination.startsWith(OPERATIONS[operation].destinationPrefix)) {
    throw unprocessable('Nesta fase só são permitidos destinos simulados (simulado://…). Sem saída externa.', 'external_destination_blocked');
  }
  const payload = body.payload && typeof body.payload === 'object' && !Array.isArray(body.payload) ? body.payload : null;
  if (!payload) throw bad('payload (objeto) obrigatório', 'payload_required');
  const c = classifyD1(JSON.stringify(payload));
  if (c.blocked) {
    audit(w, { actor: actor.ref, action: 'intent.blocked_d1', result: 'denied', reason: `d1:${c.categories.join(',')}` });
    throw unprocessable(d1Notice(c), 'd1_blocked');
  }
  const key = str(body.idempotency_key, 'idempotency_key', { required: true, max: 80 });
  const digest = digestFor(w, { operation, destination, payload, version: 1 });
  const prev = w.db.prepare('SELECT * FROM action_intents WHERE account_id=? AND operation=? AND idempotency_key=?').get(w.accountId, operation, key);
  if (prev) {
    if (prev.payload_digest !== digestFor(w, { operation, destination, payload, version: prev.payload_version })) {
      throw conflict('Mesma chave de idempotência com payload diferente.', 'idempotency_key_reuse');
    }
    return { ...intentView(w, prev.id), idempotent_replay: true };
  }
  if (body.task_id) mustGet(w, 'tasks', body.task_id, 'Tarefa');
  const id = newId('int'), now = clock.iso();
  tx(w.db, () => {
    w.db.prepare(`INSERT INTO action_intents(id,world_id,account_id,task_id,operation,destination,payload,payload_version,payload_digest,idempotency_key,effect,state,created_at,updated_at)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)`).run(id, w.id, w.accountId, body.task_id || null, operation, destination, json(payload), 1, digest, key, 'simulated', 'pending_approval', now, now);
    const intent = mustGet(w, 'action_intents', id);
    const aprId = newApproval(w, intent, getSettings(w).approval_ttl_minutes);
    audit(w, { actor: actor.ref, action: 'intent.create', resource: id, digest, approval: aprId });
    if (body.task_id) {
      const t = mustGet(w, 'tasks', body.task_id);
      if (t.state === 'running') setState(w, t, 'awaiting_approval');
    }
  });
  return intentView(w, id);
}

export function intentView(w, id) {
  const i = mustGet(w, 'action_intents', id, 'Intenção');
  const a = i.approval_id ? w.db.prepare('SELECT * FROM approvals WHERE id=?').get(i.approval_id) : null;
  return { ...i, payload: parseJson(i.payload, {}), result: parseJson(i.result, null), approval: a };
}

export function listApprovals(w, { state } = {}) {
  expireDue(w);
  const rows = w.db.prepare(`SELECT p.*, i.operation, i.destination, i.payload, i.task_id, i.state AS intent_state, i.result AS intent_result
                             FROM approvals p JOIN action_intents i ON i.id = p.intent_id
                             WHERE p.world_id=? AND p.account_id=? ${state ? 'AND p.state=?' : ''} ORDER BY p.requested_at DESC LIMIT 200`).all(...(state ? [w.id, w.accountId, state] : [w.id, w.accountId]));
  return rows.map((r) => ({ ...r, payload: parseJson(r.payload, {}), intent_result: parseJson(r.intent_result, null) }));
}

function needOwner(actor) { if (actor.type !== 'owner') throw forbidden('Só o dono decide aprovações.', 'owner_only'); }

function loadApproval(w, id) {
  expireDue(w);
  const a = mustGet(w, 'approvals', id, 'Aprovação');
  const i = mustGet(w, 'action_intents', a.intent_id, 'Intenção');
  return { a, i };
}

export function approve(w, actor, id) {
  needOwner(actor);
  return tx(w.db, () => {
    const { a, i } = loadApproval(w, id);
    if (a.state !== 'pending') throw unprocessable(`Aprovação em estado «${a.state}»: não pode ser aprovada.`, 'approval_not_pending');
    if (a.payload_digest !== i.payload_digest || a.payload_version !== i.payload_version) throw conflict('O payload mudou desde o pedido.', 'payload_changed');
    const now = clock.iso();
    w.db.prepare("UPDATE approvals SET state='approved', approver_id=?, decided_at=?, updated_at=?, record_version=record_version+1 WHERE id=? AND state='pending'").run(actor.id, now, now, id);
    w.db.prepare("UPDATE action_intents SET state='approved', updated_at=?, record_version=record_version+1 WHERE id=?").run(now, i.id);
    audit(w, { actor: actor.ref, action: 'approval.approve', resource: id, approval: id, digest: a.payload_digest });
    return mustGet(w, 'approvals', id);
  });
}

export function deny(w, actor, id, reason) {
  needOwner(actor);
  return tx(w.db, () => {
    const { a, i } = loadApproval(w, id);
    if (a.state !== 'pending') throw unprocessable(`Aprovação em estado «${a.state}»: não pode ser negada.`, 'approval_not_pending');
    const now = clock.iso();
    w.db.prepare("UPDATE approvals SET state='denied', approver_id=?, decided_at=?, reason=?, updated_at=?, record_version=record_version+1 WHERE id=?").run(actor.id, now, reason || null, now, id);
    w.db.prepare("UPDATE action_intents SET state='cancelled', updated_at=?, record_version=record_version+1 WHERE id=?").run(now, i.id);
    audit(w, { actor: actor.ref, action: 'approval.deny', resource: id, approval: id, result: 'denied', reason: reason || 'denied' });
    syncTaskAfterNegative(w, i.id, 'approval_denied');
    return mustGet(w, 'approvals', id);
  });
}

export function revoke(w, actor, id, reason) {
  needOwner(actor);
  return tx(w.db, () => {
    const { a, i } = loadApproval(w, id);
    if (!['pending', 'approved'].includes(a.state)) throw unprocessable(`Aprovação em estado «${a.state}»: não pode ser revogada.`, 'approval_not_revocable');
    const now = clock.iso();
    w.db.prepare("UPDATE approvals SET state='revoked', decided_at=?, reason=?, updated_at=?, record_version=record_version+1 WHERE id=?").run(now, reason || null, now, id);
    w.db.prepare("UPDATE action_intents SET state='invalidated', updated_at=?, record_version=record_version+1 WHERE id=? AND state IN ('pending_approval','approved')").run(now, i.id);
    audit(w, { actor: actor.ref, action: 'approval.revoke', resource: id, approval: id, result: 'denied', reason: reason || 'revoked' });
    syncTaskAfterNegative(w, i.id, 'approval_revoked');
    return mustGet(w, 'approvals', id);
  });
}

/** Alterar o payload cria nova versão/digest e invalida aprovações anteriores (CA10). */
export function changePayload(w, actor, intentId, payload) {
  needOwner(actor);
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) throw bad('payload (objeto) obrigatório', 'payload_required');
  const c = classifyD1(JSON.stringify(payload));
  if (c.blocked) throw unprocessable(d1Notice(c), 'd1_blocked');
  return tx(w.db, () => {
    expireDue(w);
    const i = mustGet(w, 'action_intents', intentId, 'Intenção');
    if (['executed', 'cancelled'].includes(i.state)) throw unprocessable('Esta intenção já terminou.', 'intent_final');
    const now = clock.iso();
    w.db.prepare("UPDATE approvals SET state='revoked', reason='payload_changed', decided_at=?, updated_at=?, record_version=record_version+1 WHERE intent_id=? AND state IN ('pending','approved')").run(now, now, intentId);
    const version = i.payload_version + 1;
    const digest = digestFor(w, { operation: i.operation, destination: i.destination, payload, version });
    w.db.prepare('UPDATE action_intents SET payload=?, payload_version=?, payload_digest=?, updated_at=?, record_version=record_version+1 WHERE id=?').run(json(payload), version, digest, now, intentId);
    const aprId = newApproval(w, mustGet(w, 'action_intents', intentId), getSettings(w).approval_ttl_minutes);
    audit(w, { actor: actor.ref, action: 'intent.payload_changed', resource: intentId, digest, approval: aprId });
    return intentView(w, intentId);
  });
}

/** Pede nova aprovação para uma intenção invalidada (ex.: expirou). */
export function requestApproval(w, actor, intentId) {
  needOwner(actor);
  return tx(w.db, () => {
    expireDue(w);
    const i = mustGet(w, 'action_intents', intentId, 'Intenção');
    if (i.state !== 'invalidated') throw unprocessable('Só intenções invalidadas precisam de novo pedido.', 'invalid_state');
    const aprId = newApproval(w, i, getSettings(w).approval_ttl_minutes);
    audit(w, { actor: actor.ref, action: 'approval.re_request', resource: intentId, approval: aprId });
    return intentView(w, intentId);
  });
}

/**
 * Consome a aprovação e executa a SIMULAÇÃO. Atómico: UPDATE condicional (um só vencedor) +
 * UNIQUE(intent_id) em action_effects. Retry/timeout devolve o resultado existente.
 */
export function execute(w, actor, approvalId) {
  needOwner(actor);
  return runWithDenials(() => tx(w.db, () => {
    const { a, i } = loadApproval(w, approvalId);
    if (i.state === 'executed' && a.state === 'consumed') {
      return { replay: true, intent: intentView(w, i.id), approval: a };
    }
    if (a.state !== 'approved') {
      throw denial(unprocessable(`Sem aprovação válida (estado «${a.state}»): nada foi executado.`, 'approval_not_valid'),
        () => audit(w, { actor: actor.ref, action: 'approval.execute', resource: approvalId, approval: approvalId, result: 'denied', reason: `state:${a.state}` }));
    }
    // Vinculação exata: conta, mundo, destino e payload têm de coincidir com o aprovado.
    const expected = digestFor(w, { operation: i.operation, destination: i.destination, payload: parseJson(i.payload, {}), version: a.payload_version });
    if (a.payload_digest !== expected || a.payload_version !== i.payload_version || a.account_id !== w.accountId || a.world_id !== w.id) {
      throw denial(conflict('A aprovação já não corresponde à ação (payload/destino/conta/mundo).', 'binding_mismatch'), () => {
        w.db.prepare("UPDATE approvals SET state='revoked', reason='binding_mismatch', updated_at=?, record_version=record_version+1 WHERE id=?").run(clock.iso(), approvalId);
        audit(w, { actor: actor.ref, action: 'approval.execute', resource: approvalId, approval: approvalId, result: 'denied', reason: 'binding_mismatch' });
      });
    }
    const now = clock.iso();
    const won = w.db.prepare("UPDATE approvals SET state='consumed', consumed_at=?, updated_at=?, record_version=record_version+1 WHERE id=? AND state='approved' AND expires_at > ?").run(now, now, approvalId, now);
    if (Number(won.changes) !== 1) throw conflict('A aprovação já foi consumida ou expirou.', 'approval_not_valid');
    const detail = { simulated: true, operation: i.operation, destination: i.destination, payload_digest: i.payload_digest, note: 'Nenhuma mensagem/publicação foi enviada: simulação interna.' };
    w.db.prepare('INSERT INTO action_effects(id,intent_id,world_id,simulated,external_calls,detail,created_at) VALUES (?,?,?,?,?,?,?)')
      .run(newId('eff'), i.id, w.id, 1, 0, json(detail), now);
    w.db.prepare("UPDATE action_intents SET state='executed', result=?, updated_at=?, record_version=record_version+1 WHERE id=?").run(json({ ...detail, executed_at: now }), now, i.id);
    audit(w, { actor: actor.ref, action: 'approval.execute', resource: approvalId, approval: approvalId, digest: i.payload_digest, reason: 'simulated' });
    if (i.task_id) {
      const t = w.db.prepare('SELECT * FROM tasks WHERE id=?').get(i.task_id);
      if (t?.state === 'awaiting_approval') setState(w, t, 'running');
    }
    return { replay: false, intent: intentView(w, i.id), approval: mustGet(w, 'approvals', approvalId) };
  }));
}
