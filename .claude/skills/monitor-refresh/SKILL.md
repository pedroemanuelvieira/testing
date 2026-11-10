---
name: monitor-refresh
description: "Analisa registos exportados de refreshes e pipelines - falhas, falhas repetidas, objetos sem sucesso recente e duracoes anomalas, com diagnostico e proximo passo. Usar na verificacao diaria ou quando um refresh falha."
---

# Monitor de refreshes e pipelines

1. **Registos.** `ls inbox/refresh`. Cada CSV tem uma linha por execução: objeto, início, fim, estado, erro (nomes de coluna flexíveis).
2. **Analisa:**
   `python3 -m foundry refresh inbox/refresh/<ficheiro> --horas 24 --max-atraso-h 26 --out out/refresh/<AAAA-MM-DD>`
3. **Lê `refresh.md`** e, para cada problema, dá o diagnóstico provável a partir da mensagem de erro:
   - tempo limite ou ligação recusada → origem indisponível ou gateway; tentar de novo fora de horas e confirmar com quem gere a origem;
   - coluna não encontrada ou tipo inválido → mudança de esquema na origem; comparar com a última carga boa;
   - credenciais ou acesso negado → credenciais expiradas no serviço; renovar (ação humana);
   - memória ou capacidade → volume cresceu; rever atualização incremental;
   - duração a dobrar sem erro → volume, bloqueios na origem ou passo de Power Query que deixou de fazer dobragem de consulta.
4. **Escalona:** três falhas seguidas no mesmo objeto abrem tarefa bloqueada:
   `python3 -m foundry tarefa criar --titulo "Refresh a falhar: <objeto>" --agente kenshin --fase ingestao --estado bloqueada --origem refresh`
5. **Escreve** `out/refresh/<AAAA-MM-DD>/leitura.md`: estado geral numa linha, depois por objeto com problema: o que aconteceu, diagnóstico provável, próximo passo, quem o dá.

Trabalhas sobre o que foi exportado. Não voltas a lançar refreshes nem alteras agendamentos: propões. Se o ambiente tiver um conector para o serviço, só leitura.
