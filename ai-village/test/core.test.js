// Núcleo: organização (CA01, CA02), tarefas e máquina de estados (CA12), delegação (CA03).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { startServer, agentByName } from './helpers.js';

async function ready() {
  const s = await startServer();
  await s.login();
  return s;
}

test('CA01 · criar/editar unidade, função e agente sem código novo; versões e referências inválidas', async (t) => {
  const s = await ready(); t.after(() => s.close());
  const unit = (await s.api('POST', '/api/w/personal/units', { name: 'Laboratório Novo', theme: 'lab', kanji: '新' })).data;
  assert.ok(unit.id.startsWith('unit_')); assert.equal(unit.record_version, 1);
  const role = (await s.api('POST', '/api/w/personal/roles', { name: 'Analista Extra', tier: 'specialist', mission: 'Analisar', default_capability_proposals: ['csv.profile'] })).data;
  assert.ok(role.id);
  const ag = await s.api('POST', '/api/w/personal/agents', { display_name: 'Nova Pessoa', title: 'Analista', org_unit_id: unit.id, role_ids: [role.id], capability_ids: ['csv.profile'] });
  assert.equal(ag.status, 200);
  assert.deepEqual(ag.data.role_ids, [role.id]);
  // edição com versão
  const upd = await s.api('PATCH', `/api/w/personal/agents/${ag.data.id}`, { title: 'Analista Sénior', expected_version: ag.data.record_version });
  assert.equal(upd.data.title, 'Analista Sénior'); assert.equal(upd.data.record_version, 2);
  // versão antiga é rejeitada (concorrência optimista)
  const stale = await s.api('PATCH', `/api/w/personal/agents/${ag.data.id}`, { title: 'X', expected_version: 1 });
  assert.equal(stale.status, 409); assert.equal(stale.data.error.code, 'stale_version');
  // sem expected_version é recusado
  assert.equal((await s.api('PATCH', `/api/w/personal/agents/${ag.data.id}`, { title: 'X' })).data.error.code, 'expected_version_required');
  // referências inválidas / entre mundos
  const other = (await s.api('GET', '/api/w/professional/org')).data.units[0].id;
  const bad = await s.api('POST', '/api/w/personal/agents', { display_name: 'Fora', org_unit_id: other });
  assert.equal(bad.status, 400); assert.equal(bad.data.error.code, 'invalid_reference');
  // capacidade desconhecida
  assert.equal((await s.api('POST', '/api/w/personal/agents', { display_name: 'Z', capability_ids: ['nao.existe'] })).data.error.code, 'unknown_capability');
});

test('CA01 · arquivar agente com tarefa activa exige cancelar/reencaminhar e mantém histórico', async (t) => {
  const s = await ready(); t.after(() => s.close());
  const w = s.app.world('personal');
  const sora = agentByName(w, 'Sora Kimura'), mei = agentByName(w, 'Mei Nakamura');
  const task = (await s.api('POST', '/api/w/personal/tasks', { title: 'Rever modelo', assigned_agent_id: sora.id })).data;
  const r1 = await s.api('POST', `/api/w/personal/agents/${sora.id}/archive`, {});
  assert.equal(r1.status, 409); assert.equal(r1.data.error.code, 'agent_has_active_tasks');
  const r2 = await s.api('POST', `/api/w/personal/agents/${sora.id}/archive`, { reassign_to: mei.id });
  assert.equal(r2.status, 200); assert.equal(r2.data.lifecycle_status, 'archived');
  const t2 = (await s.api('GET', `/api/w/personal/tasks/${task.id}`)).data;
  assert.equal(t2.assigned_agent_id, mei.id);
  assert.ok(t2.history.length >= 1);
  // arquivado não aparece na org, mas o registo e a referência persistem
  const org = (await s.api('GET', '/api/w/personal/org')).data;
  assert.ok(!org.agents.find((a) => a.id === sora.id));
  assert.equal((await s.api('GET', `/api/w/personal/agents/${sora.id}`)).data.activity_status, 'arquivado');
});

