---
name: ml-procura
description: "Previsao semanal de procura por produto com intervalos p10 a p90. Por omissao usa a media das ultimas 13 semanas; a troca de metodo por backtest so acontece a pedido (--selection-policy guarded ou adaptive). Usar para planeamento de compras, previsao de vendas por produto ou intervalos de procura."
---
<!-- Gerado por motor_ml/gerar_skills.py a partir de build_skills.py (bi_ml 0.10.0). Nao editar a mao. -->
# 913 · ml-procura (ml010-forecast)

Supervisor: Tetsuo (901). Motor: bi_ml 0.10.0 em `motor_ml/`, validado apenas com dados sinteticos.

## Entradas
Pasta com CSV conforme o contrato: sales.csv (date, order_id, customer_id, product_id, qty, revenue; opcional cost) e, quando o modulo o pede, stock.csv (date, product_id, stock_qty). Devolucoes (linhas negativas), vendas de balcao sem cliente, ids numericos e stock negativo sao tratados pela camada de preparacao e registados em qualidade_dados.json. CSV de ERP portugues: colocar csv_options.json na mesma pasta, ex. {'sep': ';', 'decimal': ',', 'encoding': 'latin-1', 'date_format': '%d/%m/%Y', 'revenue_basis': 'sem_imposto', 'currency': 'EUR'} em JSON valido (aspas duplas); datas com barras sem date_format sao recusadas (03/04 e ambiguo). Cada produto precisa de 60 semanas ou mais desde a primeira venda; stock.csv e opcional mas melhora o tratamento das semanas com ruptura.

Neste escritorio os extratos ficam em `inbox/dados/vendas/` (ou noutra pasta indicada no pedido).

## Como executar
Primeiro `python3 -m foundry ml check --data PASTA --out out/ml/check` e ler `qualidade_dados.json` (skill ml-qualidade). Depois:
`python3 -m foundry ml forecast --data PASTA --out out/ml/forecast`
Em Windows usar `python`. Um comando por chamada. Codigo de saida 2 = erro de dados com mensagem: reportar a quem pediu, nao contornar. Codigo 3 = faltam dependencias (`python -m pip install -r motor_ml/requirements.txt`).

## Saidas
forecast.csv: forecast, p10, p90, method, selection_policy, selection_horizon, candidato_backtest, wape_holdout e wape_holdout_media_13s por produto e semana. forecast_omitidos.csv: produtos sem previsao e o motivo (nunca ha omissoes silenciosas).

## Interpretacao
Usar o intervalo, nao so o ponto. Grok reportou cobertura p10-p90 a 8 semanas de 0,79 a 0,86 por horizonte (nominal 0,80). Claude ciclo04, noutro ensaio sintetico, reportou cobertura global 0,79 mas apenas 0,71 (aprox. 72%) no horizonte 7: a cobertura nominal nao e garantida por horizonte. Intervalos largos. Politicas: baseline (omissao) = media de 13 semanas, sem selecao. guarded = troca de metodo so se o candidato for pelo menos 15% melhor no backtest com horizonte igual ao pedido E ganhar em pelo menos 2/3 das dobras; medido a 8 semanas em dados sem sinal ficou igual a baseline (troca em 0 a 2% das series) e com sazonalidade e tendencia baixou o WAPE de 0,40 para 0,18 e de 0,37 para 0,22. adaptive = experimental, troca com 5% de ganho medio e piora cerca de 1% sem sinal. Se wape_holdout nao for melhor que wape_holdout_media_13s, usar a media e dizer porque.

## Acoes
Planear compras com p90 para produtos de ruptura cara e com a previsao central para o resto. Rever produtos em forecast_omitidos.csv manualmente.

## Limites e abstencao
Sem preco, promocoes ou feriados como regressores. Horizonte validado ate 8 semanas, so em dados sinteticos (2 sementes sem sinal e 2 com sinal). Semanas com ruptura sao imputadas e excluidas da avaliacao; a eficacia dessa imputacao nao foi medida contra procura latente verdadeira. guarded faz backtest de todos os candidatos; Claude ciclo04 reportou cerca de 10 minutos por semente no seu ensaio, custo dependente da maquina e dimensao. Nenhuma politica promete ganho sobre a media no historico real: comparar wape_holdout com wape_holdout_media_13s antes de usar guarded.
Se os dados nao cumprirem o contrato ou o historico for curto, NAO responder com numeros: explicar o que falta. Todos os testes do pacote usam dados sinteticos; validar no historico real da equipa antes de decidir. Nada e publicado: os resultados ficam em `out/ml/` a espera de revisao humana.
