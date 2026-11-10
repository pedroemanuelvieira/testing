---
name: fecho-do-dia
description: "Fecho do dia do escritorio - o que ficou feito, o que falhou, pendencias para amanha e atualizacoes ao quadro. Usar ao fim do dia ou quando alguem escreve fecho."
---

# Fecho do dia

1. **Estado real:** `python3 -m foundry estado --json`.
2. **Escreve** `out/diario/<AAAA-MM-DD>/fecho.md`:
   - **Feito hoje:** execuções com sucesso (rotina, funcionário, resumo) e tarefas concluídas.
   - **Falhou ou ficou por rever:** execuções falhadas ou com avisos, com o resumo e o que fazer.
   - **Entregas à espera de revisão humana:** ficheiros novos em `out/` com a data de hoje.
   - **Para amanhã:** tarefas em curso ou bloqueadas, e as rotinas de amanhã de manhã.
3. **Propõe atualizações ao quadro** (tarefas a fechar, a desbloquear, a criar) e aplica só as que decorrem diretamente de uma execução de hoje, por exemplo:
   `python3 -m foundry tarefa atualizar --id <n> --estado concluida`
   As restantes ficam como proposta no ficheiro.

Curto. Não repitas o morning: só o que mudou durante o dia.
