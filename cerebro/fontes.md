# Fontes vigiadas

Registo das fontes que os funcionários acompanham. O Susanoo, o Hachiman e o Kenshin leem daqui o ficheiro, as colunas e os limites.
As entradas abaixo correspondem aos dados fictícios de `exemplos/` (copiados para `inbox/` com `python3 -m foundry demo`).

| Fonte | Ficheiro em inbox/dados/ | Data | Métricas | Dimensões | Chave | Frescura (dias) | Referência para deriva |
|---|---|---|---|---|---|---:|---|
| Vendas semanais | `vendas_semanais.csv` | `semana` | `receita`, `unidades` | `regiao`, `categoria` | `semana,regiao,categoria` | 9 | — |
| Perfil de clientes | `atual.csv` | — | `ticket`, `itens` | `canal`, `regiao` | `cliente_id` | — | `referencia.csv` |

## Extratos para ML
Pasta `inbox/dados/vendas/`: `sales.csv` (date, order_id, customer_id, product_id, qty, revenue; opcional cost), `stock.csv` (date, product_id, stock_qty) e `csv_options.json` com separador, decimal, formato de data, base fiscal e moeda. O contrato completo está em `motor_ml/README_V010.md`.

## Registos de refresh
Pasta `inbox/refresh/`: um CSV com objeto, início, fim, estado e erro por execução, exportado do serviço ou do orquestrador de pipelines.
