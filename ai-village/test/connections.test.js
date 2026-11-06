// Ligações honestas e segredos: CA19, CA20, CA21.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { startServer, agentByName } from './helpers.js';
import { clock } from '../server/lib/util.js';

const find = async (s, pid, world = 'personal') => (await s.api('GET', `/api/w/${world}/connections`)).data.find((c) => c.provider_id === pid);
const dumpDb = (w) => JSON.stringify(['connections', 'audit_events', 'messages', 'tasks', 'evidence', 'artifacts'].map((t) => w.db.prepare(`SELECT * FROM ${t}`).all()));

test('CA19 · catálogo mostra planeada/não verificada; sem adaptador não há promoção a ligada; só prova datada promove; expira → degradada', async (t) => {
  process.env.ANTHROPIC_API_KEY = 'chave-de-teste-1234567890';
  t.after(() => { delete process.env.ANTHROPIC_API_KEY; });
  const s = await startServer({ deps: { fetch: async () => ({ ok: true, status: 200, headers: new Map(), json: async () => ({ data: [] }) }) } });
  t.after(() => s.close()); await s.login();
  const all = (await s.api('GET', '/api/w/personal/connections')).data;
  const drive = all.find((c) => c.provider_id === 'google-drive');
  assert.equal(drive.status, 'planned'); assert.equal(drive.adapter_implemented, false);
  assert.equal(all.find((c) => c.provider_id === 'demo-adapter').status, 'demo');
  assert.ok(all.every((c) => c.status !== 'connected'), 'nada nasce ligado');
  // tentar verificar um fornecedor sem adaptador → recusa honesta
  const v = await s.api('POST', `/api/w/personal/connections/${drive.id}/verify`);
  assert.equal(v.status, 422); assert.equal(v.data.error.code, 'adapter_not_implemented');
  assert.equal((await find(s, 'google-drive')).status, 'planned');
  // com prova → ligada; passada a janela de frescura → degradada (needs_reverification)
  const an = await find(s, 'anthropic-api');
  const ok = (await s.api('POST', `/api/w/personal/connections/${an.id}/verify`)).data;
  assert.equal(ok.status, 'connected'); assert.ok(ok.verified_at); assert.equal(ok.stale, false);
  clock.advance(2 * 86400_000);
  assert.equal((await s.api('GET', '/api/worlds')).status, 401, 'a sessão expirou com o tempo (TTL)');
  await s.login();
  const stale = await find(s, 'anthropic-api');
  assert.equal(stale.status, 'degraded'); assert.equal(stale.stale, true); assert.equal(stale.needs_reverification, true);
  // verificação falhada degrada, nunca promove
  delete process.env.ANTHROPIC_API_KEY;
  const fail = await s.api('POST', `/api/w/personal/connections/${an.id}/verify`);
  assert.equal(fail.data.error.code, 'secret_missing');
  assert.equal((await find(s, 'anthropic-api')).status, 'degraded');
  // mundo profissional: só desenho, nenhuma verificação real
  const pro = await find(s, 'm365-tenant', 'professional');
  assert.equal(pro.status, 'planned');
  assert.equal((await s.api('POST', `/api/w/professional/connections/${pro.id}/verify`)).data.error.code, 'world_design_only');
});

