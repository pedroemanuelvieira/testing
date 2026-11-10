---
name: ml-abc-xyz
description: "Classificacao ABC por receita bruta e XYZ por variabilidade mensal da quantidade, com leitura sazonal quando ha 24 meses ou mais. Usar para segmentar o portefolio, priorizar atencao de compras e planeamento, ou perguntas sobre produtos importantes e previsiveis."
---
<!-- Gerado por motor_ml/gerar_skills.py a partir de build_skills.py (bi_ml 0.10.0). Nao editar a mao. -->
# 918 · ml-abc-xyz (ml010-abc-xyz)

Supervisor: Tetsuo (901). Motor: bi_ml 0.10.0 em `motor_ml/`, validado apenas com dados sinteticos.

## Entradas
Pasta com CSV conforme o contrato: sales.csv (date, order_id, customer_id, product_id, qty, revenue; opcional cost) e, quando o modulo o pede, stock.csv (date, product_id, stock_qty). Devolucoes (linhas negativas), vendas de balcao sem cliente, ids numericos e stock negativo sao tratados pela camada de preparacao e registados em qualidade_dados.json. CSV de ERP portugues: colocar csv_options.json na mesma pasta, ex. {'sep': ';', 'decimal': ',', 'encoding': 'latin-1', 'date_format': '%d/%m/%Y', 'revenue_basis': 'sem_imposto', 'currency': 'EUR'} em JSON valido (aspas duplas); datas com barras sem date_format sao recusadas (03/04 e ambiguo). Janela [start,end) em inicios de mes, pelo menos 3 meses completos e cobertura completa das vendas nessa janela.

Neste escritorio os extratos ficam em `inbox/dados/vendas/` (ou noutra pasta indicada no pedido).

## Como executar
Primeiro `python3 -m foundry ml check --data PASTA --out out/ml/check` e ler `qualidade_dados.json` (skill ml-qualidade). Depois:
`python3 -m foundry ml abc-xyz --start AAAA-MM-01 --end AAAA-MM-01 --data PASTA --out out/ml/abc-xyz`
Em Windows usar `python`. Um comando por chamada. Codigo de saida 2 = erro de dados com mensagem: reportar a quem pediu, nao contornar. Codigo 3 = faltam dependencias (`python -m pip install -r motor_ml/requirements.txt`).

## Saidas
abc_xyz.csv por produto: revenue, share, abc, cv, xyz, history_incomplete, class, cv_dessazonalizado, xyz_sazonal, nota_sazonal.

## Interpretacao
A = ate 80% da receita, B ate 95%, C o resto (o produto que cruza o limite fica na classe anterior). X: CV mensal ate 0,5; Y ate 1; Z acima. U = produto sem vendas antes da janela (historico insuficiente). Com 24 meses ou mais, xyz_sazonal compara cada mes com o mesmo mes dos OUTROS anos: um produto sazonal repetido e Z no bruto mas X no sazonal (medido: 200/200), e aleatorio continua Z (198/200, 0 falsos X).

## Acoes
AX/BX: reposicao regular por previsao. AZ: atencao individual e stock de seguranca. Se xyz_sazonal for melhor que xyz, planear com o perfil sazonal, nao tratar como imprevisivel.

## Limites e abstencao
Nao e recomendacao de stock (falta lead time e nivel de servico). Artigos sem vendas na janela nao aparecem sem catalogo. Limiares sao escolhas de negocio configuraveis na funcao, nao na CLI.
Se os dados nao cumprirem o contrato ou o historico for curto, NAO responder com numeros: explicar o que falta. Todos os testes do pacote usam dados sinteticos; validar no historico real da equipa antes de decidir. Nada e publicado: os resultados ficam em `out/ml/` a espera de revisao humana.
