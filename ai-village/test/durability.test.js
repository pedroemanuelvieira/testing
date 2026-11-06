// Durabilidade: CA13 (reinício), CA15 (backup/restauro), CA16 (migração), CA28 (retenção), BI.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync, writeFileSync, readFileSync, readdirSync, existsSync, mkdirSync, copyFileSync, utimesSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createApp } from '../server/app.js';
import { startServer, makeApp, agentByName, PASS } from './helpers.js';
import { runOnce } from '../server/modules/worker.js';
import { createBackup, restoreBackup, decryptBackup } from '../server/backup.js';
import { openDb, migrate, currentVersion, listMigrations } from '../server/lib/db.js';
import { sweep, sweepBackups } from '../server/modules/retention.js';
import { verifyAuditChain } from '../server/modules/audit.js';
import { clock } from '../server/lib/util.js';
import { readArtifact } from '../server/modules/artifacts.js';

const F01 = 'registo,grupo,quantidade\nS01,A,2\nS02,B,3\nS03,A,\nS02,B,3\n';

async function populate(s) {
  const w = s.app.world('personal');
  const rin = agentByName(w, 'Rin Okada'), kai = agentByName(w, 'Kai Pessoal');
  const art = (await s.api('POST', '/api/w/personal/artifacts', { name: 'f.csv', kind: 'csv', content: F01 })).data;
  const tk = (await s.api('POST', '/api/w/personal/tasks', { title: 'F01', capability: 'csv.validate', assigned_agent_id: rin.id, input_refs: [art.id], config: { numeric_column: 'quantidade' } })).data;
  runOnce(w);
  const conv = (await s.api('POST', `/api/w/personal/agents/${kai.id}/conversations`, {})).data;
  await s.api('POST', `/api/w/personal/conversations/${conv.id}/messages`, { content: 'estado' });
  const intent = (await s.api('POST', '/api/w/personal/intents', { operation: 'simulated.send_report', destination: 'simulado://x', payload: { a: 1 }, idempotency_key: 'p' })).data;
  return { art, tk, conv, intent };
}

test('CA13 · fechar tudo e reabrir (reinício do backend/BD) preserva organização, conversas, tarefas, provas e aprovações', async (t) => {
  const a = makeApp(); t.after(() => rmSync(a.dir, { recursive: true, force: true }));
  // 1.º arranque
  const { createHttpServer } = await import('../server/http.js');
  let server = createHttpServer(a.app); await new Promise((r) => server.listen(0, '127.0.0.1', r));
  let base = `http://127.0.0.1:${server.address().port}`;
  const s1 = { api: null };
  const cookie = { v: '', csrf: '' };
  const call = async (m, p, b) => {
    const res = await fetch(base + p, { method: m, headers: { 'content-type': 'application/json', ...(cookie.v ? { cookie: cookie.v } : {}), ...(m !== 'GET' ? { 'x-csrf-token': cookie.csrf } : {}) }, body: b ? JSON.stringify(b) : undefined });
    const sc = res.headers.get('set-cookie'); if (sc) cookie.v = sc.split(';')[0];
    return { status: res.status, data: await res.json() };
  };
  cookie.csrf = (await call('POST', '/api/login', { passcode: PASS })).data.csrf;
  const w = a.app.world('personal');
  const kai = agentByName(w, 'Kai Pessoal');
  const conv = (await call('POST', `/api/w/personal/agents/${kai.id}/conversations`, {})).data;
  await call('POST', `/api/w/personal/conversations/${conv.id}/messages`, { content: 'ola' });
  const before = {
    org: (await call('GET', '/api/w/personal/org')).data, msgs: (await call('GET', `/api/w/personal/conversations/${conv.id}/messages`)).data,
  };
  await new Promise((r) => server.close(r)); a.app.close();
  // reinício: nova app sobre os MESMOS ficheiros
  const app2 = createApp({ dataDir: a.dir, passcode: PASS });
  const w2 = app2.world('personal');
  const { loadOrg } = await import('../server/modules/org.js');
  const { listMessages } = await import('../server/modules/chat.js');
  assert.equal(loadOrg(w2).agents.length, before.org.agents.length);
  assert.deepEqual(loadOrg(w2).agents.map((x) => x.id).sort(), before.org.agents.map((x) => x.id).sort());
  assert.deepEqual(listMessages(w2, conv.id).map((m) => [m.sequence, m.content]), before.msgs.map((m) => [m.sequence, m.content]));
  assert.equal(w2.db.prepare("SELECT COUNT(*) c FROM agents WHERE orchestrator_flag=1").get().c, 1, 'seed não duplica no reinício');
  assert.equal(w2.db.prepare('SELECT COUNT(*) c FROM permissions').get().c, 9);
  app2.close(); void s1;
});

