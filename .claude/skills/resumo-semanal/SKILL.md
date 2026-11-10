---
name: resumo-semanal
description: "Resumo semanal do escritorio - execucoes por funcionario, taxa de sucesso, tarefas fechadas, horas poupadas estimadas e licoes propostas para o cerebro partilhado. Usar a sexta-feira ou quando perguntam como correu a semana."
---

# Resumo semanal

1. **Dados:** `python3 -m foundry estado --json`. Usa `telemetria` (7 dias), `execucoes`, `tarefas` e `rotinas`.
2. **Escreve** `out/semana/<AAAA-MM-DD>/resumo.md`:
   - **Em três linhas:** o que o escritório entregou, o que falhou, o que precisa de decisão.
   - **Por funcionário:** execuções, sucesso, o resultado mais relevante da semana.
   - **Quadro:** tarefas concluídas, abertas, bloqueadas há mais de uma semana.
   - **Horas poupadas (estimativa):** execuções com sucesso × o tempo manual declarado em `cerebro/regras.md` para essa rotina. Mostra a conta. Sem tabela declarada, escreve "sem estimativa: falta a tabela de tempos" em vez de um número.
   - **Rotinas a rever:** as que falharam duas ou mais vezes, e as que foram sempre ignoradas por falta de entradas (candidatas a desligar ou a corrigir a origem).
   - **Para decidir:** no máximo três pontos, cada um com a pergunta concreta.
3. **Lições propostas:** `out/semana/<AAAA-MM-DD>/licoes_propostas.md`. Um padrão só é lição se se repetiu pelo menos duas vezes (a mesma falha, a mesma correção pedida, a mesma pergunta em aberto). Cada lição numa linha, com a evidência. Ignora casos isolados.
4. **Não gravas no cérebro.** As lições aprovadas pela equipa são acrescentadas a `cerebro/licoes.md` numa sessão interativa.

Termina com as três prioridades propostas para a próxima semana e o tema sugerido para a reunião de equipa.
