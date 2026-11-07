// Segurança HTTP e isolamento: sessão/CSRF/headers, CA17 (mundos), CA18 (contas), integridade da auditoria.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { startServer, agentByName } from './helpers.js';
import { verifyAuditChain } from '../server/modules/audit.js';
import { mustGet } from '../server/modules/common.js';
import { getTask } from '../server/modules/tasks.js';
import { readArtifact } from '../server/modules/artifacts.js';
import { newId, clock } from '../server/lib/util.js';

test('Sessão: tudo exige login; CSRF e origem; rate limit; cabeçalhos de segurança; sem path traversal', async (t) => {
  const s = await startServer(); t.after(() => s.close());
  assert.equal((await s.api('GET', '/api/worlds')).status, 401);
  assert.equal((await s.api('GET', '/api/w/personal/tasks')).status, 401);
  assert.equal((await s.api('POST', '/api/w/personal/tasks', { title: 'x' })).status, 401);
  assert.equal((await s.api('GET', '/api/session')).data.authenticated, false);
  assert.equal((await s.login('errado')).status, 401);
  const ok = await s.login();
  assert.equal(ok.status, 200);
  assert.match(ok.headers.get('set-cookie'), /HttpOnly; SameSite=Strict/);
  assert.equal((await s.api('GET', '/api/worlds')).status, 200);
  // CSRF: sem token → 403; origem alheia → 403
  const saved = s.state.csrf; s.state.csrf = '';
  assert.equal((await s.api('POST', '/api/w/personal/tasks', { title: 'x' })).data.error.code, 'csrf');
  s.state.csrf = saved;
  const evil = await s.raw('POST', '/api/w/personal/tasks', { title: 'x' }, { origin: 'http://evil.example' });
  assert.equal(evil.status, 403); assert.equal(evil.data.error.code, 'bad_origin');
  // headers
  const h = (await s.raw('GET', '/')).headers;
  assert.match(h.get('content-security-policy'), /default-src 'self'/); assert.equal(h.get('x-content-type-options'), 'nosniff'); assert.equal(h.get('x-frame-options'), 'DENY');
  // traversal estático
  assert.equal((await s.raw('GET', '/..%2f..%2fserver/index.js')).status, 404);
  assert.equal((await s.raw('GET', '/%2e%2e/package.json')).status, 404);
  // logout invalida
  await s.api('POST', '/api/logout', {});
  assert.equal((await s.api('GET', '/api/worlds')).status, 401);
});

test('Sessão: rate limit de login', async (t) => {
  const s = await startServer(); t.after(() => s.close());
  let last;
  for (let i = 0; i < 9; i++) last = await s.login('nao');
  assert.equal(last.status, 429);
  assert.equal((await s.login()).status, 429, 'mesmo o passcode certo é travado durante a janela');
});

test('CA17 · mundos isolados: IDs, artefactos, auditoria, BI e exportação não atravessam; world_id no corpo é ignorado', async (t) => {
  const s = await startServer(); t.after(() => s.close()); await s.login();
  const pw = s.app.world('personal'), qw = s.app.world('professional');
  assert.notEqual(pw.file, qw.file, 'cada mundo tem o seu ficheiro de BD');
  const apolo = agentByName(pw, 'Apolo');
  const tk = (await s.api('POST', '/api/w/personal/tasks', { title: 'Só pessoal', assigned_agent_id: apolo.id, world_id: 'professional' })).data;
  assert.equal(tk.world_id, 'personal');
  const art = (await s.api('POST', '/api/w/personal/artifacts', { name: 'a.csv', kind: 'csv', content: 'x\n1\n' })).data;
  for (const [m, p] of [['GET', `/api/w/professional/tasks/${tk.id}`], ['GET', `/api/w/professional/artifacts/${art.id}`], ['GET', `/api/w/professional/artifacts/${art.id}/content`],
    ['GET', `/api/w/professional/agents/${apolo.id}`], ['GET', `/api/w/professional/conversations/${apolo.id}/messages`]]) {
    const r = await s.api(m, p);
    assert.equal(r.status, 404, p);
    assert.ok(!JSON.stringify(r.data).includes('Só pessoal'), 'sem fuga de conteúdo/existência');
  }
  // listas, auditoria, KPIs e CSV do outro mundo não contêm nada do pessoal
  const proTasks = (await s.api('GET', '/api/w/professional/tasks')).data;
  assert.ok(proTasks.every((t) => t.world_id === 'professional' && t.id !== tk.id), 'nenhuma tarefa do pessoal no profissional');
  assert.equal((await s.api('GET', '/api/w/professional/bi/kpis')).data.tasks_total, proTasks.length, 'KPIs só contam o próprio mundo');
  assert.ok(!JSON.stringify((await s.api('GET', '/api/w/professional/audit?limit=300')).data).includes(tk.id));
  const csv = (await s.raw('GET', '/api/w/professional/bi/export/fact_task.csv')).data;
  assert.ok(!String(csv).includes(tk.id));
  assert.equal((await s.api('GET', '/api/w/inexistente/overview')).status, 404);
  // delegação cruzada: agente profissional não pode ser atribuído no pessoal
  const atlas = qw.db.prepare("SELECT id FROM agents WHERE display_name='Raiden'").get();
  assert.equal((await s.api('POST', '/api/w/personal/tasks', { title: 'x', assigned_agent_id: atlas.id })).status, 404);
});

