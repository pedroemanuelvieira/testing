// Inventário honesto de ligações (RF09, CA19–CA21). Estado «ligada» exige PROVA datada nesta app/conta.
// Sem adaptador implementado → continua «planeada», por mais que o conector exista noutro ambiente.
import { clock, json, parseJson, newId, forbidden, notFound, unprocessable, bad, HttpError, redact } from '../lib/util.js';
import { tx } from '../lib/db.js';
import { str, requireBody, mustGet, strList } from './common.js';
import { audit } from './audit.js';
import * as anthropic from '../adapters/anthropic.js';
import { DEMO_PROVIDER_REF } from '../adapters/demo.js';
import { setState } from './tasks.js';
import { recordTombstone } from './retention.js';

export const PROVIDERS = {
  'demo-adapter': {
    label: 'Conversa demo (determinística)', category: 'model', scopes: ['chat'],
    note: 'Offline, sem modelo. Não é AI operacional.',
    async verify() { return { http_status: null, detail: 'self-check local', provider_ref: DEMO_PROVIDER_REF }; },
    resultingStatus: 'demo',
  },
  'anthropic-api': {
    label: 'Claude API (Anthropic)', category: 'model', scopes: ['chat'], secretEnv: 'ANTHROPIC_API_KEY',
    note: 'Requer chave de API (não a subscrição de chat). Chave só no servidor.',
    verify: (conn, deps) => anthropic.verify(conn, deps), resultingStatus: 'connected',
  },
  'google-drive': { label: 'Google Drive (Source_of_truth)', category: 'source', scopes: ['read'], note: 'Adaptador por implementar (OAuth mínimo, só leitura). O conector do ambiente de conceção não é transportável.' },
  'gmail-personal': { label: 'Gmail (pessoal)', category: 'source', scopes: ['read'], note: 'Planeada. Só leitura e só depois de higienização (D1).' },
  'calendar-personal': { label: 'Calendário (pessoal)', category: 'source', scopes: ['read'], note: 'Planeada.' },
  'notebooklm': { label: 'NotebookLM', category: 'source', scopes: ['read'], note: 'Sem API comprovada; apenas importação manual higienizada.' },
  'm365-tenant': { label: 'Microsoft 365 / SharePoint (tenant)', category: 'source', scopes: ['read'], note: 'Só desenho. Dados reais só no ambiente profissional aprovado (G3).' },
  'powerbi-fabric': { label: 'Power BI / Fabric', category: 'source', scopes: ['read'], note: 'Só desenho (G3). Modelos semânticos ficam no tenant.' },
  'azure-devops': { label: 'Azure DevOps', category: 'source', scopes: ['read', 'write'], note: 'Só desenho (G3).' },
  'copilot-studio': { label: 'Copilot Studio / Power Automate', category: 'source', scopes: ['read'], note: 'Só desenho (G3).' },
};

const view = (c) => {
  const proof = parseJson(c.proof, null);
  let status = c.status, stale = false;
  if (status === 'connected' && c.verified_at && (clock.now() - Date.parse(c.verified_at)) / 1000 > c.freshness_seconds) { status = 'degraded'; stale = true; }
  const p = PROVIDERS[c.provider_id];
  return {
    id: c.id, provider_id: c.provider_id, label: c.label, category: c.category, status, stored_status: c.status, stale, needs_reverification: stale || ['pending', 'degraded'].includes(c.status),
    external_account_alias: c.external_account_alias, granted_scopes: parseJson(c.granted_scopes, []), available_scopes: p?.scopes || [],
    secret_ref: c.secret_ref, verified_at: c.verified_at, proof, freshness_seconds: c.freshness_seconds, revoked_at: c.revoked_at,
    adapter_implemented: Boolean(p?.verify), notes: p?.note || c.notes, config: parseJson(c.config, {}), record_version: c.record_version,
  };
};

export function listConnections(w) { return w.db.prepare('SELECT * FROM connections WHERE world_id=? AND account_id=? ORDER BY category DESC, label').all(w.id, w.accountId).map(view); }
export function getConnection(w, id) { return view(mustGet(w, 'connections', id, 'Ligação')); }

export function seedConnections(w, ids) {
  const now = clock.iso();
  for (const pid of ids) {
    const p = PROVIDERS[pid];
    const status = pid === 'demo-adapter' ? 'demo' : 'planned';
    w.db.prepare(`INSERT INTO connections(id,world_id,account_id,provider_id,label,category,adapter_version,external_account_alias,status,secret_ref,freshness_seconds,notes,created_at,updated_at)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)`).run(newId('conn'), w.id, w.accountId, pid, p.label, p.category, p.verify ? '1' : null, null, status,
      p.secretEnv ? `env:${p.secretEnv}` : null, pid === 'demo-adapter' ? 31536000 : 86400, p.note || '', now, now);
  }
}

