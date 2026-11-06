// Organização: OrgUnit, Role, Agent (RF01). Sem código novo por função: tudo é dado editável.
import { newId, clock, json, parseJson, conflict, bad, notFound, unprocessable } from '../lib/util.js';
import { tx } from '../lib/db.js';
import { str, int, oneOf, strList, requireBody, updateVersioned, mustGet, mapConstraint } from './common.js';
import { audit } from './audit.js';
import { CAPABILITIES } from './capabilities.js';

const ACTIVE_TASK_STATES = "('draft','pending','assigned','running','awaiting_approval','blocked')";
const base = (w) => ({ id: null, world_id: w.id, now: clock.iso() });

// ---------- leitura ----------
const agentOut = (w, a, roleMap) => ({
  ...a,
  capability_ids: parseJson(a.capability_ids, []),
  orchestrator_flag: Boolean(a.orchestrator_flag),
  appearance: parseJson(a.appearance_ref, null),
  role_ids: roleMap.get(a.id) || [],
  ...activity(w, a),
});

// Estado de actividade DERIVADO da BD — nunca guardado, nunca simulado (RF04/CA05).
function activity(w, a) {
  if (a.lifecycle_status !== 'active') return { activity_status: a.lifecycle_status === 'archived' ? 'arquivado' : 'inativo', active_attempts: 0, blocked_tasks: 0 };
  const act = w.db.prepare(`SELECT COUNT(*) c FROM execution_attempts x JOIN tasks t ON t.id = x.task_id
                            WHERE x.state='running' AND t.assigned_agent_id = ?`).get(a.id).c;
  const blocked = w.db.prepare("SELECT COUNT(*) c FROM tasks WHERE assigned_agent_id = ? AND state IN ('blocked','failed')").get(a.id).c;
  const status = act > 0 ? 'ocupado' : blocked > 0 ? 'bloqueado' : 'disponivel';
  return { activity_status: status, active_attempts: act, blocked_tasks: blocked };
}

export function loadOrg(w, { includeArchived = false } = {}) {
  const lifecycle = includeArchived ? '' : "AND lifecycle_status <> 'archived'";
  const roleMap = new Map();
  for (const r of w.db.prepare('SELECT agent_id, role_id FROM agent_roles').all()) {
    if (!roleMap.has(r.agent_id)) roleMap.set(r.agent_id, []);
    roleMap.get(r.agent_id).push(r.role_id);
  }
  const units = w.db.prepare(`SELECT * FROM org_units WHERE world_id = ? ${lifecycle} ORDER BY plot, name`).all(w.id);
  const roles = w.db.prepare(`SELECT * FROM roles WHERE world_id = ? ${lifecycle} ORDER BY name`).all(w.id)
    .map((r) => ({ ...r, responsibilities: parseJson(r.responsibilities, []), limits: parseJson(r.limits, []), default_capability_proposals: parseJson(r.default_capability_proposals, []) }));
  const agents = w.db.prepare(`SELECT * FROM agents WHERE world_id = ? ${lifecycle} ORDER BY orchestrator_flag DESC, display_name`).all(w.id)
    .map((a) => agentOut(w, a, roleMap));
  return { units, roles, agents };
}

export function getAgent(w, id) {
  const a = mustGet(w, 'agents', id, 'Agente');
  const roleMap = new Map([[a.id, w.db.prepare('SELECT role_id FROM agent_roles WHERE agent_id = ?').all(a.id).map((r) => r.role_id)]]);
  return agentOut(w, a, roleMap);
}

