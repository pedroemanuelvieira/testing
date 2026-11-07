// Equipa do Dojo no mundo profissional (brief Dojo_layout_brief.md — dados fictícios).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createApp } from '../server/app.js';
import { seedDojoV1 } from '../server/seed-dojo.js';
import { loadOrg } from '../server/modules/org.js';

const DOJO = ['Amaterasu', 'Tsukuyomi', 'Susanoo', 'Hachiman', 'Tetsuo', 'Kenshin', 'Raiden', 'Kai Profissional', 'Mugen', 'pedro-lab', 'Auditor', 'Todoroki'];

test('Dojo: 12 agentes, 9 salas, funções, um só orquestrador; 9xx atualizados sem duplicar', (t) => {
  const dir = mkdtempSync(join(tmpdir(), 'dojo-')); t.after(() => rmSync(dir, { recursive: true, force: true }));
  const app = createApp({ dataDir: dir, passcode: 'x' }); t.after(() => app.close());
  const w = app.world('professional');
  const o = loadOrg(w);
  const names = o.agents.map((a) => a.display_name);
  for (const n of DOJO) assert.ok(names.includes(n), n);
  for (const old of ['Turing', 'Arquimedes', 'Atlas BI']) assert.ok(!names.includes(old), `${old} foi renomeado, não duplicado`);
  assert.equal(o.agents.filter((a) => a.orchestrator_flag).length, 1);
  assert.equal(o.agents.find((a) => a.orchestrator_flag).display_name, 'Kai Profissional', 'D2/D3: orquestrador continua o Kai');
  assert.equal(o.units.length, 9, 'só as 9 salas ativas; unidades antigas arquivadas');
  assert.equal(o.agents.find((a) => a.display_name === 'Todoroki').activity_status, 'inativo', 'Em pausa → inativo');
  assert.equal(o.agents.find((a) => a.display_name === 'Tsukuyomi').manager_agent_id, o.agents.find((a) => a.display_name === 'Amaterasu').id);
  const tetsuo = o.agents.find((a) => a.display_name === 'Tetsuo');
  assert.match(tetsuo.title, /901/); assert.equal(tetsuo.org_unit_id, o.units.find((u) => u.name === 'Sala do Futuro').id);
  // nada disto entra no mundo pessoal
  assert.ok(!loadOrg(app.world('personal')).agents.some((a) => ['Amaterasu', 'Tetsuo', 'Raiden'].includes(a.display_name)));
});

test('Dojo: tarefas nos estados do brief, pelo caminho legítimo (prova na concluída)', (t) => {
  const dir = mkdtempSync(join(tmpdir(), 'dojo-')); t.after(() => rmSync(dir, { recursive: true, force: true }));
  const app = createApp({ dataDir: dir, passcode: 'x' }); t.after(() => app.close());
  const w = app.world('professional');
  const st = Object.fromEntries(w.db.prepare('SELECT title, state FROM tasks').all().map((r) => [r.title, r.state]));
  assert.deepEqual(st, {
    'Rever avisos do modelo de qualidade': 'running', 'Fechar ligação de referências': 'blocked',
    'Preparar demo do portal': 'assigned', 'Atualizar guia rápido': 'assigned', 'Rever regras do ciclo de vida': 'completed',
  });
  const done = w.db.prepare("SELECT id FROM tasks WHERE state='completed'").get();
  const ev = w.db.prepare('SELECT kind, mode FROM evidence WHERE task_id=?').all(done.id);
  assert.deepEqual(ev.map((e) => [e.kind, e.mode]), [['manual_note', 'manual']], 'concluída só com prova manual');
});

test('Dojo: atualização idempotente (repetir não duplica) e aplicada uma vez em BD existente', (t) => {
  const dir = mkdtempSync(join(tmpdir(), 'dojo-')); t.after(() => rmSync(dir, { recursive: true, force: true }));
  let app = createApp({ dataDir: dir, passcode: 'x' });
  const count = (w) => ['agents', 'org_units', 'roles', 'tasks', 'permissions', 'evidence'].map((x) => w.db.prepare(`SELECT COUNT(*) c FROM ${x}`).get().c);
  const before = count(app.world('professional'));
  seedDojoV1(app.world('professional')); // repetição forçada (ex.: falha a meio)
  assert.deepEqual(count(app.world('professional')), before);
  app.close();
  app = createApp({ dataDir: dir, passcode: 'x' }); t.after(() => app.close());
  assert.deepEqual(count(app.world('professional')), before, 'reinício não reaplica');
});
