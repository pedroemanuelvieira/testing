---
name: testes-rls
description: "Gera a matriz papel x tabela de RLS de um modelo PBIP/TMDL, identifica tabelas nao protegidas e prepara os casos de teste a executar em 'Ver como'. Usar antes de publicar um modelo com seguranca ao nivel da linha ou quando perguntam quem ve o que."
---

# Testes de RLS

1. **Gera a matriz:**
   `python3 -m foundry tmdl rls inbox/modelos/<modelo> --out out/revisao/<AAAA-MM-DD>/<modelo>`
2. **Lê `rls.md`.** Para cada papel: que tabelas têm filtro direto, quais são protegidas por relação e quais ficam sem filtro. O filtro propaga do lado «um» para o lado «muitos»; relações bidirecionais propagam nos dois sentidos e merecem atenção redobrada.
3. **Avalia as tabelas sem filtro.** Um calendário sem filtro é normal. Objetivos, margens, custos ou dados de pessoas sem filtro são um risco: diz qual e porquê.
4. **Completa os casos de teste** com o que a ferramenta não sabe: os utilizadores de teste a usar (marcadores como `<UPN_TESTE_A>`), um visual por tabela sensível, o total esperado por papel calculado na fonte.
5. **Entrega** `out/revisao/<AAAA-MM-DD>/<modelo>/rls.md` com a matriz, os riscos e a lista de casos com a coluna "Passou?" por preencher.

A matriz é uma leitura estática do modelo. O RLS só fica validado quando uma pessoa executa os casos no Power BI Desktop (Modelação → Ver como) e regista o resultado. Nunca escrevas "RLS validado" antes disso. Filtros visuais num relatório não são segurança.
