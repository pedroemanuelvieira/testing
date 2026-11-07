// Atualização do mundo PROFISSIONAL com a equipa do «Dojo» (brief Dojo_layout_brief.md, dados fictícios).
// Idempotente: cada passo verifica se já existe (unidade/função/agente por nome, tarefa por chave),
// para correr tanto em BDs novas como em BDs já semeadas — e para poder ser repetido após falha.
//
// Decisões:
//  - D2/D3: o orquestrador do mundo continua a ser o Kai Profissional. A Amaterasu («Orquestradora:
//    briefing do dia» no Dojo) entra como coordenadora do dia (cargo da app, SEM orchestrator_flag).
//  - Os agentes 9xx que já existiam são os mesmos do Dojo com outro nome de persona: Turing→Tetsuo,
//    Arquimedes→Kenshin, Atlas BI→Raiden. Atualiza-se o registo (histórico preservado), não se duplica.
//  - Salas do Dojo = unidades (edifícios) da vila. As unidades antigas ficam arquivadas se vazias.
//  - Tarefas reproduzem os estados do Dojo pelo caminho legítimo (iniciar, bloquear com nota,
//    concluir com nota = prova manual), nunca escrevendo estados à mão.
import { clock, parseJson } from './lib/util.js';
import { createUnit, createRole, createAgent, updateAgent, updateUnit, archiveUnit } from './modules/org.js';
import { grantPermission, OWNER } from './modules/policy.js';
import { createTask, startManual, completeManual, transitionTask } from './modules/tasks.js';
import { audit } from './modules/audit.js';
import { createProject, createRoutine, recordRun } from './modules/routines.js';
import { lastSlots } from './modules/schedule.js';

const look = (o) => ({ type: 'procedural', ...o });
const ECO_NOTE = ' (Entidade da app que reflete a ficha do Dojo; não é nem altera o agente original.)';

const ROOMS = [
  ['comando', 'Comando', 'Coordenação do dia e briefing.', 'tower', '指令'],
  ['reunioes', 'Sala de Reuniões', 'Triagem de mensagens e pedidos.', 'hall', '会議'],
  ['futuro', 'Sala do Futuro', 'ML, quebras e oportunidades.', 'dojo', '未来'],
  ['bi', 'Estúdio BI', 'Vendas, dashboards e stories de BI.', 'lab', '分析'],
  ['oficina', 'Oficina', 'Automação, ETL e vigia do portal.', 'workshop', '工房'],
  ['kai', 'Sala do Kai', 'Entrada e encaminhamento de pedidos.', 'garden', '案内'],
  ['torii', 'Torii', 'Blueprints e passagem entre mundos (Ponte).', 'dock', '鳥居'],
  ['forja', 'Forja', 'Skills e testes.', 'workshop', '鍛冶'],
  ['conselho', 'Conselho', 'Auditoria independente.', 'vault', '監査'],
];

// [chave, função, nível, missão, capacidades]
const ROLES = [
  ['briefing', 'Coordenadora do dia (briefing)', 'c_level', 'Prepara o briefing do dia e o fecho da semana.', ['ops.briefing', 'strategy.synthesize']],
  ['triagem', 'Triagem de mensagens', 'specialist', 'Triagem de mensagens e pedidos, 4×/dia.', ['ops.triage']],
  ['quebras', 'Quebras e oportunidades', 'specialist', 'Deteta quebras e oportunidades nos dados.', ['bi.insights']],
  ['vendas', 'Vendas da semana', 'specialist', 'Relatório semanal de vendas.', ['bi.sales_weekly']],
  ['ml', 'ML', 'specialist', 'Modelos de ML em produção e em preparação.', ['ds.baseline']],
  ['etl', 'Automação e ETL', 'specialist', 'Saúde do ETL, vigia do portal e arquivista.', ['data.etl', 'impl.build']],
  ['dash', 'Dashboards', 'specialist', 'Dashboards e demo do portal.', ['bi.modeling']],
  ['encaminhamento', 'Entrada e encaminhamento', 'orchestrator', 'Recebe pedidos e encaminha para o agente certo.', ['ops.plan']],
  ['ponte', 'Blueprints e passagem', 'specialist', 'Blueprints higienizados e passagem entre mundos.', ['blueprint.write']],
  ['lab', 'Skills e testes', 'specialist', 'Desenha e testa skills.', ['skills.test']],
  ['auditoria', 'Auditoria', 'control', 'Auditoria independente da equipa.', ['control.review']],
];

