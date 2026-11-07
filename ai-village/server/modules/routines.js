// Rotinas agendadas, registos de execução, painel «Hoje» e projetos (incl. ML).
// A app NÃO corre estas rotinas: regista execuções feitas noutro ambiente (manual ou importação),
// e calcula honestamente o que estava previsto, o que foi registado e o que falta (REQUISITOS RF04).
import { newId, clock, json, parseJson, bad, unprocessable, HttpError } from '../lib/util.js';
import { tx } from '../lib/db.js';
import { str, oneOf, requireBody, updateVersioned, mustGet } from './common.js';
import { audit } from './audit.js';
import { classifyD1, d1Notice } from './d1.js';
import { validateSchedule, slotsForDay, nextSlot, lastSlots, cadenceLabel, lisbonDate } from './schedule.js';

export const GRACE_MS = 60 * 60 * 1000; // depois do slot, 1 h «à espera do registo»; depois disso, «não correu»
const SEVERITY = { failed: 6, missed: 5, warn: 4, awaiting: 3, pending: 2, ok: 1, none: 0 };
export const PROJECT_STATES = ['active', 'paused', 'done', 'in_production', 'preparing', 'blocked', 'on_demand'];

function guardText(w, actor, text, what) {
  const c = classifyD1(text || '');
  if (c.blocked) {
    audit(w, { actor: actor.ref, action: `${what}.blocked_d1`, result: 'denied', reason: `d1:${c.categories.join(',')}` });
    throw new HttpError(422, 'd1_blocked', d1Notice(c), { categories: c.categories });
  }
}

// ---------------- projetos ----------------
const projOut = (p) => p;
export function listProjects(w) {
  return w.db.prepare(`SELECT p.*, (SELECT COUNT(*) FROM tasks t WHERE t.project_id=p.id AND t.state NOT IN ('completed','cancelled')) open_tasks,
      (SELECT COUNT(*) FROM tasks t WHERE t.project_id=p.id) total_tasks
    FROM projects p WHERE p.world_id=? AND p.account_id=? AND p.lifecycle_status='active' ORDER BY p.kind DESC, p.number, p.title`).all(w.id, w.accountId).map(projOut);
}
export function getProject(w, id) {
  const p = mustGet(w, 'projects', id, 'Projeto');
  const tasks = w.db.prepare("SELECT id,title,state,assigned_agent_id,due_at FROM tasks WHERE project_id=? ORDER BY CASE state WHEN 'running' THEN 0 WHEN 'blocked' THEN 1 WHEN 'assigned' THEN 2 ELSE 3 END, updated_at DESC").all(id);
  const routines = w.db.prepare("SELECT id,title FROM routines WHERE project_id=? AND lifecycle_status='active'").all(id);
  return { ...p, tasks, routines };
}
function projectFields(body, partial) {
  const f = {};
  if (!partial || body.title !== undefined) f.title = str(body.title, 'title', { required: true, max: 120 });
  if (body.number !== undefined) f.number = str(body.number, 'number', { max: 12 }) || '';
  if (body.kind !== undefined) f.kind = oneOf(body.kind, ['ml', 'general'], 'kind');
  if (body.state !== undefined) f.state = oneOf(body.state, PROJECT_STATES, 'state');
  if (body.cadence !== undefined) f.cadence = str(body.cadence, 'cadence', { max: 60 }) || '';
  if (body.last_point !== undefined) f.last_point = str(body.last_point, 'last_point', { max: 300 }) || '';
  if (body.last_point_status !== undefined) f.last_point_status = oneOf(body.last_point_status, ['ok', 'warn', 'failed', 'none'], 'last_point_status');
  if (body.next_step !== undefined) f.next_step = str(body.next_step, 'next_step', { max: 300 }) || '';
  return f;
}
export function createProject(w, actor, body) {
  requireBody(body);
  const f = projectFields(body, false);
  guardText(w, actor, [f.title, f.last_point, f.next_step].join(' '), 'project');
  const owner = body.owner_agent_id ? mustGet(w, 'agents', body.owner_agent_id, 'Agente dono').id : null;
  const id = newId('prj'), now = clock.iso();
  return tx(w.db, () => {
    w.db.prepare(`INSERT INTO projects(id,world_id,account_id,number,title,kind,state,cadence,last_point,last_point_status,next_step,owner_agent_id,created_at,updated_at)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)`).run(id, w.id, w.accountId, f.number || '', f.title, f.kind || 'general', f.state || 'active', f.cadence || '',
      f.last_point || '', f.last_point_status || 'none', f.next_step || '', owner, now, now);
    audit(w, { actor: actor.ref, action: 'project.create', resource: id });
    return getProject(w, id);
  });
}
export function updateProject(w, actor, id, body) {
  requireBody(body);
  mustGet(w, 'projects', id, 'Projeto');
  const f = projectFields(body, true);
  guardText(w, actor, [f.title, f.last_point, f.next_step].filter(Boolean).join(' '), 'project');
  if (body.owner_agent_id !== undefined) f.owner_agent_id = body.owner_agent_id ? mustGet(w, 'agents', body.owner_agent_id, 'Agente dono').id : null;
  return tx(w.db, () => {
    updateVersioned(w, 'projects', id, body.expected_version, f);
    audit(w, { actor: actor.ref, action: 'project.update', resource: id });
    return getProject(w, id);
  });
}

