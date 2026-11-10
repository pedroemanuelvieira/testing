---
name: ml-ruturas
description: "Estima unidades, receita e margem perdidas por falta de stock com contrafactual de nivel local e padrao semanal, sinalizando rupturas muito longas ou produtos possivelmente descontinuados. Usar para impacto de rupturas e priorizacao de reposicao."
---
<!-- Gerado por motor_ml/gerar_skills.py a partir de build_skills.py (bi_ml 0.10.0). Nao editar a mao. -->
# 914 · ml-ruturas (ml010-stockout)

Supervisor: Tetsuo (901). Motor: bi_ml 0.10.0 em `motor_ml/`, validado apenas com dados sinteticos.

## Entradas
Pasta com CSV conforme o contrato: sales.csv (date, order_id, customer_id, product_id, qty, revenue; opcional cost) e, quando o modulo o pede, stock.csv (date, product_id, stock_qty). Devolucoes (linhas negativas), vendas de balcao sem cliente, ids numericos e stock negativo sao tratados pela camada de preparacao e registados em qualidade_dados.json. CSV de ERP portugues: colocar csv_options.json na mesma pasta, ex. {'sep': ';', 'decimal': ',', 'encoding': 'latin-1', 'date_format': '%d/%m/%Y', 'revenue_basis': 'sem_imposto', 'currency': 'EUR'} em JSON valido (aspas duplas); datas com barras sem date_format sao recusadas (03/04 e ambiguo). stock.csv obrigatorio (snapshot de fim de dia por produto).

Neste escritorio os extratos ficam em `inbox/dados/vendas/` (ou noutra pasta indicada no pedido).

## Como executar
Primeiro `python3 -m foundry ml check --data PASTA --out out/ml/check` e ler `qualidade_dados.json` (skill ml-qualidade). Depois:
`python3 -m foundry ml stockout --data PASTA --out out/ml/stockout`
Em Windows usar `python`. Um comando por chamada. Codigo de saida 2 = erro de dados com mensagem: reportar a quem pediu, nao contornar. Codigo 3 = faltam dependencias (`python -m pip install -r motor_ml/requirements.txt`).

## Saidas
rupturas_eventos.csv (por evento: dias, truncado, possivel_descontinuado, unid, receita e margem perdidas) e rupturas_resumo.csv por produto.

## Interpretacao
E um limite superior para o dia em que a ruptura comeca (snapshot de fim de dia). A perda de um evento conta no maximo 60 dias; acima disso fica truncado, e se continua ate ao fim dos dados fica como possivel_descontinuado e nao deve entrar no total. Se os codigos de vendas e stock nao casarem, o modulo falha em vez de reportar zero rupturas.

## Acoes
Ordenar por receita_perdida. Para possivel_descontinuado confirmar com compras se o produto saiu do catalogo.

## Limites e abstencao
Sem substituicao entre produtos nem reposicao a meio do dia. Sobrestima cerca de 17% face a referencia sintetica. Buracos no stock acima de 7 dias ficam como desconhecidos, nao como ruptura.
Se os dados nao cumprirem o contrato ou o historico for curto, NAO responder com numeros: explicar o que falta. Todos os testes do pacote usam dados sinteticos; validar no historico real da equipa antes de decidir. Nada e publicado: os resultados ficam em `out/ml/` a espera de revisao humana.
