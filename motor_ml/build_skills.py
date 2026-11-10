"""Gera skills Claude autocontidas a partir do pacote bi_ml (v0.4, OBJ-009).

Uso: python build_skills.py [destino]   (default: dist_skills)
Cada skill = SKILL.md + scripts/run.py + scripts/bi_ml/ (copia do pacote). Validar com
quick_validate.py do skill-creator. Uma unica fonte de verdade: editar SPECS, nao os SKILL.md gerados.
"""
import os, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
COMMON_INPUT = ("Pasta com CSV conforme o contrato: sales.csv (date, order_id, customer_id, product_id, qty, revenue; "
                "opcional cost) e, quando o modulo o pede, stock.csv (date, product_id, stock_qty). "
                "Devolucoes (linhas negativas), vendas de balcao sem cliente, ids numericos e stock negativo sao "
                "tratados pela camada de preparacao e registados em qualidade_dados.json. CSV de ERP portugues: colocar "
                "csv_options.json na mesma pasta, ex. {'sep': ';', 'decimal': ',', 'encoding': 'latin-1', 'date_format': '%d/%m/%Y', 'revenue_basis': 'sem_imposto', 'currency': 'EUR'} em JSON valido (aspas duplas); "
                "datas com barras sem date_format sao recusadas (03/04 e ambiguo).")

