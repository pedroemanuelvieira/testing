// Registo de capacidades. Adicionar uma função nova ao sistema = acrescentar uma entrada aqui
// (e, se tiver execução automática, um executor). Cargos/agentes apontam para capacidades por id.
//
// - `executor`: função síncrona e determinística executada pelo WORKER (nunca pelo browser).
// - sem `executor`: a tarefa é de trabalho manual — o agente DEMO não a executa; Pedro regista
//   o resultado com nota (Evidence 'manual_note'). Isto evita fingir execução (RF04/CA05).
import { validateCsv, profileCsv, decodeUtf8 } from './csv.js';

export const CAPABILITIES = {
  'csv.validate': {
    label: 'Validar CSV sintético', taskKind: 'csv_validation', category: 'dados',
    keywords: ['csv', 'validar', 'validação', 'ficheiro', 'duplicados', 'linhas'],
    needsInput: true, limitations: [
      'Validação determinística executada no worker; o conteúdo do ficheiro nunca é executado.',
      'Duplicados = linha exata além da primeira ocorrência; a soma NÃO deduplica.',
      'Apenas dados sintéticos (D1).'],
    executor({ text, config, step }) {
      step('decode_utf8'); const t = decodeUtf8(text);
      step('parse_and_validate'); const report = validateCsv(t, config);
      step('aggregate');
      return { report, summary: { rows_read: report.rows_read, valid_numeric: report.valid_numeric, invalid_numeric: report.invalid_numeric, duplicates_exact: report.duplicates_exact, sum_numeric: report.sum_numeric } };
    },
  },
  'csv.profile': {
    label: 'Perfilar colunas de um CSV', taskKind: 'csv_profile', category: 'dados',
    keywords: ['perfil', 'profile', 'colunas', 'distintos', 'nulos', 'qualidade'],
    needsInput: true, limitations: [
      'Perfil descritivo determinístico (tipos inferidos, nulos, distintos, extremos).',
      'Não substitui validação de regras de negócio; apenas dados sintéticos (D1).'],
    executor({ text, step }) {
      step('decode_utf8'); const t = decodeUtf8(text);
      step('profile_columns'); const report = profileCsv(t);
      return { report, summary: { rows_read: report.rows_read, columns: report.columns_count } };
    },
  },
  'report.village_kpis': {
    label: 'Relatório de KPIs da vila', taskKind: 'village_report', category: 'bi',
    keywords: ['kpi', 'relatório', 'relatorio', 'indicadores', 'painel', 'vila'],
    needsInput: false, limitations: [
      'Fotografia dos números do backend neste instante; não contém conteúdo de mensagens.'],
    executor({ kpiSnapshot, step }) {
      step('collect_metrics'); const report = kpiSnapshot();
      return { report, summary: { tasks_total: report.tasks_total, completed: report.tasks_by_state.completed || 0 } };
    },
  },
  // Capacidades de trabalho manual/humano-no-ciclo (sem executor automático nesta fase).
  'blueprint.write': { label: 'Desenhar blueprint higienizado', category: 'desenho', keywords: ['blueprint', 'especificação', 'desenho'] },
  'control.review': { label: 'Rever evidência e controlo', category: 'controlo', keywords: ['auditar', 'auditoria', 'rever', 'controlo', 'conformidade'] },
  'learn.explain': { label: 'Explicar conceitos e estudo', category: 'ensino', keywords: ['explica', 'conceito', 'estudo', 'curso', 'aprender'] },
  'learn.coach': { label: 'Acompanhar projetos e trabalhos', category: 'ensino', keywords: ['trabalho', 'projeto', 'socrático', 'tutor'] },
  'wellness.plan': { label: 'Plano de treino e recuperação', category: 'vida', keywords: ['treino', 'exercício', 'recuperação', 'saúde'] },
  'finance.scenarios': { label: 'Cenários e análise de carteira (fictícia)', category: 'vida', keywords: ['investimento', 'carteira', 'cenários', 'cripto'] },
  'strategy.synthesize': { label: 'Sintetizar objetivos e resultados', category: 'direção', keywords: ['estratégia', 'objetivos', 'resultados', 'prioridades'] },
  'ops.plan': { label: 'Planear e coordenar execução', category: 'execução', keywords: ['plano', 'planear', 'execução', 'coordenar'] },
  'tech.runtime': { label: 'Runtime, modelos e ligações', category: 'tecnologia', keywords: ['modelo', 'api', 'ligação', 'ligações', 'conector', 'runtime'] },
  'bi.modeling': { label: 'Modelação semântica e dashboards', category: 'bi', keywords: ['dashboard', 'modelo semântico', 'dax', 'power bi', 'fabric'] },
  'bi.requirements': { label: 'Requisitos e stories de BI', category: 'bi', keywords: ['story', 'stories', 'épico', 'requisitos'] },
  'impl.build': { label: 'Implementação em plataformas', category: 'execução', keywords: ['implementar', 'construir', 'copilot'] },
  'ds.baseline': { label: 'Ciência de dados e baselines', category: 'dados', keywords: ['baseline', 'ml', 'previsão', 'modelo preditivo'] },
  // Funções do Dojo (equipa profissional) — trabalho manual nesta conta (mundo só de desenho).
  'ops.briefing': { label: 'Briefing do dia', category: 'direção', keywords: ['briefing', 'morning', 'resumo do dia'] },
  'ops.triage': { label: 'Triagem de mensagens', category: 'execução', keywords: ['triagem', 'mensagens', 'emails', 'pedidos'] },
  'bi.insights': { label: 'Quebras e oportunidades', category: 'bi', keywords: ['quebras', 'oportunidades', 'desvios', 'anomalias'] },
  'bi.sales_weekly': { label: 'Vendas da semana', category: 'bi', keywords: ['vendas', 'semana', 'semanal'] },
  'data.etl': { label: 'Automação e ETL', category: 'dados', keywords: ['etl', 'automação', 'pipeline', 'processos'] },
  'skills.test': { label: 'Skills e testes', category: 'tecnologia', keywords: ['skill', 'skills', 'testes', 'lab'] },
};

export const capabilityList = () => Object.entries(CAPABILITIES).map(([id, c]) => ({
  id, label: c.label, category: c.category, auto_execute: Boolean(c.executor), task_kind: c.taskKind || 'manual',
  needs_input: Boolean(c.needsInput), limitations: c.limitations || [],
}));

export const executableCapability = (id) => (CAPABILITIES[id]?.executor ? CAPABILITIES[id] : null);
export const kindForCapability = (id) => CAPABILITIES[id]?.taskKind || 'manual';