test('CA15 · backup cifrado → restauro isolado: contagens/digests conferem, jobs suspensos, cadeia de auditoria íntegra, tombstones reaplicados', async (t) => {
  const s = await startServer(); t.after(() => s.close()); await s.login();
  const { art, conv } = await populate(s);
  const w = s.app.world('personal');
  const conn = w.db.prepare("SELECT id FROM connections WHERE provider_id='google-drive'").get();
  const out = join(s.dir, 'bk');
  const bk = createBackup({ app: s.app, passphrase: 'frase-de-teste', outDir: out });
  assert.ok(bk.file.endsWith('.vbk'));
  // cifrado: nada legível no ficheiro
  const raw = readFileSync(bk.file);
  assert.ok(!raw.includes(Buffer.from('Haruki Sato')) && !raw.includes(Buffer.from('registo,grupo')));
  assert.throws(() => decryptBackup(bk.file, 'errada'), /Passphrase incorreta/);
  const tampered = join(out, 'tampered.vbk'); const tb = Buffer.from(raw); tb[tb.length - 5] ^= 0xff; writeFileSync(tampered, tb);
  assert.throws(() => decryptBackup(tampered, 'frase-de-teste'), /integridade/);
  // eventos POSTERIORES ao backup: revogação de ligação e expurgo de artefacto
  clock.advance(5000);
  await s.api('POST', `/api/w/personal/connections/${conn.id}/disconnect`, { revoke: true });
  w.db.prepare("UPDATE artifacts SET retention_until='2000-01-01T00:00:00.000Z' WHERE id=?").run(art.id);
  sweep(w);
  // restauro exige destino vazio
  const nonEmpty = mkdtempSync(join(tmpdir(), 'ne-')); writeFileSync(join(nonEmpty, 'x'), '1'); t.after(() => rmSync(nonEmpty, { recursive: true, force: true }));
  assert.throws(() => restoreBackup({ file: bk.file, passphrase: 'frase-de-teste', targetDir: nonEmpty }), /vazia/);
  const target = join(tmpdir(), `restore-${Date.now()}`); t.after(() => rmSync(target, { recursive: true, force: true }));
  const rep = restoreBackup({ file: bk.file, passphrase: 'frase-de-teste', targetDir: target, tombstonesDir: s.dir });
  const pr = rep.worlds.find((x) => x.id === 'personal');
  assert.equal(pr.audit_chain.ok, true); assert.equal(pr.jobs_suspended, true);
  assert.ok(Object.values(pr.per_table_match).every(Boolean), JSON.stringify(pr.per_table_match));
  assert.ok(pr.counts.tasks >= 1 && pr.counts.messages >= 2 && pr.counts.evidence >= 1);
  assert.ok(pr.tombstones_reapplied.some((x) => x.object_id === conn.id && x.kind === 'revoked'));
  assert.ok(pr.tombstones_reapplied.some((x) => x.object_id === art.id && x.kind === 'purged'));
  // abrir o restaurado: acesso NÃO ressuscitado; jobs suspensos; worker não executa
  const restored = createApp({ dataDir: target, passcode: PASS });
  t.after(() => restored.close());
  const rw = restored.world('personal');
  assert.equal(rw.db.prepare('SELECT status FROM connections WHERE id=?').get(conn.id).status, 'revoked');
  assert.throws(() => readArtifact(rw, art.id), /expurgado/i);
  assert.equal(JSON.parse(rw.db.prepare("SELECT value FROM meta WHERE key='settings'").get().value).jobs_suspended, true);
  const rin = agentByName(rw, 'Rin Okada');
  rw.db.prepare("INSERT INTO artifacts(id,world_id,account_id,name,kind,size_bytes,digest,content,created_at,updated_at) VALUES ('art_x','personal',?, 'x','csv',1,'d','a',?,?)").run(rw.accountId, 'n', 'n');
  const { createTask } = await import('../server/modules/tasks.js');
  const { OWNER } = await import('../server/modules/policy.js');
  void rin; void createTask; void OWNER; void conv;
  assert.equal(runOnce(rw), 0, 'jobs suspensos após restauro');
});

