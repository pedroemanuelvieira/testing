---
name: ml-ciclo-vida
description: "Classifica clientes por fase do ciclo de vida (novo, ativo, em risco, perdido, reativado) relativamente ao ritmo proprio de compra de cada cliente. Usar para base ativa, clientes em risco, reativacao ou segmentacao por comportamento de compra."
---
<!-- Gerado por motor_ml/gerar_skills.py a partir de build_skills.py (bi_ml 0.10.0). Nao editar a mao. -->
# 911 · ml-ciclo-vida (ml010-lifecycle)

Supervisor: Tetsuo (901). Motor: bi_ml 0.10.0 em `motor_ml/`, validado apenas com dados sinteticos.

## Entradas
Pasta com CSV conforme o contrato: sales.csv (date, order_id, customer_id, product_id, qty, revenue; opcional cost) e, quando o modulo o pede, stock.csv (date, product_id, stock_qty). Devolucoes (linhas negativas), vendas de balcao sem cliente, ids numericos e stock negativo sao tratados pela camada de preparacao e registados em qualidade_dados.json. CSV de ERP portugues: colocar csv_options.json na mesma pasta, ex. {'sep': ';', 'decimal': ',', 'encoding': 'latin-1', 'date_format': '%d/%m/%Y', 'revenue_basis': 'sem_imposto', 'currency': 'EUR'} em JSON valido (aspas duplas); datas com barras sem date_format sao recusadas (03/04 e ambiguo). customer_id obrigatorio para este modulo: vendas anonimas sao excluidas com aviso.

Neste escritorio os extratos ficam em `inbox/dados/vendas/` (ou noutra pasta indicada no pedido).

## Como executar
Primeiro `python3 -m foundry ml check --data PASTA --out out/ml/check` e ler `qualidade_dados.json` (skill ml-qualidade). Depois:
`python3 -m foundry ml lifecycle --data PASTA --out out/ml/lifecycle`
Em Windows usar `python`. Um comando por chamada. Codigo de saida 2 = erro de dados com mensagem: reportar a quem pediu, nao contornar. Codigo 3 = faltam dependencias (`python -m pip install -r motor_ml/requirements.txt`).

## Saidas
lifecycle.csv por cliente: stage, recency, freq_30/90/180, monetary_180, aov, tenure, mean_gap, gap_ratio. relatorio_lifecycle.json com a contagem por fase.

## Interpretacao
A fase compara a recencia com o intervalo medio proprio (ativo ate 1,5x, em risco ate 3x, perdido acima). Num teste com verdade conhecida, mais de 85% dos clientes que abandonaram ficaram em perdido ou em risco.

## Acoes
Em risco: contacto de retencao. Perdido: campanha de reativacao com custo controlado. Novo: onboarding. Reativado: monitorizar recaida.

## Limites e abstencao
Clientes com 1 compra nao tem ritmo (usa tenure). Sazonalidade longa (compras anuais) classifica como perdido por erro: confirmar o ciclo do negocio.
Se os dados nao cumprirem o contrato ou o historico for curto, NAO responder com numeros: explicar o que falta. Todos os testes do pacote usam dados sinteticos; validar no historico real da equipa antes de decidir. Nada e publicado: os resultados ficam em `out/ml/` a espera de revisao humana.