SPECS = [
 dict(name="bi-ml-qualidade-dados", cmd="check",
  desc="Verifica e prepara extratos de ERP antes de qualquer analise de ML para BI: devolucoes, vendas sem cliente, duplicados, ids que nao casam entre vendas e stock, stock negativo. Usar sempre primeiro, ou quando o utilizador pedir para validar ou limpar dados de vendas e stock.",
  inputs=COMMON_INPUT,
  outputs="qualidade_dados.json (contagens e valores afetados por cada decisao de preparacao, lista de avisos) e relatorio_check.json (periodo, n.o de produtos, cobertura de stock por receita).",
  interp="Ler os avisos antes de usar qualquer outro modulo. Tres naturezas separadas: vendas brutas (qty>0), devolucoes (qty<0: devolucoes_unidades, devolucoes_valor) e ajustes de valor (descontos em linha e notas de credito/debito so de valor: ajustes_valor_liquido). receita_liquida = receita_bruta - devolucoes_valor + ajustes_valor_liquido e reconcilia exatamente com a soma do extrato (reconciliado_com_entrada=true); se falhar, o modulo para. Duplicados exatos nao sao removidos sem pedido: perguntar ao utilizador se sao legitimos. Linhas nao-produto (portes, embalagem) distorcem ABC/basket: o aviso 'possivel_nao_produto' aparece quando um id esta em >=60% das encomendas; listar esses ids em csv_options.json (\"exclude_products\") e a reconciliacao mantem-se exata (nao_produto_valor).",
  actions="Se cobertura_stock for baixa, pedir a lista de codigos do stock (formatos diferentes: zeros a esquerda, prefixos, maiusculas). Nunca corrigir ids por palpite.",
  limits="Nao infere impostos: declarar em csv_options.json revenue_basis (sem_imposto ou com_imposto) e currency (ex. EUR); sem isso os comandos com valores monetarios avisam que margens e ROI so valem com receita, custo e gasto na mesma base. Nunca dividir por uma taxa unica (taxas mistas e isencoes). Nao valida o resto da semantica do negocio (preco). Nao junta tabelas de fontes diferentes. Erro de dados termina com codigo 2 e mensagem: nao contornar, perguntar."),
 dict(name="bi-ml-ciclo-vida-cliente", cmd="lifecycle",
  desc="Classifica clientes por fase do ciclo de vida (novo, ativo, em risco, perdido, reativado) relativamente ao ritmo proprio de compra de cada cliente. Usar para base ativa, clientes em risco, reativacao ou segmentacao por comportamento de compra.",
  inputs=COMMON_INPUT + " customer_id obrigatorio para este modulo: vendas anonimas sao excluidas com aviso.",
  outputs="lifecycle.csv por cliente: stage, recency, freq_30/90/180, monetary_180, aov, tenure, mean_gap, gap_ratio. relatorio_lifecycle.json com a contagem por fase.",
  interp="A fase compara a recencia com o intervalo medio proprio (ativo ate 1,5x, em risco ate 3x, perdido acima). Num teste com verdade conhecida, mais de 85% dos clientes que abandonaram ficaram em perdido ou em risco.",
  actions="Em risco: contacto de retencao. Perdido: campanha de reativacao com custo controlado. Novo: onboarding. Reativado: monitorizar recaida.",
  limits="Clientes com 1 compra nao tem ritmo (usa tenure). Sazonalidade longa (compras anuais) classifica como perdido por erro: confirmar o ciclo do negocio."),
 dict(name="bi-ml-churn", cmd="churn",
  desc="Modelo de churn com validacao temporal honesta (treino, validacao que escolhe, teste que so reporta) e comparacao com o baseline de recencia. Usar para lista de clientes a reter, priorizacao de retencao ou perguntas sobre quem vai deixar de comprar.",
  inputs=COMMON_INPUT + " Precisa de 450 dias de historico ou mais (180 de arranque + purga de 2x90 + horizonte de 90); abaixo disso o modulo falha com mensagem.",
  outputs="churn_scores.csv por cliente: p_churn, decil (10 = maior risco), clv_12m_heuristica e risco_x_valor (p_churn x valor, para priorizar retencao; o valor e uma heuristica cujo ranking equivale a margem recente x 2). relatorio_churn.json: metricas de validacao e de teste por candidato (baseline_recencia, logistica, gbm), modelo escolhido, taxa de churn do teste.",
  interp="Se o modelo escolhido for baseline_recencia, o ML nao acrescenta nada: dizer isso. O erro-padrao do AUC ronda 0,01 com cerca de 1300 clientes: diferencas inferiores a isso entre modelos sao ruido. Churn aqui significa nao comprar nos proximos 90 dias.",
  actions="Atuar sobre os decis 9 e 10 ordenados por risco_x_valor. Medir o efeito da retencao com um grupo de controlo, nao com antes e depois.",
  limits="Horizonte de 90 dias errado para ciclos longos (B2B). Probabilidades calibradas so no sentido estatistico, nao garantem causalidade. Dados de teste sinteticos sao faceis (baseline AUC 0,88)."),
 dict(name="bi-ml-previsao-procura", cmd="forecast",
  desc="Previsao semanal de procura por produto com intervalos p10 a p90. Por omissao usa a media das ultimas 13 semanas; a troca de metodo por backtest so acontece a pedido (--selection-policy guarded ou adaptive). Usar para planeamento de compras, previsao de vendas por produto ou intervalos de procura.",
  inputs=COMMON_INPUT + " Cada produto precisa de 60 semanas ou mais desde a primeira venda; stock.csv e opcional mas melhora o tratamento das semanas com ruptura.",
  outputs="forecast.csv: forecast, p10, p90, method, selection_policy, selection_horizon, candidato_backtest, wape_holdout e wape_holdout_media_13s por produto e semana. forecast_omitidos.csv: produtos sem previsao e o motivo (nunca ha omissoes silenciosas).",
  interp="Usar o intervalo, nao so o ponto. Grok reportou cobertura p10-p90 a 8 semanas de 0,79 a 0,86 por horizonte (nominal 0,80). Claude ciclo04, noutro ensaio sintetico, reportou cobertura global 0,79 mas apenas 0,71 (aprox. 72%) no horizonte 7: a cobertura nominal nao e garantida por horizonte. Intervalos largos. Politicas: baseline (omissao) = media de 13 semanas, sem selecao. guarded = troca de metodo so se o candidato for pelo menos 15% melhor no backtest com horizonte igual ao pedido E ganhar em pelo menos 2/3 das dobras; medido a 8 semanas em dados sem sinal ficou igual a baseline (troca em 0 a 2% das series) e com sazonalidade e tendencia baixou o WAPE de 0,40 para 0,18 e de 0,37 para 0,22. adaptive = experimental, troca com 5% de ganho medio e piora cerca de 1% sem sinal. Se wape_holdout nao for melhor que wape_holdout_media_13s, usar a media e dizer porque.",
  actions="Planear compras com p90 para produtos de ruptura cara e com a previsao central para o resto. Rever produtos em forecast_omitidos.csv manualmente.",
  limits="Sem preco, promocoes ou feriados como regressores. Horizonte validado ate 8 semanas, so em dados sinteticos (2 sementes sem sinal e 2 com sinal). Semanas com ruptura sao imputadas e excluidas da avaliacao; a eficacia dessa imputacao nao foi medida contra procura latente verdadeira. guarded faz backtest de todos os candidatos; Claude ciclo04 reportou cerca de 10 minutos por semente no seu ensaio, custo dependente da maquina e dimensao. Nenhuma politica promete ganho sobre a media no historico real: comparar wape_holdout com wape_holdout_media_13s antes de usar guarded."),
 dict(name="bi-ml-perda-ruptura", cmd="stockout",
  desc="Estima unidades, receita e margem perdidas por falta de stock com contrafactual de nivel local e padrao semanal, sinalizando rupturas muito longas ou produtos possivelmente descontinuados. Usar para impacto de rupturas e priorizacao de reposicao.",
  inputs=COMMON_INPUT + " stock.csv obrigatorio (snapshot de fim de dia por produto).",
  outputs="rupturas_eventos.csv (por evento: dias, truncado, possivel_descontinuado, unid, receita e margem perdidas) e rupturas_resumo.csv por produto.",
  interp="E um limite superior para o dia em que a ruptura comeca (snapshot de fim de dia). A perda de um evento conta no maximo 60 dias; acima disso fica truncado, e se continua ate ao fim dos dados fica como possivel_descontinuado e nao deve entrar no total. Se os codigos de vendas e stock nao casarem, o modulo falha em vez de reportar zero rupturas.",
  actions="Ordenar por receita_perdida. Para possivel_descontinuado confirmar com compras se o produto saiu do catalogo.",
  limits="Sem substituicao entre produtos nem reposicao a meio do dia. Sobrestima cerca de 17% face a referencia sintetica. Buracos no stock acima de 7 dias ficam como desconhecidos, nao como ruptura."),
 dict(name="bi-ml-desvio-vendas", cmd="variance",
  desc="Explica desvios de vendas: decomposicao preco, volume e mix que fecha por linha, anomalias semanais por MAD e desvio face a orcamento ou previsao mensal. Usar para explicar porque a receita subiu ou desceu face a um periodo ou ao plano.",
  inputs=COMMON_INPUT + " Para planos: budget_plan.csv e/ou forecast_plan.csv (period, product_id, planned_qty, planned_revenue; previsao exige issued_at anterior ao mes).",
  outputs="pvm.csv (efeito_preco, efeito_volume, efeito_mix, desvio_total por produto), anomalias.csv, budget_variance.csv e forecast_variance.csv quando ha plano.",
  interp="Preco + volume + mix somam exatamente o desvio total em cada produto. A CLI compara janelas de igual duracao (--days, por omissao 90). Ao usar a funcao pvm com periodos de duracao diferente (mais de 10%) ha aviso; usar per_day=True para taxas diarias. Meses do plano sem qualquer venda no extrato sao erro de cobertura, nao venda zero.",
  actions="Atacar primeiro o maior efeito absoluto. Anomalia com z robusto acima de 3,5 pede verificacao de dados antes de explicacao de negocio.",
  limits="Descritivo: nao atribui causa. Meses abertos nao entram. Percentagem sobre plano zero e desconhecida."),
 dict(name="bi-ml-basket", cmd="basket",
  desc="Analise de cesto de compras com pares de produtos, suporte, confianca, lift e controlo de falsas descobertas (Benjamini-Hochberg). Usar para cross-sell, bundles e produtos comprados em conjunto.",
  inputs=COMMON_INPUT + " Uma encomenda e um order_id; funciona com vendas anonimas.",
  outputs="basket_pares.csv: n_ab, support, conf_a_b, conf_b_a, lift, leverage, p, q_bh, significativo, encomendas_incrementais (n_ab menos o esperado sob independencia), material, elegivel e motivo_exclusao. Pares com menos de 20 coocorrencias nao entram.",
  interp="Usar so elegivel=True. elegivel = significativo (Benjamini-Hochberg) E material. Com muitas encomendas quase tudo e significativo: pedir ao utilizador, ANTES de ver os pares, um limiar de negocio (--min-lift e/ou --min-incremental-orders, a partir da margem por encomenda e do custo da acao). Sem limiar, material fica vazio e elegivel=False, com aviso; os pares ficam disponiveis para exploracao, mas recommend nao os recomenda. Tabelas antigas sem elegivel devem ser recalculadas com limiar declarado. Em teste com verdade conhecida recuperou os 3 pares plantados. Lift alto com poucas coocorrencias engana: olhar tambem para leverage e n_ab.",
  actions="Sugerir o par com maior confianca no sentido relevante (conf_a_b para quem leva A). Testar a oferta com grupo de controlo.",
  limits="So pares, sem sequencia temporal nem margem. Associacao nao e uplift causal: testar a oferta com grupo de controlo. Validar o limiar num periodo posterior. Cuidado com encomendas gigantes (custo quadratico por encomenda)."),
 dict(name="bi-ml-roi-incremental", cmd="roi-series",
  desc="ROI incremental de uma campanha ou investimento a partir de uma serie semanal do resultado agregado e de controlos nao afetados, com intervalo por placebo no tempo e diagnosticos de validade. Usar quando perguntarem pelo retorno de campanhas ou promocoes, ou se vale renovar um investimento.",
  inputs="serie.csv semanal: date, outcome (receita do alvo MAIS dos produtos canibalizados) e UM de dois tipos de controlo. (a) control_1..control_K: receita de produtos que a campanha nao deve afetar (use 3 ou mais); sem desenho o resultado e so indicio estatistico. (b) holdout_1..holdout_M: unidades de holdout reservadas ANTES da campanha por atribuicao aleatoria e nao expostas, JUNTO com --desenho aleatorizado|holdout_geografico|holdout_clientes; e o unico caminho para uma decisao causal. Declarar --desenho sem colunas holdout_* e recusado, e colunas holdout_* sem --desenho tambem. Parametros: --intervention-date, --spend, --margin-rate. Exemplo: python scripts/run.py roi-series --data DIR --series serie.csv --intervention-date 2025-03-01 --spend 3000 --margin-rate 0.35 (DIR precisa de sales.csv).",
  outputs="relatorio_roi-series.json: incremental, ic (90%), roi, roi_ic, decisao (positivo, negativo, indicio_estatistico_positivo, indicio_estatistico_negativo, inconclusivo, nao_afirmar), causal, evidencia_para_revisao, autorizacao (sempre humana_obrigatoria), pode_decidir_renovacao (sempre false), concordancia_especificacoes, roi_ic_racio, valido, verificavel, loo_spread, espaco_flag, espaco_controlos, holdout, avisos.",
  interp="O pacote nunca autoriza renovar: pode_decidir_renovacao e sempre false. evidencia_para_revisao=true (exige --desenho, colunas holdout_* e concordancia entre o modelo com tendencia e o modelo de racio) significa evidencia estatistica condicionada ao desenho, a levar a um decisor humano que confirme atribuicao aleatoria documentada, holdout nao exposto, unidade de aleatorizacao e tamanho. Se as duas especificacoes discordarem, a decisao e inconclusivo. Sem desenho, a decisao e indicio_estatistico_*: um choque externo (concorrente, clima, preco) com efeito ZERO da campanha produz o mesmo resultado (medido: 3/3 cenarios), por isso dizer 'o resultado mudou face ao contrafactual', nunca 'a campanha causou'. Nunca citar um ROI se decisao for nao_afirmar ou inconclusivo. O limite inferior do IC pode apoiar uma revisao humana, mas nao e criterio suficiente para renovar; confirmar inferencia ao nivel das unidades aleatorizadas. valido=False quando retirar um controlo muda a conclusao ou um controlo se desvia dos outros no periodo da campanha (placebo no espaco). verificavel=False (sem holdout: menos de 3 controlos; sempre: pouco historico) significa que a contaminacao nao se consegue testar.",
  actions="Se indicio_estatistico_*, propor holdout ou teste A/B na proxima vaga antes de decidir. Se inconclusivo, propor teste A/B em vez de decidir. Se valido mas verificavel=False, dizer a limitacao ao decisor.",
  limits="Medido em dados simulados: IC com cobertura 0,83 a 0,93, falso positivo sob efeito nulo 12%. Contaminacao de um controlo sem redundancia de controlos destroi a estimativa (vies ate -100%). Placebo no espaco (2 ou mais controlos): alarmes falsos 0 a 9%, deteta cerca de 90% de um desvio de 2,7 desvios sem sazonalidade forte e 41% com ela; um choque aditivo igual em todos os controlos tambem dispara o alarme (abstencao). Com holdout aleatorizado de 6 regioes, efeito zero, 80 mundos por cenario: 'positivo' em 0% sem choque, 0% com choque multiplicativo de +10% e 7,5% com choque aditivo (nominal unilateral 5%; antes da regra de concordancia 17,5%); potencia cerca de 60 a 66% para um efeito de 25 por semana durante 30 semanas. Erro de Monte Carlo cerca de 3 pontos. Claude ciclo04 reportou ainda 27,5% de decisoes positivas e 15% negativas sob efeito zero, com poucas regioes, holdout agregado K=1 e choques regionais heterogeneos. A concordancia nao assegura calibracao; estas taxas sao especificas dessa simulacao, nao garantias gerais. A inferencia e sobre a serie agregada, nao ao nivel das unidades aleatorizadas: e evidencia exploratoria condicionada, nao um teste de aleatorizacao. Sem holdout, um choque so no alvo e 100% atribuido a campanha. Valido nao e prova. Sazonalidade omitida alarga o IC. Nao e prova causal. O metodo antigo de racio de controlos SEM holdout (roi legado) tinha vies de +10% a +27% e nao e recomendado; com holdout, o racio so serve de segunda especificacao."),
 dict(name="bi-ml-abc-xyz", cmd="abc-xyz --start AAAA-MM-01 --end AAAA-MM-01",
  desc="Classificacao ABC por receita bruta e XYZ por variabilidade mensal da quantidade, com leitura sazonal quando ha 24 meses ou mais. Usar para segmentar o portefolio, priorizar atencao de compras e planeamento, ou perguntas sobre produtos importantes e previsiveis.",
  inputs=COMMON_INPUT + " Janela [start,end) em inicios de mes, pelo menos 3 meses completos e cobertura completa das vendas nessa janela.",
  outputs="abc_xyz.csv por produto: revenue, share, abc, cv, xyz, history_incomplete, class, cv_dessazonalizado, xyz_sazonal, nota_sazonal.",
  interp="A = ate 80% da receita, B ate 95%, C o resto (o produto que cruza o limite fica na classe anterior). X: CV mensal ate 0,5; Y ate 1; Z acima. U = produto sem vendas antes da janela (historico insuficiente). Com 24 meses ou mais, xyz_sazonal compara cada mes com o mesmo mes dos OUTROS anos: um produto sazonal repetido e Z no bruto mas X no sazonal (medido: 200/200), e aleatorio continua Z (198/200, 0 falsos X).",
  actions="AX/BX: reposicao regular por previsao. AZ: atencao individual e stock de seguranca. Se xyz_sazonal for melhor que xyz, planear com o perfil sazonal, nao tratar como imprevisivel.",
  limits="Nao e recomendacao de stock (falta lead time e nivel de servico). Artigos sem vendas na janela nao aparecem sem catalogo. Limiares sao escolhas de negocio configuraveis na funcao, nao na CLI."),
 dict(name="bi-ml-coortes", cmd="cohorts",
  desc="Retencao por coorte de primeira compra observada: percentagem de clientes que voltam a comprar em cada mes de idade e receita por coorte. Usar para curvas de retencao, comparar coortes ou avaliar mudancas de aquisicao.",
  inputs=COMMON_INPUT + " Exige cobertura completa das transacoes desde a primeira compra; vendas anonimas sao excluidas com aviso.",
  outputs="cohort_retention.csv: cohort, month_age, customers, active, retention, revenue (so meses fechados).",
  interp="Retencao = proporcao com compra naquele mes, nao sobrevivencia permanente. A primeira compra e a observada no extrato: historico truncado cria falsas coortes novas.",
  actions="Comparar coortes na mesma idade. Antes de concluir sobre aquisicao, verificar mix de canais e sazonalidade.",
  limits="Descritivo; sem inferencia causal. Meses incompletos excluidos."),
]

