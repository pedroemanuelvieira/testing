---
name: sql-powerquery
description: "Escreve, explica ou reve SQL de leitura e Power Query (M) a partir de linguagem natural. Usar para pedidos como 'escreve a query para', 'o que faz este M', 'porque e que esta query e lenta'."
---

# SQL e Power Query

1. **Esquema primeiro.** Pede ou lê as tabelas, colunas, chaves e granularidade. Sem esquema, escreve a query com nomes genéricos entre `<…>` e diz que são para substituir.
2. **Escreve só leitura.** `SELECT` com colunas explícitas (nunca `SELECT *`), filtro de datas por parâmetro, junções com a chave completa. Nunca `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `DROP` ou `TRUNCATE`.
3. **Confere a granularidade.** Antes de juntar, diz o grão de cada tabela; uma junção que multiplica linhas é o erro mais comum. Inclui uma query de controlo (contagem de linhas e total antes e depois).
4. **Power Query (M):** passos com nomes legíveis, tipos definidos uma vez no fim, filtros e remoção de colunas o mais cedo possível para manter a dobragem de consulta. Assinala o passo que a quebra.
5. **Explica** em 3 a 6 linhas o que a query faz, os pressupostos e o que pode correr mal (nulos nas chaves, fusos horários, duplicados).
6. **Rever uma query lenta:** filtros em colunas indexadas, funções aplicadas à coluna filtrada, junções sem chave, subconsultas repetidas, ordenações desnecessárias.
7. **Guarda** em `out/queries/<AAAA-MM-DD>/<nome>.sql` ou `.pq`, com um cabeçalho: objetivo, autor (funcionário), fonte, grão do resultado.

Não executas queries em bases de dados de produção a menos que o ambiente tenha uma ligação de leitura aprovada e o pedido o diga. Nunca escrevas credenciais numa query: usa parâmetros.
