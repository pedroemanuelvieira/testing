// Helpers de validação e de escrita versionada (concorrência optimista, RF/§6).
import { HttpError, bad, conflict, notFound, clock } from '../lib/util.js';

export function str(v, name, { required = false, max = 500, min = 0 } = {}) {
  if (v === undefined || v === null || v === '') {
    if (required) throw bad(`Campo obrigatório: ${name}`, 'field_required', { field: name });
    return required ? '' : (v === undefined ? undefined : '');
  }
  if (typeof v !== 'string') throw bad(`Campo inválido (texto esperado): ${name}`, 'field_invalid', { field: name });
  const s = v.trim();
  if (s.length < min || (required && !s)) throw bad(`Campo obrigatório: ${name}`, 'field_required', { field: name });
  if (s.length > max) throw bad(`Campo demasiado longo (${max}): ${name}`, 'field_too_long', { field: name });
  return s;
}

export function int(v, name, { min = -Infinity, max = Infinity, required = false } = {}) {
  if (v === undefined || v === null || v === '') {
    if (required) throw bad(`Campo obrigatório: ${name}`, 'field_required', { field: name });
    return undefined;
  }
  const n = Number(v);
  if (!Number.isInteger(n) || n < min || n > max) throw bad(`Valor inválido: ${name}`, 'field_invalid', { field: name });
  return n;
}

export function oneOf(v, allowed, name, { required = false } = {}) {
  if (v === undefined || v === null) {
    if (required) throw bad(`Campo obrigatório: ${name}`, 'field_required', { field: name });
    return undefined;
  }
  if (!allowed.includes(v)) throw bad(`Valor inválido para ${name}`, 'field_invalid', { field: name, allowed });
  return v;
}

export function strList(v, name, { max = 30, itemMax = 200 } = {}) {
  if (v === undefined || v === null) return undefined;
  if (!Array.isArray(v)) throw bad(`Lista esperada: ${name}`, 'field_invalid', { field: name });
  if (v.length > max) throw bad(`Lista demasiado longa: ${name}`, 'field_too_long', { field: name });
  return v.map((x) => str(String(x), name, { required: true, max: itemMax }));
}

export function requireBody(body) {
  if (!body || typeof body !== 'object' || Array.isArray(body)) throw bad('Corpo JSON esperado', 'body_invalid');
  return body;
}

/**
 * UPDATE com controlo de versão. `expected` é obrigatório: um cliente com
 * versão antiga é rejeitado (409) em vez de sobrescrever (§6).
 */
export function updateVersioned(w, table, id, expected, sets) {
  if (expected === undefined || expected === null) {
    throw bad('expected_version é obrigatório para actualizar', 'expected_version_required');
  }
  const cols = Object.keys(sets);
  const sql = `UPDATE ${table} SET ${cols.map((c) => `${c} = ?`).join(', ')}${cols.length ? ',' : ''} updated_at = ?, record_version = record_version + 1
               WHERE id = ? AND world_id = ? AND record_version = ?`;
  const r = w.db.prepare(sql).run(...cols.map((c) => sets[c]), clock.iso(), id, w.id, Number(expected));
  if (Number(r.changes) === 0) {
    const row = w.db.prepare(`SELECT record_version FROM ${table} WHERE id = ? AND world_id = ?`).get(id, w.id);
    if (!row) throw notFound();
    throw conflict('Versão desactualizada: recarrega e tenta de novo.', 'stale_version', { current_version: row.record_version });
  }
}

// Objetos de dados/execução pertencem a uma CONTA dentro do mundo (CA18): outra conta recebe 404,
// sem revelar a existência. A estrutura organizacional (agentes, unidades, funções) é do mundo.
export const ACCOUNT_SCOPED = new Set(['tasks', 'conversations', 'messages', 'artifacts', 'connections', 'approvals', 'action_intents', 'evidence', 'execution_attempts']);
export function mustGet(w, table, id, label = 'Recurso') {
  const row = id ? w.db.prepare(`SELECT * FROM ${table} WHERE id = ? AND world_id = ?`).get(id, w.id) : null;
  if (!row || (ACCOUNT_SCOPED.has(table) && row.account_id && w.accountId && row.account_id !== w.accountId)) throw notFound(`${label} não encontrado`);
  return row;
}

export const mapConstraint = (e) => {
  if (e instanceof HttpError) return e;
  const msg = String(e?.message || e);
  if (/one_active_orchestrator|UNIQUE constraint failed: agents\.world_id/.test(msg)) {
    return conflict('Já existe um orquestrador activo neste mundo.', 'orchestrator_exists');
  }
  if (/UNIQUE constraint/.test(msg)) return conflict('Registo duplicado.', 'duplicate');
  if (/FOREIGN KEY/.test(msg)) return bad('Referência inválida.', 'invalid_reference');
  return e;
};

/**
 * Negações têm de ficar auditadas mesmo quando a transacção faz rollback.
 * `denial(err, fn)` anexa um efeito a executar DEPOIS do rollback (ex.: gravar o evento de auditoria).
 */
export function denial(err, after) { err.after = after; return err; }
export function runWithDenials(fn) {
  try { return fn(); }
  catch (e) {
    if (typeof e?.after === 'function') { try { e.after(); } catch { /* auditoria best-effort */ } }
    throw e;
  }
}