// [nome no Dojo, nº, sala, função, nome antigo na app (se existir), aparência, ativo?]
const AGENTS = [
  ['Amaterasu', 'D01', 'comando', 'briefing', null, look({ gender: 'f', skin: 1, hair: '#14121a', style: 'long', eyes: '#2a1b10', outfit: 'kimono', accent: '#f4c24a', glasses: false }), true],
  ['Tsukuyomi', 'D02', 'reunioes', 'triagem', null, look({ gender: 'm', skin: 1, hair: '#c9c9d1', style: 'sidepart', eyes: '#1f2937', outfit: 'haori', accent: '#a78bfa', glasses: false }), true],
  ['Susanoo', 'D03', 'futuro', 'quebras', null, look({ gender: 'm', skin: 3, hair: '#14121a', style: 'spiky', eyes: '#2a1b10', outfit: 'techwear', accent: '#60a5fa', glasses: false }), true],
  ['Hachiman', 'D04', 'bi', 'vendas', null, look({ gender: 'm', skin: 2, hair: '#2a1b14', style: 'short', eyes: '#3a2a1c', outfit: 'suit', accent: '#34d399', glasses: true }), true],
  ['Tetsuo', '901', 'futuro', 'ml', 'Turing', null, true],
  ['Kenshin', '900', 'oficina', 'etl', 'Arquimedes', null, true],
  ['Raiden', '903', 'bi', 'dash', 'Atlas BI', null, true],
  ['Kai Profissional', '00', 'kai', 'encaminhamento', 'Kai Profissional', null, true],
  ['Mugen', '01', 'torii', 'ponte', null, look({ gender: 'm', skin: 4, hair: '#3a2417', style: 'undercut', eyes: '#3a2418', outfit: 'haori', accent: '#ff5a4d', glasses: false }), true],
  ['pedro-lab', 'LAB', 'forja', 'lab', null, look({ gender: 'm', skin: 2, hair: '#1b1b22', style: 'buzz', eyes: '#2a2018', outfit: 'labcoat', accent: '#22d3ee', glasses: true }), true],
  ['Auditor', '800', 'conselho', 'auditoria', null, look({ gender: 'f', skin: 2, hair: '#1a1a1f', style: 'bun', eyes: '#222a35', outfit: 'suit', accent: '#94a3b8', glasses: true }), true],
  ['Todoroki', 'D05', 'oficina', 'etl', null, look({ gender: 'm', skin: 5, hair: '#161312', style: 'short', eyes: '#2a1d14', outfit: 'hoodie', accent: '#fb923c', glasses: false }), false],
];
const RESPONSIBLE = { comando: 'Amaterasu', reunioes: 'Tsukuyomi', futuro: 'Tetsuo', bi: 'Raiden', oficina: 'Kenshin', kai: 'Kai Profissional', torii: 'Mugen', forja: 'pedro-lab', conselho: 'Auditor' };

function nextWeekday(target) { // 0=dom … 5=sex
  const d = new Date(clock.now());
  const add = (target - d.getUTCDay() + 7) % 7 || 7;
  d.setUTCDate(d.getUTCDate() + add);
  return d.toISOString().slice(0, 10);
}

