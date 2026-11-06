// Backup cifrado (AES-256-GCM + scrypt) e restauro isolado com verificação (RNF04, RNF08, CA15).
//  - O backup contém as BDs dos mundos (não a BD de sessões/passcode).
//  - O restauro exige pasta de destino VAZIA, verifica digests e cadeia de auditoria,
//    SUSPENDE os jobs e reaplica tombstones/revogações posteriores ao backup ANTES de dar acesso.
import { createCipheriv, createDecipheriv, scryptSync, randomBytes } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync, readdirSync, existsSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { openDb, migrate, currentVersion } from './lib/db.js';
import { sha256, clock, digestOf, parseJson, json } from './lib/util.js';
import { verifyAuditChain } from './modules/audit.js';
import { readSidecarTombstones } from './modules/retention.js';

const MAGIC = Buffer.from('VBK1');
const KEY_OPTS = { N: 16384 };
const TABLES = ['accounts', 'org_units', 'roles', 'agents', 'agent_roles', 'permissions', 'conversations', 'messages', 'artifacts', 'tasks',
  'execution_attempts', 'evidence', 'connections', 'action_intents', 'approvals', 'action_effects', 'audit_events', 'tombstones'];

export function integritySnapshot(db) {
  const counts = {}, digests = {};
  for (const t of TABLES) {
    counts[t] = db.prepare(`SELECT COUNT(*) c FROM ${t}`).get().c;
    const ids = db.prepare(`SELECT ${t === 'agent_roles' ? "agent_id||':'||role_id" : t === 'audit_events' ? 'hash' : 'id'} k FROM ${t} ORDER BY k`).all().map((r) => r.k);
    digests[t] = sha256(ids.join('|'));
  }
  return { counts, digests };
}

export function createBackup({ app, passphrase, outDir }) {
  if (!passphrase) throw new Error('Passphrase de backup obrigatória (VILLAGE_BACKUP_PASSPHRASE).');
  const worlds = [];
  const tmp = join(tmpdir(), `village-bk-${process.pid}-${Date.now()}`);
  mkdirSync(tmp, { recursive: true });
  try {
    for (const w of app.worlds()) {
      const f = join(tmp, `${w.id}.db`);
      w.db.exec(`VACUUM INTO '${f.replace(/'/g, "''")}'`);
      const buf = readFileSync(f);
      worlds.push({ id: w.id, name: w.name, kind: w.kind, policy: w.policy, sha256: sha256(buf), data: buf.toString('base64'), snapshot: integritySnapshot(w.db) });
    }
  } finally { rmSync(tmp, { recursive: true, force: true }); }
  const payload = Buffer.from(JSON.stringify({ format: 1, created_at: clock.iso(), worlds }), 'utf8');
  const salt = randomBytes(16), iv = randomBytes(12);
  const cipher = createCipheriv('aes-256-gcm', scryptSync(passphrase, salt, 32, KEY_OPTS), iv);
  const enc = Buffer.concat([cipher.update(payload), cipher.final()]);
  const file = Buffer.concat([MAGIC, salt, iv, cipher.getAuthTag(), enc]);
  mkdirSync(outDir, { recursive: true });
  const name = `village-${clock.iso().replace(/[:.]/g, '-')}.vbk`;
  writeFileSync(join(outDir, name), file, { mode: 0o600 });
  return { file: join(outDir, name), bytes: file.length, worlds: worlds.map((x) => ({ id: x.id, snapshot: x.snapshot })) };
}

export function decryptBackup(file, passphrase) {
  const buf = readFileSync(file);
  if (!buf.subarray(0, 4).equals(MAGIC)) throw new Error('Ficheiro de backup inválido.');
  const salt = buf.subarray(4, 20), iv = buf.subarray(20, 32), tag = buf.subarray(32, 48), enc = buf.subarray(48);
  try {
    const d = createDecipheriv('aes-256-gcm', scryptSync(passphrase, salt, 32, KEY_OPTS), iv);
    d.setAuthTag(tag);
    return JSON.parse(Buffer.concat([d.update(enc), d.final()]).toString('utf8'));
  } catch { throw new Error('Passphrase incorreta ou backup corrompido (falha de integridade).'); }
}

/**
 * Restaura para `targetDir` (tem de estar vazio). Devolve relatório por mundo:
 * contagens/digests vs. snapshot do backup, cadeia de auditoria, tombstones reaplicados e estado dos jobs.
 */
export function restoreBackup({ file, passphrase, targetDir, tombstonesDir }) {
  if (existsSync(targetDir) && readdirSync(targetDir).length) throw new Error('A pasta de destino tem de estar vazia (restauro isolado).');
  const data = decryptBackup(file, passphrase);
  mkdirSync(join(targetDir, 'worlds'), { recursive: true });
  const report = { created_at: data.created_at, worlds: [] };
  for (const wd of data.worlds) {
    const buf = Buffer.from(wd.data, 'base64');
    if (sha256(buf) !== wd.sha256) throw new Error(`Digest inválido para o mundo ${wd.id}.`);
    const dbFile = join(targetDir, 'worlds', `${wd.id}.db`);
    writeFileSync(dbFile, buf);
    const db = openDb(dbFile);
    const w = { id: wd.id, db };
    // 1) jobs suspensos até revisão manual
    const cur = parseJson(db.prepare("SELECT value FROM meta WHERE key='settings'").get()?.value, {});
    db.prepare("INSERT OR REPLACE INTO meta(key,value) VALUES ('settings', ?)").run(json({ ...cur, jobs_suspended: true }));
    // 2) reaplicar tombstones/revogações posteriores ao backup (ficheiro lateral, fora do backup)
    const applied = [];
    for (const t of tombstonesDir ? readSidecarTombstones(tombstonesDir, wd.id) : []) {
      if (t.at <= data.created_at) continue;
      if (t.object_type === 'artifact' && t.kind === 'purged') db.prepare("UPDATE artifacts SET content=NULL, purged_at=? WHERE id=?").run(t.at, t.object_id);
      else if (t.object_type === 'connection') db.prepare("UPDATE connections SET status=?, secret_ref=NULL, proof=NULL, verified_at=NULL, granted_scopes='[]', revoked_at=? WHERE id=?").run(t.kind === 'revoked' ? 'revoked' : 'disconnected', t.at, t.object_id);
      else if (t.object_type === 'conversation' && t.kind === 'purged') db.prepare("UPDATE messages SET content=NULL, state='purged', meta='{}' WHERE conversation_id=?").run(t.object_id);
      applied.push({ object_type: t.object_type, object_id: t.object_id, kind: t.kind });
    }
    const snap = integritySnapshot(db);
    const chain = verifyAuditChain(w);
    const matches = {};
    for (const [tbl, c] of Object.entries(wd.snapshot.counts)) matches[tbl] = c === snap.counts[tbl] && wd.snapshot.digests[tbl] === snap.digests[tbl];
    report.worlds.push({
      id: wd.id, schema_version: currentVersion(db), audit_chain: chain, tombstones_reapplied: applied, jobs_suspended: true,
      counts: snap.counts, matches_backup: Object.values(matches).every(Boolean), per_table_match: matches,
    });
    db.close();
  }
  report.digest = digestOf(report.worlds.map((x) => x.counts));
  return report;
}
