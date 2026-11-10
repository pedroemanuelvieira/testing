---
name: qualidade-dados
description: "Perfil de qualidade de um CSV ou extrato - nulos, duplicados, tipos, unicidade da chave, frescura, buracos na serie e valores extremos. Usar antes de qualquer analise sobre uma fonte nova, ou quando ha suspeita de erro nos dados."
---

# Qualidade de dados

1. **Perfil:**
   `python3 -m foundry perfil <ficheiro.csv> --chave <col1,col2> --data <coluna de data> --max-dias <limite> --out out/qualidade/<AAAA-MM-DD>/<fonte>`
   Separador e codificação são detetados; com `;` assume vírgula decimal. A chave e o limite de frescura de cada fonte estão em `cerebro/fontes.md`.
2. **Lê `qualidade.md`** e separa:
   - **bloqueia a análise:** chave não única, coluna numérica com valores não numéricos, dados desatualizados para lá do limite, buracos na série;
   - **a confirmar com o dono dos dados:** linhas duplicadas, nulos acima de 20%, o mesmo valor escrito de formas diferentes, valores extremos, negativos onde não se esperam.
3. **Não corrijas por palpite.** Não removas duplicados, não imputes nulos, não alteres identificadores. Descreve o problema, a dimensão (quantas linhas, que percentagem) e a pergunta a fazer ao dono dos dados.
4. **Para extratos de vendas destinados a ML**, usa antes a skill `ml-qualidade` (910), que conhece o contrato do motor.
5. **Entrega** `out/qualidade/<AAAA-MM-DD>/<fonte>/parecer.md`: pode usar-se, pode usar-se com reservas (quais), não usar (porquê), e as perguntas para o dono dos dados.

Se o ficheiro tiver dados pessoais (nomes, emails, NIF), di-lo e confirma que está no ambiente aprovado antes de continuar.