// ---------- validações de grafo ----------
function wouldCycle(w, table, col, id, newParent) {
  let cur = newParent;
  const seen = new Set([id]);
  while (cur) {
    if (seen.has(cur)) return true;
    seen.add(cur);
    const r = w.db.prepare(`SELECT ${col} p FROM ${table} WHERE id = ? AND world_id = ?`).get(cur, w.id);
    cur = r ? r.p : null;
  }
  return false;
}
function sameWorldRef(w, table, id, label) {
  if (!id) return null;
  const r = w.db.prepare(`SELECT id, lifecycle_status FROM ${table} WHERE id = ? AND world_id = ?`).get(id, w.id);
  if (!r) throw bad(`${label} inválido para este mundo`, 'invalid_reference', { field: label });
  if (r.lifecycle_status === 'archived') throw unprocessable(`${label} está arquivado`, 'archived_reference');
  return id;
}

// ---------- OrgUnit ----------
export function createUnit(w, actor, body) {
  requireBody(body);
  const d = base(w); d.id = newId('unit');
  const parent = sameWorldRef(w, 'org_units', body.parent_unit_id, 'parent_unit_id');
  const resp = body.responsible_agent_id ? sameWorldRef(w, 'agents', body.responsible_agent_id, 'responsible_agent_id') : null;
  const name = str(body.name, 'name', { required: true, max: 80 });
  const plot = int(body.plot, 'plot', { min: 0, max: 40 }) ?? w.db.prepare('SELECT COALESCE(MAX(plot),-1)+1 n FROM org_units WHERE world_id = ?').get(w.id).n;
  return tx(w.db, () => {
    w.db.prepare(`INSERT INTO org_units(id,world_id,account_id,name,purpose,parent_unit_id,responsible_agent_id,theme,kanji,plot,created_at,updated_at)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?)`).run(d.id, w.id, w.accountId, name, str(body.purpose, 'purpose', { max: 400 }) || '', parent, resp,
      oneOf(body.theme, THEMES, 'theme') || 'hall', str(body.kanji, 'kanji', { max: 6 }) || '', plot, d.now, d.now);
    audit(w, { actor: actor.ref, action: 'unit.create', resource: d.id });
    return mustGet(w, 'org_units', d.id);
  });
}
export const THEMES = ['tower', 'lab', 'dojo', 'workshop', 'garden', 'vault', 'hall', 'dock'];

export function updateUnit(w, actor, id, body) {
  requireBody(body);
  const cur = mustGet(w, 'org_units', id, 'Unidade');
  const sets = {};
  if (body.name !== undefined) sets.name = str(body.name, 'name', { required: true, max: 80 });
  if (body.purpose !== undefined) sets.purpose = str(body.purpose, 'purpose', { max: 400 });
  if (body.theme !== undefined) sets.theme = oneOf(body.theme, THEMES, 'theme');
  if (body.kanji !== undefined) sets.kanji = str(body.kanji, 'kanji', { max: 6 });
  if (body.plot !== undefined) sets.plot = int(body.plot, 'plot', { min: 0, max: 40 });
  if (body.responsible_agent_id !== undefined) sets.responsible_agent_id = body.responsible_agent_id ? sameWorldRef(w, 'agents', body.responsible_agent_id, 'responsible_agent_id') : null;
  if (body.parent_unit_id !== undefined) {
    const p = body.parent_unit_id ? sameWorldRef(w, 'org_units', body.parent_unit_id, 'parent_unit_id') : null;
    if (p && wouldCycle(w, 'org_units', 'parent_unit_id', id, p)) throw unprocessable('A hierarquia de unidades não pode ter ciclos.', 'cycle');
    sets.parent_unit_id = p;
  }
  return tx(w.db, () => {
    updateVersioned(w, 'org_units', id, body.expected_version, sets);
    audit(w, { actor: actor.ref, action: 'unit.update', resource: cur.id });
    return mustGet(w, 'org_units', id);
  });
}

