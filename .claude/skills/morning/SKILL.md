---
name: morning
description: "Arranque do dia do escritorio - o que correu durante a noite e de manha, falhas, tarefas em foco, bloqueios e tres prioridades. Usar quando alguem escreve morning, bom dia ou pergunta o que ha para hoje."
---

# Morning

1. **Estado real:** `python3 -m foundry estado --json`. Usa `rotinas[].ultima`, `execucoes`, `tarefas` e `eventos`.
2. **O que mudou desde ontem:** lê os ficheiros de `out/` com a data de hoje ou de ontem que existirem (triagem, refresh, vigia, kpis, ml).
3. **Escreve** `out/diario/<AAAA-MM-DD>/morning.md`, que caiba num ecrã de telemóvel:
   - **Alertas** (só se houver): execuções falhadas, refreshes em falha repetida, anomalias, tarefas bloqueadas ou com prazo ultrapassado.
   - **Três prioridades do dia**, cada uma com o próximo passo e quem o dá (pessoa por papel ou funcionário). Critério: bloqueios primeiro, depois prazos de hoje, depois tarefas em foco.
   - **Fila:** pedidos por triar, tarefas pendentes por funcionário (só contagens).
   - **Hoje corre:** as rotinas agendadas para hoje, com a hora.
4. Se houver calendário ou email ligados no ambiente, acrescenta as reuniões de hoje e o que preparar. Se não houver, não os menciones.

Sem novidades, diz isso em duas linhas. Não inventes reuniões, prazos nem prioridades que os dados não sustentam.

Termina com: "Queres que trate de algum destes?"