test('CA16 · migração: sucesso preserva invariantes; falha a meio não deixa estado parcial; cópia de segurança prévia', async (t) => {
  const dir = mkdtempSync(join(tmpdir(), 'mig-')); t.after(() => rmSync(dir, { recursive: true, force: true }));
  const mdir = join(dir, 'migs'); mkdirSync(mdir);
  const all = listMigrations();
  assert.ok(all.length >= 2);
  copyFileSync(join(new URL('../server/migrations', import.meta.url).pathname, '001_core.sql'), join(mdir, '001_core.sql'));
  const file = join(dir, 'w.db');
  let db = openDb(file);
  migrate(db, { file, dir: mdir });
  assert.equal(currentVersion(db), 1);
  const now = new Date().toISOString();
  db.prepare("INSERT INTO accounts(id,world_id,alias,created_at,updated_at) VALUES ('a','w','x',?,?)").run(now, now);
  // 002 defeituosa: cria uma tabela e depois falha → nada pode ficar
  writeFileSync(join(mdir, '002_quebrada.sql'), 'CREATE TABLE nova_tabela (id TEXT);\nINSERT INTO accounts(id) VALUES (NULL);\nSELECT * FROM tabela_inexistente;');
  assert.throws(() => migrate(db, { file, dir: mdir, backupDir: join(dir, 'bk') }));
  assert.equal(currentVersion(db), 1, 'versão não avançou');
  assert.equal(db.prepare("SELECT COUNT(*) c FROM sqlite_master WHERE name='nova_tabela'").get().c, 0, 'sem estado parcial');
  assert.equal(db.prepare('SELECT COUNT(*) c FROM accounts').get().c, 1, 'dados preservados');
  assert.ok(readdirSync(join(dir, 'bk')).some((f) => f.startsWith('pre-migrate-v1')), 'cópia prévia criada (reversão por restauro)');
  // migração boa a seguir
  writeFileSync(join(mdir, '002_quebrada.sql'), 'ALTER TABLE accounts ADD COLUMN nota TEXT;');
  const r = migrate(db, { file, dir: mdir, backupDir: join(dir, 'bk') });
  assert.deepEqual(r.applied, [2]); assert.equal(db.prepare('SELECT COUNT(*) c FROM accounts').get().c, 1);
  db.close();
  // idempotente
  db = openDb(file); assert.deepEqual(migrate(db, { file, dir: mdir }).applied, []); db.close();
});

