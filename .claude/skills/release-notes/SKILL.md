---
name: release-notes
description: "Escreve as notas de uma publicacao de modelo ou relatorio Power BI para os utilizadores, a partir das alteracoes no projeto. Usar quando um modelo ou relatorio foi alterado e e preciso comunicar o que mudou."
---

# Notas de publicação

1. **O que mudou.** Usa a fonte disponível: o diff do projeto PBIP (`git diff` ou `git log` entre versões), a comparação de dois dicionários (`out/dicionario/`), ou a descrição dada por quem alterou.
2. **Separa** por impacto no utilizador:
   - **Novo:** páginas, medidas, filtros que passaram a existir.
   - **Alterado:** o que dá agora um número diferente. Para cada medida alterada: o que mudou na definição, a partir de quando, e um exemplo do efeito.
   - **Corrigido:** erros resolvidos.
   - **Removido ou substituído:** e o que usar em vez disso.
3. **Linguagem de quem usa o relatório**, não de quem o constrói: "A margem passa a descontar devoluções" em vez de "alterada a medida [Margem %]".
4. **Números que mudam** merecem destaque no topo: são a primeira coisa que os utilizadores notam.
5. **Guarda** `out/release-notes/<AAAA-MM-DD>/<relatorio>.md` com: título e data, resumo em duas linhas, as quatro secções (só as que tiverem conteúdo), quem contactar (papel).

Nada é enviado: o texto fica pronto para a pessoa responsável rever e publicar.
