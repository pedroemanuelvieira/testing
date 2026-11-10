---
name: briefing-bi
description: "Briefing diario de BI para a equipa - junta o que os funcionarios produziram (refreshes, triagem, vigia, KPIs, ML) numa pagina com alertas e decisoes pedidas. Usar de manha depois das rotinas, ou quando pedem o ponto de situacao."
---

# Briefing de BI

1. **Estado:** `python3 -m foundry estado --json`.
2. **Recolhe** o que existe de hoje e de ontem em `out/`: `refresh/`, `triagem/`, `vigia/`, `kpis/`, `ml/`, `revisao/`. Lê as leituras (`leitura.md`, `triagem.md`, `parecer.md`), não os JSON completos.
3. **Escreve** `out/briefing/<AAAA-MM-DD>/briefing.md`, uma página:
   - **Semáforo:** dados (refreshes e qualidade), indicadores (anomalias e KPIs), trabalho (fila e bloqueios). Verde, amarelo ou vermelho, com a razão numa linha.
   - **Precisa de uma pessoa hoje:** no máximo cinco pontos, por ordem de impacto, cada um com o que decidir ou fazer e o ficheiro onde está o detalhe.
   - **Feito pelos funcionários:** uma linha por execução relevante.
   - **Sem dados:** o que não correu por falta de entradas, para ninguém assumir que está tudo bem.
4. **Verifica** antes de entregar: cada número do briefing está num ficheiro de `out/`? Algum funcionário reportou avisos que ficaram de fora?
5. **Regista:** `python3 -m foundry evento "Briefing de BI" --agente amaterasu --nivel ok --detalhe "<semáforo em 10 palavras>"`.

Não repitas relatórios: aponta para eles. Sem novidades, o briefing são três linhas.
