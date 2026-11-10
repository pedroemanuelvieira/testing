# Estados e promoção

Cada funcionário tem um estado em `escritorio/equipa.json`. Um estado só sobe com evidência datada e a aprovação de uma pessoa. Um ficheiro existir não prova que algo está instalado, testado ou em produção.

| Estado | Significa | Evidência exigida para chegar aqui |
|---|---|---|
| `documentado` | Há uma descrição ou blueprint | Blueprint em 8 secções |
| `configurado` | Os ficheiros existem e a configuração é válida | `python3 -m foundry validar` sem erros |
| `instalado` | Corre no ambiente profissional da equipa | Uma execução real registada (data, quem, n.º da execução) |
| `verificado` | Os casos de teste passaram com dados reais | 3 a 5 casos, incluindo um de recusa, e parecer do Auditor |
| `producao` | Em uso regular, com dono e métrica | 4 semanas de piloto, horas poupadas medidas, plano de reversão |

Neste repositório-modelo todos os funcionários estão em `configurado`: foram escritos e validados, não instalados nem testados com dados reais.

## Checklist de promoção

- [ ] Sem dados reais em ficheiros versionados (`python3 -m foundry fronteira`)
- [ ] Casos de teste passaram, incluindo um que o funcionário deve recusar ou escalar
- [ ] Dono (pessoa da equipa) e métrica de valor definidos
- [ ] Limites escritos na skill e transmitidos nas entregas
- [ ] Parecer do Auditor (800) em `out/auditoria/`
- [ ] Compatível com a política de IA da organização
- [ ] Aprovação registada: preencher `evidencia` em `equipa.json` com data, quem aprovou e onde está a prova

## Desligar

Todos os meses o Auditor lista funcionários e rotinas sem uso ou sem valor. Desligar é pôr `"ativa": false` na rotina ou descer o estado, com o motivo em `cerebro/decisoes.md`. Nada é apagado.

## Novas ideias

Pontuação: **valor × viabilidade ÷ risco**. Skills primeiro: só se cria um funcionário quando há uma função com dono próprio. A skill `novo-funcionario` conduz o processo, do blueprint aos testes.
