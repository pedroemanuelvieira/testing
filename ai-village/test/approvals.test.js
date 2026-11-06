// Aprovações e ações simuladas: CA09, CA10, CA11.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { startServer, agentByName } from './helpers.js';
import { clock } from '../server/lib/util.js';

const intentBody = (extra = {}) => ({ operation: 'simulated.send_report', destination: 'simulado://interno/relatorio', payload: { assunto: 'Relatório F01', linhas: 4 }, idempotency_key: 'i-1', ...extra });
const effects = (s) => s.app.world('personal').db.prepare('SELECT COUNT(*) c FROM action_effects').get().c;

async function setup(t) { const s = await startServer(); t.after(() => s.close()); await s.login(); return s; }

test('CA09 · pré-visualização exata, aprovação de uso único e rótulo de simulação sem saída externa', async (t) => {
  const s = await setup(t);
  const i = (await s.api('POST', '/api/w/personal/intents', intentBody())).data;
  assert.equal(i.state, 'pending_approval');
  const a = i.approval;
  assert.equal(a.state, 'pending'); assert.equal(a.payload_digest, i.payload_digest); assert.match(a.effect, /SIMULAÇÃO/);
  assert.ok(a.expires_at > a.requested_at);
  await s.api('POST', `/api/w/personal/approvals/${a.id}/approve`);
  const ex = (await s.api('POST', `/api/w/personal/approvals/${a.id}/execute`)).data;
  assert.equal(ex.replay, false); assert.equal(ex.intent.state, 'executed'); assert.equal(ex.approval.state, 'consumed');
  assert.equal(ex.intent.result.simulated, true);
  const eff = s.app.world('personal').db.prepare('SELECT * FROM action_effects').get();
  assert.equal(eff.simulated, 1); assert.equal(eff.external_calls, 0);
  // destinos externos são recusados à nascença (H09)
  const ext = await s.api('POST', '/api/w/personal/intents', intentBody({ destination: 'mailto:alguem@example.com', idempotency_key: 'i-2' }));
  assert.equal(ext.data.error.code, 'external_destination_blocked');
  assert.equal((await s.api('POST', '/api/w/personal/intents', intentBody({ operation: 'email.send', idempotency_key: 'i-3' }))).data.error.code, 'unknown_operation');
  // auditoria correlaciona intent → approval → execução
  const au = (await s.api('GET', '/api/w/personal/audit?limit=50')).data;
  for (const act of ['intent.create', 'approval.approve', 'approval.execute']) assert.ok(au.some((e) => e.action === act), act);
});

test('CA10 · negar, revogar, expirar e alterar payload impedem execução; revogação imediatamente antes também', async (t) => {
  const s = await setup(t);
  const mk = async (k) => (await s.api('POST', '/api/w/personal/intents', intentBody({ idempotency_key: k }))).data;
  // negar
  const d = await mk('deny');
  await s.api('POST', `/api/w/personal/approvals/${d.approval.id}/deny`, { reason: 'não quero' });
  assert.equal((await s.api('POST', `/api/w/personal/approvals/${d.approval.id}/execute`)).data.error.code, 'approval_not_valid');
  // aprovar → revogar antes de executar
  const r = await mk('revoke');
  await s.api('POST', `/api/w/personal/approvals/${r.approval.id}/approve`);
  await s.api('POST', `/api/w/personal/approvals/${r.approval.id}/revoke`, { reason: 'mudei de ideias' });
  assert.equal((await s.api('POST', `/api/w/personal/approvals/${r.approval.id}/execute`)).status, 422);
  // expirar
  const e = await mk('exp');
  await s.api('POST', `/api/w/personal/approvals/${e.approval.id}/approve`);
  clock.advance(16 * 60_000);
  const ex = await s.api('POST', `/api/w/personal/approvals/${e.approval.id}/execute`);
  assert.equal(ex.status, 422); assert.match(ex.data.error.message, /expired/);
  // alterar payload invalida a aprovação anterior e cria nova versão/digest
  const p = await mk('payload');
  await s.api('POST', `/api/w/personal/approvals/${p.approval.id}/approve`);
  const changed = (await s.api('POST', `/api/w/personal/intents/${p.id}/payload`, { payload: { assunto: 'Outro', linhas: 5 } })).data;
  assert.equal(changed.payload_version, 2); assert.notEqual(changed.payload_digest, p.payload_digest);
  assert.equal(changed.approval.state, 'pending');
  const old = (await s.api('GET', '/api/w/personal/approvals')).data.find((x) => x.id === p.approval.id);
  assert.equal(old.state, 'revoked');
  assert.equal((await s.api('POST', `/api/w/personal/approvals/${p.approval.id}/execute`)).status, 422);
  assert.equal(effects(s), 0, 'zero efeitos em todos os casos negativos');
  // cada negativa ficou auditada com motivo
  const au = (await s.api('GET', '/api/w/personal/audit?limit=100')).data;
  assert.ok(au.filter((x) => x.action === 'approval.execute' && x.result === 'denied').length >= 3);
});

