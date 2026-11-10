"""Testes Claude ciclo 03 (v0.7): contrato causal do ROI com holdout real, placebo no espaco, falhas de v0.6."""
import json
import numpy as np, pandas as pd, pytest
from bi_ml import planning, cli
from bi_ml.contract import ContractError


# ---------------- mundos ----------------
def _hw(seed, effect=0.0, shock="none", R=6, n=160, k=130, agg=False):
    """Holdout aleatorizado: R regioes com dinamica comum nao linear; metade tratada, metade holdout."""
    rng = np.random.default_rng(seed); t = np.arange(n)
    G = 100 + 0.4 * t + 12 * np.sin(2 * np.pi * t / 52 + rng.uniform(0, 6.28)) + rng.normal(0, 2, n).cumsum() * 0.3
    w = rng.uniform(0.8, 1.2, R); S = np.column_stack([w[r] * G + rng.normal(0, 4, n) for r in range(R)])
    if shock == "mult":
        S[k:] *= 1.10
    perm = rng.permutation(R); tr, ho = perm[:R // 2], perm[R // 2:]
    y = S[:, tr].sum(axis=1); y[k:] += effect
    C = S[:, ho]
    return y, (C.sum(axis=1, keepdims=True) if agg else C), k


def _target_only_shock(seed, shock=20.0, n=160, k=130):
    """Mundo do Grok/ChatGPT: choque externo SO no alvo, efeito da campanha ZERO, 3 controlos iid."""
    rng = np.random.default_rng(seed)
    c = rng.normal(100, 5, (n, 3)); y = c.sum(1) * 0.5 + rng.normal(0, 3, n); y[k:] += shock
    return y, c, k


def _write_series(tmp_path, y, C, k, prefix):
    dates = pd.date_range("2023-01-02", periods=len(y), freq="W-MON")
    s = pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "outcome": y, **{f"{prefix}_{i+1}": C[:, i] for i in range(C.shape[1])}})
    f = tmp_path / "serie.csv"; s.to_csv(f, index=False)
    pd.DataFrame(dict(date=["2025-01-01"], order_id=["1"], customer_id=["C"], product_id=["P"], qty=[1], revenue=[1])).to_csv(tmp_path / "sales.csv", index=False)
    return f, str(dates[k].date())


def _cli(tmp_path, f, d0, *extra):
    return cli.main(["roi-series", "--data", str(tmp_path), "--out", str(tmp_path / "o"), "--series", str(f),
                     "--intervention-date", d0, "--spend", "100", "--margin-rate", "0.5", *extra])


# ---------------- contrato: a etiqueta so vale com holdout real ----------------
def test_declared_design_without_holdout_estimate_is_rejected():
    y, c, k = _target_only_shock(0)
    res = planning.controlled_incremental_ci(y, c, k)                    # controlos quaisquer
    with pytest.raises(ContractError, match="holdout"):
        planning.roi_decision(res, 100, .5, desenho="aleatorizado")      # v0.6: dava positivo/causal/pode renovar
    res_h = planning.controlled_incremental_ci(y, c, k, holdout=True)
    with pytest.raises(ContractError, match="declarar o desenho"):
        planning.roi_decision(res_h, 100, .5)                            # holdout sem desenho declarado


def test_cli_design_requires_holdout_columns_and_vice_versa(tmp_path, capsys):
    y, c, k = _target_only_shock(1)
    f, d0 = _write_series(tmp_path, y, c, k, "control")
    assert _cli(tmp_path, f, d0, "--desenho", "aleatorizado") == 2        # desenho sem colunas holdout_*
    assert "holdout_" in capsys.readouterr().err
    f, d0 = _write_series(tmp_path, y, c, k, "holdout")
    assert _cli(tmp_path, f, d0) == 2                                     # colunas holdout_* sem desenho
    assert "exigem --desenho" in capsys.readouterr().err


@pytest.mark.slow
def test_real_holdout_decides_and_does_not_confuse_market_shock():
    """Choque de mercado +10% em todas as regioes, efeito ZERO: poucos 'positivo' (medido 17%); com efeito real decide."""
    def rate(effect, agg=False, n=40):
        out = {}
        for s in range(n):
            y, C, k = _hw(s, effect=effect, shock="mult", agg=agg)
            r = planning.controlled_incremental_ci(y, C, k, holdout=True)
            assert r["verificavel"]                                       # K=1 ou 3: o holdout nao fica bloqueado
            d = planning.roi_decision(r, spend=1, margin_rate=1.0, desenho="aleatorizado")
            out[d["decisao"]] = out.get(d["decisao"], 0) + 1
        return {k_: v / n for k_, v in out.items()}
    zero = rate(0.0); real = rate(25.0); agg = rate(25.0, agg=True)
    assert zero.get("positivo", 0) <= 0.30            # medido 0,17 (nominal 0,10: residuo declarado)
    assert real.get("positivo", 0) >= 0.45            # medido ~0,65
    assert agg.get("positivo", 0) >= 0.45             # holdout agregado K=1 tambem decide
    assert real.get("nao_afirmar", 0) <= 0.10


def test_causal_decision_carries_conditional_warning():
    h = dict(incremental=1000, ic=(900, 1100), valido=True, verificavel=True, avisos=[], holdout=True)
    d = planning.roi_decision(h, 100, .5, desenho="aleatorizado")
    assert d["causal"] and any("CONDICIONADO" in a for a in d["avisos"])


# ---------------- placebo no espaco ----------------
def test_space_placebo_calibration_and_power():
    def mk(s, delta=0.0):
        c = np.random.default_rng(s).normal(100, 5, (160, 3)); c[130:, 0] += delta; return c
    fa = np.mean([planning._space_placebo(mk(s), 130)[0] for s in range(40)])
    det = np.mean([planning._space_placebo(mk(s, 15.0), 130)[0] for s in range(40)])
    assert fa <= 0.20                                   # medido 0,09 (v0.7 intermedia com min-max: 0,225)
    assert det >= 0.90                                  # medido 1,00 para +15 (3 desvios)


def test_nonlinear_common_dynamics_do_not_block_valid_analyses():
    """v0.4: o z do proprio controlo dava 'valido' em so 57% dos casos limpos com dinamica comum nao linear."""
    ok = []
    for s in range(30):
        rng = np.random.default_rng(s); t = np.arange(160)
        f = 0.5 * t + 6 * np.sin(2 * np.pi * t / 52) + rng.normal(0, 2, 160).cumsum() * 0.3
        C = 20 + 0.4 * f[:, None] + rng.normal(0, 3, (160, 3)); y = 100 + f + rng.normal(0, 5, 160); y[130:] += 40
        ok.append(planning.controlled_incremental_ci(y, C, 130)["valido"])
    assert np.mean(ok) >= 0.85                          # medido 0,97
