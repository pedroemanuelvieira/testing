// Artefactos (entradas e relatórios) e Evidence (prova). Integridade por digest SHA-256 (RF08).
import { newId, sha256, clock, addDays, json, parseJson, HttpError, notFound, unprocessable } from '../lib/util.js';
import { classifyD1, d1Notice } from './d1.js';
import { CSV_LIMITS } from './csv.js';
import { getSettings } from './settings.js';
import { audit } from './audit.js';
import { mustGet } from './common.js';

export function createArtifact(w, actor, { name, kind = 'text', media_type = 'text/plain', content, classification = 'synthetic', skipD1 = false }) {
  if (typeof content !== 'string' || !content.length) throw new HttpError(400, 'content_required', 'Conteúdo obrigatório.');
  const size = Buffer.byteLength(content, 'utf8');
  const limit = kind === 'csv' ? CSV_LIMITS.maxBytes : 1_500_000;
  if (size > limit) throw new HttpError(413, 'too_large', `Acima do limite de ${limit} bytes.`);
  if (!skipD1) {
    const c = classifyD1(content);
    if (c.blocked) {
      // Parar o ramo: nada é guardado nem resumido. Só o motivo (categoria) vai para a auditoria.
      audit(w, { actor: actor.ref, action: 'ingest.blocked_d1', result: 'denied', reason: `d1:${c.categories.join(',')}` });
      throw new HttpError(422, 'd1_blocked', d1Notice(c), { categories: c.categories });
    }
  }
  const id = newId('art'), now = clock.iso();
  const st = getSettings(w);
  w.db.prepare(`INSERT INTO artifacts(id,world_id,account_id,name,kind,media_type,size_bytes,digest,content,classification,retention_until,created_at,updated_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)`).run(id, w.id, w.accountId, String(name || 'sem-nome').slice(0, 120), kind, media_type, size,
    sha256(content), content, classification, addDays(now, st.retention_content_days), now, now);
  audit(w, { actor: actor.ref, action: 'artifact.create', resource: id, digest: sha256(content) });
  return artifactMeta(w, id);
}

export function artifactMeta(w, id) {
  const a = mustGet(w, 'artifacts', id, 'Artefacto');
  const { content, account_id, world_id, ...meta } = a; void content; void account_id; void world_id;
  return { id: meta.id, name: meta.name, kind: meta.kind, media_type: meta.media_type, size_bytes: meta.size_bytes, digest: meta.digest, classification: meta.classification, retention_until: meta.retention_until, purged_at: meta.purged_at, created_at: meta.created_at };
}

// Devolve o conteúdo SÓ depois de verificar a integridade (digest recalculado).
export function readArtifact(w, id) {
  const a = mustGet(w, 'artifacts', id, 'Artefacto');
  if (a.purged_at || a.content === null) throw new HttpError(410, 'artifact_purged', 'Artefacto expurgado pela política de retenção.');
  if (sha256(a.content) !== a.digest) throw new HttpError(500, 'artifact_corrupt', 'Falha de integridade do artefacto.');
  return a;
}

export function createEvidence(w, e) {
  const id = newId('evd'), now = clock.iso();
  const st = getSettings(w);
  w.db.prepare(`INSERT INTO evidence(id,world_id,account_id,task_id,attempt_id,kind,input_digest,artifact_id,output_digest,executor_ref,
      executed_steps,captured_at,source_ref,source_version,classification,limitations,summary,mode,retention_until,created_at,updated_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`).run(id, w.id, w.accountId, e.task_id, e.attempt_id || null, e.kind, e.input_digest || null,
    e.artifact_id || null, e.output_digest || null, e.executor_ref, json(e.steps || []), e.captured_at || now, e.source_ref || null,
    e.source_version || null, e.classification || 'synthetic', json(e.limitations || []), json(e.summary || {}), e.mode || 'real_execution',
    addDays(now, st.retention_content_days), now, now);
  return id;
}

const evOut = (r) => ({
  ...r, executed_steps: parseJson(r.executed_steps, []), limitations: parseJson(r.limitations, []), summary: parseJson(r.summary, {}),
});

export function listEvidence(w, { taskId, limit = 100 } = {}) {
  const acc = w.accountId;
  const rows = taskId
    ? w.db.prepare('SELECT * FROM evidence WHERE world_id=? AND account_id=? AND task_id=? ORDER BY created_at DESC').all(w.id, acc, taskId)
    : w.db.prepare('SELECT * FROM evidence WHERE world_id=? AND account_id=? ORDER BY created_at DESC LIMIT ?').all(w.id, acc, Math.min(limit, 300));
  return rows.map(evOut);
}

// Prova + relatório, com verificação de integridade do artefacto de saída.
export function getEvidence(w, id) {
  const r = mustGet(w, 'evidence', id, 'Prova');
  const out = evOut(r);
  let report = null, integrity = 'sem_artefacto';
  if (r.artifact_id) {
    const a = w.db.prepare('SELECT content, digest, purged_at FROM artifacts WHERE id=? AND world_id=?').get(r.artifact_id, w.id);
    if (!a || a.purged_at || a.content === null) integrity = 'expurgado';
    else if (sha256(a.content) !== a.digest || (r.output_digest && a.digest !== r.output_digest)) integrity = 'FALHA';
    else { integrity = 'ok'; report = parseJson(a.content, a.content); }
  }
  return { ...out, report, integrity };
}

export function assertTaskHasEvidence(w, taskId) {
  const c = w.db.prepare('SELECT COUNT(*) c FROM evidence WHERE task_id = ? AND world_id = ?').get(taskId, w.id).c;
  if (!c) throw unprocessable('Conclusão exige resultado e prova (Evidence).', 'evidence_required');
}
