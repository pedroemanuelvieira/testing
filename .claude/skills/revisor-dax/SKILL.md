---
name: revisor-dax
description: "Reve medidas DAX e o modelo semantico de um projeto PBIP/TMDL antes de publicar - referencias partidas, divisoes sem DIVIDE, FILTER sobre tabelas inteiras, relacoes bidirecionais, formatos e descricoes em falta. Usar para rever um modelo ou uma medida."
---

# Revisão de DAX e modelo

1. **Corre a revisão** no projeto (pasta com ficheiros `.tmdl`):
   `python3 -m foundry tmdl lint inbox/modelos/<modelo> --out out/revisao/<AAAA-MM-DD>/<modelo>`
   Código de saída 1 significa que há erros; 2, que a pasta não tem TMDL (pedir o projeto em formato PBIP).
2. **Lê `revisao_modelo.md`.** Regras: M = medidas, C = colunas, R = relações, T = tabelas, S = segurança. Erros bloqueiam a publicação; avisos pedem correção ou justificação; notas são sugestões.
3. **Acrescenta o juízo** que a ferramenta não tem. Para cada erro e aviso: é mesmo um problema neste modelo? Qual é a correção? Escreve o DAX corrigido. Exemplos:
   - `[A] / [B]` → `DIVIDE([A], [B])`
   - `CALCULATE([M], FILTER(Vendas, Vendas[Canal] = "Online"))` → `CALCULATE([M], Vendas[Canal] = "Online")` ou `KEEPFILTERS(...)`
   - `IFERROR(x / y, 0)` → `DIVIDE(x, y, 0)`
4. **Verifica as regras da casa** em `cerebro/regras.md` (nomes, pastas de apresentação, formato, descrição obrigatória).
5. **Para uma medida solta** colada na conversa: revê-a com os mesmos critérios e diz que pressupostos fizeste sobre o modelo.
6. **Escreve** `out/revisao/<AAAA-MM-DD>/<modelo>/parecer.md`: veredito numa linha (pode publicar, pode publicar com reparos, não publicar), a lista de correções por ordem de gravidade com o DAX proposto, e o que não foi possível avaliar.
7. **Abre tarefa** para cada erro: `python3 -m foundry tarefa criar --titulo "Corrigir <objeto>" --agente benkei --fase transformacao --origem revisao`.

A revisão é estática. Desempenho mede-se no Performance Analyzer do Power BI Desktop; resultados validam-se contra a fonte. Nunca edites o modelo nem abras PBIX/PBIT.