export function seedDojoV1(w) {
  const db = w.db;
  const findUnit = (n) => db.prepare("SELECT * FROM org_units WHERE name=? AND lifecycle_status='active'").get(n);
  const findRole = (n) => db.prepare("SELECT * FROM roles WHERE name=? AND lifecycle_status='active'").get(n);
  const findAgent = (n) => db.prepare("SELECT * FROM agents WHERE display_name=? AND lifecycle_status<>'archived'").get(n);

  // 1) Salas → unidades
  const U = {};
  ROOMS.forEach(([key, name, purpose, theme, kanji], i) => {
    U[key] = (findUnit(name) || createUnit(w, OWNER, { name, purpose, theme, kanji, plot: i })).id;
  });

  // 2) Funções
  const R = {};
  for (const [key, name, tier, mission, caps] of ROLES) {
    R[key] = (findRole(name) || createRole(w, OWNER, { name, tier, mission, responsibilities: [mission], limits: ['Nesta conta: só desenho, sem dados reais'], default_capability_proposals: caps })).id;
  }
  const capsOf = (roleKey) => ROLES.find((r) => r[0] === roleKey)[4];

  // 3) Agentes (atualiza os 9xx existentes; cria os restantes)
  const A = {};
  for (const [name, num, room, roleKey, oldName, appearance, active] of AGENTS) {
    const fnName = ROLES.find((r) => r[0] === roleKey)[1];
    const title = `${fnName} (${num})`;
    const existing = findAgent(name) || (oldName ? findAgent(oldName) : null);
    if (existing) {
      const extraTitle = oldName && oldName !== name ? ` · ex-${oldName}` : '';
      const curCaps = parseJson(existing.capability_ids, []);
      const a = updateAgent(w, OWNER, existing.id, {
        display_name: name, title: `${title}${extraTitle}`.slice(0, 80), org_unit_id: U[room], role_ids: [R[roleKey]],
        capability_ids: [...new Set([...curCaps, ...capsOf(roleKey)])], expected_version: existing.record_version,
      });
      A[name] = a.id;
    } else {
      A[name] = createAgent(w, OWNER, {
        display_name: name, title, org_unit_id: U[room], role_ids: [R[roleKey]], capability_ids: capsOf(roleKey),
        origin: 'ecosystem_ref', appearance, description: `${fnName}. Agente do Dojo (nº ${num}).${ECO_NOTE}`,
      }).id;
    }
    if (!active) {
      const cur = db.prepare('SELECT * FROM agents WHERE id=?').get(A[name]);
      if (cur.lifecycle_status === 'active') updateAgent(w, OWNER, cur.id, { lifecycle_status: 'deactivated', expected_version: cur.record_version });
    }
  }
  // Os D0x reportam à coordenadora do dia.
  for (const n of ['Tsukuyomi', 'Susanoo', 'Hachiman', 'Todoroki']) {
    const cur = db.prepare('SELECT * FROM agents WHERE id=?').get(A[n]);
    if (!cur.manager_agent_id) updateAgent(w, OWNER, cur.id, { manager_agent_id: A.Amaterasu, expected_version: cur.record_version });
  }
  // Minerva (902) não consta do Dojo: mantém-se, na sala de BI (stories e documentação de BI).
  const minerva = findAgent('Minerva');
  if (minerva && !Object.values(U).includes(minerva.org_unit_id)) updateAgent(w, OWNER, minerva.id, { org_unit_id: U.bi, expected_version: minerva.record_version });

  // 4) Responsáveis das salas
  for (const [room, n] of Object.entries(RESPONSIBLE)) {
    const u = db.prepare('SELECT * FROM org_units WHERE id=?').get(U[room]);
    if (u.responsible_agent_id !== A[n]) updateUnit(w, OWNER, u.id, { responsible_agent_id: A[n], expected_version: u.record_version });
  }
  // 5) Unidades antigas: arquivar se ficaram vazias (histórico preservado).
  for (const old of ['Direção (desenho)', 'Esquadrão 9xx (desenho)']) {
    const u = findUnit(old);
    if (!u) continue;
    const used = db.prepare("SELECT COUNT(*) c FROM agents WHERE org_unit_id=? AND lifecycle_status<>'archived'").get(u.id).c;
    if (!used) archiveUnit(w, OWNER, u.id, u.record_version);
  }
  // 6) Delegação: a coordenadora do dia pode delegar a toda a equipa (1 nível). Pedro autoriza; negado por omissão.
  const hasPerm = db.prepare('SELECT 1 FROM permissions WHERE principal_id=? AND revoked_at IS NULL').get(A.Amaterasu);
  if (!hasPerm) grantPermission(w, OWNER, { principal_id: A.Amaterasu, resource_scope: '*', allowed_actions: ['delegate'], delegation_limit: 1 });

  // 7) Tarefas (estados do Dojo reproduzidos pelo caminho legítimo)
  const today = new Date(clock.now()).toISOString().slice(0, 10);
  const mk = (key, body) => createTask(w, OWNER, { idempotency_key: key, ...body });
  const t1 = mk('dojo-t1', { title: 'Rever avisos do modelo de qualidade', objective: 'Projeto: ML · Qualidade (910).', assigned_agent_id: A.Tetsuo, capability: 'ds.baseline', due_at: today });
  if (t1.state === 'assigned') startManual(w, OWNER, t1.id);
  const t2 = mk('dojo-t2', { title: 'Fechar ligação de referências', objective: 'Projeto: ML · Ruturas (914).', assigned_agent_id: A.Tetsuo, capability: 'ds.baseline' });
  if (t2.state === 'assigned') transitionTask(w, OWNER, t2.id, 'blocked', { note: 'Falta ligação de referências' });
  mk('dojo-t3', { title: 'Preparar demo do portal', objective: 'Projeto: Portal.', assigned_agent_id: A.Raiden, capability: 'bi.modeling', due_at: nextWeekday(5) });
  mk('dojo-t4', { title: 'Atualizar guia rápido', objective: 'Sem projeto.', assigned_agent_id: A['Kai Profissional'], capability: 'ops.plan' });
  const t5 = mk('dojo-t5', { title: 'Rever regras do ciclo de vida', objective: 'Projeto: ML · Ciclo de vida (911).', assigned_agent_id: A.Tetsuo, capability: 'ds.baseline' });
  if (t5.state === 'assigned') startManual(w, OWNER, t5.id);
  if (db.prepare('SELECT state FROM tasks WHERE id=?').get(t5.id).state === 'running') {
    completeManual(w, OWNER, t5.id, { note: 'Importada do brief do Dojo (exemplo fictício), onde estava concluída. Registo manual; não foi executada nesta app.' });
  }
  audit(w, { actor: 'system:seed', action: 'world.seed_dojo_v1', resource: w.id });
  return { units: U, roles: R, agents: A };
}

