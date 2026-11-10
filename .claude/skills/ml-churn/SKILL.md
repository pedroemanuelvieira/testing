---
name: ml-churn
description: "Modelo de churn com validacao temporal honesta (treino, validacao que escolhe, teste que so reporta) e comparacao com o baseline de recencia. Usar para lista de clientes a reter, priorizacao de retencao ou perguntas sobre quem vai deixar de comprar."
---
<!-- Gerado por motor_ml/gerar_skills.py a partir de build_skills.py (bi_ml 0.10.0). Nao editar a mao. -->
# 912 · ml-churn (ml010-churn)

Supervisor: Tetsuo (901). Motor: bi_ml 0.10.0 em `motor_ml/`, validado apenas com dados sinteticos.

## Entradas
Pasta com CSV conforme o contrato: sales.csv (date, order_id, customer_id, product_id, qty, revenue; opcional cost) e, quando o modulo o pede, stock.csv (date, product_id, stock_qty). Devolucoes (linhas negativas), vendas de balcao sem cliente, ids numericos e stock negativo sao tratados pela camada de preparacao e registados em qualidade_dados.json. CSV de ERP portugues: colocar csv_options.json na mesma pasta, ex. {'sep': ';', 'decimal': ',', 'encoding': 'latin-1', 'date_format': '%d/%m/%Y', 'revenue_basis': 'sem_imposto', 'currency': 'EUR'} em JSON valido (aspas duplas); datas com barras sem date_format sao recusadas (03/04 e ambiguo). Precisa de 450 dias de historico ou mais (180 de arranque + purga de 2x90 + horizonte de 90); abaixo disso o modulo falha com mensagem.

Neste escritorio os extratos ficam em `inbox/dados/vendas/` (ou noutra pasta indicada no pedido).

## Como executar
Primeiro `python3 -m foundry ml check --data PASTA --out out/ml/check` e ler `qualidade_dados.json` (skill ml-qualidade). Depois:
`python3 -m foundry ml churn --data PASTA --out out/ml/churn`
Em Windows usar `python`. Um comando por chamada. Codigo de saida 2 = erro de dados com mensagem: reportar a quem pediu, nao contornar. Codigo 3 = faltam dependencias (`python -m pip install -r motor_ml/requirements.txt`).

## Saidas
churn_scores.csv por cliente: p_churn, decil (10 = maior risco), clv_12m_heuristica e risco_x_valor (p_churn x valor, para priorizar retencao; o valor e uma heuristica cujo ranking equivale a margem recente x 2). relatorio_churn.json: metricas de validacao e de teste por candidato (baseline_recencia, logistica, gbm), modelo escolhido, taxa de churn do teste.

## Interpretacao
Se o modelo escolhido for baseline_recencia, o ML nao acrescenta nada: dizer isso. O erro-padrao do AUC ronda 0,01 com cerca de 1300 clientes: diferencas inferiores a isso entre modelos sao ruido. Churn aqui significa nao comprar nos proximos 90 dias.

## Acoes
Atuar sobre os decis 9 e 10 ordenados por risco_x_valor. Medir o efeito da retencao com um grupo de controlo, nao com antes e depois.

## Limites e abstencao
Horizonte de 90 dias errado para ciclos longos (B2B). Probabilidades calibradas so no sentido estatistico, nao garantem causalidade. Dados de teste sinteticos sao faceis (baseline AUC 0,88).
Se os dados nao cumprirem o contrato ou o historico for curto, NAO responder com numeros: explicar o que falta. Todos os testes do pacote usam dados sinteticos; validar no historico real da equipa antes de decidir. Nada e publicado: os resultados ficam em `out/ml/` a espera de revisao humana.
