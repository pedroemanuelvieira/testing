"""Conselheiro de hiperparâmetros: recomendações, validação e indicador de risco."""
import pytest

from mlstudio import advisor
from mlstudio.advisor import DataProfile
from mlstudio.knowledge import KnowledgeBase
from mlstudio.ml.factory import SUPERVISED, make_estimator, model_available

KB = KnowledgeBase()


@pytest.mark.parametrize("model", [m.id for m in KB.models])
def test_recommend_every_model_and_validate_its_own_recommendation(model):
    spec = KB.model(model)
    task = spec.tasks[0]
    prof = DataProfile(n_rows=8000, n_features=20, task=task, positive_rate=0.1 if task == "binary_classification" else None,
                       season_length=7, freq="D", series_length=700, n_series=3)
    rec = advisor.recommend(model, prof)
    assert set(rec["params"]) == {h.name for h in spec.hyperparameters}
    assert all(d["reason"] for d in rec["details"])
    val = advisor.validate(model, rec["params"], prof)
    assert val["valid"], val["issues"]
    if task in SUPERVISED and model_available(model):
        make_estimator(model, task, rec["params"])  # parâmetros convertíveis para a biblioteca


def test_recommendations_adapt_to_data_and_use_case():
    small = DataProfile(n_rows=2000, n_features=15, task="binary_classification", positive_rate=0.2, imbalance="moderado")
    big = DataProfile(n_rows=500_000, n_features=15, task="binary_classification", positive_rate=0.2, imbalance="moderado")
    s = advisor.recommend("lightgbm", small)["params"]
    b = advisor.recommend("lightgbm", big)["params"]
    assert s["num_leaves"] < b["num_leaves"]
    fraud = DataProfile(n_rows=20_000, n_features=13, task="binary_classification", positive_rate=0.012, imbalance="extremo")
    x = advisor.recommend("xgboost", fraud, "fraude_transacoes")["params"]
    assert 5 < x["scale_pos_weight"] < 82  # raiz do rácio para métricas de ranking
    credit = advisor.recommend("logistic_regression", DataProfile(n_rows=8000, task="binary_classification",
                                                                  positive_rate=0.08, imbalance="forte"), "risco_credito")
    assert credit["goal"] == "interpretabilidade"


def test_validation_flags_risky_configurations():
    prof = DataProfile(n_rows=5000, n_features=20, task="binary_classification", positive_rate=0.2)
    val = advisor.validate("lightgbm", {"learning_rate": 0.6, "num_leaves": 400, "max_depth": 5, "n_estimators": 2000}, prof)
    msgs = " ".join(i["message"] for i in val["issues"])
    assert "Taxa de aprendizagem" in msgs and "2^max_depth" in msgs
    assert val["assessment"]["overfit_level"] == "alto"
    bad = advisor.validate("random_forest", {"max_features": "tudo"}, prof)
    assert not bad["valid"]
    out = advisor.validate("logistic_regression", {"C": 1e6}, prof)
    assert any(i["level"] == "error" for i in out["issues"])


def test_assessment_increases_with_complexity():
    prof = DataProfile(n_rows=10_000, task="binary_classification")
    spec = KB.model("lightgbm")
    low = advisor.assess(spec, {"num_leaves": 8, "learning_rate": 0.03, "n_estimators": 200, "min_child_samples": 100}, prof)
    high = advisor.assess(spec, {"num_leaves": 255, "learning_rate": 0.2, "n_estimators": 2000, "min_child_samples": 2}, prof)
    assert high["overfit_risk"] > low["overfit_risk"] and low["underfit_risk"] > high["underfit_risk"]


def test_search_space_is_bounded_for_small_data():
    space = advisor.search_space("lightgbm", DataProfile(n_rows=2000, task="binary_classification"))
    assert space["num_leaves"]["high"] <= 63