// ---------------------------------------------------------------------------------------------
// v2 — Projetos (ML + Portal) e rotinas agendadas do Dojo, com as últimas execuções do brief.
// As execuções importadas ligam-se aos slots MAIS RECENTES já passados (nunca a slots futuros),
// com source='import' e nota a dizer que são exemplos fictícios do brief.

const PROJECTS = [
  ['910', 'Qualidade dos dados', 'ml', 'in_production', 'dias úteis', '6 de 7 modelos prontos', 'warn', ''],
  ['911', 'Ciclo de vida', 'ml', 'in_production', 'semanal', 'Estável', 'ok', ''],
  ['915', 'Desvios preço-volume-mix', 'ml', 'in_production', 'mensal', 'Estável', 'ok', ''],
  ['918', 'ABC-XYZ', 'ml', 'in_production', 'mensal', 'Com avisos', 'warn', ''],
  ['919', 'Coortes', 'ml', 'in_production', 'mensal', 'Estável', 'ok', ''],
  ['912', 'Churn', 'ml', 'preparing', '', '', 'none', 'Comparar com baseline'],
  ['913', 'Procura', 'ml', 'preparing', '', '', 'none', 'Testar média de 13 semanas'],
  ['914', 'Ruturas', 'ml', 'blocked', '', '', 'none', 'Falta ligação de referências'],
  ['916', 'Basket', 'ml', 'on_demand', '', '', 'none', 'Precisa de limiar de negócio'],
  ['917', 'ROI', 'ml', 'on_demand', '', '', 'none', 'Corre por campanha'],
  ['', 'Portal', 'general', 'active', '', 'Demo em preparação', 'none', 'Preparar demo do portal'],
];

