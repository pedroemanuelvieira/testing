// Políticas e permissões — avaliadas SEMPRE no servidor, negação por omissão (RF02, RNF03).
// O cargo organizacional não concede acesso; só Permission explícita concedida pelo dono (Pedro).
import { newId, clock, json, parseJson, forbidden, bad, notFound, unprocessable } from '../lib/util.js';
import { tx } from '../lib/db.js';
import { str, int, requireBody, mustGet } from './common.js';
import { audit } from './audit.js';

export const OWNER = { type: 'owner', id: 'owner:pedro', ref: 'owner:pedro' };
export const agentActor = (id) => ({ type: 'agent', id, ref: `agent:${id}` });

const out = (p) => ({ ...p, allowed_actions: parseJson(p.allowed_actions, []) });

export function listPermissions(w) {
  return w.db.prepare('SELECT * FROM permissions WHERE world_id=? ORDER BY created_at DESC').all(w.id).map(out);
}

export function grantPermission(w, actor, body) {
  requireBody(body);
  if (actor.type !== 'owner') throw forbidden('Só o dono pode conceder permissões.', 'owner_only'); // concessão não excede o concedente
  const principal = mustGet(w, 'agents', body.principal_id, 'Agente (principal)');
  const scope = str(body.resource_scope, 'resource_scope', { required: true, max: 80 });
  if (!/^(\*|agent:[a-z0-9_]+|unit:[a-z0-9_]+)$/.test(scope)) throw bad('Escopo inválido (usa *, agent:<id> ou unit:<id>).', 'invalid_scope');
  if (scope.startsWith('agent:')) mustGet(w, 'agents', scope.slice(6), 'Agente (escopo)');
  if (scope.startsWith('unit:')) mustGet(w, 'org_units', scope.slice(5), 'Unidade (escopo)');
  const actions = body.allowed_actions ?? ['delegate'];
  if (!Array.isArray(actions) || !actions.length || actions.some((a) => !['delegate'].includes(a))) throw bad('Ações permitidas inválidas.', 'invalid_actions');
  const id = newId('perm'), now = clock.iso();
  const limit = int(body.delegation_limit, 'delegation_limit', { min: 1, max: 6 }) ?? 1;
  return tx(w.db, () => {
    w.db.prepare(`INSERT INTO permissions(id,world_id,account_id,principal_id,resource_scope,allowed_actions,delegation_limit,valid_from,expires_at,granted_by,created_at,updated_at)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?)`).run(id, w.id, w.accountId, principal.id, scope, json(actions), limit, now, body.expires_at || null, actor.ref, now, now);
    audit(w, { actor: actor.ref, action: 'permission.grant', resource: id });
    return out(mustGet(w, 'permissions', id));
  });
}

export function revokePermission(w, actor, id) {
  if (actor.type !== 'owner') throw forbidden('Só o dono pode revogar permissões.', 'owner_only');
  mustGet(w, 'permissions', id, 'Permissão');
  return tx(w.db, () => {
    w.db.prepare('UPDATE permissions SET revoked_at = COALESCE(revoked_at, ?), updated_at = ?, record_version = record_version + 1 WHERE id = ?').run(clock.iso(), clock.iso(), id);
    audit(w, { actor: actor.ref, action: 'permission.revoke', resource: id });
    return out(mustGet(w, 'permissions', id));
  });
}

function scopeMatches(w, scope, assignee) {
  if (scope === '*') return true;
  if (scope === `agent:${assignee.id}`) return true;
  if (scope.startsWith('unit:')) return assignee.org_unit_id === scope.slice(5);
  return false;
}

/**
 * Pode `delegatorId` delegar a `assignee` a uma profundidade `depth`?
 * Devolve a permissão que permite — ou lança 403 com motivo (deny by default).
 */
export function authorizeDelegation(w, delegatorId, assignee, depth) {
  const now = clock.iso();
  const perms = w.db.prepare(`SELECT * FROM permissions WHERE world_id=? AND principal_id=? AND revoked_at IS NULL
                              AND valid_from <= ? AND (expires_at IS NULL OR expires_at > ?)`).all(w.id, delegatorId, now, now);
  const ok = perms.find((p) => parseJson(p.allowed_actions, []).includes('delegate') && scopeMatches(w, p.resource_scope, assignee) && depth <= p.delegation_limit);
  if (!ok) {
    const anyScope = perms.some((p) => scopeMatches(w, p.resource_scope, assignee));
    throw forbidden(anyScope ? 'Profundidade de delegação acima do limite concedido.' : 'Sem permissão de delegação para este destino (negado por omissão).',
      anyScope ? 'delegation_depth_exceeded' : 'delegation_denied');
  }
  return ok;
}
