// Adaptador DEMO: determinístico, offline, sem modelo. Fala em nome do agente com respostas
// baseadas em dados reais do backend (estado, tarefas, equipa). NÃO é AI operacional (H05/CA04):
// cada mensagem fica gravada com mode='demo' e o histórico nunca muda de rótulo.
import { parseJson } from '../lib/util.js';
import { CAPABILITIES } from '../modules/capabilities.js';

export const DEMO_PROVIDER_REF = 'demo-deterministico@1';
const norm = (s) => s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');

const STATE_PT = {
  draft: 'rascunho', pending: 'pendente', assigned: 'atribuída', running: 'em execução', awaiting_approval: 'a aguardar aprovação',
  completed: 'concluída', blocked: 'bloqueada', failed: 'falhada', cancelled: 'cancelada',
};

function routeCapability(text, w, self) {
  const t = norm(text);
  let best = null;
  for (const [id, c] of Object.entries(CAPABILITIES)) {
    const score = (c.keywords || []).reduce((n, k) => n + (t.includes(norm(k)) ? 1 : 0), 0);
    if (score > 0 && (!best || score > best.score)) best = { id, score, c };
  }
  if (!best) return null;
  const rows = w.db.prepare("SELECT * FROM agents WHERE world_id=? AND lifecycle_status='active'").all(w.id)
    .filter((a) => parseJson(a.capability_ids, []).includes(best.id));
  const target = rows.find((a) => a.id === self.id) || rows[0];
  return { capability: best.id, label: best.c.label, auto: Boolean(best.c.executor), needsInput: Boolean(best.c.needsInput), target };
}

export function respond({ w, agent, text }) {
  const t = norm(text);
  const name = agent.display_name;
  const myTasks = w.db.prepare("SELECT title,state FROM tasks WHERE assigned_agent_id=? ORDER BY updated_at DESC LIMIT 6").all(agent.id);
  const counts = {};
  for (const r of w.db.prepare('SELECT state, COUNT(*) c FROM tasks WHERE assigned_agent_id=? GROUP BY state').all(agent.id)) counts[r.state] = r.c;

  if (/\b(ola|oi|bom dia|boa tarde|boa noite|hey)\b/.test(t)) {
    return { text: `Olá, Pedro. Sou ${name}${agent.title ? `, ${agent.title}` : ''}. Estou em modo demonstração: respondo com regras fixas e dados reais da app, sem modelo de linguagem. Diz-me «estado», «tarefas» ou «ajuda».` };
  }
  if (/(quem es|o que fazes|a tua funcao|missao|apresenta|descreve-te)/.test(t)) {
    return { text: `${agent.description || 'Sem descrição registada.'}${agent.title ? ` Cargo: ${agent.title}.` : ''}` };
  }
  if (/(estado|ponto de situacao|como esta|novidades)/.test(t)) {
    const parts = Object.entries(counts).map(([s, c]) => `${c} ${STATE_PT[s] || s}`);
    return { text: parts.length ? `Neste momento tenho: ${parts.join(', ')}. (Números lidos agora da base de dados.)` : 'Não tenho tarefas atribuídas neste momento.' };
  }
  if (/(tarefas|pendentes|em curso|o que tens)/.test(t)) {
    return { text: myTasks.length ? `As minhas tarefas mais recentes:\n${myTasks.map((x) => `• ${x.title} — ${STATE_PT[x.state] || x.state}`).join('\n')}` : 'Não tenho tarefas atribuídas. Podes delegar-me uma no botão «Delegar tarefa».' };
  }
  if (/(equipa|reports|organograma|colegas|quem trabalha)/.test(t)) {
    const team = w.db.prepare("SELECT display_name,title FROM agents WHERE manager_agent_id=? AND lifecycle_status='active' ORDER BY display_name").all(agent.id);
    const boss = agent.manager_agent_id ? w.db.prepare('SELECT display_name,title FROM agents WHERE id=?').get(agent.manager_agent_id) : null;
    return { text: `${boss ? `Reporto a ${boss.display_name} (${boss.title}). ` : ''}${team.length ? `A minha equipa direta: ${team.map((x) => x.display_name).join(', ')}.` : 'Não tenho reportes diretos.'}` };
  }
  if (/(ajuda|help|o que consegues|comandos)/.test(t)) {
    return { text: 'No modo demo posso: dizer o meu estado, listar tarefas, descrever a minha função e equipa, e sugerir a quem encaminhar um pedido (ex.: «validar um csv», «fazer relatório de kpis»). Para trabalho real, cria uma tarefa — o worker executa e devolve prova.' };
  }
  const route = routeCapability(text, w, agent);
  if (route && route.target) {
    const who = route.target.id === agent.id ? 'eu próprio(a)' : route.target.display_name;
    const how = route.auto
      ? (route.needsInput ? 'Em Trabalho → Nova tarefa, carrega o CSV sintético; o worker valida no backend e devolve a prova.' : 'O worker executa já no backend e devolve a prova.')
      : 'Esta capacidade ainda não tem execução automática: fica como tarefa manual, com nota e prova registadas por ti.';
    return {
      text: `Isto cabe a «${route.label}» — ${who}. ${how}`,
      suggestion: { capability: route.capability, agent_id: route.target.id, agent_name: route.target.display_name, title: text.slice(0, 120), needs_input: route.needsInput, auto: route.auto },
    };
  }
  return { text: 'No modo demo não interpreto linguagem livre. Tenta «estado», «tarefas», «equipa» ou descreve o que precisas com palavras como csv, kpi, blueprint, auditoria… para eu sugerir o encaminhamento certo.' };
}
