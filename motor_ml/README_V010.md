# BI ML v0.10 — ChatGPT, ciclo04

Pacote executável de análises BI/ML com contratos CSV, testes sintéticos e gerador de dez skills. Este é o guia da versão atual; os README anteriores ficam preservados como histórico. Aprovação técnica do ChatGPT para o âmbito descrito abaixo; ainda sem consenso dos três modelos e sem validação em dados reais.

## Instalar e verificar

Usar Python 3.12 num ambiente isolado. O ficheiro requirements.txt fixa o ambiente principal validado. Também foi testado pandas 3.0.0 com as restantes dependências iguais.

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-test.txt
sha256sum -c MANIFEST_v0.10.sha256
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python -m pytest tests -q
python -m bi_ml.cli --help
```

Windows: ativar `.venv\Scripts\activate` e configurar as duas variáveis de ambiente pelo shell usado. Não é necessária conexão a serviços externos durante a execução dos módulos. A instalação de dependências exige acesso aos pacotes ou wheels locais. A instalação limpa de todas as dependências a partir deste ficheiro não foi repetida neste ciclo: as versões fixadas correspondem ao ambiente em que os testes passaram.

## Entradas e execução

A pasta `dados` deve conter `sales.csv`: date, order_id, customer_id (pode ser nulo para vendas anónimas), product_id, qty, revenue; cost é opcional. Preparação de devoluções, ajustes e exclusões é feita por `prepare.py`; `contract.py` valida os dados preparados. Nunca corrigir identificadores ou imputar semântica fiscal por palpite.

`stock.csv` (date, product_id, stock_qty) é necessário para rupturas. `budget_plan.csv` e `forecast_plan.csv` são opcionais para desvio: period, product_id, planned_qty, planned_revenue; previsão exige issued_at anterior ao mês previsto. Uma linha por produto/mês. Ver contratos e documentação gerada para os restantes requisitos, histórico mínimo e cobertura.

Exemplo de `csv_options.json` para um extrato português cuja receita foi confirmada sem imposto:

```json
{"sep":";","decimal":",","encoding":"utf-8","date_format":"%d/%m/%Y","revenue_basis":"sem_imposto","currency":"EUR"}
```

Configurar segundo o extrato; estes valores não são inferidos. Para um CSV ISO com vírgula separadora e ponto decimal, omitir as opções de formato. Receita, custo e gasto têm de estar na mesma base. Não se desconta IVA com uma taxa presumida.

```sh
python -m bi_ml.cli check --data dados --out saida/check
python -m bi_ml.cli lifecycle --data dados --out saida/lifecycle
python -m bi_ml.cli churn --data dados --out saida/churn
python -m bi_ml.cli forecast --data dados --out saida/forecast --horizon 8
python -m bi_ml.cli stockout --data dados --out saida/stockout
python -m bi_ml.cli variance --data dados --out saida/variance
python -m bi_ml.cli cohorts --data dados --out saida/cohorts
python -m bi_ml.cli abc-xyz --data dados --out saida/abc --start 2024-01-01 --end 2025-01-01
python -m bi_ml.cli basket --data dados --out saida/basket
```

As datas são exemplos: fornecer uma janela completa existente. Basket sem limiar produz análise exploratória, `material` vazio e `elegivel=False`. Para recomendar, definir antes de inspecionar os resultados `--min-lift` e/ou `--min-incremental-orders` com fundamento no negócio. Não foi introduzido um limiar universal. Pares antigos sem `elegivel` precisam de ser recalculados antes de chamar `recommend`.

ROI exige CSV regularmente espaçado com date, outcome e control_*; com desenho declarado, usar holdout_* reservado antes da intervenção e não exposto. Exemplo de forma de chamada (data, gasto e margem são ilustrativos, a substituir por valores declarados):

```sh
python -m bi_ml.cli roi-series --data dados --out saida/roi --series dados/series.csv --intervention-date 2025-01-06 --spend 100 --margin-rate 0.4 --desenho aleatorizado
```

O ROI é exploratório e condicionado ao desenho. Nunca autoriza renovação: `pode_decidir_renovacao=False`, `autorizacao=humana_obrigatoria`. Os intervalos não são testes de aleatorização ao nível das unidades. Ler os avisos, mesmo quando `decisao=positivo` e `verificavel=True`.

Cada comando grava CSV e relatórios JSON. Ler `qualidade_dados.json` antes de usar resultados. `all` executa vários módulos, mas não inclui ABC/XYZ nem roi-series; pode guardar erros por módulo mesmo retornando código zero. Inspecionar os campos `erro` no relatório. Não tratar sucesso do processo como sucesso de todos os módulos. `python run_all.py --out saida_demo` gera uma demonstração sintética; `--data dados` usa o extrato fornecido.

## Skills geradas

```sh
python build_skills.py dist_skills_v010
```

Usar um destino dedicado: o gerador substitui a pasta de destino existente. Cada skill contém SKILL.md, scripts/run.py e uma cópia do pacote. Duas skills geradas foram executadas fora da árvore pelos testes (forecast e basket). Foram geradas e verificadas localmente; não foram instaladas em nenhum catálogo pessoal nem executadas no Claude, Copilot ou Grok.

## Alterações desde v0.9

- Basket: significância sem limiar comercial deixa de implicar elegibilidade; preservam-se os pares e explica-se a exclusão. `recommend` não aceita tabelas antigas sem elegibilidade e suporta resultados vazios.
- ROI: aviso explícito sobre poucas unidades, holdout agregado e choques heterogéneos; aviso presente também quando o resultado se abstém. O estimador e a concordância OLS/rácio não foram alterados.
- Avisos fiscais/moeda passam a abranger ABC/XYZ e coortes, que contêm receita.
- Gerador alinhado com estas alterações e com as limitações de previsão reportadas pelo Claude. `__version__` corrigida de 0.8.0 (no bundle v0.9) para 0.10.0.
- Dez regressões novas; uma asserção herdada atualizada porque exigia explicitamente o comportamento antigo do basket. Mantêm-se os restantes testes e os README históricos.

## Validação e limites

Neste ciclo: base v0.9 com 87 testes aprovados; v0.10 com 97 aprovados em pandas 2.2.3 e 97 em pandas 3.0.0, zero skips/falhas. Inclui testes slow, verdade sintética, CLI e execução das skills geradas. Testes não demonstram calibração universal ou eficácia em produção.

Evidência externa identificada: Claude ciclo04 reportou 27,5% de decisões ROI positivas e 15% negativas sob efeito zero, com seis regiões, K=1 agregado e choque regional heterogéneo; não repeti esses 80 mundos neste ciclo. A documentação transmite esse resultado como relato do Claude. A taxa de 0–7,5% noutros cenários não é garantia geral.

Forecast: média 13 semanas por defeito; guarded/adaptive opcionais. Claude reportou cobertura global de 79%, mas aproximadamente 71–72% no horizonte 7, e cerca de dez minutos por semente no seu benchmark guarded. Estes valores não foram repetidos neste ciclo. Os testes herdados de sinal/guarded passaram. Horizonte avaliado até oito semanas e apenas sintético. A eficácia da imputação de rupturas contra procura latente verdadeira continua não medida. Stockout é aproximação; CLV é heurística; associações basket não são uplift causal.

Não há instalação externa, dados reais, validação empresarial, análise exaustiva de todas as distribuições nem prova de consenso. Aprovar software neste âmbito não autoriza decisões financeiras automáticas. A integração exige dados conformes e parâmetros de negócio explícitos onde o contrato os requer.
