---
name: ml-basket
description: "Analise de cesto de compras com pares de produtos, suporte, confianca, lift e controlo de falsas descobertas (Benjamini-Hochberg). Usar para cross-sell, bundles e produtos comprados em conjunto."
---
<!-- Gerado por motor_ml/gerar_skills.py a partir de build_skills.py (bi_ml 0.10.0). Nao editar a mao. -->
# 916 · ml-basket (ml010-basket)

Supervisor: Tetsuo (901). Motor: bi_ml 0.10.0 em `motor_ml/`, validado apenas com dados sinteticos.

## Entradas
Pasta com CSV conforme o contrato: sales.csv (date, order_id, customer_id, product_id, qty, revenue; opcional cost) e, quando o modulo o pede, stock.csv (date, product_id, stock_qty). Devolucoes (linhas negativas), vendas de balcao sem cliente, ids numericos e stock negativo sao tratados pela camada de preparacao e registados em qualidade_dados.json. CSV de ERP portugues: colocar csv_options.json na mesma pasta, ex. {'sep': ';', 'decimal': ',', 'encoding': 'latin-1', 'date_format': '%d/%m/%Y', 'revenue_basis': 'sem_imposto', 'currency': 'EUR'} em JSON valido (aspas duplas); datas com barras sem date_format sao recusadas (03/04 e ambiguo). Uma encomenda e um order_id; funciona com vendas anonimas.

Neste escritorio os extratos ficam em `inbox/dados/vendas/` (ou noutra pasta indicada no pedido).

## Como executar
Primeiro `python3 -m foundry ml check --data PASTA --out out/ml/check` e ler `qualidade_dados.json` (skill ml-qualidade). Depois:
`python3 -m foundry ml basket --data PASTA --out out/ml/basket`
Em Windows usar `python`. Um comando por chamada. Codigo de saida 2 = erro de dados com mensagem: reportar a quem pediu, nao contornar. Codigo 3 = faltam dependencias (`python -m pip install -r motor_ml/requirements.txt`).

## Saidas
basket_pares.csv: n_ab, support, conf_a_b, conf_b_a, lift, leverage, p, q_bh, significativo, encomendas_incrementais (n_ab menos o esperado sob independencia), material, elegivel e motivo_exclusao. Pares com menos de 20 coocorrencias nao entram.

## Interpretacao
Usar so elegivel=True. elegivel = significativo (Benjamini-Hochberg) E material. Com muitas encomendas quase tudo e significativo: pedir ao utilizador, ANTES de ver os pares, um limiar de negocio (--min-lift e/ou --min-incremental-orders, a partir da margem por encomenda e do custo da acao). Sem limiar, material fica vazio e elegivel=False, com aviso; os pares ficam disponiveis para exploracao, mas recommend nao os recomenda. Tabelas antigas sem elegivel devem ser recalculadas com limiar declarado. Em teste com verdade conhecida recuperou os 3 pares plantados. Lift alto com poucas coocorrencias engana: olhar tambem para leverage e n_ab.

## Acoes
Sugerir o par com maior confianca no sentido relevante (conf_a_b para quem leva A). Testar a oferta com grupo de controlo.

## Limites e abstencao
So pares, sem sequencia temporal nem margem. Associacao nao e uplift causal: testar a oferta com grupo de controlo. Validar o limiar num periodo posterior. Cuidado com encomendas gigantes (custo quadratico por encomenda).
Se os dados nao cumprirem o contrato ou o historico for curto, NAO responder com numeros: explicar o que falta. Todos os testes do pacote usam dados sinteticos; validar no historico real da equipa antes de decidir. Nada e publicado: os resultados ficam em `out/ml/` a espera de revisao humana.
