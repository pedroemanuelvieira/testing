---
name: ml-roi
description: "ROI incremental de uma campanha ou investimento a partir de uma serie semanal do resultado agregado e de controlos nao afetados, com intervalo por placebo no tempo e diagnosticos de validade. Usar quando perguntarem pelo retorno de campanhas ou promocoes, ou se vale renovar um investimento."
---
<!-- Gerado por motor_ml/gerar_skills.py a partir de build_skills.py (bi_ml 0.10.0). Nao editar a mao. -->
# 917 · ml-roi (ml010-roi-series)

Supervisor: Tetsuo (901). Motor: bi_ml 0.10.0 em `motor_ml/`, validado apenas com dados sinteticos.

## Entradas
serie.csv semanal: date, outcome (receita do alvo MAIS dos produtos canibalizados) e UM de dois tipos de controlo. (a) control_1..control_K: receita de produtos que a campanha nao deve afetar (use 3 ou mais); sem desenho o resultado e so indicio estatistico. (b) holdout_1..holdout_M: unidades de holdout reservadas ANTES da campanha por atribuicao aleatoria e nao expostas, JUNTO com --desenho aleatorizado|holdout_geografico|holdout_clientes; e o unico caminho para uma decisao causal. Declarar --desenho sem colunas holdout_* e recusado, e colunas holdout_* sem --desenho tambem. Parametros: --intervention-date, --spend, --margin-rate. Exemplo: python scripts/run.py roi-series --data DIR --series serie.csv --intervention-date 2025-03-01 --spend 3000 --margin-rate 0.35 (DIR precisa de sales.csv).

Neste escritorio os extratos ficam em `inbox/dados/vendas/` (ou noutra pasta indicada no pedido).

## Como executar
Primeiro `python3 -m foundry ml check --data PASTA --out out/ml/check` e ler `qualidade_dados.json` (skill ml-qualidade). Depois:
`python3 -m foundry ml roi-series --data PASTA --out out/ml/roi-series`
Em Windows usar `python`. Um comando por chamada. Codigo de saida 2 = erro de dados com mensagem: reportar a quem pediu, nao contornar. Codigo 3 = faltam dependencias (`python -m pip install -r motor_ml/requirements.txt`).

## Saidas
relatorio_roi-series.json: incremental, ic (90%), roi, roi_ic, decisao (positivo, negativo, indicio_estatistico_positivo, indicio_estatistico_negativo, inconclusivo, nao_afirmar), causal, evidencia_para_revisao, autorizacao (sempre humana_obrigatoria), pode_decidir_renovacao (sempre false), concordancia_especificacoes, roi_ic_racio, valido, verificavel, loo_spread, espaco_flag, espaco_controlos, holdout, avisos.

## Interpretacao
O pacote nunca autoriza renovar: pode_decidir_renovacao e sempre false. evidencia_para_revisao=true (exige --desenho, colunas holdout_* e concordancia entre o modelo com tendencia e o modelo de racio) significa evidencia estatistica condicionada ao desenho, a levar a um decisor humano que confirme atribuicao aleatoria documentada, holdout nao exposto, unidade de aleatorizacao e tamanho. Se as duas especificacoes discordarem, a decisao e inconclusivo. Sem desenho, a decisao e indicio_estatistico_*: um choque externo (concorrente, clima, preco) com efeito ZERO da campanha produz o mesmo resultado (medido: 3/3 cenarios), por isso dizer 'o resultado mudou face ao contrafactual', nunca 'a campanha causou'. Nunca citar um ROI se decisao for nao_afirmar ou inconclusivo. O limite inferior do IC pode apoiar uma revisao humana, mas nao e criterio suficiente para renovar; confirmar inferencia ao nivel das unidades aleatorizadas. valido=False quando retirar um controlo muda a conclusao ou um controlo se desvia dos outros no periodo da campanha (placebo no espaco). verificavel=False (sem holdout: menos de 3 controlos; sempre: pouco historico) significa que a contaminacao nao se consegue testar.

## Acoes
Se indicio_estatistico_*, propor holdout ou teste A/B na proxima vaga antes de decidir. Se inconclusivo, propor teste A/B em vez de decidir. Se valido mas verificavel=False, dizer a limitacao ao decisor.

## Limites e abstencao
Medido em dados simulados: IC com cobertura 0,83 a 0,93, falso positivo sob efeito nulo 12%. Contaminacao de um controlo sem redundancia de controlos destroi a estimativa (vies ate -100%). Placebo no espaco (2 ou mais controlos): alarmes falsos 0 a 9%, deteta cerca de 90% de um desvio de 2,7 desvios sem sazonalidade forte e 41% com ela; um choque aditivo igual em todos os controlos tambem dispara o alarme (abstencao). Com holdout aleatorizado de 6 regioes, efeito zero, 80 mundos por cenario: 'positivo' em 0% sem choque, 0% com choque multiplicativo de +10% e 7,5% com choque aditivo (nominal unilateral 5%; antes da regra de concordancia 17,5%); potencia cerca de 60 a 66% para um efeito de 25 por semana durante 30 semanas. Erro de Monte Carlo cerca de 3 pontos. Claude ciclo04 reportou ainda 27,5% de decisoes positivas e 15% negativas sob efeito zero, com poucas regioes, holdout agregado K=1 e choques regionais heterogeneos. A concordancia nao assegura calibracao; estas taxas sao especificas dessa simulacao, nao garantias gerais. A inferencia e sobre a serie agregada, nao ao nivel das unidades aleatorizadas: e evidencia exploratoria condicionada, nao um teste de aleatorizacao. Sem holdout, um choque so no alvo e 100% atribuido a campanha. Valido nao e prova. Sazonalidade omitida alarga o IC. Nao e prova causal. O metodo antigo de racio de controlos SEM holdout (roi legado) tinha vies de +10% a +27% e nao e recomendado; com holdout, o racio so serve de segunda especificacao.
Se os dados nao cumprirem o contrato ou o historico for curto, NAO responder com numeros: explicar o que falta. Todos os testes do pacote usam dados sinteticos; validar no historico real da equipa antes de decidir. Nada e publicado: os resultados ficam em `out/ml/` a espera de revisao humana.