test('CA20 · desligar/revogar nega novas chamadas, bloqueia jobs dependentes, invalida segredo/prova e regista tombstone', async (t) => {
  process.env.ANTHROPIC_API_KEY = 'chave-de-teste-1234567890';
  t.after(() => { delete process.env.ANTHROPIC_API_KEY; });
  const s = await startServer({ deps: { fetch: async () => ({ ok: true, status: 200, headers: new Map(), json: async () => ({ data: [{}] }) }) } });
  t.after(() => s.close()); await s.login();
  const w = s.app.world('personal');
  const an = await find(s, 'anthropic-api');
  await s.api('POST', `/api/w/personal/connections/${an.id}/verify`);
  await s.api('PATCH', `/api/w/personal/connections/${an.id}`, { granted_scopes: ['chat'] });
  const apolo = agentByName(w, 'Apolo');
  const dep = (await s.api('POST', '/api/w/personal/tasks', { title: 'Depende da ligação', assigned_agent_id: apolo.id, config: { connection_id: an.id } })).data;
  const indep = (await s.api('POST', '/api/w/personal/tasks', { title: 'Independente', assigned_agent_id: apolo.id })).data;
  const r = (await s.api('POST', `/api/w/personal/connections/${an.id}/disconnect`, { revoke: true })).data;
  assert.equal(r.blocked_tasks, 1); assert.equal(r.connection.status, 'revoked');
  assert.equal(r.connection.secret_ref, null); assert.equal(r.connection.proof, null); assert.deepEqual(r.connection.granted_scopes, []);
  assert.match(r.remote_revocation, /manual/);
  assert.equal((await s.api('GET', `/api/w/personal/tasks/${dep.id}`)).data.error_code, 'connection_revoked');
  assert.equal((await s.api('GET', `/api/w/personal/tasks/${indep.id}`)).data.state, 'assigned');
  // não se pode reverificar nem alterar uma ligação revogada
  assert.equal((await s.api('POST', `/api/w/personal/connections/${an.id}/verify`)).status, 422);
  assert.equal((await s.api('PATCH', `/api/w/personal/connections/${an.id}`, { granted_scopes: ['chat'] })).status, 422);
  assert.equal(w.db.prepare("SELECT COUNT(*) c FROM tombstones WHERE object_id=? AND kind='revoked'").get(an.id).c, 1);
});

test('CA21 · segredo-canário nunca aparece em UI/respostas, BD, logs, evidência; rotação deixa a chave anterior sem uso', async (t) => {
  const K1 = 'CANARIO_SEGREDO_AAAA1111bbbb2222', K2 = 'CANARIO_SEGREDO_ZZZZ9999yyyy8888';
  process.env.ANTHROPIC_API_KEY = K1;
  t.after(() => { delete process.env.ANTHROPIC_API_KEY; });
  const seenKeys = [];
  let failNext = false;
  const fakeFetch = async (url, init) => {
    seenKeys.push(init.headers['x-api-key']);
    // o fornecedor "ecoa" a chave num erro — a app tem de redigir
    if (failNext) return { ok: false, status: 500, headers: new Map(), json: async () => ({ error: `falha com ${init.headers['x-api-key']}` }) };
    return { ok: true, status: 200, headers: new Map(), json: async () => ({ data: [] }) };
  };
  const s = await startServer({ deps: { fetch: fakeFetch } });
  t.after(() => s.close()); await s.login();
  const logs = []; const origErr = console.error; console.error = (...a) => logs.push(a.join(' ')); t.after(() => { console.error = origErr; });
  const responses = [];
  const call = async (m, p, b) => { const r = await s.api(m, p, b); responses.push(JSON.stringify(r.data)); return r; };
  const an = await find(s, 'anthropic-api');
  await call('POST', `/api/w/personal/connections/${an.id}/verify`);
  failNext = true;
  await call('POST', `/api/w/personal/connections/${an.id}/verify`);
  failNext = false;
  await call('GET', '/api/w/personal/connections'); await call('GET', '/api/w/personal/audit?limit=200'); await call('GET', '/api/w/personal/overview');
  // rotação: nova chave no servidor; a anterior deixa de ser usada
  process.env.ANTHROPIC_API_KEY = K2;
  await call('POST', `/api/w/personal/connections/${an.id}/verify`);
  assert.deepEqual([...new Set(seenKeys)], [K1, K2]); assert.equal(seenKeys.at(-1), K2);
  const everything = responses.join('\n') + dumpDb(s.app.world('personal')) + logs.join('\n');
  for (const k of [K1, K2, 'AAAA1111', 'ZZZZ9999']) assert.ok(!everything.includes(k), `segredo vazou: ${k}`);
  // cabeçalhos da resposta HTTP também limpos
  const h = await s.raw('GET', '/api/w/personal/connections');
  assert.ok(![...h.headers.entries()].join().includes('CANARIO'));
});