export function archiveUnit(w, actor, id, expectedVersion) {
  mustGet(w, 'org_units', id, 'Unidade');
  const active = w.db.prepare("SELECT COUNT(*) c FROM agents WHERE org_unit_id = ? AND lifecycle_status <> 'archived'").get(id).c;
  const kids = w.db.prepare("SELECT COUNT(*) c FROM org_units WHERE parent_unit_id = ? AND lifecycle_status = 'active'").get(id).c;
  if (active || kids) throw conflict('A unidade ainda tem agentes ou subunidades activos: move-os primeiro.', 'unit_not_empty', { agents: active, subunits: kids });
  return tx(w.db, () => {
    updateVersioned(w, 'org_units', id, expectedVersion, { lifecycle_status: 'archived' });
    audit(w, { actor: actor.ref, action: 'unit.archive', resource: id });
    return mustGet(w, 'org_units', id);
  });
}

// ---------- Role ----------
export function createRole(w, actor, body) {
  requireBody(body);
  const id = newId('role'), now = clock.iso();
  const parent = sameWorldRef(w, 'roles', body.parent_role_id, 'parent_role_id');
  const caps = strList(body.default_capability_proposals, 'default_capability_proposals') || [];
  for (const c of caps) if (!CAPABILITIES[c]) throw bad(`Capacidade desconhecida: ${c}`, 'unknown_capability');
  return tx(w.db, () => {
    w.db.prepare(`INSERT INTO roles(id,world_id,account_id,name,mission,responsibilities,limits,default_capability_proposals,parent_role_id,tier,created_at,updated_at)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?)`).run(id, w.id, w.accountId, str(body.name, 'name', { required: true, max: 80 }),
      str(body.mission, 'mission', { max: 600 }) || '', json(strList(body.responsibilities, 'responsibilities') || []),
      json(strList(body.limits, 'limits') || []), json(caps), parent,
      oneOf(body.tier, ['ceo', 'c_level', 'director', 'specialist', 'orchestrator', 'control'], 'tier') || 'specialist', now, now);
    audit(w, { actor: actor.ref, action: 'role.create', resource: id });
    return mustGet(w, 'roles', id);
  });
}

export function updateRole(w, actor, id, body) {
  requireBody(body);
  mustGet(w, 'roles', id, 'Função');
  const sets = {};
  if (body.name !== undefined) sets.name = str(body.name, 'name', { required: true, max: 80 });
  if (body.mission !== undefined) sets.mission = str(body.mission, 'mission', { max: 600 });
  if (body.responsibilities !== undefined) sets.responsibilities = json(strList(body.responsibilities, 'responsibilities'));
  if (body.limits !== undefined) sets.limits = json(strList(body.limits, 'limits'));
  if (body.tier !== undefined) sets.tier = oneOf(body.tier, ['ceo', 'c_level', 'director', 'specialist', 'orchestrator', 'control'], 'tier');
  if (body.default_capability_proposals !== undefined) {
    const caps = strList(body.default_capability_proposals, 'default_capability_proposals');
    for (const c of caps) if (!CAPABILITIES[c]) throw bad(`Capacidade desconhecida: ${c}`, 'unknown_capability');
    sets.default_capability_proposals = json(caps);
  }
  if (body.parent_role_id !== undefined) {
    const p = body.parent_role_id ? sameWorldRef(w, 'roles', body.parent_role_id, 'parent_role_id') : null;
    if (p && wouldCycle(w, 'roles', 'parent_role_id', id, p)) throw unprocessable('A hierarquia de funções não pode ter ciclos.', 'cycle');
    sets.parent_role_id = p;
  }
  return tx(w.db, () => {
    updateVersioned(w, 'roles', id, body.expected_version, sets);
    audit(w, { actor: actor.ref, action: 'role.update', resource: id });
    return mustGet(w, 'roles', id);
  });
}