// ---------------- rotinas ----------------
function runsFor(w, routineId, limit = 20) {
  return w.db.prepare('SELECT * FROM routine_runs WHERE routine_id=? ORDER BY COALESCE(slot_at, recorded_at) DESC LIMIT ?').all(routineId, limit);
}

/** Vista calculada de uma rotina: slots de hoje com estado, última execução, próxima execução e chip de estado. */
export function routineView(w, r, now = clock.now()) {
  const schedule = parseJson(r.schedule, {});
  const runs = runsFor(w, r.id);
  const bySlot = new Map(runs.filter((x) => x.slot_at).map((x) => [Date.parse(x.slot_at), x]));
  const today = r.enabled ? slotsForDay(schedule, now).map((slot) => {
    const run = bySlot.get(slot);
    const status = run ? run.status : slot > now ? 'pending' : now - slot < GRACE_MS ? 'awaiting' : 'missed';
    return { slot_at: new Date(slot).toISOString(), status, note: run?.note || '', recorded_at: run?.recorded_at || null, run_id: run?.id || null };
  }) : [];
  const last = runs[0] || null;
  const passed = today.filter((x) => x.status !== 'pending');
  let chip;
  if (!r.enabled) chip = 'disabled';
  else if (today.length) chip = passed.length ? passed.reduce((a, b) => (SEVERITY[b.status] >= SEVERITY[a.status] ? b : a)).status : 'pending';
  else chip = last ? last.status : 'none';
  const next = r.enabled ? nextSlot(schedule, now) : null;
  return {
    id: r.id, title: r.title, agent_id: r.agent_id, project_id: r.project_id, enabled: Boolean(r.enabled), schedule, cadence: cadenceLabel(schedule),
    record_version: r.record_version, today, chip, next_run_at: next ? new Date(next).toISOString() : null,
    last_run: last ? { status: last.status, note: last.note, slot_at: last.slot_at, recorded_at: last.recorded_at, source: last.source } : null,
  };
}

export function listRoutines(w) {
  return w.db.prepare("SELECT * FROM routines WHERE world_id=? AND account_id=? AND lifecycle_status='active' ORDER BY title").all(w.id, w.accountId).map((r) => routineView(w, r));
}

export function createRoutine(w, actor, body) {
  requireBody(body);
  const title = str(body.title, 'title', { required: true, max: 120 });
  guardText(w, actor, title, 'routine');
  const err = validateSchedule(body.schedule);
  if (err) throw bad(err, 'schedule_invalid');
  const agent = mustGet(w, 'agents', body.agent_id, 'Agente');
  const project = body.project_id ? mustGet(w, 'projects', body.project_id, 'Projeto').id : null;
  const id = newId('rot'), now = clock.iso();
  return tx(w.db, () => {
    w.db.prepare('INSERT INTO routines(id,world_id,account_id,agent_id,project_id,title,schedule,enabled,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)')
      .run(id, w.id, w.accountId, agent.id, project, title, json(body.schedule), body.enabled === false ? 0 : 1, now, now);
    audit(w, { actor: actor.ref, action: 'routine.create', resource: id });
    return routineView(w, mustGet(w, 'routines', id));
  });
}

