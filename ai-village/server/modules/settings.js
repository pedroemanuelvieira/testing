// Definições por mundo (guardadas na tabela meta). Valores por defeito = hipóteses H06/H07/H08, reversíveis.
import { parseJson, json, bad } from '../lib/util.js';
import { int } from './common.js';
import { audit } from './audit.js';

export const DEFAULT_SETTINGS = {
  retention_content_days: 30,   // H08: conteúdo/provas
  retention_audit_days: 90,     // H08: auditoria minimizada
  backup_retention_days: 7,     // H08: backup cifrado
  approval_ttl_minutes: 15,
  lease_seconds: 60,
  max_attempts: 3,
  max_active_tasks_per_agent: 8,
  max_delegation_depth: 3,
  csv_max_bytes: 1_000_000,     // H06
  csv_max_rows: 10_000,
  jobs_suspended: false,
};

export function getSettings(w) {
  const row = w.db.prepare("SELECT value FROM meta WHERE key='settings'").get();
  return { ...DEFAULT_SETTINGS, ...parseJson(row?.value, {}) };
}

export function updateSettings(w, actor, patch) {
  const cur = getSettings(w);
  const next = { ...cur };
  const spec = {
    retention_content_days: [1, 3650], retention_audit_days: [1, 3650], backup_retention_days: [1, 365],
    approval_ttl_minutes: [1, 1440], lease_seconds: [5, 3600], max_attempts: [1, 10],
    max_active_tasks_per_agent: [1, 100], max_delegation_depth: [1, 6],
  };
  for (const [k, [min, max]] of Object.entries(spec)) {
    if (patch[k] !== undefined) next[k] = int(patch[k], k, { min, max, required: true });
  }
  if (patch.jobs_suspended !== undefined) next.jobs_suspended = Boolean(patch.jobs_suspended);
  if (!patch || typeof patch !== 'object') throw bad('Corpo inválido', 'body_invalid');
  w.db.prepare("INSERT OR REPLACE INTO meta(key,value) VALUES ('settings', ?)").run(json(next));
  audit(w, { actor: actor.ref, action: 'settings.update', resource: 'settings' });
  return next;
}