TEMPLATE = """---
name: {name}
description: "{desc}"
---
# {name}

## Quando usar
{desc}

## Entradas
{inputs}

## Como executar
Primeiro `python scripts/run.py check --data PASTA --out SAIDA` e ler `qualidade_dados.json`. Depois:
`python scripts/run.py {cmd} --data PASTA --out SAIDA`
(requer Python 3.10+ com pandas, numpy, scikit-learn e scipy). Codigo de saida 2 = erro de dados com mensagem: reportar ao utilizador, nao contornar.

## Saidas
{outputs}

## Interpretacao
{interp}

## Acoes
{actions}

## Limites e abstencao
{limits}
Se os dados nao cumprirem o contrato ou o historico for curto, NAO responder com numeros: explicar o que falta. Todos os testes do pacote usam dados sinteticos; validar no historico real do utilizador antes de decidir.
"""

RUN_PY = '''"""Lancador da skill: python scripts/run.py <comando> --data PASTA --out SAIDA"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bi_ml import cli
sys.exit(cli.main())
'''


def build(dest):
    if os.path.exists(dest):
        shutil.rmtree(dest)
    for s in SPECS:
        d = os.path.join(dest, s["name"]); os.makedirs(os.path.join(d, "scripts"))
        desc = s["desc"].replace('"', "'")
        assert "<" not in desc and ">" not in desc and len(desc) <= 1024, s["name"]
        body = TEMPLATE.format(name=s["name"], desc=desc, cmd=s["cmd"], inputs=s["inputs"], outputs=s["outputs"],
                               interp=s["interp"], actions=s["actions"], limits=s["limits"])
        open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8").write(body)
        open(os.path.join(d, "scripts", "run.py"), "w", encoding="utf-8").write(RUN_PY)
        shutil.copytree(os.path.join(HERE, "bi_ml"), os.path.join(d, "scripts", "bi_ml"),
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return [s["name"] for s in SPECS]


if __name__ == "__main__":
    print(build(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "dist_skills")))