test('CA18 · contas A/B no mesmo mundo: A não acede a tarefa/artefacto/conversa/ligação/aprovação de B', async (t) => {
  const s = await startServer(); t.after(() => s.close()); await s.login();
  const w = s.app.world('personal');
  const apolo = agentByName(w, 'Apolo');
  const tk = (await s.api('POST', '/api/w/personal/tasks', { title: 'Da conta B', assigned_agent_id: apolo.id })).data;
  const art = (await s.api('POST', '/api/w/personal/artifacts', { name: 'b.csv', kind: 'csv', content: 'x\n1\n' })).data;
  const conv = (await s.api('POST', `/api/w/personal/agents/${apolo.id}/conversations`, {})).data;
  const conn = (await s.api('GET', '/api/w/personal/connections')).data[0];
  const intent = (await s.api('POST', '/api/w/personal/intents', { operation: 'simulated.publish_note', destination: 'simulado://x', payload: { a: 1 }, idempotency_key: 'k' })).data;
  // segunda conta no mesmo mundo
  const accA = newId('acc'), now = clock.iso();
  w.db.prepare('INSERT INTO accounts(id,world_id,alias,identity_kind,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?)').run(accA, 'personal', 'Conta A', 'synthetic', 'active', now, now);
  const asA = { ...w, accountId: accA };
  assert.throws(() => getTask(asA, tk.id), /não encontrad/i);
  assert.throws(() => readArtifact(asA, art.id), /não encontrad/i);
  for (const [tbl, id] of [['conversations', conv.id], ['connections', conn.id], ['approvals', intent.approval.id], ['action_intents', intent.id]]) {
    assert.throws(() => mustGet(asA, tbl, id), /não encontrad/i, tbl);
  }
  assert.equal(mustGet(w, 'tasks', tk.id).id, tk.id, 'a conta dona continua a aceder');
});

test('Auditoria: append-only (triggers), cadeia de hashes verificável e deteção de adulteração', async (t) => {
  const s = await startServer(); t.after(() => s.close()); await s.login();
  const w = s.app.world('personal');
  await s.api('POST', '/api/w/personal/tasks', { title: 'gera auditoria', assigned_agent_id: agentByName(w, 'Apolo').id });
  assert.equal((await s.api('GET', '/api/w/personal/audit/verify')).data.ok, true);
  assert.throws(() => w.db.prepare("UPDATE audit_events SET result='x' WHERE event_sequence=1").run(), /append-only/);
  assert.throws(() => w.db.prepare('DELETE FROM audit_events WHERE event_sequence=1').run(), /append-only/);
  // adulteração "por fora" (trigger removido) é detetada pela cadeia
  w.db.exec('DROP TRIGGER audit_no_update');
  w.db.prepare("UPDATE audit_events SET actor_ref='intruso' WHERE event_sequence=2").run();
  const v = verifyAuditChain(w);
  assert.equal(v.ok, false); assert.equal(v.broken_at, 2);
});

test('Retratos: só imagens reais (magic bytes), limite de tamanho, acesso autenticado', async (t) => {
  const s = await startServer(); t.after(() => s.close()); await s.login();
  const png = Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), Buffer.alloc(32, 1)]);
  const good = await s.api('POST', '/api/w/personal/portraits', { data_url: `data:image/png;base64,${png.toString('base64')}` });
  assert.equal(good.status, 201); assert.match(good.data.file, /^[a-f0-9]{32}\.png$/);
  const fake = await s.api('POST', '/api/w/personal/portraits', { data_url: `data:image/png;base64,${Buffer.from('<script>alert(1)</script>').toString('base64')}` });
  assert.equal(fake.data.error.code, 'image_invalid');
  assert.equal((await s.api('POST', '/api/w/personal/portraits', { data_url: 'data:text/html;base64,PGI+' })).status, 400);
  const got = await s.raw('GET', `/api/w/personal/portraits/${good.data.file}`);
  assert.equal(got.status, 200); assert.equal(got.headers.get('content-type'), 'image/png');
  assert.equal((await s.raw('GET', '/api/w/personal/portraits/..%2f..%2fvillage.db')).status, 404);
});