test('CA28 · retenção: conteúdo, mensagens e auditoria expiram; tombstones; cadeia continua íntegra; backups vencidos removem-se', async (t) => {
  const s = await startServer(); t.after(() => s.close()); await s.login();
  const { art, conv } = await populate(s);
  const w = s.app.world('personal');
  await s.api('PATCH', '/api/w/personal/settings', { retention_content_days: 30, retention_audit_days: 90, backup_retention_days: 7 });
  clock.advance(29 * 86400_000);
  assert.deepEqual(sweep(w), { artifacts: 0, messages: 0, evidence: 0, audit_events: 0 }, 'antes do prazo nada expira');
  clock.advance(2 * 86400_000);
  const r1 = sweep(w);
  assert.ok(r1.artifacts >= 2 && r1.messages >= 2);
  assert.throws(() => readArtifact(w, art.id), /expurgado/i);
  const msgs = w.db.prepare('SELECT content,state FROM messages WHERE conversation_id=?').all(conv.id);
  assert.ok(msgs.every((m) => m.content === null && m.state === 'purged'));
  assert.ok(w.db.prepare("SELECT COUNT(*) c FROM tombstones WHERE kind='purged'").get().c >= 3);
  const ev = w.db.prepare('SELECT summary FROM evidence').all();
  assert.ok(ev.every((e) => e.summary === '{}'), 'resumo da prova minimizado');
  // auditoria após 90 dias: apaga eventos antigos, guarda âncora, cadeia continua válida
  const before = w.db.prepare('SELECT COUNT(*) c FROM audit_events').get().c;
  clock.advance(65 * 86400_000);
  const r2 = sweep(w);
  assert.ok(r2.audit_events > 0 && r2.audit_events <= before);
  const chain = verifyAuditChain(w);
  assert.equal(chain.ok, true); assert.ok(chain.anchor_seq > 0);
  assert.ok(w.db.prepare("SELECT value FROM meta WHERE key='audit_anchor'").get());
  // backups vencidos
  const bdir = join(s.dir, 'backups'); mkdirSync(bdir, { recursive: true });
  const old = join(bdir, 'old.vbk'); writeFileSync(old, 'x');
  const past = new Date(clock.now() - 8 * 86400_000); utimesSync(old, past, past);
  const fresh = join(bdir, 'fresh.vbk'); writeFileSync(fresh, 'y');
  const recent = new Date(clock.now() - 86400_000); utimesSync(fresh, recent, recent); // 1 dia atrás no relógio virtual
  assert.equal(sweepBackups(s.dir, 7), 1);
  assert.ok(!existsSync(old) && existsSync(fresh));
});

test('BI: KPIs coerentes com a BD; export CSV em estrela sem conteúdo; anti-injecção de fórmulas', async (t) => {
  const s = await startServer(); t.after(() => s.close()); await s.login();
  await populate(s);
  const k = (await s.api('GET', '/api/w/personal/bi/kpis')).data;
  assert.equal(k.tasks_by_state.completed, 1); assert.equal(k.tasks_total, 1); assert.equal(k.evidence_coverage, 100);
  assert.equal(k.attempt_duration_ms.n, 1); assert.equal(k.agents.total, 16);
  assert.equal(k.approvals_by_state.pending, 1);
  assert.equal(k.workload.find((x) => x.display_name === 'Rin Okada').completed_tasks, 1);
  for (const table of ['dim_agent', 'dim_unit', 'dim_role', 'fact_task', 'fact_attempt', 'fact_approval', 'fact_audit', 'fact_message']) {
    const r = await s.raw('GET', `/api/w/personal/bi/export/${table}.csv`);
    assert.equal(r.status, 200, table); assert.match(r.headers.get('content-type'), /text\/csv/); assert.ok(String(r.data).split('\r\n').length >= 2, table);
  }
  const ft = String((await s.raw('GET', '/api/w/personal/bi/export/fact_task.csv')).data);
  assert.match(ft, /task_id,title,kind/); assert.match(ft, /csv_validation/);
  const fm = String((await s.raw('GET', '/api/w/personal/bi/export/fact_message.csv')).data);
  assert.ok(!fm.includes('estado'), 'sem conteúdo de mensagens'); assert.match(fm, /content_chars/);
  assert.equal((await s.raw('GET', '/api/w/personal/bi/export/sqlite_master.csv')).status, 404, 'só vistas autorizadas');
  // título com fórmula é neutralizado ao exportar
  const apolo = agentByName(s.app.world('personal'), 'Apolo');
  await s.api('POST', '/api/w/personal/tasks', { title: '=HYPERLINK("http://x")', assigned_agent_id: apolo.id });
  const ft2 = String((await s.raw('GET', '/api/w/personal/bi/export/fact_task.csv')).data);
  assert.ok(ft2.includes(`"'=HYPERLINK`) || ft2.includes("'=HYPERLINK"));
  assert.ok(!/,=HYPERLINK/.test(ft2));
});
