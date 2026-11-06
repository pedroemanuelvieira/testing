// Conversas: CA04 (demo persistente), CA22 (D1), CA26 (modelo real, sem fallback silencioso).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { startServer, agentByName } from './helpers.js';

async function setup(t, opts) { const s = await startServer(opts); t.after(() => s.close()); await s.login(); return s; }

test('CA04 · conversa demo persiste no backend, mantém ordem, agente e rótulo demo', async (t) => {
  const s = await setup(t);
  const w = s.app.world('personal');
  const kai = agentByName(w, 'Kai Pessoal');
  const conv = (await s.api('POST', `/api/w/personal/agents/${kai.id}/conversations`, {})).data;
  assert.equal(conv.mode, 'demo');
  const r1 = (await s.api('POST', `/api/w/personal/conversations/${conv.id}/messages`, { content: 'Bom dia!' })).data;
  assert.equal(r1.reply.mode, 'demo'); assert.equal(r1.reply.author_type, 'agent'); assert.equal(r1.reply.provider_ref, 'demo-deterministico@1');
  const r2 = (await s.api('POST', `/api/w/personal/conversations/${conv.id}/messages`, { content: 'preciso de validar um csv de vendas' })).data;
  assert.equal(r2.reply.meta.suggestion.capability, 'csv.validate');
  assert.equal(r2.reply.meta.suggestion.agent_name, 'Rin Okada');
  // "fechar e reabrir o browser" = nova sessão HTTP: o histórico vem do backend
  const s2 = await startServer(); // outro servidor/BD: prova que NÃO vem de storage do browser
  t.after(() => s2.close());
  const msgs = (await s.api('GET', `/api/w/personal/conversations/${conv.id}/messages`)).data;
  assert.deepEqual(msgs.map((m) => m.sequence), [1, 2, 3, 4]);
  assert.deepEqual(msgs.map((m) => m.author_type), ['owner', 'agent', 'owner', 'agent']);
  assert.ok(msgs.every((m) => m.mode === 'demo'));
  // sem rede de modelos: o adaptador demo não chamou fetch
  let called = 0;
  const s3 = await setup(t, { deps: { fetch: () => { called++; throw new Error('sem rede'); } } });
  const k3 = agentByName(s3.app.world('personal'), 'Kai Pessoal');
  const c3 = (await s3.api('POST', `/api/w/personal/agents/${k3.id}/conversations`, {})).data;
  await s3.api('POST', `/api/w/personal/conversations/${c3.id}/messages`, { content: 'estado' });
  assert.equal(called, 0);
  // estado devolve números reais (BD), não texto fixo
  const tk = (await s3.api('POST', '/api/w/personal/tasks', { title: 'T', assigned_agent_id: k3.id })).data;
  const st = (await s3.api('POST', `/api/w/personal/conversations/${c3.id}/messages`, { content: 'qual o estado?' })).data;
  assert.match(st.reply.content, /1 atribuída/); void tk;
});

test('CA04 · retry com o mesmo request_id não duplica mensagens', async (t) => {
  const s = await setup(t);
  const kai = agentByName(s.app.world('personal'), 'Kai Pessoal');
  const conv = (await s.api('POST', `/api/w/personal/agents/${kai.id}/conversations`, {})).data;
  const a = (await s.api('POST', `/api/w/personal/conversations/${conv.id}/messages`, { content: 'ajuda', request_id: 'req-1' })).data;
  const b = (await s.api('POST', `/api/w/personal/conversations/${conv.id}/messages`, { content: 'ajuda', request_id: 'req-1' })).data;
  assert.equal(b.replay, true); assert.equal(a.owner.id, b.owner.id);
  assert.equal((await s.api('GET', `/api/w/personal/conversations/${conv.id}/messages`)).data.length, 2);
});

test('CA22 · conteúdo proibido (canários): ramo parado, nada guardado nem resumido; chat, CSV e notas', async (t) => {
  const s = await setup(t);
  const w = s.app.world('personal');
  const kai = agentByName(w, 'Kai Pessoal'), apolo = agentByName(w, 'Apolo');
  const conv = (await s.api('POST', `/api/w/personal/agents/${kai.id}/conversations`, {})).data;
  for (const [txt, cat] of [
    ['o meu email é joao.silva@empresa-real.pt', 'email_real'],
    ['IBAN PT50 0002 0123 1234 5678 9015 4', 'iban'],
    ['NIF 123456789 do cliente', 'nif_rotulado'],
    ['CANARIO_D1_PROIBIDO fatura cliente', 'canario_d1'],
    ['chave sk-ant-api03-ABCDEFGHIJKLMNOP', 'credencial'],
  ]) {
    const r = await s.api('POST', `/api/w/personal/conversations/${conv.id}/messages`, { content: txt });
    assert.equal(r.data.blocked, true, txt);
    assert.equal(r.data.owner.state, 'blocked'); assert.equal(r.data.owner.content, null);
    assert.match(r.data.owner.reason_code, new RegExp(cat));
    assert.match(r.data.reply.content, /versão higienizada/);
  }
  // NADA do conteúdo ficou na BD (mensagens, auditoria, artefactos)
  const dump = JSON.stringify([
    w.db.prepare('SELECT * FROM messages').all(), w.db.prepare('SELECT * FROM audit_events').all(), w.db.prepare('SELECT * FROM artifacts').all(),
  ]);
  for (const needle of ['joao.silva', 'empresa-real', '0002 0123', '123456789', 'ABCDEFGHIJKLMNOP']) assert.ok(!dump.includes(needle), needle);
  // upload CSV bloqueado
  const up = await s.api('POST', '/api/w/personal/artifacts', { name: 'x.csv', kind: 'csv', content: 'nome,email\nA,ana@empresa-real.pt\n' });
  assert.equal(up.status, 422); assert.equal(up.data.error.code, 'd1_blocked');
  // nota manual bloqueada
  const tk = (await s.api('POST', '/api/w/personal/tasks', { title: 'T', assigned_agent_id: apolo.id })).data;
  await s.api('POST', `/api/w/personal/tasks/${tk.id}/start-manual`);
  const nt = await s.api('POST', `/api/w/personal/tasks/${tk.id}/complete-manual`, { note: 'resultado com CANARIO_D1_PROIBIDO' });
  assert.equal(nt.status, 422);
  assert.equal((await s.api('GET', `/api/w/personal/tasks/${tk.id}`)).data.state, 'running', 'continua a correr: transacção desfeita');
  // domínios de exemplo e dados sintéticos passam
  const ok = await s.api('POST', `/api/w/personal/conversations/${conv.id}/messages`, { content: 'usa ana@example.com e <CLIENTE_EXEMPLO>' });
  assert.equal(ok.data.blocked, undefined);
  // a auditoria regista só a categoria
  assert.ok((await s.api('GET', '/api/w/personal/audit?limit=100')).data.some((e) => e.action === 'chat.blocked_d1' && /d1:/.test(e.reason_code)));
});