test('CA11 · retry/concorrência: no máximo um efeito; mesma chave com digest distinto é rejeitada', async (t) => {
  const s = await setup(t);
  const i = (await s.api('POST', '/api/w/personal/intents', intentBody({ idempotency_key: 'conc' }))).data;
  await s.api('POST', `/api/w/personal/approvals/${i.approval.id}/approve`);
  const results = await Promise.all(Array.from({ length: 6 }, () => s.api('POST', `/api/w/personal/approvals/${i.approval.id}/execute`)));
  assert.ok(results.every((r) => r.status === 200), JSON.stringify(results.map((r) => r.status)));
  assert.equal(results.filter((r) => r.data.replay === false).length, 1, 'um só vencedor');
  assert.equal(results.filter((r) => r.data.replay === true).length, 5, 'os restantes recebem o resultado existente');
  assert.equal(effects(s), 1);
  // pedido repetido com a mesma chave devolve a mesma intenção
  const again = (await s.api('POST', '/api/w/personal/intents', intentBody({ idempotency_key: 'conc' }))).data;
  assert.equal(again.id, i.id); assert.equal(again.idempotent_replay, true);
  // mesma chave, payload diferente → 409
  const clash = await s.api('POST', '/api/w/personal/intents', intentBody({ idempotency_key: 'conc', payload: { assunto: 'Diferente' } }));
  assert.equal(clash.status, 409); assert.equal(clash.data.error.code, 'idempotency_key_reuse');
  // garantia a nível de BD: segundo efeito para a mesma intenção é impossível
  assert.throws(() => s.app.world('personal').db.prepare("INSERT INTO action_effects(id,intent_id,world_id,created_at) VALUES ('x',?,?,?)").run(i.id, 'personal', 'now'), /UNIQUE/);
});

test('Tarefa ↔ aprovação: awaiting_approval é espera; negar/expirar bloqueia; não se salta a aprovação', async (t) => {
  const s = await setup(t);
  const w = s.app.world('personal');
  const apolo = agentByName(w, 'Apolo');
  const tk = (await s.api('POST', '/api/w/personal/tasks', { title: 'Enviar plano', assigned_agent_id: apolo.id })).data;
  await s.api('POST', `/api/w/personal/tasks/${tk.id}/start-manual`);
  const i = (await s.api('POST', '/api/w/personal/intents', intentBody({ task_id: tk.id, idempotency_key: 'tk' }))).data;
  let d = (await s.api('GET', `/api/w/personal/tasks/${tk.id}`)).data;
  assert.equal(d.state, 'awaiting_approval');
  assert.equal((await s.api('GET', `/api/w/personal/agents/${apolo.id}`)).data.activity_status, 'ocupado', 'a tentativa continua ativa');
  // saltar a aprovação → rejeitado
  assert.equal((await s.api('POST', `/api/w/personal/tasks/${tk.id}/transition`, { to: 'running' })).status, 422);
  assert.equal((await s.api('POST', `/api/w/personal/tasks/${tk.id}/transition`, { to: 'completed' })).status, 422);
  await s.api('POST', `/api/w/personal/approvals/${i.approval.id}/approve`);
  await s.api('POST', `/api/w/personal/approvals/${i.approval.id}/execute`);
  d = (await s.api('GET', `/api/w/personal/tasks/${tk.id}`)).data;
  assert.equal(d.state, 'running');
  // negar bloqueia a tarefa
  const tk2 = (await s.api('POST', '/api/w/personal/tasks', { title: 'Outra', assigned_agent_id: apolo.id })).data;
  await s.api('POST', `/api/w/personal/tasks/${tk2.id}/start-manual`);
  const i2 = (await s.api('POST', '/api/w/personal/intents', intentBody({ task_id: tk2.id, idempotency_key: 'tk2' }))).data;
  await s.api('POST', `/api/w/personal/approvals/${i2.approval.id}/deny`, {});
  assert.equal((await s.api('GET', `/api/w/personal/tasks/${tk2.id}`)).data.error_code, 'approval_denied');
});