test('CA02 · ciclos e segundo orquestrador são rejeitados no servidor; cargo não concede permissões', async (t) => {
  const s = await ready(); t.after(() => s.close());
  const w = s.app.world('personal');
  const haruki = agentByName(w, 'Haruki Sato'), mei = agentByName(w, 'Mei Nakamura'), sora = agentByName(w, 'Sora Kimura');
  // Haruki → Mei → Sora: fazer Haruki reportar a Sora cria ciclo
  const cyc = await s.api('PATCH', `/api/w/personal/agents/${haruki.id}`, { manager_agent_id: sora.id, expected_version: haruki.record_version });
  assert.equal(cyc.status, 422); assert.equal(cyc.data.error.code, 'cycle');
  // auto-referência
  assert.equal((await s.api('PATCH', `/api/w/personal/agents/${mei.id}`, { manager_agent_id: mei.id, expected_version: mei.record_version })).data.error.code, 'cycle');
  // segundo orquestrador no mesmo mundo
  const second = await s.api('POST', '/api/w/personal/agents', { display_name: 'Outro Kai', orchestrator_flag: true });
  assert.equal(second.status, 409); assert.equal(second.data.error.code, 'orchestrator_exists');
  // ciclo de unidades
  const units = (await s.api('GET', '/api/w/personal/org')).data.units;
  const a = units[0], b = units[1];
  await s.api('PATCH', `/api/w/personal/units/${b.id}`, { parent_unit_id: a.id, expected_version: b.record_version });
  const cu = await s.api('PATCH', `/api/w/personal/units/${a.id}`, { parent_unit_id: b.id, expected_version: a.record_version });
  assert.equal(cu.data.error.code, 'cycle');
  // CEO (cargo) sem permissão explícita para outro mundo/escopo: delegar a quem está fora do escopo → negado
  const takumi = agentByName(w, 'Takumi Mori');
  const denied = await s.api('POST', '/api/w/personal/tasks', { title: 'x', assigned_agent_id: mei.id, delegated_by: takumi.id });
  assert.equal(denied.status, 403); assert.equal(denied.data.error.code, 'delegation_denied');
});

test('CA03 · delegação só dentro do escopo concedido; profundidade e prioridade proposta vs aprovada', async (t) => {
  const s = await ready(); t.after(() => s.close());
  const w = s.app.world('personal');
  const kai = agentByName(w, 'Kai Pessoal'), rin = agentByName(w, 'Rin Okada'), mei = agentByName(w, 'Mei Nakamura'), ponte = agentByName(w, 'Ponte');
  const parent = (await s.api('POST', '/api/w/personal/tasks', { title: 'Objetivo-mãe', assigned_agent_id: kai.id })).data;
  const ok = await s.api('POST', '/api/w/personal/tasks', { title: 'Filha', parent_task_id: parent.id, assigned_agent_id: rin.id, delegated_by: kai.id, proposed_priority: 2 });
  assert.equal(ok.status, 201); assert.equal(ok.data.delegated_by, kai.id); assert.equal(ok.data.parent_task_id, parent.id); assert.equal(ok.data.depth, 1);
  assert.ok(ok.data.scope_ref, 'guarda a permissão que autorizou');
  assert.equal(ok.data.approved_priority, null);
  const pr = await s.api('POST', `/api/w/personal/tasks/${ok.data.id}/priority`, { approved_priority: 1, expected_version: ok.data.record_version });
  assert.equal(pr.data.proposed_priority, 2); assert.equal(pr.data.approved_priority, 1);
  // Mei só tem escopo na sua unidade (BI): delegar à Ponte (Execução) é negado
  const out = await s.api('POST', '/api/w/personal/tasks', { title: 'Fora de escopo', assigned_agent_id: ponte.id, delegated_by: mei.id });
  assert.equal(out.status, 403);
  // revogar a permissão do Kai → negado por omissão
  const perms = (await s.api('GET', '/api/w/personal/permissions')).data.filter((p) => p.principal_id === kai.id);
  for (const p of perms) await s.api('POST', `/api/w/personal/permissions/${p.id}/revoke`);
  const after = await s.api('POST', '/api/w/personal/tasks', { title: 'Depois da revogação', assigned_agent_id: rin.id, delegated_by: kai.id });
  assert.equal(after.status, 403); assert.equal(after.data.error.code, 'delegation_denied');
  // a negação ficou auditada
  const audit = (await s.api('GET', '/api/w/personal/audit?limit=20')).data;
  assert.ok(audit.some((e) => e.action === 'task.delegate' && e.result === 'denied'));
});

