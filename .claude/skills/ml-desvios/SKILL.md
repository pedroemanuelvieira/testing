---
name: ml-desvios
description: "Explica desvios de vendas: decomposicao preco, volume e mix que fecha por linha, anomalias semanais por MAD e desvio face a orcamento ou previsao mensal. Usar para explicar porque a receita subiu ou desceu face a um periodo ou ao plano."
---
<!-- Gerado por motor_ml/gerar_skills.py a partir de build_skills.py (bi_ml 0.10.0). Nao editar a mao. -->
# 915 · ml-desvios (ml010-variance)

Supervisor: Tetsuo (901). Motor: bi_ml 0.10.0 em `motor_ml/`, validado apenas com dados sinteticos.

## Entradas
Pasta com CSV conforme o contrato: sales.csv (date, order_id, customer_id, product_id, qty, revenue; opcional cost) e, quando o modulo o pede, stock.csv (date, product_id, stock_qty). Devolucoes (linhas negativas), vendas de balcao sem cliente, ids numericos e stock negativo sao tratados pela camada de preparacao e registados em qualidade_dados.json. CSV de ERP portugues: colocar csv_options.json na mesma pasta, ex. {'sep': ';', 'decimal': ',', 'encoding': 'latin-1', 'date_format': '%d/%m/%Y', 'revenue_basis': 'sem_imposto', 'currency': 'EUR'} em JSON valido (aspas duplas); datas com barras sem date_format sao recusadas (03/04 e ambiguo). Para planos: budget_plan.csv e/ou forecast_plan.csv (period, product_id, planned_qty, planned_revenue; previsao exige issued_at anterior ao mes).

Neste escritorio os extratos ficam em `inbox/dados/vendas/` (ou noutra pasta indicada no pedido).

## Como executar
Primeiro `python3 -m foundry ml check --data PASTA --out out/ml/check` e ler `qualidade_dados.json` (skill ml-qualidade). Depois:
`python3 -m foundry ml variance --data PASTA --out out/ml/variance`
Em Windows usar `python`. Um comando por chamada. Codigo de saida 2 = erro de dados com mensagem: reportar a quem pediu, nao contornar. Codigo 3 = faltam dependencias (`python -m pip install -r motor_ml/requirements.txt`).

## Saidas
pvm.csv (efeito_preco, efeito_volume, efeito_mix, desvio_total por produto), anomalias.csv, budget_variance.csv e forecast_variance.csv quando ha plano.

## Interpretacao
Preco + volume + mix somam exatamente o desvio total em cada produto. A CLI compara janelas de igual duracao (--days, por omissao 90). Ao usar a funcao pvm com periodos de duracao diferente (mais de 10%) ha aviso; usar per_day=True para taxas diarias. Meses do plano sem qualquer venda no extrato sao erro de cobertura, nao venda zero.

## Acoes
Atacar primeiro o maior efeito absoluto. Anomalia com z robusto acima de 3,5 pede verificacao de dados antes de explicacao de negocio.

## Limites e abstencao
Descritivo: nao atribui causa. Meses abertos nao entram. Percentagem sobre plano zero e desconhecida.
Se os dados nao cumprirem o contrato ou o historico for curto, NAO responder com numeros: explicar o que falta. Todos os testes do pacote usam dados sinteticos; validar no historico real da equipa antes de decidir. Nada e publicado: os resultados ficam em `out/ml/` a espera de revisao humana.