export function updateConnection(w, actor, id, body) {
  requireBody(body);
  const c = mustGet(w, 'connections', id, 'Ligação');
  if (['revoked'].includes(c.status)) throw unprocessable('Ligação revogada: não pode ser alterada.', 'revoked');
  const p = PROVIDERS[c.provider_id];
  const sets = {};
  if (body.external_account_alias !== undefined) sets.external_account_alias = str(body.external_account_alias, 'external_account_alias', { max: 80 }) || null;
  if (body.granted_scopes !== undefined) {
    const scopes = strList(body.granted_scopes, 'granted_scopes') || [];
    for (const s of scopes) if (!p?.scopes.includes(s)) throw bad(`Âmbito não suportado: ${s}`, 'invalid_scope');
    sets.granted_scopes = json(scopes);
  }
  if (body.config !== undefined && body.config && typeof body.config === 'object') {
    const cfg = {};
    if (body.config.model) cfg.model = str(body.config.model, 'model', { max: 80 });
    sets.config = json({ ...parseJson(c.config, {}), ...cfg });
  }
  if (body.freshness_seconds !== undefined) sets.freshness_seconds = Math.min(Math.max(Number(body.freshness_seconds) || 86400, 60), 31536000);
  const cols = Object.keys(sets);
  if (!cols.length) return view(c);
  if (body.expected_version !== undefined && Number(body.expected_version) !== c.record_version) throw new HttpError(409, 'stale_version', 'Versão desactualizada.');
  w.db.prepare(`UPDATE connections SET ${cols.map((k) => `${k}=?`).join(',')}, updated_at=?, record_version=record_version+1 WHERE id=?`).run(...cols.map((k) => sets[k]), clock.iso(), id);
  audit(w, { actor: actor.ref, action: 'connection.update', resource: id });
  return getConnection(w, id);
}

/** Diagnóstico read-only. Só uma verificação bem-sucedida (com prova) promove o estado. */
export async function verifyConnection(w, actor, id, deps = {}) {
  const c = mustGet(w, 'connections', id, 'Ligação');
  if (['revoked', 'disconnected'].includes(c.status)) throw unprocessable('Ligação desligada/revogada: volta a ligar antes de verificar.', 'not_active');
  const p = PROVIDERS[c.provider_id];
  if (!p?.verify) {
    audit(w, { actor: actor.ref, action: 'connection.verify', resource: id, result: 'denied', reason: 'adapter_not_implemented' });
    throw unprocessable('Ainda não existe adaptador implementado para este fornecedor: permanece «planeada» (nada foi ligado).', 'adapter_not_implemented');
  }
  const now = clock.iso();
  try {
    const proof = await p.verify(c, deps);
    w.db.prepare("UPDATE connections SET status=?, verified_at=?, proof=?, updated_at=?, record_version=record_version+1 WHERE id=?")
      .run(p.resultingStatus, now, json({ ...proof, checked_at: now, adapter: 'v1' }), now, id);
    audit(w, { actor: actor.ref, action: 'connection.verify', resource: id, reason: 'ok' });
    return getConnection(w, id);
  } catch (e) {
    const code = e.code || 'verify_failed';
    const next = c.status === 'connected' ? 'degraded' : 'pending';
    w.db.prepare("UPDATE connections SET status=?, proof=?, updated_at=?, record_version=record_version+1 WHERE id=?")
      .run(next, json({ error_code: code, checked_at: now }), now, id);
    audit(w, { actor: actor.ref, action: 'connection.verify', resource: id, result: 'error', reason: code });
    throw e instanceof HttpError ? new HttpError(e.status, e.code, redact(e.message)) : e;
  }
}

/**
 * Desligar/revogar (RF10/CA20): nega novas chamadas e contexto, bloqueia jobs dependentes,
 * invalida segredo-referência/prova e regista tombstone para o restauro não ressuscitar acesso.
 */
export function disconnect(w, actor, id, { revoke = false } = {}) {
  if (actor.type !== 'owner') throw forbidden('Só o dono desliga ligações.', 'owner_only');
  mustGet(w, 'connections', id, 'Ligação');
  const result = tx(w.db, () => {
    const now = clock.iso();
    w.db.prepare("UPDATE connections SET status=?, revoked_at=?, secret_ref=CASE WHEN ? THEN NULL ELSE secret_ref END, proof=NULL, verified_at=NULL, granted_scopes='[]', updated_at=?, record_version=record_version+1 WHERE id=?")
      .run(revoke ? 'revoked' : 'disconnected', now, revoke ? 1 : 0, now, id);
    let blocked = 0;
    for (const t of w.db.prepare("SELECT * FROM tasks WHERE world_id=? AND state IN ('pending','assigned','running','awaiting_approval')").all(w.id)) {
      if (parseJson(t.config, {}).connection_id !== id) continue;
      w.db.prepare("UPDATE execution_attempts SET state='cancelled', ended_at=?, updated_at=?, error_code='connection_revoked' WHERE task_id=? AND state='running'").run(now, now, t.id);
      setState(w, t, 'blocked', { error_code: 'connection_revoked' }, { skipEdges: true });
      blocked++;
    }
    const convs = w.db.prepare("UPDATE conversations SET model_binding_ref=NULL, updated_at=? WHERE model_binding_ref=?").run(now, id);
    audit(w, { actor: actor.ref, action: revoke ? 'connection.revoke' : 'connection.disconnect', resource: id, reason: `blocked_tasks:${blocked}` });
    return { blocked_tasks: blocked, unbound_conversations: Number(convs.changes) };
  });
  recordTombstone(w, { object_type: 'connection', object_id: id, kind: revoke ? 'revoked' : 'disconnected' });
  return { ...result, connection: getConnection(w, id), remote_revocation: 'manual: revoga a chave/consentimento no fornecedor; a app bloqueou localmente.' };
}

export function activeModelConnection(w, id) {
  let c = null;
  try { c = id ? mustGet(w, 'connections', id) : null; } catch { c = null; }
  if (!c) return null;
  const v = view(c);
  return { row: c, view: v, usable: v.status === 'connected' && v.granted_scopes.includes('chat') };
}