export function archiveRole(w, actor, id, expectedVersion) {
  mustGet(w, 'roles', id, 'Função');
  const used = w.db.prepare(`SELECT COUNT(*) c FROM agent_roles ar JOIN agents a ON a.id = ar.agent_id
                             WHERE ar.role_id = ? AND a.lifecycle_status <> 'archived'`).get(id).c;
  if (used) throw conflict('Há agentes com esta função: retira-a primeiro.', 'role_in_use', { agents: used });
  return tx(w.db, () => {
    updateVersioned(w, 'roles', id, expectedVersion, { lifecycle_status: 'archived' });
    audit(w, { actor: actor.ref, action: 'role.archive', resource: id });
    return mustGet(w, 'roles', id);
  });
}

// ---------- Agent ----------
function validateCaps(caps) {
  for (const c of caps) if (!CAPABILITIES[c]) throw bad(`Capacidade desconhecida: ${c}`, 'unknown_capability');
}
function setRoles(w, agentId, roleIds) {
  w.db.prepare('DELETE FROM agent_roles WHERE agent_id = ?').run(agentId);
  for (const rid of roleIds) {
    sameWorldRef(w, 'roles', rid, 'role_ids');
    w.db.prepare('INSERT OR IGNORE INTO agent_roles(agent_id, role_id) VALUES (?,?)').run(agentId, rid);
  }
}
function checkManager(w, id, managerId) {
  if (!managerId) return null;
  sameWorldRef(w, 'agents', managerId, 'manager_agent_id');
  if (managerId === id) throw unprocessable('Um agente não pode reportar a si próprio.', 'cycle');
  if (id && wouldCycle(w, 'agents', 'manager_agent_id', id, managerId)) throw unprocessable('A cadeia hierárquica não pode ter ciclos.', 'cycle');
  return managerId;
}

export function createAgent(w, actor, body) {
  requireBody(body);
  const id = newId('agt'), now = clock.iso();
  const caps = strList(body.capability_ids, 'capability_ids') || [];
  validateCaps(caps);
  const unit = sameWorldRef(w, 'org_units', body.org_unit_id, 'org_unit_id');
  const manager = checkManager(w, null, body.manager_agent_id);
  const roleIds = strList(body.role_ids, 'role_ids') || [];
  const appearance = body.appearance === undefined ? null : json(body.appearance);
  try {
    return tx(w.db, () => {
      w.db.prepare(`INSERT INTO agents(id,world_id,account_id,display_name,title,org_unit_id,manager_agent_id,description,capability_ids,policy_ref,
          lifecycle_status,appearance_ref,orchestrator_flag,origin,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`).run(id, w.id, w.accountId, str(body.display_name, 'display_name', { required: true, max: 60 }),
        str(body.title, 'title', { max: 80 }) || '', unit, manager, str(body.description, 'description', { max: 800 }) || '', json(caps),
        str(body.policy_ref, 'policy_ref', { max: 80 }) || null, 'active', appearance, body.orchestrator_flag ? 1 : 0,
        str(body.origin, 'origin', { max: 40 }) || 'app', now, now);
      setRoles(w, id, roleIds);
      audit(w, { actor: actor.ref, action: 'agent.create', resource: id });
      return getAgent(w, id);
    });
  } catch (e) { throw mapConstraint(e); }
}

export function updateAgent(w, actor, id, body) {
  requireBody(body);
  const cur = mustGet(w, 'agents', id, 'Agente');
  const sets = {};
  if (body.display_name !== undefined) sets.display_name = str(body.display_name, 'display_name', { required: true, max: 60 });
  if (body.title !== undefined) sets.title = str(body.title, 'title', { max: 80 });
  if (body.description !== undefined) sets.description = str(body.description, 'description', { max: 800 });
  if (body.org_unit_id !== undefined) sets.org_unit_id = body.org_unit_id ? sameWorldRef(w, 'org_units', body.org_unit_id, 'org_unit_id') : null;
  if (body.manager_agent_id !== undefined) sets.manager_agent_id = checkManager(w, id, body.manager_agent_id);
  if (body.capability_ids !== undefined) { const caps = strList(body.capability_ids, 'capability_ids'); validateCaps(caps); sets.capability_ids = json(caps); }
  if (body.appearance !== undefined) sets.appearance_ref = json(body.appearance);
  if (body.orchestrator_flag !== undefined) sets.orchestrator_flag = body.orchestrator_flag ? 1 : 0;
  if (body.lifecycle_status !== undefined) {
    sets.lifecycle_status = oneOf(body.lifecycle_status, ['active', 'deactivated'], 'lifecycle_status');
  }
  try {
    return tx(w.db, () => {
      updateVersioned(w, 'agents', id, body.expected_version, sets);
      if (body.role_ids !== undefined) setRoles(w, id, strList(body.role_ids, 'role_ids'));
      audit(w, { actor: actor.ref, action: 'agent.update', resource: cur.id,
        reason: sets.lifecycle_status ? `lifecycle:${sets.lifecycle_status}` : undefined });
      return getAgent(w, id);
    });
  } catch (e) { throw mapConstraint(e); }
}

