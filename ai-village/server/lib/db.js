// Acesso SQLite (node:sqlite), transacções e migrações versionadas.
import { DatabaseSync } from 'node:sqlite';
import { readdirSync, readFileSync, mkdirSync, copyFileSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { sha256, clock } from './util.js';

const here = dirname(fileURLToPath(import.meta.url));
export const MIGRATIONS_DIR = join(here, '..', 'migrations');

export function openDb(file) {
  if (file !== ':memory:') mkdirSync(dirname(file), { recursive: true });
  const db = new DatabaseSync(file);
  db.exec('PRAGMA journal_mode = WAL; PRAGMA foreign_keys = ON; PRAGMA busy_timeout = 5000; PRAGMA synchronous = NORMAL;');
  return db;
}

// Transacção imediata (escritor único) com rollback automático.
export function tx(db, fn) {
  db.exec('BEGIN IMMEDIATE');
  try {
    const r = fn();
    db.exec('COMMIT');
    return r;
  } catch (e) {
    try { db.exec('ROLLBACK'); } catch { /* já terminada */ }
    throw e;
  }
}

export function listMigrations(dir = MIGRATIONS_DIR) {
  return readdirSync(dir)
    .filter((f) => /^\d{3}_.+\.sql$/.test(f))
    .sort()
    .map((f) => {
      const sql = readFileSync(join(dir, f), 'utf8');
      return { version: Number(f.slice(0, 3)), name: f.slice(4, -4), sql, checksum: sha256(sql) };
    });
}

export function currentVersion(db) {
  const t = db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'").get();
  if (!t) return 0;
  return db.prepare('SELECT COALESCE(MAX(version),0) v FROM schema_migrations').get().v;
}

/**
 * Aplica migrações pendentes. Cada migração corre numa transacção; se falhar,
 * nada fica aplicado (CA16). Antes de migrar, se a BD já tem dados, faz cópia
 * de segurança do ficheiro para permitir reversão por restauro.
 */
export function migrate(db, { file, dir = MIGRATIONS_DIR, upTo = Infinity, backupDir } = {}) {
  const all = listMigrations(dir).filter((m) => m.version <= upTo);
  const from = currentVersion(db);
  const pending = all.filter((m) => m.version > from);
  if (!pending.length) return { from, to: from, applied: [] };
  if (from > 0 && file && file !== ':memory:' && backupDir) {
    mkdirSync(backupDir, { recursive: true });
    db.exec('PRAGMA wal_checkpoint(TRUNCATE)');
    if (existsSync(file)) copyFileSync(file, join(backupDir, `pre-migrate-v${from}-${Date.now()}.db`));
  }
  const applied = [];
  for (const m of pending) {
    tx(db, () => {
      db.exec(m.sql);
      db.prepare('INSERT INTO schema_migrations(version,name,applied_at,checksum) VALUES (?,?,?,?)')
        .run(m.version, m.name, clock.iso(), m.checksum);
    });
    applied.push(m.version);
  }
  return { from, to: currentVersion(db), applied };
}
