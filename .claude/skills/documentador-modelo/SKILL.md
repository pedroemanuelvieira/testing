---
name: documentador-modelo
description: "Gera o dicionario de um modelo semantico PBIP/TMDL - tabelas, colunas, medidas com expressao e dependencias, relacoes, papeis e diagrama. Usar para documentar um modelo, responder 'que medidas temos' ou preparar o onboarding de um analista."
---

# Dicionário do modelo

1. **Gera:**
   `python3 -m foundry tmdl doc inbox/modelos/<modelo> --out out/dicionario/<AAAA-MM-DD>/<modelo>`
   Produz `dicionario.md` (legível) e `dicionario.json` (medidas com expressão e dependências).
2. **Completa as descrições em falta.** Para cada medida sem descrição, propõe uma frase a partir da expressão e do nome, e marca-a como _proposta_. A definição oficial vive em `cerebro/glossario.md`; se a proposta contradisser o glossário, assinala o conflito em vez de escolher.
3. **Assinala** o que um leitor novo precisa de saber: medidas que dependem de outras em cadeia, medidas com filtros embutidos, relações inativas e a medida que as usa, colunas ocultas que são chaves.
4. **Compara com a versão anterior**, se existir em `out/dicionario/`: medidas novas, removidas e com expressão alterada. Isto alimenta as notas de publicação da Sakura.
5. **Entrega** o dicionário e uma nota curta: quantas tabelas, medidas e papéis, quantas descrições ficaram por confirmar, o que mudou.

As descrições propostas só passam a oficiais quando o dono do modelo as aceitar e as escrever no próprio modelo (linhas `///` no TMDL). Não edites o modelo.