test('CA12 · transições inválidas, conclusão sem prova, saltar aprovação e executar cancelada são rejeitadas; retry conserva falha', async (t) => {
  const s = await ready(); t.after(() => s.close());
  const w = s.app.world('personal');
  const apolo = agentByName(w, 'Apolo');
  const tk = (await s.api('POST', '/api/w/personal/tasks', { title: 'Plano semanal', assigned_agent_id: apolo.id })).data;
  assert.equal(tk.state, 'assigned');
  for (const to of ['completed', 'running', 'failed']) {
    const r = await s.api('POST', `/api/w/personal/tasks/${tk.id}/transition`, { to });
    assert.equal(r.status, 422, `to=${to}`); assert.equal(r.data.error.code, 'transition_not_allowed');
  }
  assert.equal((await s.api('POST', `/api/w/personal/tasks/${tk.id}/transition`, { to: 'awaiting_approval' })).data.error.code, 'invalid_transition');
  // fluxo manual com prova
  assert.equal((await s.api('POST', `/api/w/personal/tasks/${tk.id}/start-manual`)).data.state, 'running');
  assert.equal((await s.api('POST', `/api/w/personal/tasks/${tk.id}/complete-manual`, { note: '' })).status, 400);
  const done = await s.api('POST', `/api/w/personal/tasks/${tk.id}/complete-manual`, { note: 'Plano de 3 sessões criado (fictício).' });
  assert.equal(done.data.state, 'completed');
  const d = (await s.api('GET', `/api/w/personal/tasks/${tk.id}`)).data;
  assert.equal(d.evidence.length, 1); assert.equal(d.evidence[0].kind, 'manual_note'); assert.equal(d.evidence[0].mode, 'manual');
  // terminal não reabre
  assert.equal((await s.api('POST', `/api/w/personal/tasks/${tk.id}/transition`, { to: 'pending' })).data.error.code, 'invalid_transition');
  // cancelada não reexecuta
  const c = (await s.api('POST', '/api/w/personal/tasks', { title: 'A cancelar', assigned_agent_id: apolo.id })).data;
  await s.api('POST', `/api/w/personal/tasks/${c.id}/transition`, { to: 'cancelled' });
  assert.equal((await s.api('POST', `/api/w/personal/tasks/${c.id}/start-manual`)).status, 422);
  assert.equal((await s.api('POST', `/api/w/personal/tasks/${c.id}/transition`, { to: 'assigned', assigned_agent_id: apolo.id })).data.error.code, 'invalid_transition');
  // bloqueio exige motivo; desbloqueio exige nota
  const b = (await s.api('POST', '/api/w/personal/tasks', { title: 'Bloqueável', assigned_agent_id: apolo.id })).data;
  assert.equal((await s.api('POST', `/api/w/personal/tasks/${b.id}/transition`, { to: 'blocked' })).data.error.code, 'note_required');
  assert.equal((await s.api('POST', `/api/w/personal/tasks/${b.id}/transition`, { to: 'blocked', note: 'à espera de dados' })).data.state, 'blocked');
  assert.equal((await s.api('POST', `/api/w/personal/tasks/${b.id}/transition`, { to: 'pending' })).data.error.code, 'note_required');
  // a negação de "concluir sem prova" ficou auditada (mesmo com rollback)
  const audit = (await s.api('GET', '/api/w/personal/audit?limit=100')).data;
  assert.ok(audit.some((e) => e.action === 'task.transition' && e.result === 'denied'));
});

test('Tarefas: idempotência, concorrência por agente, agente desativado e capacidade em falta', async (t) => {
  const s = await ready(); t.after(() => s.close());
  const w = s.app.world('personal');
  const rin = agentByName(w, 'Rin Okada'), apolo = agentByName(w, 'Apolo');
  const body = { title: 'Idem', assigned_agent_id: apolo.id, idempotency_key: 'k1' };
  const a = (await s.api('POST', '/api/w/personal/tasks', body)).data;
  const b = (await s.api('POST', '/api/w/personal/tasks', body)).data;
  assert.equal(a.id, b.id); assert.equal(b.idempotent_replay, true);
  assert.equal((await s.api('POST', '/api/w/personal/tasks', { ...body, title: 'Outro título' })).data.error.code, 'idempotency_key_reuse');
  // capacidade em falta
  const art = (await s.api('POST', '/api/w/personal/artifacts', { name: 'a.csv', kind: 'csv', content: 'a,b\n1,2\n' })).data;
  const lack = await s.api('POST', '/api/w/personal/tasks', { title: 'x', capability: 'csv.validate', assigned_agent_id: apolo.id, input_refs: [art.id], config: { numeric_column: 'b' } });
  assert.equal(lack.data.error.code, 'agent_lacks_capability');
  // agente desativado não recebe trabalho
  await s.api('PATCH', `/api/w/personal/agents/${rin.id}`, { lifecycle_status: 'deactivated', expected_version: rin.record_version });
  const off = await s.api('POST', '/api/w/personal/tasks', { title: 'x', capability: 'csv.validate', assigned_agent_id: rin.id, input_refs: [art.id], config: { numeric_column: 'b' } });
  assert.equal(off.data.error.code, 'agent_inactive');
  // limite de concorrência
  await s.api('PATCH', '/api/w/personal/settings', { max_active_tasks_per_agent: 2 });
  await s.api('POST', '/api/w/personal/tasks', { title: 'c1', assigned_agent_id: apolo.id });
  const lim = await s.api('POST', '/api/w/personal/tasks', { title: 'c2', assigned_agent_id: apolo.id });
  assert.equal(lim.status, 429);
});