/**
 * Arquivar preserva histórico e referências. Com tarefas activas exige
 * cancelar ou reencaminhar explicitamente (CA01).
 */
export function archiveAgent(w, actor, id, { expected_version, reassign_to, cancel_active } = {}) {
  const a = mustGet(w, 'agents', id, 'Agente');
  const active = w.db.prepare(`SELECT id FROM tasks WHERE assigned_agent_id = ? AND state IN ${ACTIVE_TASK_STATES}`).all(id);
  if (active.length && !reassign_to && !cancel_active) {
    throw conflict('O agente tem tarefas activas: reencaminha (reassign_to) ou cancela (cancel_active).', 'agent_has_active_tasks', { tasks: active.map((t) => t.id) });
  }
  if (reassign_to) {
    if (reassign_to === id) throw bad('Destino de reencaminhamento inválido', 'invalid_reference');
    const dest = mustGet(w, 'agents', reassign_to, 'Agente de destino');
    if (dest.lifecycle_status !== 'active') throw unprocessable('O agente de destino não está activo.', 'inactive_target');
  }
  try {
    return tx(w.db, () => {
      const now = clock.iso();
      for (const t of active) {
        const running = w.db.prepare("SELECT id FROM execution_attempts WHERE task_id = ? AND state='running'").get(t.id);
        if (running) {
          w.db.prepare("UPDATE execution_attempts SET state='cancelled', ended_at=?, updated_at=?, error_code='agent_archived' WHERE id=?").run(now, now, running.id);
        }
        if (reassign_to) {
          w.db.prepare("UPDATE tasks SET assigned_agent_id=?, state=CASE WHEN state='running' THEN 'assigned' ELSE state END, updated_at=?, record_version=record_version+1 WHERE id=?").run(reassign_to, now, t.id);
          audit(w, { actor: actor.ref, action: 'task.reassign', resource: t.id, reason: 'agent_archived' });
        } else {
          w.db.prepare("UPDATE tasks SET state='cancelled', error_code='agent_archived', updated_at=?, record_version=record_version+1 WHERE id=?").run(now, t.id);
          audit(w, { actor: actor.ref, action: 'task.cancel', resource: t.id, reason: 'agent_archived' });
        }
      }
      // Responsável de unidade arquivado deixa de o ser (a unidade mantém-se).
      w.db.prepare('UPDATE org_units SET responsible_agent_id = NULL WHERE responsible_agent_id = ?').run(id);
      updateVersioned(w, 'agents', id, expected_version ?? a.record_version, { lifecycle_status: 'archived', orchestrator_flag: 0 });
      audit(w, { actor: actor.ref, action: 'agent.archive', resource: id });
      return getAgent(w, id);
    });
  } catch (e) { throw mapConstraint(e); }
}

export function getOrchestrator(w) {
  return w.db.prepare("SELECT * FROM agents WHERE world_id = ? AND orchestrator_flag = 1 AND lifecycle_status = 'active'").get(w.id) || null;
}
