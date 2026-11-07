// Rotinas agendadas, painel «Hoje» e projetos (Dojo · brief). Relógio controlado.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { startServer, agentByName } from './helpers.js';
import { clock } from '../server/lib/util.js';
import { slotsForDay, lisbonToUtc, nextSlot, cadenceLabel } from '../server/modules/schedule.js';

const WED_1030 = Date.parse('2026-11-04T10:30:00Z'); // quarta, Lisboa = UTC em novembro

test('Agenda: dias úteis, semanal e horário de verão de Lisboa', () => {
  assert.equal(slotsForDay({ kind: 'weekdays', times: ['09:00'] }, Date.parse('2026-11-07T12:00:00Z')).length, 0, 'sábado sem slots');
  assert.equal(new Date(lisbonToUtc(2026, 7, 1, 9, 0)).toISOString(), '2026-07-01T08:00:00.000Z', 'verão = UTC+1');
  assert.equal(new Date(nextSlot({ kind: 'weekly', weekday: 2, times: ['09:07'] }, WED_1030)).toISOString(), '2026-11-10T09:07:00.000Z');
  assert.equal(cadenceLabel({ kind: 'weekdays', times: ['09:26'] }), 'dias úteis 09:26');
});

test('Hoje: previstas, registadas, não correu, à espera e por correr — sem inventar execuções', async (t) => {
  const s = await startServer(); t.after(() => s.close());
  clock.set(WED_1030); await s.login();
  const w = s.app.world('personal');
  const kai = agentByName(w, 'Kai Pessoal');
  const r = (await s.api('POST', '/api/w/personal/routines', { agent_id: kai.id, title: 'Briefing', schedule: { kind: 'weekdays', times: ['08:00', '10:00', '18:00'] } })).data;
  assert.deepEqual(r.today.map((x) => x.status), ['missed', 'awaiting', 'pending'], '08:00 >1h sem registo = não correu; 10:00 dentro da tolerância; 18:00 futuro');
  let k = (await s.api('GET', '/api/w/personal/today')).data.kpis;
  assert.deepEqual([k.scheduled, k.recorded, k.failed_or_missed, k.awaiting, k.pending], [3, 0, 1, 1, 1]);
  // registo sem slot explícito → liga ao slot passado mais recente ainda sem registo (10:00)
  const a = (await s.api('POST', `/api/w/personal/routines/${r.id}/runs`, { status: 'warn', note: '2 avisos' })).data;
  assert.equal(a.today[1].status, 'warn');
  const b = (await s.api('POST', `/api/w/personal/routines/${r.id}/runs`, { status: 'ok' })).data;
  assert.equal(b.today[0].status, 'ok', 'o seguinte vai para o slot das 08:00');
  k = (await s.api('GET', '/api/w/personal/today')).data.kpis;
  assert.deepEqual([k.recorded, k.with_warnings, k.failed_or_missed, k.pending], [2, 1, 0, 1]);
  // um registo por slot; nada de slots futuros
  assert.equal((await s.api('POST', `/api/w/personal/routines/${r.id}/runs`, { status: 'ok', slot_at: '2026-11-04T08:00:00.000Z' })).status, 409);
  assert.equal((await s.api('POST', `/api/w/personal/routines/${r.id}/runs`, { status: 'ok', slot_at: '2026-11-04T18:00:00.000Z' })).data.error.code, 'slot_in_future');
  // D1 na nota
  assert.equal((await s.api('POST', `/api/w/personal/routines/${r.id}/runs`, { status: 'ok', slot_at: null, note: 'enviado a ana@empresa-real.pt' })).data.error.code, 'd1_blocked');
  // desativada: sai das previstas
  await s.api('PATCH', `/api/w/personal/routines/${r.id}`, { enabled: false, expected_version: r.record_version });
  assert.equal((await s.api('GET', '/api/w/personal/today')).data.kpis.scheduled, 0);
  // «precisa de mim»: falhas aparecem
  const r2 = (await s.api('POST', '/api/w/personal/routines', { agent_id: kai.id, title: 'Triagem', schedule: { kind: 'daily', times: ['09:00'] } })).data;
  await s.api('POST', `/api/w/personal/routines/${r2.id}/runs`, { status: 'failed', note: 'limite de uso' });
  assert.ok((await s.api('GET', '/api/w/personal/today')).data.needs_me.some((n) => n.kind === 'routine' && n.title === 'Triagem'));
  assert.equal((await s.api('POST', '/api/w/personal/routines', { agent_id: kai.id, title: 'X', schedule: { kind: 'weekly', times: ['25:00'] } })).data.error.code, 'schedule_invalid');
});

test('Projetos: criar, ligar tarefas, isolamento entre mundos e export BI', async (t) => {
  const s = await startServer(); t.after(() => s.close()); await s.login();
  const w = s.app.world('personal');
  const p = (await s.api('POST', '/api/w/personal/projects', { number: '920', title: 'Previsão sintética', kind: 'ml', state: 'preparing', next_step: 'baseline' })).data;
  const tk = (await s.api('POST', '/api/w/personal/tasks', { title: 'Definir baseline', assigned_agent_id: agentByName(w, 'Apolo').id, project_id: p.id })).data;
  assert.equal(tk.project_id, p.id);
  const d = (await s.api('GET', `/api/w/personal/projects/${p.id}`)).data;
  assert.deepEqual(d.tasks.map((x) => x.id), [tk.id]);
  assert.equal((await s.api('PATCH', `/api/w/personal/projects/${p.id}`, { state: 'in_production', expected_version: p.record_version })).data.state, 'in_production');
  assert.equal((await s.api('GET', `/api/w/professional/projects/${p.id}`)).status, 404, 'projeto não atravessa mundos');
  assert.equal((await s.api('POST', '/api/w/personal/tasks', { title: 'x', project_id: (await s.api('GET', '/api/w/professional/projects')).data[0].id })).status, 404);
  for (const tbl of ['fact_routine_run', 'dim_routine', 'dim_project']) assert.equal((await s.raw('GET', `/api/w/personal/bi/export/${tbl}.csv`)).status, 200, tbl);
});

test('Dojo v2: 11 projetos, 9 rotinas com as execuções do brief em slots passados, tarefas ligadas', async (t) => {
  const s = await startServer(); t.after(() => s.close()); await s.login();
  const w = s.app.world('professional');
  const projects = (await s.api('GET', '/api/w/professional/projects')).data;
  assert.equal(projects.length, 11);
  assert.equal(projects.filter((p) => p.state === 'in_production').length, 5);
  const routines = (await s.api('GET', '/api/w/professional/routines')).data;
  assert.equal(routines.length, 9);
  const runs = w.db.prepare('SELECT slot_at, recorded_at, source FROM routine_runs').all();
  assert.equal(runs.length, 7);
  assert.ok(runs.every((r) => r.source === 'import' && Date.parse(r.slot_at) <= clock.now()), 'nunca em slots futuros');
  assert.equal(routines.find((r) => r.title === 'Triagem de mensagens').last_run.status, 'failed');
  assert.equal(routines.find((r) => r.title === 'Vigia do portal').last_run, null, 'sem registo ainda');
  const p910 = projects.find((p) => p.number === '910');
  assert.equal((await s.api('GET', `/api/w/professional/projects/${p910.id}`)).data.tasks[0].title, 'Rever avisos do modelo de qualidade');
});
