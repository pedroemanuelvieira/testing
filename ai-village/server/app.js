// Montagem da aplicação: registo de mundos, BDs por mundo (fronteira de dados, H10), migrações e seed.
// Cada mundo tem o SEU ficheiro SQLite: sem JOINs, caches ou filas partilhadas entre mundos (RNF02).
import { join } from 'node:path';
import { mkdirSync } from 'node:fs';
import { openDb, migrate } from './lib/db.js';
import { newId, clock, parseJson, json, notFound } from './lib/util.js';
import { initAuth } from './auth.js';
import { seedPersonal, seedProfessional } from './seed.js';
import { getSettings } from './modules/settings.js';

export const WORLD_DEFS = [
  { id: 'personal', name: 'Mundo Pessoal', kind: 'personal', policy: { execution: true, data: 'synthetic_only', d1: 'strict', label: 'Pessoal · dados fictícios' }, seed: seedPersonal },
  { id: 'professional', name: 'Mundo Profissional (desenho)', kind: 'professional', policy: { execution: false, data: 'design_only', d1: 'strict', label: 'Profissional · só desenho' }, seed: seedProfessional },
];

export function createApp({ dataDir, deps = {}, passcode } = {}) {
  mkdirSync(join(dataDir, 'worlds'), { recursive: true });
  const meta = openDb(join(dataDir, 'village.db'));
  const auth = initAuth(meta, { passcode });
  meta.exec(`CREATE TABLE IF NOT EXISTS worlds (id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL, db_file TEXT NOT NULL, policy TEXT NOT NULL, created_at TEXT NOT NULL)`);
  const cache = new Map();

  function open(def, row) {
    const file = join(dataDir, 'worlds', `${def.id}.db`);
    const db = openDb(file);
    migrate(db, { file, backupDir: join(dataDir, 'migration-backups') });
    return { id: def.id, name: row?.name || def.name, kind: def.kind, policy: row ? parseJson(row.policy, def.policy) : def.policy, db, file, dataDir, deps, accountId: null };
  }

  for (const def of WORLD_DEFS) {
    let row = meta.prepare('SELECT * FROM worlds WHERE id=?').get(def.id);
    const isNew = !row;
    if (isNew) {
      meta.prepare('INSERT INTO worlds(id,name,kind,db_file,policy,created_at) VALUES (?,?,?,?,?,?)').run(def.id, def.name, def.kind, `worlds/${def.id}.db`, json(def.policy), clock.iso());
      row = meta.prepare('SELECT * FROM worlds WHERE id=?').get(def.id);
    }
    const w = open(def, row);
    // Conta sintética do mundo (identidade opaca; sem contas reais nesta fase).
    let acc = w.db.prepare('SELECT id FROM accounts WHERE world_id=? LIMIT 1').get(def.id);
    if (!acc) {
      const id = newId('acc'), now = clock.iso();
      w.db.prepare('INSERT INTO accounts(id,world_id,alias,identity_kind,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?)')
        .run(id, def.id, def.kind === 'personal' ? 'Conta Pedro (sintética)' : 'Conta Pedro profissional (desenho)', 'synthetic', 'active', now, now);
      acc = { id };
    }
    w.accountId = acc.id;
    w.db.prepare("INSERT OR IGNORE INTO meta(key,value) VALUES ('world_id', ?)").run(def.id);
    const seeded = w.db.prepare("SELECT value FROM meta WHERE key='seeded'").get();
    if (!seeded) {
      def.seed(w);
      w.db.prepare("INSERT OR REPLACE INTO meta(key,value) VALUES ('seeded','1')").run();
    }
    cache.set(def.id, w);
  }

  return {
    meta, dataDir, deps, generatedPasscode: auth.generated,
    world(id) { const w = cache.get(id); if (!w) throw notFound('Mundo não encontrado'); return w; },
    worlds() { return [...cache.values()]; },
    close() { for (const w of cache.values()) { try { w.db.close(); } catch { /* já fechada */ } } try { meta.close(); } catch { /* já fechada */ } },
    settings: (w) => getSettings(w),
  };
}
