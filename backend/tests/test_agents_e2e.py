"""Percurso completo dos agentes por tipo de problema (dados de demonstração)."""
import pandas as pd
import pytest

CASES = {
    "churn_clientes": ("binary_classification", "roc_auc", 0.75),
    "clv": ("regression", None, None),
    "drivers_nps": ("multiclass_classification", "f1_macro", 0.5),
    "previsao_vendas": ("forecasting", None, None),
    "segmentacao_clientes": ("clustering", None, None),
    "anomalias_despesas": ("anomaly_detection", None, None),
    "cabaz_compras": ("association_rules", None, None),
}


@pytest.mark.parametrize("uc", list(CASES))
def test_autopilot_runs_end_to_end(orch, uc):
    pt, metric, minimum = CASES[uc]
    p = orch.create_project("", use_case_id=uc)
    res = orch.autopilot(p.id, include_deployment=True)
    statuses = {s["agent_id"]: s["status"] for s in res["steps"]}
    assert "error" not in statuses.values(), res["steps"]
    assert statuses.get("deployment") in ("ok", "warning")
    proj = orch.store.get(p.id)
    assert proj.problem_type == pt and proj.champion_version_id and proj.production_version_id
    meta = orch.registry.get(proj.champion_version_id)
    if metric:
        assert meta["metrics_test"][metric] >= minimum
        assert meta["metrics_test"][metric] > meta["baseline_metrics"][metric]
    for aid in proj.latest_runs:  # todos os resultados são serializáveis e têm resumo
        run = orch.store.latest_run(proj, aid)
        assert run["summary"]


def test_quality_agent_flags_leakage(orch):
    p = orch.create_project("", use_case_id="atraso_pagamentos")
    orch.run_agent(p.id, "connector")
    orch.store.update(p.id, excluded_columns=[])  # remove a exclusão do caso de uso
    res = orch.run_agent(p.id, "quality")
    assert "dias_atraso" in res["outputs"]["excluded"]
    assert any(i["level"] == "critical" for i in res["insights"])


def test_training_with_tuning_and_scoring_and_monitoring(orch):
    p = orch.create_project("", use_case_id="lead_scoring")
    for aid in ("connector", "quality", "features"):
        orch.run_agent(p.id, aid)
    orch.store.update(p.id, selected_models=["lightgbm", "logistic_regression"])
    res = orch.run_agent(p.id, "training", {"tune": True, "n_iter": 3})
    assert res["outputs"]["champion_version_id"]
    assert any(r["tentativas"] == 3 for r in res["outputs"]["leaderboard"])
    ev = orch.run_agent(p.id, "evaluation", {"capacity": 500})
    assert 0 < ev["outputs"]["threshold"] < 1
    dep = orch.run_agent(p.id, "deployment", {"publish": "export"})
    assert dep["outputs"]["rows"] == 5000 and dep["outputs"]["files"]
    mon_ok = orch.run_agent(p.id, "monitoring")
    mon_drift = orch.run_agent(p.id, "monitoring", {"simulate_drift": True})
    assert mon_drift["outputs"]["max_psi"] > mon_ok["outputs"]["max_psi"]
    assert mon_drift["outputs"]["status"] in ("atenção", "crítico")


def test_scoring_is_robust_to_missing_and_wrong_types(orch):
    from mlstudio.agents.operations import score_frame

    p = next(x for x in orch.store.list() if x.use_case_id == "churn_clientes" and x.champion_version_id)
    meta = orch.registry.get(p.champion_version_id)
    ctx = orch.context(p.id)
    df = pd.DataFrame([{f: None for f in meta["features"]} | {"n_reclamacoes_6m": "3", "plano": "Básico"}])
    out = score_frame(ctx, meta, df)
    assert 0 <= out.loc[0, "probabilidade"] <= 1 and out.loc[0, "principais_motivos"]


def test_framing_suggests_use_case_from_question(orch):
    p = orch.create_project("Pergunta livre", problem_type="binary_classification")
    res = orch.run_agent(p.id, "framing", {"question": "quero saber que colaboradores vão sair da empresa"})
    assert res["outputs"]["suggestions"][0]["id"] == "attrition"
    assert orch.store.get(p.id).use_case_id == "attrition"