export function updateRoutine(w, actor, id, body) {
  requireBody(body);
  mustGet(w, 'routines', id, 'Rotina');
  const sets = {};
  if (body.title !== undefined) { sets.title = str(body.title, 'title', { required: true, max: 120 }); guardText(w, actor, sets.title, 'routine'); }
  if (body.schedule !== undefined) { const err = validateSchedule(body.schedule); if (err) throw bad(err, 'schedule_invalid'); sets.schedule = json(body.schedule); }
  if (body.enabled !== undefined) sets.enabled = body.enabled ? 1 : 0;
  if (body.agent_id !== undefined) sets.agent_id = mustGet(w, 'agents', body.agent_id, 'Agente').id;
  if (body.project_id !== undefined) sets.project_id = body.project_id ? mustGet(w, 'projects', body.project_id, 'Projeto').id : null;
  return tx(w.db, () => {
    updateVersioned(w, 'routines', id, body.expected_version, sets);
    audit(w, { actor: actor.ref, action: 'routine.update', resource: id });
    return routineView(w, mustGet(w, 'routines', id));
  });
}

/**
 * Regista uma execução. Por omissão liga-a ao slot mais recente ainda sem registo (≤ agora);
 * `slot_at: null` explícito = execução fora de agenda. Um registo por slot (índice único).
 */
export function recordRun(w, actor, routineId, body, { source = 'manual' } = {}) {
  requireBody(body);
  const r = mustGet(w, 'routines', routineId, 'Rotina');
  const status = oneOf(body.status, ['ok', 'warn', 'failed'], 'status', { required: true });
  const note = str(body.note, 'note', { max: 300 }) || '';
  guardText(w, actor, note, 'routine_run');
  const schedule = parseJson(r.schedule, {});
  const now = clock.now();
  let slot = null;
  if (body.slot_at === null) slot = null;
  else if (body.slot_at !== undefined) {
    const t = Date.parse(body.slot_at);
    if (Number.isNaN(t)) throw bad('slot_at inválido', 'field_invalid');
    if (t > now) throw unprocessable('Não se regista uma execução de um slot futuro.', 'slot_in_future');
    slot = new Date(t).toISOString();
  } else {
    const recorded = new Set(w.db.prepare('SELECT slot_at FROM routine_runs WHERE routine_id=? AND slot_at IS NOT NULL').all(routineId).map((x) => x.slot_at));
    const candidates = lastSlots(schedule, now, 10).reverse().map((x) => new Date(x).toISOString());
    slot = candidates.find((x) => !recorded.has(x)) || null;
  }
  const id = newId('run'), iso = clock.iso();
  try {
    return tx(w.db, () => {
      w.db.prepare('INSERT INTO routine_runs(id,world_id,account_id,routine_id,slot_at,recorded_at,status,note,source,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)')
        .run(id, w.id, w.accountId, routineId, slot, body.recorded_at || iso, status, note, source, iso, iso);
      audit(w, { actor: actor.ref, action: 'routine.run_recorded', resource: routineId, reason: `${status}${slot ? '' : ':fora_de_agenda'}` });
      return routineView(w, mustGet(w, 'routines', routineId));
    });
  } catch (e) {
    if (/UNIQUE/.test(String(e.message))) throw new HttpError(409, 'run_already_recorded', 'Esse slot já tem uma execução registada.');
    throw e;
  }
}

/** Painel «Hoje no portal»: KPIs do dia (hora de Lisboa) + rotinas + linha do tempo. */
export function today(w, now = clock.now()) {
  const routines = listRoutines(w);
  const slots = routines.flatMap((r) => r.today.map((s) => ({ ...s, routine_id: r.id, title: r.title, agent_id: r.agent_id })));
  const count = (st) => slots.filter((s) => s.status === st).length;
  const needsMe = [
    ...routines.filter((r) => ['failed', 'missed'].includes(r.chip)).map((r) => ({ kind: 'routine', id: r.id, title: r.title, status: r.chip })),
    ...w.db.prepare("SELECT id,title,state FROM tasks WHERE world_id=? AND account_id=? AND state IN ('blocked','failed','awaiting_approval')").all(w.id, w.accountId)
      .map((t) => ({ kind: 'task', id: t.id, title: t.title, status: t.state })),
    ...w.db.prepare("SELECT id,summary FROM approvals WHERE world_id=? AND account_id=? AND state='pending'").all(w.id, w.accountId)
      .map((a) => ({ kind: 'approval', id: a.id, title: a.summary, status: 'pending' })),
  ];
  return {
    date: lisbonDate(now), now: new Date(now).toISOString(),
    kpis: {
      scheduled: slots.length, recorded: count('ok') + count('warn') + count('failed'), with_warnings: count('warn'),
      failed_or_missed: count('failed') + count('missed'), awaiting: count('awaiting'), pending: count('pending'),
    },
    routines, slots, needs_me: needsMe,
  };
}
