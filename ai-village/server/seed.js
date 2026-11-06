// Seed da organização inicial, derivada da Source_of_truth (HIERARQUIA_E_PAPEIS, Plano v2.2, REQUISITOS §4).
//  - D2: um orquestrador por mundo (Kai). CEO/diretores são cargos propostos da APP (D3), não orquestradores.
//  - Agentes com origin='ecosystem_ref' refletem as fichas do ecossistema (Ponte, Oráculo, Apolo, Feynman,
//    Sócrates, Auditor, 9xx) como ENTIDADES DA APP: não instalam nem alteram os bots originais.
//  - Só dados fictícios (D1). Nomes dos cargos são inventados para a app.
import { newId, clock, json } from './lib/util.js';
import { tx } from './lib/db.js';
import { createUnit, createRole, createAgent, updateUnit } from './modules/org.js';
import { grantPermission, OWNER } from './modules/policy.js';
import { seedConnections } from './modules/connections.js';
import { audit } from './modules/audit.js';

const look = (o) => ({ type: 'procedural', ...o });
const ECO = 'ecosystem_ref';
const ECO_NOTE = ' (Entidade da app que reflete a ficha do ecossistema; não é nem altera o bot original.)';

export function seedPersonal(w) {
  const U = {}, R = {}, A = {};
  const unit = (key, name, purpose, theme, kanji, plot) => { U[key] = createUnit(w, OWNER, { name, purpose, theme, kanji, plot }).id; };
  unit('sede', 'Sede & Gabinete', 'Direção da vila: objetivos, síntese de resultados e coordenação geral.', 'tower', '本社', 0);
  unit('bi', 'Dados & BI', 'Dados, qualidade, modelos semânticos e dashboards.', 'lab', '分析', 1);
  unit('tec', 'Tecnologia & AI Lab', 'Runtime, modelos, ligações e segurança da app.', 'workshop', '技術', 2);
  unit('exec', 'Execução & Blueprints', 'Transformar ideias em blueprints e planos executáveis.', 'dock', '実行', 3);
  unit('learn', 'Aprendizagem', 'Estudo, curso e acompanhamento de projetos.', 'dojo', '学', 4);
  unit('vida', 'Vida Pessoal', 'Bem-estar, treino e finanças pessoais (fictícias nesta instância).', 'garden', '暮', 5);
  unit('ctrl', 'Controlo', 'Revisão independente de evidência e conformidade.', 'vault', '監査', 6);

  const role = (key, name, tier, mission, responsibilities, limits, caps) => {
    R[key] = createRole(w, OWNER, { name, tier, mission, responsibilities, limits, default_capability_proposals: caps }).id;
  };
  role('ceo', 'CEO', 'ceo', 'Sintetizar objetivos e resultados da vila e alinhar as direções.',
    ['Sintetizar objetivos e resultados', 'Propor prioridades ao Pedro', 'Arbitrar entre direções'], ['Não sobrepõe o orquestrador', 'Não concede permissões', 'Prioridades são decididas pelo Pedro'], ['strategy.synthesize']);
  role('cdo', 'Chief Data Officer', 'c_level', 'Responsável por dados, qualidade e BI.', ['Governar qualidade de dados', 'Priorizar entregas de BI'], ['Só dados sintéticos nesta instância'], ['bi.modeling', 'report.village_kpis']);
  role('cto', 'Chief Technology & AI Officer', 'c_level', 'Responsável por runtime, modelos e ligações.', ['Manter o runtime e o worker', 'Avaliar adaptadores de modelos'], ['Não liga contas sem autorização do Pedro'], ['tech.runtime']);
  role('coo', 'Chief Operating Officer', 'c_level', 'Responsável por planear e coordenar a execução.', ['Planos de execução', 'Blueprints higienizados'], ['Não executa ações externas'], ['ops.plan']);
  role('cco', 'Chief Control Officer', 'control', 'Garante revisão independente de evidência.', ['Rever evidência', 'Auditar exequibilidade'], ['Não aprova a sua própria ação consequente'], ['control.review']);
  role('dir', 'Diretor/a', 'director', 'Dirige uma unidade e propõe delegações.', ['Gerir a equipa da unidade', 'Propor delegações'], ['Cargo não concede acesso por si'], []);
  role('esp', 'Especialista', 'specialist', 'Executa trabalho especializado dentro dos limites da sua função.', ['Executar tarefas atribuídas'], ['Só dentro do escopo delegado'], []);
  role('orq', 'Orquestrador', 'orchestrator', 'Ponto de entrada único do mundo: triagem, encaminhamento e consolidação.', ['Triagem de fronteira', 'Encaminhar para o agente certo', 'Consolidar respostas'], ['Um por mundo', 'Não amplia acessos nem inventa execução'], ['ops.plan', 'report.village_kpis']);

  const agent = (key, d) => {
    A[key] = createAgent(w, OWNER, {
      ...d, org_unit_id: U[d.unit], manager_agent_id: d.manager ? A[d.manager] : undefined, role_ids: d.roles.map((r) => R[r]),
      description: d.description + (d.origin === ECO ? ECO_NOTE : ''),
    }).id;
  };
  agent('kai', { display_name: 'Kai Pessoal', title: 'Orquestrador pessoal', unit: 'sede', roles: ['orq'], origin: ECO, orchestrator_flag: true,
    capability_ids: ['ops.plan', 'report.village_kpis'],
    description: 'Ponto de entrada e orquestrador do mundo pessoal: triagem de fronteira, encaminhamento para o agente certo, consolidação de respostas e planos de estudo.',
    appearance: look({ gender: 'm', skin: 2, hair: '#1b1b22', style: 'sidepart', eyes: '#2a2018', outfit: 'techwear', accent: '#22d3ee', glasses: false }) });
  agent('haruki', { display_name: 'Haruki Sato', title: 'CEO', unit: 'sede', roles: ['ceo'], capability_ids: ['strategy.synthesize'],
    description: 'Sintetiza objetivos e resultados da vila e alinha as direções. Cargo proposto pela app; não substitui o orquestrador.',
    appearance: look({ gender: 'm', skin: 2, hair: '#9aa0a6', style: 'sidepart', eyes: '#3b2a1a', outfit: 'suit', accent: '#f4c24a', glasses: true }) });
  agent('mei', { display_name: 'Mei Nakamura', title: 'Chief Data Officer', unit: 'bi', roles: ['cdo'], manager: 'haruki', capability_ids: ['bi.modeling', 'report.village_kpis'],
    description: 'Governa a qualidade dos dados e prioriza as entregas de BI da vila.',
    appearance: look({ gender: 'f', skin: 2, hair: '#17161c', style: 'bob', eyes: '#2b1d14', outfit: 'suit', accent: '#a78bfa', glasses: false }) });
  agent('sora', { display_name: 'Sora Kimura', title: 'Diretor de BI', unit: 'bi', roles: ['dir'], manager: 'mei', capability_ids: ['bi.modeling', 'bi.requirements'],
    description: 'Dirige a equipa de BI: modelos semânticos, requisitos e dashboards.',
    appearance: look({ gender: 'm', skin: 3, hair: '#1a1410', style: 'spiky', eyes: '#2a1b10', outfit: 'techwear', accent: '#34d399', glasses: false }) });
  agent('rin', { display_name: 'Rin Okada', title: 'Engenheira de Dados', unit: 'bi', roles: ['esp'], manager: 'sora', capability_ids: ['csv.validate', 'csv.profile'],
    description: 'Valida e perfila ficheiros CSV sintéticos no worker e devolve relatório com prova. Executa de verdade no backend.',
    appearance: look({ gender: 'f', skin: 1, hair: '#2c1a14', style: 'bun', eyes: '#3a2a1c', outfit: 'labcoat', accent: '#22d3ee', glasses: true }) });
  agent('yui', { display_name: 'Yui Kobayashi', title: 'Chief Technology & AI Officer', unit: 'tec', roles: ['cto'], manager: 'haruki', capability_ids: ['tech.runtime'],
    description: 'Mantém o runtime, o worker e avalia adaptadores de modelos e ligações.',
    appearance: look({ gender: 'f', skin: 2, hair: '#0f172a', style: 'long', eyes: '#1f2937', outfit: 'techwear', accent: '#f472b6', glasses: false }) });
  agent('ren', { display_name: 'Ren Takahashi', title: 'Chief Operating Officer', unit: 'exec', roles: ['coo'], manager: 'haruki', capability_ids: ['ops.plan'],
    description: 'Planeia e coordena a execução entre unidades.',
    appearance: look({ gender: 'm', skin: 3, hair: '#241b16', style: 'undercut', eyes: '#2a1e14', outfit: 'haori', accent: '#fb923c', glasses: false }) });
  agent('ponte', { display_name: 'Ponte', title: 'Blueprints higienizados (01)', unit: 'exec', roles: ['esp'], manager: 'ren', origin: ECO, capability_ids: ['blueprint.write'],
    description: 'Transforma ideias em blueprints higienizados (BP_<nome>_vX.Y) e fecha o ciclo com a nota de retorno.',
    appearance: look({ gender: 'f', skin: 4, hair: '#3a2417', style: 'long', eyes: '#3a2418', outfit: 'haori', accent: '#60a5fa', glasses: false }) });
  agent('takumi', { display_name: 'Takumi Mori', title: 'Diretor de Aprendizagem', unit: 'learn', roles: ['dir'], manager: 'haruki', capability_ids: ['learn.coach'],
    description: 'Dirige estudo, curso e acompanhamento de projetos.',
    appearance: look({ gender: 'm', skin: 2, hair: '#1c1713', style: 'short', eyes: '#2a1c12', outfit: 'kimono', accent: '#f87171', glasses: true }) });
  agent('feynman', { display_name: 'Feynman', title: 'Mentor teórico (200)', unit: 'learn', roles: ['esp'], manager: 'takumi', origin: ECO, capability_ids: ['learn.explain'],
    description: 'Explica conceitos em Definição → Analogia → Como funciona → Impacto no negócio → Onde falha.',
    appearance: look({ gender: 'm', skin: 5, hair: '#2b2b2b', style: 'short', eyes: '#2b1d12', outfit: 'labcoat', accent: '#fbbf24', glasses: false }) });
  agent('socrates', { display_name: 'Sócrates', title: 'Tutor de projetos (201)', unit: 'learn', roles: ['esp'], manager: 'takumi', origin: ECO, capability_ids: ['learn.coach'],
    description: 'Método socrático: diagnóstico antes da resposta e revisão por critério de avaliação.',
    appearance: look({ gender: 'm', skin: 3, hair: '#8b8f96', style: 'buzz', eyes: '#2b2118', outfit: 'kimono', accent: '#a3e635', glasses: true }) });
  agent('aiko', { display_name: 'Aiko Watanabe', title: 'Diretora de Vida Pessoal', unit: 'vida', roles: ['dir'], manager: 'haruki', capability_ids: ['wellness.plan'],
    description: 'Dirige bem-estar, treino e finanças pessoais (fictícias).',
    appearance: look({ gender: 'f', skin: 1, hair: '#2a1713', style: 'bun', eyes: '#35231a', outfit: 'kimono', accent: '#f9a8d4', glasses: false }) });
  agent('apolo', { display_name: 'Apolo', title: 'Treino e performance (101)', unit: 'vida', roles: ['esp'], manager: 'aiko', origin: ECO, capability_ids: ['wellness.plan'],
    description: 'Plano semanal de força, cardio e recuperação. Perante dor ou lesão remete para um profissional de saúde.',
    appearance: look({ gender: 'm', skin: 4, hair: '#161312', style: 'undercut', eyes: '#2a1d14', outfit: 'hoodie', accent: '#fb7185', glasses: false }) });
  agent('oraculo', { display_name: 'Oráculo', title: 'Investimentos fictícios (100)', unit: 'vida', roles: ['esp'], manager: 'aiko', origin: ECO, capability_ids: ['finance.scenarios'],
    description: 'Factos com fonte e data, concentração da carteira e 3 cenários; não é consultor financeiro e não dá ordens. Nesta instância só carteiras fictícias.',
    appearance: look({ gender: 'f', skin: 3, hair: '#4a2f1f', style: 'bob', eyes: '#3b2a1b', outfit: 'suit', accent: '#c084fc', glasses: true }) });
  agent('daichi', { display_name: 'Daichi Ito', title: 'Chief Control Officer', unit: 'ctrl', roles: ['cco'], manager: 'haruki', capability_ids: ['control.review'],
    description: 'Revê evidência e garante que ninguém aprova a sua própria ação consequente.',
    appearance: look({ gender: 'm', skin: 2, hair: '#12100e', style: 'sidepart', eyes: '#241a12', outfit: 'suit', accent: '#94a3b8', glasses: false }) });
  agent('auditor', { display_name: 'Auditor Independente', title: 'Auditoria (800)', unit: 'ctrl', roles: ['esp'], manager: 'daichi', origin: ECO, capability_ids: ['control.review'],
    description: 'Audita a exequibilidade do ecossistema e dos planos, com veredito, evidência e plano de prova.',
    appearance: look({ gender: 'f', skin: 2, hair: '#1a1a1f', style: 'long', eyes: '#222a35', outfit: 'suit', accent: '#38bdf8', glasses: true }) });

  // Responsáveis de unidade
  const resp = { sede: 'haruki', bi: 'mei', tec: 'yui', exec: 'ren', learn: 'takumi', vida: 'aiko', ctrl: 'daichi' };
  for (const [u, a] of Object.entries(resp)) {
    const cur = w.db.prepare('SELECT record_version v FROM org_units WHERE id=?').get(U[u]).v;
    updateUnit(w, OWNER, U[u], { responsible_agent_id: A[a], expected_version: cur });
  }

  // Delegação (Pedro autoriza; negado por omissão para tudo o resto).
  const grant = (a, scope, limit) => grantPermission(w, OWNER, { principal_id: A[a], resource_scope: scope, allowed_actions: ['delegate'], delegation_limit: limit });
  grant('kai', '*', 2); grant('haruki', '*', 3);
  grant('mei', `unit:${U.bi}`, 2); grant('sora', `unit:${U.bi}`, 1); grant('yui', `unit:${U.tec}`, 1); grant('ren', `unit:${U.exec}`, 1);
  grant('takumi', `unit:${U.learn}`, 1); grant('aiko', `unit:${U.vida}`, 1); grant('daichi', `unit:${U.ctrl}`, 1);

  seedConnections(w, ['demo-adapter', 'anthropic-api', 'google-drive', 'gmail-personal', 'calendar-personal', 'notebooklm']);
  audit(w, { actor: 'system:seed', action: 'world.seed', resource: w.id });
  return { units: U, roles: R, agents: A };
}

