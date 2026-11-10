# Hierarquia e papéis do escritório

**Equipa → Orquestradora → Funcionários → Skills → Repositório**

É o mesmo modelo de cinco níveis da arquitetura de agentes de origem, aplicado ao escritório da equipa de BI.

| Nível | Aqui | Recebe | Entrega | Limite |
|---|---|---|---|---|
| 1. Equipa | As pessoas da equipa de BI | Resultados, alternativas, evidência | Objetivo, prioridade, autorizações, aceitação | Decide o que importa; não precisa de escolher a skill |
| 2. Orquestradora | Amaterasu (D01), `CLAUDE.md` | O pedido e o registo `equipa.json` | Trabalho coordenado e verificado | Não amplia acessos nem inventa execuções |
| 3. Funcionários | `.claude/agents/*.md` | Tarefa delimitada e critérios | O resultado da sua especialidade | Não redefinem o objetivo nem as prioridades |
| 4. Skills | `.claude/skills/*/SKILL.md` | Uma tarefa específica | Método, passos e verificação | São procedimentos, não identidades, e não concedem ferramentas |
| 5. Repositório | `cerebro/`, `escritorio/`, `inbox/`, `out/` | Materiais e resultados | Fontes consultáveis e histórico | Informa, não dá ordens |

Conectores, o motor local (`foundry/`) e os modelos Claude são meios de execução transversais, não um nível de autoridade.

## Mapa para os perfis de origem

Os nomes japoneses são nomes de apresentação. Os identificadores técnicos e os perfis de origem mantêm-se.

| Escritório | N.º | Perfil de origem | Função |
|---|---|---|---|
| Amaterasu | D01 | papel de orquestrador | Coordenação e briefing |
| Tsukuyomi | D02 | proposta «Triagem de pedidos» | Triagem |
| Susanoo | D03 | propostas «Monitor de qualidade» e «Alertas de anomalia» | Deriva e anomalias |
| Hachiman | D04 | proposta «Briefing semanal» | Analytics |
| Benkei | D05 | propostas «Revisor DAX» e «Testes de RLS» | Revisão |
| Kenshin | 900 | Arquimedes | Dados e implementação |
| Tetsuo | 901 | Turing | ML; supervisor dos módulos 910 a 919 |
| Sakura | 902 | Minerva | Trabalho e documentação |
| Raiden | 903 | Atlas BI | Modelos e dashboards |
| Auditor | 800 | Auditor Independente | Auditoria |
| Tomoshibi | ASS | assistente diário | Rotina |
| Kioku | PRG | progresso | Progresso e memória |

A série D é nova e pertence a este escritório. As séries 8xx e 9xx seguem as definições de origem. Os dez módulos 910 a 919 são skills do Tetsuo sobre o motor `bi_ml` 0.10.0, não funcionários.

## Fluxo de um pedido

1. **Pedido:** alguém da equipa escreve o que precisa (ou uma rotina dispara).
2. **Seleção:** a Amaterasu escolhe o funcionário e a skill; um pedido simples resolve-o ela.
3. **Execução:** o funcionário segue a skill; os números vêm das ferramentas.
4. **Verificação:** contra o pedido e contra `cerebro/regras.md`.
5. **Entrega:** resultado em `out/`, com limitações e próximo passo.
6. **Revisão humana:** nada sai de `out/` sem o OK de uma pessoa.
7. **Memória:** tarefas e eventos no quadro; lições propostas no resumo semanal.

## Um orquestrador por contexto

Este escritório tem uma orquestradora, a Amaterasu. Os orquestradores pessoais de cada membro da equipa, noutras contas ou ferramentas, não são substituídos nem acedem a este repositório.
