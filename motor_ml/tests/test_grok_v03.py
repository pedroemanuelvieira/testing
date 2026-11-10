"""Testes Grok ciclo 01 (v0.3): verdade injetada, varias sementes, perda de cobertura."""
import numpy as np, pandas as pd, pytest
from bi_ml import synth, customers, demand, contract
from bi_ml.planning import plan_variance, controlled_incremental_ci


@pytest.fixture(scope="module")
def world():
    return synth.make(seed=11, n_cust=900, n_prod=30, days=730)


def test_churn_selects_on_validation_not_test(world):
    _, m, _ = customers.churn_model(world[0])
    order = ["baseline_recencia", "logistica", "gbm"]
    best = order[0]
    for n in order[1:]:
        if m["validacao"][n]["auc"] >= m["validacao"][best]["auc"] + 0.01:
            best = n
    assert m["escolhido"] == best
    assert m["cutoffs"]["validacao"] < m["cutoffs"]["teste"]
    assert m["teste"][m["escolhido"]]["auc"] > 0.70


def _roi_world(seed, contam=0.0, n=160, k=130):
    rng = np.random.default_rng(seed); t = np.arange(n); ctrl = rng.uniform(10, 30, n)
    target = 100 + 2 * t + 3 * ctrl + rng.normal(0, 5, n); sub = 80 + t + ctrl + rng.normal(0, 5, n)
    target[k:] += 20; sub[k:] -= 8
    c = ctrl.copy(); c[k:] += contam
    return target + sub, c, k, 12 * (n - k)


def test_roi_ci_covers_truth_multiseed():
    cov = []
    for s in range(60):
        y, c, k, truth = _roi_world(s)
        r = controlled_incremental_ci(y, c, k)
        cov.append(r["ic"][0] <= truth <= r["ic"][1])
    assert np.mean(cov) >= 0.80  # nominal 0.90; medido 0.873 em 150 sementes


def test_roi_flags_strong_control_contamination():
    flags = [not controlled_incremental_ci(*_roi_world(s, contam=8)[:3])["valido"] for s in range(40)]
    assert np.mean(flags) >= 0.9


def test_plan_variance_rejects_missing_sales_month():
    sales = pd.DataFrame(dict(date=pd.to_datetime(['2025-01-05', '2025-03-05']), order_id=['1', '2'],
                              customer_id=['A', 'A'], product_id=['P', 'P'], qty=[1, 1], revenue=[10, 10]))
    plan = pd.DataFrame(dict(period=['2025-01-01', '2025-02-01', '2025-03-01'], product_id=['P'] * 3,
                             planned_qty=[1] * 3, planned_revenue=[10] * 3))
    with pytest.raises(contract.ContractError):
        plan_variance(sales, plan, '2025-04-01')
    r = plan_variance(sales, plan, '2025-04-01', allow_empty_months=True)
    assert r.loc[r.period == '2025-02-01', 'status'].item() == 'no_sales'


def test_forecast_holdout_ignores_censored_weeks_and_baseline_champion(world):
    sales, stock, _, _ = world
    fc = demand.forecast_all(sales, stock, h=4)
    g = fc.groupby("product_id").first()
    # o metodo so difere da media se ganhou >= 5% no backtest
    alt = g[g.method != "media_13s"]
    assert (alt.wape_backtest <= 0.95 * alt.wape_media_13s + 1e-12).all()
    assert "semanas_holdout_censuradas" in fc.columns


def test_forecast_interval_coverage_on_future(world):
    sales, stock, _, _ = world
    d, _ = demand.weekly_demand(sales, stock)
    cut = d.index[-4]
    f = demand.forecast_all(sales[sales.date < cut], stock[stock.date < cut], h=4)
    act = d.loc[d.index >= cut].reset_index(drop=True)
    hits = [r.p10 <= act[r.product_id].iloc[r.week_ahead - 1] <= r.p90 for r in f.itertuples()]
    assert np.mean(hits) >= 0.70  # nominal 0.80; v0.2 dava 0.558, v0.3 0.792 (seed 11)
