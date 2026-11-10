---
name: ml-qualidade
description: "Verifica e prepara extratos de ERP antes de qualquer analise de ML para BI: devolucoes, vendas sem cliente, duplicados, ids que nao casam entre vendas e stock, stock negativo. Usar sempre primeiro, ou quando o utilizador pedir para validar ou limpar dados de vendas e stock."
---
<!-- Gerado por motor_ml/gerar_skills.py a partir de build_skills.py (bi_ml 0.10.0). Nao editar a mao. -->
# 910 · ml-qualidade (ml010-check)

Supervisor: Tetsuo (901). Motor: bi_ml 0.10.0 em `motor_ml/`, validado apenas com dados sinteticos.

## Entradas
Pasta com CSV conforme o contrato: sales.csv (date, order_id, customer_id, product_id, qty, revenue; opcional cost) e, quando o modulo o pede, stock.csv (date, product_id, stock_qty). Devolucoes (linhas negativas), vendas de balcao sem cliente, ids numericos e stock negativo sao tratados pela camada de preparacao e registados em qualidade_dados.json. CSV de ERP portugues: colocar csv_options.json na mesma pasta, ex. {'sep': ';', 'decimal': ',', 'encoding': 'latin-1', 'date_format': '%d/%m/%Y', 'revenue_basis': 'sem_imposto', 'currency': 'EUR'} em JSON valido (aspas duplas); datas com barras sem date_format sao recusadas (03/04 e ambiguo).

Neste escritorio os extratos ficam em `inbox/dados/vendas/` (ou noutra pasta indicada no pedido).

## Como executar
`python3 -m foundry ml check --data PASTA --out out/ml/check`
Em Windows usar `python`. Um comando por chamada. Codigo de saida 2 = erro de dados com mensagem: reportar a quem pediu, nao contornar. Codigo 3 = faltam dependencias (`python -m pip install -r motor_ml/requirements.txt`).

## Saidas
qualidade_dados.json (contagens e valores afetados por cada decisao de preparacao, lista de avisos) e relatorio_check.json (periodo, n.o de produtos, cobertura de stock por receita).

## Interpretacao
Ler os avisos antes de usar qualquer outro modulo. Tres naturezas separadas: vendas brutas (qty>0), devolucoes (qty<0: devolucoes_unidades, devolucoes_valor) e ajustes de valor (descontos em linha e notas de credito/debito so de valor: ajustes_valor_liquido). receita_liquida = receita_bruta - devolucoes_valor + ajustes_valor_liquido e reconcilia exatamente com a soma do extrato (reconciliado_com_entrada=true); se falhar, o modulo para. Duplicados exatos nao sao removidos sem pedido: perguntar ao utilizador se sao legitimos. Linhas nao-produto (portes, embalagem) distorcem ABC/basket: o aviso 'possivel_nao_produto' aparece quando um id esta em >=60% das encomendas; listar esses ids em csv_options.json ("exclude_products") e a reconciliacao mantem-se exata (nao_produto_valor).

## Acoes
Se cobertura_stock for baixa, pedir a lista de codigos do stock (formatos diferentes: zeros a esquerda, prefixos, maiusculas). Nunca corrigir ids por palpite.

## Limites e abstencao
Nao infere impostos: declarar em csv_options.json revenue_basis (sem_imposto ou com_imposto) e currency (ex. EUR); sem isso os comandos com valores monetarios avisam que margens e ROI so valem com receita, custo e gasto na mesma base. Nunca dividir por uma taxa unica (taxas mistas e isencoes). Nao valida o resto da semantica do negocio (preco). Nao junta tabelas de fontes diferentes. Erro de dados termina com codigo 2 e mensagem: nao contornar, perguntar.
Se os dados nao cumprirem o contrato ou o historico for curto, NAO responder com numeros: explicar o que falta. Todos os testes do pacote usam dados sinteticos; validar no historico real da equipa antes de decidir. Nada e publicado: os resultados ficam em `out/ml/` a espera de revisao humana.
