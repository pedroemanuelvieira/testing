# Estender a plataforma

Toda a base de conhecimento vive em YAML (`backend/mlstudio/knowledge/data/`). Depois de qualquer alteração corra
`make test` — o teste `test_knowledge.py` verifica a integridade de todas as referências cruzadas.

> Dica YAML: valores com `: ` ou que comecem por `%`, `>` ou `[` devem ir entre aspas. Em listas em linha `[a, b]`
> não use vírgulas decimais (`0,97`) — use a forma em bloco (`- "0,97 ..."`).

## Novo caso de uso

Acrescente uma entrada a `use_cases.yaml`:

```yaml
- id: previsao_devolucoes
  name: Previsão de devoluções
  area: comercial
  areas: [comercial, logistica]
  problem_type: binary_classification
  summary: ...
  business_question: Que encomendas vão ser devolvidas?
  decision: ...
  unit: Encomenda
  target: {column: devolvida, definition: "1 se devolvida em 30 dias", positive_class: 1}
  recommended_models:
    - {model: lightgbm, why: ...}
    - {model: logistic_regression, why: ...}
  metrics: {primary: pr_auc, secondary: [recall], business: ...}
  profile: {interpretability: média, imbalance: forte, goal: equilibrado}
  business_costs: {cost_fp: 2, cost_fn: 25, benefit_tp: 18}
  demo: {}               # ou aponte para uma tabela demo / do vosso Power BI
  powerbi_output: {table: Previsoes_Devolucoes, columns: [...], visuals: [...], measures: [{name: ..., dax: ...}]}
  ai_act_risk: mínimo
  terms: [pr_auc, desequilibrio_classes]
```

Os agentes passam automaticamente a usar o caso (modelos, métricas, custos, saída para o Power BI).

## Novo termo do glossário

Acrescente a um dos ficheiros `glossary_0*.yaml` (`id`, `term`, `category`, `level`, `short`, `definition`, `example`,
`formula`, `pitfalls`, `related`, `steps`). Use o `id` em `terms:` de casos, passos ou guias para o ligar.

## Novo modelo

1. Acrescente a ficha a `models.yaml` com os hiperparâmetros (tipo, intervalo, efeito ↑/↓, espaço de pesquisa).
2. Em `ml/factory.py → make_estimator` converta os parâmetros para a biblioteca.
3. (Opcional) Regras específicas em `advisor/__init__.py → _rules` e validações em `validate`.

## Novo agente

```python
from mlstudio.core.agent import Agent, AgentCard
from mlstudio.core import agent as B

class UpliftAgent(Agent):
    card = AgentCard(id="uplift", name="Agente de Uplift", component="Modelação causal", role="...",
                     description="...", step="treino", problem_types=["binary_classification"])

    def run(self, ctx, result, **params):
        df = ctx.data()
        ...
        result.blocks.append(B.kpis([B.kpi("Uplift médio", 0.021, "pct", term="uplift")]))
        result.summary = "..."
```

Registe-o em `agents/__init__.py` (`_ORDER`). A UI desenha os blocos sem alterações e a API expõe-no em
`POST /api/projects/{id}/agents/uplift/run`.