test('CA26 · modelo real: exige ligação verificada + âmbito; erros visíveis; nunca cai para demo em silêncio', async (t) => {
  process.env.ANTHROPIC_API_KEY = 'sk-ant-TESTE-nao-real-0123456789';
  t.after(() => { delete process.env.ANTHROPIC_API_KEY; });
  const calls = [];
  let mode = 'ok';
  const fakeFetch = async (url, init) => {
    calls.push({ url, init });
    if (mode === 'timeout') { const e = new Error('abort'); e.name = 'AbortError'; throw e; }
    if (mode === '429') return { ok: false, status: 429, headers: new Map(), json: async () => ({}) };
    if (url.includes('/v1/models')) return { ok: true, status: 200, headers: new Map([['request-id', 'req_models']]), json: async () => ({ data: [{ id: 'm1' }] }) };
    return { ok: true, status: 200, headers: new Map([['request-id', 'req_abc']]), json: async () => ({ model: 'claude-sonnet-5-5', content: [{ type: 'text', text: 'Resposta real simulada.' }], usage: { input_tokens: 5, output_tokens: 4 } }) };
  };
  const s = await setup(t, { deps: { fetch: fakeFetch } });
  const w = s.app.world('personal');
  const kai = agentByName(w, 'Kai Pessoal');
  const conn = (await s.api('GET', '/api/w/personal/connections')).data.find((c) => c.provider_id === 'anthropic-api');
  // sem verificação → indisponível
  let r = await s.api('POST', `/api/w/personal/agents/${kai.id}/conversations`, { mode: 'real', connection_id: conn.id });
  assert.equal(r.status, 409); assert.equal(r.data.error.code, 'real_not_available');
  // verificar → ligada, mas ainda sem âmbito «chat» concedido
  const v = (await s.api('POST', `/api/w/personal/connections/${conn.id}/verify`)).data;
  assert.equal(v.status, 'connected'); assert.equal(v.proof.http_status, 200);
  r = await s.api('POST', `/api/w/personal/agents/${kai.id}/conversations`, { mode: 'real', connection_id: conn.id });
  assert.equal(r.status, 409, 'âmbito chat não concedido');
  await s.api('PATCH', `/api/w/personal/connections/${conn.id}`, { granted_scopes: ['chat'] });
  const conv = (await s.api('POST', `/api/w/personal/agents/${kai.id}/conversations`, { mode: 'real', connection_id: conn.id })).data;
  assert.equal(conv.mode, 'real');
  const ok = (await s.api('POST', `/api/w/personal/conversations/${conv.id}/messages`, { content: 'Olá' })).data;
  assert.equal(ok.reply.mode, 'real'); assert.equal(ok.reply.provider_ref, 'anthropic:claude-sonnet-5-5'); assert.equal(ok.reply.content, 'Resposta real simulada.');
  const last = calls.at(-1);
  assert.equal(JSON.parse(last.init.body).model, 'claude-sonnet-5-5');
  assert.equal(last.init.headers['x-api-key'], process.env.ANTHROPIC_API_KEY);
  // timeout / 429 → erro visível, pedido conservado, sem resposta demo
  mode = 'timeout';
  const t1 = (await s.api('POST', `/api/w/personal/conversations/${conv.id}/messages`, { content: 'outra' })).data;
  assert.equal(t1.error.code, 'provider_timeout'); assert.equal(t1.reply.state, 'error'); assert.notEqual(t1.reply.mode, 'demo');
  mode = '429';
  const t2 = (await s.api('POST', `/api/w/personal/conversations/${conv.id}/messages`, { content: 'mais uma' })).data;
  assert.equal(t2.error.code, 'provider_rate_limited');
  const msgs = (await s.api('GET', `/api/w/personal/conversations/${conv.id}/messages`)).data;
  assert.ok(msgs.filter((m) => m.author_type === 'owner').length === 3, 'pedidos conservados');
  assert.ok(!msgs.some((m) => m.mode === 'demo'));
  // desligar a ligação → conversa real deixa de responder (sem demo)
  mode = 'ok';
  await s.api('POST', `/api/w/personal/connections/${conn.id}/disconnect`, {});
  const after = await s.api('POST', `/api/w/personal/conversations/${conv.id}/messages`, { content: 'ainda aí?' });
  assert.equal(after.status, 409); assert.equal(after.data.error.code, 'real_not_available');
});