export function seedProfessional(w) {
  const U = {}, A = {};
  U.sede = createUnit(w, OWNER, { name: 'Direção (desenho)', purpose: 'Cargos propostos para o mundo profissional. Só desenho nesta conta.', theme: 'tower', kanji: '本社', plot: 0 }).id;
  U.esq = createUnit(w, OWNER, { name: 'Esquadrão 9xx (desenho)', purpose: 'Agentes de implementação, dados, stories e BI do ambiente profissional.', theme: 'workshop', kanji: '工房', plot: 1 }).id;
  const orq = createRole(w, OWNER, { name: 'Orquestrador', tier: 'orchestrator', mission: 'Ponto de entrada único do mundo profissional.', responsibilities: ['Planos de trabalho', 'Prioridades com dados reais (no tenant)'], limits: ['Nesta conta: apenas desenho, sem dados reais'] }).id;
  const esp = createRole(w, OWNER, { name: 'Especialista 9xx', tier: 'specialist', mission: 'Implementa, modela ou documenta no ambiente profissional.', responsibilities: [], limits: ['Execução real só no tenant após G3'] }).id;
  const mk = (d) => createAgent(w, OWNER, { ...d, org_unit_id: U[d.unit], role_ids: [d.role], origin: ECO, description: d.description + ECO_NOTE }).id;
  A.kai = mk({ display_name: 'Kai Profissional', title: 'Orquestrador profissional (desenho)', unit: 'sede', role: orq, orchestrator_flag: true, capability_ids: ['ops.plan'],
    description: 'Orquestrador do mundo profissional (D3). Nesta conta existe apenas como desenho.',
    appearance: look({ gender: 'm', skin: 2, hair: '#1b1b22', style: 'sidepart', eyes: '#2a2018', outfit: 'suit', accent: '#f4c24a', glasses: true }) });
  A.arq = mk({ display_name: 'Arquimedes', title: 'Implementação (900)', unit: 'esq', role: esp, capability_ids: ['impl.build'],
    description: 'Converte blueprints e skills em agentes/fluxos e devolve a nota de retorno.',
    appearance: look({ gender: 'm', skin: 3, hair: '#3a3a3a', style: 'short', eyes: '#2a1c12', outfit: 'techwear', accent: '#fb923c', glasses: false }) });
  A.tur = mk({ display_name: 'Turing', title: 'Ciência de dados (901)', unit: 'esq', role: esp, capability_ids: ['ds.baseline'],
    description: 'Baseline primeiro, avaliação ligada ao negócio e plano de monitorização.',
    appearance: look({ gender: 'm', skin: 1, hair: '#1b1713', style: 'spiky', eyes: '#2a1f16', outfit: 'labcoat', accent: '#22d3ee', glasses: true }) });
  A.min = mk({ display_name: 'Minerva', title: 'Stories e documentação (902)', unit: 'esq', role: esp, capability_ids: ['bi.requirements'],
    description: 'Épicos e stories no Azure DevOps e documentação para utilizadores.',
    appearance: look({ gender: 'f', skin: 2, hair: '#2a1a14', style: 'bob', eyes: '#35261a', outfit: 'haori', accent: '#f9a8d4', glasses: false }) });
  A.atl = mk({ display_name: 'Atlas BI', title: 'Dashboards Power BI (903)', unit: 'esq', role: esp, capability_ids: ['bi.modeling'],
    description: 'Reconstrói relatórios Power BI como dashboards interativos.',
    appearance: look({ gender: 'm', skin: 4, hair: '#17130f', style: 'undercut', eyes: '#2a1c12', outfit: 'techwear', accent: '#a78bfa', glasses: false }) });
  for (const [u, a] of [['sede', 'kai'], ['esq', 'arq']]) {
    const cur = w.db.prepare('SELECT record_version v FROM org_units WHERE id=?').get(U[u]).v;
    updateUnit(w, OWNER, U[u], { responsible_agent_id: A[a], expected_version: cur });
  }
  grantPermission(w, OWNER, { principal_id: A.kai, resource_scope: '*', allowed_actions: ['delegate'], delegation_limit: 2 });
  seedConnections(w, ['demo-adapter', 'anthropic-api', 'm365-tenant', 'powerbi-fabric', 'azure-devops', 'copilot-studio']);
  audit(w, { actor: 'system:seed', action: 'world.seed', resource: w.id });
  return { units: U, agents: A };
}
