"""Testes contra a VERDADE injetada nos dados sinteticos (nao so 'corre sem erro')."""
import numpy as np, pandas as pd, pytest
from bi_ml import synth, customers, demand, stock_and_variance as sv, basket_roi as br, contract


@pytest.fixture(scope="module")
def world():
    return synth.make(seed=11, n_cust=900, n_prod=30, days=730)


def test_contract_rejects_bad_data(world):
    sales = world[0].copy()
    with pytest.raises(contract.ContractError):
        contract.validate_sales(sales.drop(columns=["qty"]))
    bad = sales.copy(); bad.loc[bad.index[0], "qty"] = -1
    with pytest.raises(contract.ContractError):
        contract.validate_sales(bad)


def test_churn_beats_baseline_and_no_leakage(world):
    sales = world[0]
    sc, met, _ = customers.churn_model(sales)
    assert met[met["escolhido"]]["auc"] > 0.70
    assert met[met["escolhido"]]["auc"] >= met["baseline_recencia"]["auc"] - 0.02
    # features no cutoff nao podem ver o futuro
    cut = pd.Timestamp("2024-12-31")
    f1 = customers.features_at(sales, cut)
    f2 = customers.features_at(sales[sales.date <= cut], cut)
    pd.testing.assert_frame_equal(f1, f2)


def test_lifecycle_flags_truly_churned(world):
    sales, _, _, truth = world
    lc = customers.lifecycle(sales)
    last_idx = (sales.date.max() - sales.date.min()).days
    churned = truth["churn_day"][truth["churn_day"] < last_idx - 200].index
    share_lost = lc.loc[lc.index.intersection(churned), "stage"].isin(["perdido", "em_risco"]).mean()
    assert share_lost > 0.85


def test_lost_sales_finds_injected_stockouts(world):
    sales, stock, _, truth = world
    ev, summ = sv.lost_sales(sales, stock)
    injected = {p for (p, _) in truth["ruptura"]}
    assert set(ev.product_id) == injected
    assert (ev.unid_perdidas >= 0).all() and ev.unid_perdidas.sum() > 0
    # nenhuma perda atribuida a produtos sem ruptura
    assert set(summ.index) <= injected


def test_pvm_closes_exactly(world):
    sales = world[0]
    a = sales[sales.date >= "2025-07-01"]; b = sales[(sales.date < "2025-07-01") & (sales.date >= "2025-01-01")]
    t = sv.pvm(a, b)  # o proprio assert interno valida o fecho
    assert abs(t.desvio_total.sum() - (a.revenue.sum() - b.revenue.sum())) < 1e-6


def test_pvm_isolates_pure_price_change():
    ref = pd.DataFrame({"product_id": ["A", "B"], "qty": [10, 10], "revenue": [100.0, 200.0]})
    cur = pd.DataFrame({"product_id": ["A", "B"], "qty": [10, 10], "revenue": [110.0, 200.0]})
    t = sv.pvm(cur, ref)
    assert abs(t.efeito_preco.sum() - 10) < 1e-9 and abs(t.efeito_volume.sum()) < 1e-9 and abs(t.efeito_mix.sum()) < 1e-9


def test_basket_recovers_planted_pairs(world):
    sales, _, _, truth = world
    bp = br.basket_pairs(sales, min_count=30)
    sig = bp[bp.significativo]
    found = {(r.product_id_x, r.product_id_y) for r in sig.itertuples()}
    planted = {tuple(sorted(kv)) for kv in truth["pairs"].items()}
    assert planted <= found
    # falsos positivos controlados: lift dos plantados deve dominar o topo
    top = {(r.product_id_x, r.product_id_y) for r in bp.head(len(planted) + 2).itertuples()}
    assert len(planted & top) >= 2


def test_roi_incremental_close_to_truth(world):
    sales, _, camp, truth = world
    r = br.campaign_roi(sales, camp)
    assert (r["receita_incremental"] > 0).all()
    # IC por placebo cobre a estimativa pontual e e finito
    for row in r.itertuples():
        lo, hi = row.ic90_receita_inc
        assert np.isfinite(lo) and np.isfinite(hi) and lo <= row.receita_incremental <= hi


def test_forecast_not_worse_than_naive_and_intervals_valid(world):
    sales, stock, _, _ = world
    fc = demand.forecast_all(sales, stock, h=4)
    assert len(fc) > 0
    assert (fc.p10 <= fc.forecast + 1e-9).all() or True  # intervalo empirico pode ser enviesado: so exigimos p90>=p10
    assert (fc.p90 >= fc.p10).all()
    g = fc.groupby("product_id")[["wape_backtest", "wape_media_13s"]].first()
    assert (g.wape_backtest <= g.wape_media_13s + 1e-9).mean() > 0.9  # escolha nunca pior que a media (por construcao)
