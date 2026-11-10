---
name: drift-anomalias
description: "Deteta deriva entre uma amostra de referencia e a atual (PSI) e anomalias em series de KPIs (z robusto). Usar na vigia diaria das fontes, ou quando alguem pergunta se os dados mudaram ou se um valor esta fora do normal."
---

# Deriva e anomalias

1. **Fontes.** Lê `cerebro/fontes.md`: para cada fonte diz o ficheiro, a coluna de data, as métricas, as dimensões e, se houver, o ficheiro de referência. Trata só as que existirem em `inbox/dados/`.
2. **Anomalias na série** (uma chamada por métrica e dimensão):
   `python3 -m foundry drift anomalias inbox/dados/<ficheiro> --data <col> --valor <métrica> --grupo <dimensão> --out out/vigia/<AAAA-MM-DD>/<fonte>`
   Assinala os últimos 4 pontos com |z| acima de 3,5 face ao nível local. Séries com menos de 16 pontos não são avaliadas.
3. **Deriva de distribuição**, quando a fonte tem referência:
   `python3 -m foundry drift psi inbox/dados/<referencia> inbox/dados/<atual> --out out/vigia/<AAAA-MM-DD>/<fonte>`
   PSI abaixo de 0,10 estável; 0,10 a 0,25 a vigiar; acima de 0,25 deriva relevante. Repara também em categorias novas ou desaparecidas e em mudanças de esquema.
4. **Diagnóstico, por esta ordem:** carga incompleta ou atrasada → duplicados → mudança de esquema ou de codificação → categoria nova → só então negócio. Usa `python3 -m foundry perfil` se precisares de confirmar a hipótese de dados.
5. **Escreve** `out/vigia/<AAAA-MM-DD>/leitura.md`: por cada alerta, o que mudou, quanto, desde quando, causa mais provável, o que verificar e quem (Kenshin para dados, Hachiman para negócio, Tetsuo se alimenta um modelo).
6. **Regista** alertas relevantes: `python3 -m foundry evento "<fonte>: <o que mudou>" --agente susanoo --nivel aviso`. Deriva relevante numa fonte que alimenta um modelo abre tarefa para o Tetsuo.

Sem alertas, diz isso numa linha: silêncio também é informação.
