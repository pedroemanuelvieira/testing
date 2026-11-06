// Retenção, expurgo e tombstones (RF10, RNF08, CA28). Hipótese H08: conteúdo 30d, auditoria 90d, backup 7d.
// Eliminação lógica ≠ expurgo: o expurgo apaga o CONTEÚDO e deixa tombstone com o motivo.
// Os tombstones também vão para um ficheiro lateral FORA dos backups, para um restauro
// reaplicar revogações/expurgos posteriores ANTES de dar acesso (CA15).
import { appendFileSync, mkdirSync, readFileSync, existsSync, readdirSync, statSync, unlinkSync } from 'node:fs';
import { join } from 'node:path';
import { clock, newId, addDays } from '../lib/util.js';
import { getSettings } from './settings.js';
import { audit, purgeAuditBefore } from './audit.js';

export function recordTombstone(w, { object_type, object_id, kind, reason }) {
  const at = clock.iso();
  w.db.prepare('INSERT INTO tombstones(id,object_type,object_id,kind,reason,occurred_at) VALUES (?,?,?,?,?,?)')
    .run(newId('tmb'), object_type, object_id, kind, reason || null, at);
  if (w.dataDir) {
    const dir = join(w.dataDir, 'tombstones');
    mkdirSync(dir, { recursive: true });
    appendFileSync(join(dir, `${w.id}.jsonl`), JSON.stringify({ object_type, object_id, kind, reason: reason || null, at }) + '\n');
  }
}

export function sweep(w) {
  const now = clock.iso();
  const st = getSettings(w);
  const res = { artifacts: 0, messages: 0, evidence: 0, audit_events: 0 };

  const arts = w.db.prepare('SELECT id FROM artifacts WHERE world_id=? AND purged_at IS NULL AND retention_until IS NOT NULL AND retention_until < ?').all(w.id, now);
  for (const a of arts) {
    w.db.prepare('UPDATE artifacts SET content=NULL, purged_at=?, updated_at=?, record_version=record_version+1 WHERE id=?').run(now, now, a.id);
    recordTombstone(w, { object_type: 'artifact', object_id: a.id, kind: 'purged', reason: 'retention' });
    res.artifacts++;
  }
  const convs = w.db.prepare('SELECT id FROM conversations WHERE world_id=? AND retention_until IS NOT NULL AND retention_until < ?').all(w.id, now);
  for (const c of convs) {
    const r = w.db.prepare("UPDATE messages SET content=NULL, meta='{}', state='purged', updated_at=? WHERE conversation_id=? AND state <> 'purged'").run(now, c.id);
    if (Number(r.changes)) { recordTombstone(w, { object_type: 'conversation', object_id: c.id, kind: 'purged', reason: 'retention' }); res.messages += Number(r.changes); }
  }
  const ev = w.db.prepare("UPDATE evidence SET summary='{}', updated_at=? WHERE world_id=? AND retention_until IS NOT NULL AND retention_until < ? AND summary <> '{}'").run(now, w.id, now);
  res.evidence = Number(ev.changes);

  const cutoff = addDays(now, -st.retention_audit_days);
  res.audit_events = purgeAuditBefore(w, cutoff);
  if (res.artifacts || res.messages || res.audit_events) audit(w, { actor: 'system:retention', action: 'retention.sweep', reason: JSON.stringify(res) });
  return res;
}

// Backups cifrados vencidos (nível da app, não do mundo).
export function sweepBackups(dataDir, days) {
  const dir = join(dataDir, 'backups');
  if (!existsSync(dir)) return 0;
  let n = 0;
  for (const f of readdirSync(dir)) {
    if (!f.endsWith('.vbk')) continue;
    const p = join(dir, f);
    if (clock.now() - statSync(p).mtimeMs > days * 86400000) { unlinkSync(p); n++; }
  }
  return n;
}

export function readSidecarTombstones(dataDir, worldId) {
  const f = join(dataDir, 'tombstones', `${worldId}.jsonl`);
  if (!existsSync(f)) return [];
  return readFileSync(f, 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l));
}