// [agente, título, agenda, projeto(nº), execuções do brief (mais antiga → mais recente)]
const ROUTINES = [
  ['Amaterasu', 'Briefing do dia', { kind: 'weekdays', times: ['09:26'] }, null, [['ok', '3 pedidos e 2 emails a responder; dados OK']]],
  ['Tsukuyomi', 'Triagem de mensagens', { kind: 'daily', times: ['09:04', '12:04', '15:04', '18:04'] }, null, [['failed', 'Limite de uso atingido']]],
  ['Kenshin', 'Saúde do ETL', { kind: 'weekdays', times: ['09:08'] }, null, [['warn', '2 processos com falha de 41']]],
  ['Tetsuo', '910 · Qualidade para ML', { kind: 'weekdays', times: ['08:47'] }, '910', [['ok', '6 de 7 modelos prontos']]],
  ['Tetsuo', '911 · Ciclo de vida', { kind: 'weekly', weekday: 2, times: ['09:07'] }, '911', [['ok', 'em risco estável; 9 novos em risco']]],
  ['Hachiman', 'Vendas da semana', { kind: 'weekly', weekday: 1, times: ['09:21'] }, null, [['ok', '+3,1% face ao ano anterior']]],
  ['Kenshin', 'Vigia do portal', { kind: 'weekdays', times: ['18:12'] }, 'Portal', []],
  ['Amaterasu', 'Fecho da semana', { kind: 'weekly', weekday: 5, times: ['16:47'] }, null, []],
  ['Kenshin', 'Arquivista', { kind: 'weekly', weekday: 0, times: ['07:37'] }, null, [['ok', '120 documentos antigos apagados']]],
];
const TASK_PROJECT = { 'dojo-t1': '910', 'dojo-t2': '914', 'dojo-t3': 'Portal', 'dojo-t5': '911' };

export function seedDojoV2(w) {
  const db = w.db;
  const agentId = (n) => db.prepare("SELECT id FROM agents WHERE display_name=? AND lifecycle_status<>'archived'").get(n)?.id;
  const P = {};
  for (const [number, title, kind, state, cadence, last, lastStatus, next] of PROJECTS) {
    const key = number || title;
    const found = db.prepare("SELECT id FROM projects WHERE world_id=? AND title=? AND lifecycle_status='active'").get(w.id, title);
    P[key] = found ? found.id : createProject(w, OWNER, {
      number, title, kind, state, cadence, last_point: last, last_point_status: lastStatus, next_step: next,
      owner_agent_id: agentId(kind === 'ml' ? 'Tetsuo' : 'Raiden'),
    }).id;
  }
  for (const [key, num] of Object.entries(TASK_PROJECT)) {
    db.prepare('UPDATE tasks SET project_id=? WHERE idempotency_key=? AND account_id=? AND project_id IS NULL').run(P[num], key, w.accountId);
  }
  const now = clock.now();
  for (const [agent, title, schedule, proj, runs] of ROUTINES) {
    if (db.prepare("SELECT 1 FROM routines WHERE world_id=? AND title=? AND lifecycle_status='active'").get(w.id, title)) continue;
    const r = createRoutine(w, OWNER, { agent_id: agentId(agent), title, schedule, project_id: proj ? P[proj] : undefined });
    const slots = lastSlots(schedule, now, runs.length);
    runs.forEach(([status, note], i) => {
      if (!slots[i]) return;
      const slotIso = new Date(slots[i]).toISOString();
      recordRun(w, OWNER, r.id, { status, note: `${note} — exemplo do brief Dojo (fictício)`, slot_at: slotIso, recorded_at: new Date(slots[i] + 3 * 60000).toISOString() }, { source: 'import' });
    });
  }
  audit(w, { actor: 'system:seed', action: 'world.seed_dojo_v2', resource: w.id });
  return { projects: P };
}
