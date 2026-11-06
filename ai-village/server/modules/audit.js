// Auditoria append-only com cadeia de hashes (integridade verificável, RF08).
// Guarda apenas metadados e digests — nunca prompts, tokens ou conteúdo integral (minimização).
import { newId, sha256, canonical, clock, redact } from '../lib/util.js';

const GENESIS = '0'.repeat(64);

function anchor(db) {
  const row = db.prepare("SELECT value FROM meta WHERE key='audit_anchor'").get();
  return row ? JSON.parse(row.value) : { seq: 0, hash: GENESIS };
}

export function audit(w, e) {
  const db = w.db;
  const last = db.prepare('SELECT hash FROM audit_events ORDER BY event_sequence DESC LIMIT 1').get();
  const prev = last ? last.hash : anchor(db).hash;
  const row = {
    id: newId('aud'),
    world_id: w.id,
    actor_ref: e.actor || 'system',
    action: e.action,
    resource_ref: e.resource || null,
    result: e.result || 'ok',
    reason_code: e.reason ? redact(e.reason).slice(0, 120) : null,
    correlation_id: e.correlation || null,
    payload_digest: e.digest || null,
    approval_ref: e.approval || null,
    occurred_at: clock.iso(),
  };
  const hash = sha256(prev + canonical(row));
  db.prepare(`INSERT INTO audit_events(id,world_id,actor_ref,action,resource_ref,result,reason_code,correlation_id,payload_digest,approval_ref,prev_hash,hash,occurred_at)
              VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)`)
    .run(row.id, row.world_id, row.actor_ref, row.action, row.resource_ref, row.result, row.reason_code,
      row.correlation_id, row.payload_digest, row.approval_ref, prev, hash, row.occurred_at);
  return row.id;
}

export function verifyAuditChain(w) {
  const a = anchor(w.db);
  let prev = a.hash;
  let count = 0;
  const rows = w.db.prepare('SELECT * FROM audit_events ORDER BY event_sequence ASC').all();
  for (const r of rows) {
    const body = {
      id: r.id, world_id: r.world_id, actor_ref: r.actor_ref, action: r.action, resource_ref: r.resource_ref,
      result: r.result, reason_code: r.reason_code, correlation_id: r.correlation_id, payload_digest: r.payload_digest,
      approval_ref: r.approval_ref, occurred_at: r.occurred_at,
    };
    if (r.prev_hash !== prev || r.hash !== sha256(prev + canonical(body))) {
      return { ok: false, checked: count, broken_at: r.event_sequence };
    }
    prev = r.hash;
    count++;
  }
  return { ok: true, checked: count, anchor_seq: a.seq };
}

// Expurgo de auditoria antiga: guarda o hash do último evento removido como âncora.
export function purgeAuditBefore(w, isoCutoff) {
  const db = w.db;
  const last = db.prepare('SELECT event_sequence seq, hash FROM audit_events WHERE occurred_at < ? ORDER BY event_sequence DESC LIMIT 1').get(isoCutoff);
  if (!last) return 0;
  db.prepare("INSERT OR REPLACE INTO meta(key,value) VALUES ('audit_purge','1')").run();
  try {
    const r = db.prepare('DELETE FROM audit_events WHERE event_sequence <= ?').run(last.seq);
    db.prepare("INSERT OR REPLACE INTO meta(key,value) VALUES ('audit_anchor', ?)").run(JSON.stringify({ seq: last.seq, hash: last.hash }));
    return Number(r.changes);
  } finally {
    db.prepare("INSERT OR REPLACE INTO meta(key,value) VALUES ('audit_purge','0')").run();
  }
}

export function listAudit(w, { limit = 100, resource, before } = {}) {
  const lim = Math.min(Math.max(Number(limit) || 100, 1), 500);
  const where = [];
  const args = [];
  if (resource) { where.push('resource_ref = ?'); args.push(resource); }
  if (before) { where.push('event_sequence < ?'); args.push(Number(before)); }
  const sql = `SELECT event_sequence, actor_ref, action, resource_ref, result, reason_code, correlation_id, approval_ref, occurred_at
               FROM audit_events ${where.length ? 'WHERE ' + where.join(' AND ') : ''} ORDER BY event_sequence DESC LIMIT ${lim}`;
  return w.db.prepare(sql).all(...args);
}
