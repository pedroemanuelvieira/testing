"""Testes Grok ciclo 03 (v0.9): politica guarded (OBJ-032), concordancia de especificacoes e separacao
evidencia/autorizacao no ROI (OBJ-003), limiar de efeito no basket (OBJ-033), semantica fiscal (IVA),
gerador de skills alinhado e skill gerada executavel. Tudo sintetico."""
import json, os, subprocess, sys, warnings
import numpy as np, pandas as pd, pytest
from bi_ml import demand, planning, basket_roi as br, synth, cli
from bi_ml.contract import DataQualityWarning

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------- OBJ-032: guarded ----------------
def _weekly(q, pid="A"):
    return pd.DataFrame(dict(date=pd.date_range("2023-01-02", periods=len(q), freq="W-MON"), product_id=pid, qty=q))


def test_guarded_is_accepted_and_falls_back_on_noise():
    rng = np.random.default_rng(3)
    s = pd.concat([_weekly(rng.poisson(20, 110).astype(float), p) for p in "ABC"])
    f = demand.forecast_all(s, h=8, selection_policy="guarded")
    assert set(f.selection_policy) == {"guarded"} and set(f.selection_horizon) == {8}
    assert (f.method == "media_13s").mean() >= 2 / 3          # ruido puro: a guarda quase nunca troca
    with pytest.raises(ValueError):
        demand.forecast_all(s, selection_policy="auto")


@pytest.mark.slow
def test_guarded_finds_signal_at_h8():
    """make_signal: guarded tem de bater a media com folga a 8 semanas (medido 0,18 vs 0,40 na semente 1)."""
    sig = synth.make_signal(seed=1, n_prod=4, years=3.5)
    dall, _ = demand.weekly_demand(sig)
    origin = (sig.date.max() - pd.Timedelta(weeks=9)).to_period("W-SUN").end_time.normalize()
    fc = demand.forecast_all(sig[sig.date <= origin], None, h=8, selection_policy="guarded")
    dh, _ = demand.weekly_demand(sig[sig.date <= origin]); fut = dall[dall.index > origin].iloc[:8]
    e_c = e_b = tot = 0.0
    for r in fc.itertuples():
        a = fut[r.product_id].iloc[r.week_ahead - 1]
        e_c += abs(a - r.forecast); e_b += abs(a - dh[r.product_id].values[-13:].mean()); tot += a
    assert (fc.method != "media_13s").any()
    assert e_c / tot < 0.8 * (e_b / tot)


def test_guarded_requires_fold_majority(monkeypatch):
    """Ganho medio grande vindo de UMA dobra nao chega: a guarda exige vitoria em >= 2/3 das dobras."""
    def fake_backtest(series, h=4, n_folds=4, step=4, methods=demand.METHODS, fold_errors=None):
        fe = {m: [0.5] * 6 for m in methods}
        if "gbm" in fe:
            fe["gbm"] = [0.0, 0.0, 0.0, 0.9, 0.9, 0.6]     # media 0,40 (20% melhor) mas ganha so em 3/6 dobras
        if fold_errors is not None:
            fold_errors.update(fe)
        return {m: float(np.mean(v)) for m, v in fe.items()}, {m: [0.0] for m in methods}
    monkeypatch.setattr(demand, "backtest", fake_backtest)
    s = _weekly(np.arange(1, 101, dtype=float))
    assert set(demand.forecast_all(s, h=8, selection_policy="guarded").method) == {"media_13s"}
    assert set(demand.forecast_all(s, h=8, selection_policy="adaptive").method) == {"gbm"}


# ---------------- OBJ-003: concordancia + autorizacao humana ----------------
def _hd(ic, ic_r):
    return dict(incremental=1000, ic=ic, ic_racio=ic_r, valido=True, verificavel=True, avisos=[], holdout=True)


def test_disagreeing_specifications_are_inconclusive():
    d = planning.roi_decision(_hd((900, 1100), (-50, 1500)), 100, .5, desenho="aleatorizado")
    assert d["decisao"] == "inconclusivo" and d["concordancia_especificacoes"] is False
    assert any("discordam" in a for a in d["avisos"]) and not d["evidencia_para_revisao"]


def test_package_never_authorises_renewal():
    d = planning.roi_decision(_hd((900, 1100), (850, 1150)), 100, .5, desenho="aleatorizado")
    assert d["decisao"] == "positivo" and d["evidencia_para_revisao"] and d["concordancia_especificacoes"]
    assert d["pode_decidir_renovacao"] is False and d["autorizacao"] == "humana_obrigatoria"
    assert any("HUMANA" in a for a in d["avisos"])


def _hw(seed, effect=0.0, shock="mult", n=160, k=130, R=6):
    rng = np.random.default_rng(seed); t = np.arange(n)
    G = 100 + 0.4 * t + 12 * np.sin(2 * np.pi * t / 52 + rng.uniform(0, 6.28)) + rng.normal(0, 2, n).cumsum() * 0.3
    w = rng.uniform(0.8, 1.2, R); S = np.column_stack([w[r] * G + rng.normal(0, 4, n) for r in range(R)])
    if shock == "mult":
        S[k:] *= 1.10
    elif shock == "add":
        S[k:] += 0.10 * S[:k].mean()
    perm = rng.permutation(R); tr, ho = perm[:R // 2], perm[R // 2:]
    y = S[:, tr].sum(axis=1); y[k:] += effect
    return y, S[:, ho], k


@pytest.mark.slow
@pytest.mark.parametrize("shock", ["mult", "add"])
def test_market_shock_false_positive_near_nominal(shock):
    """Efeito ZERO com choque de mercado em todas as regioes. v0.8: 17,5% 'positivo' (OLS sozinho).
    v0.9: medido 0,0% (mult) e 7,5% (aditivo) em 80 mundos; aqui sementes 100-139 (fora das usadas para desenhar)."""
    pos = 0
    for s in range(100, 140):
        y, C, k = _hw(s, shock=shock)
        d = planning.roi_decision(planning.controlled_incremental_ci(y, C, k, holdout=True), 1, 1.0, desenho="aleatorizado")
        pos += d["decisao"] == "positivo"
    assert pos / 40 <= 0.125


@pytest.mark.slow
def test_agreement_keeps_power():
    pos = 0
    for s in range(100, 140):
        y, C, k = _hw(s, effect=25.0)
        d = planning.roi_decision(planning.controlled_incremental_ci(y, C, k, holdout=True), 1, 1.0, desenho="aleatorizado")
        pos += d["decisao"] == "positivo"
    assert pos / 40 >= 0.45                                  # medido 0,61-0,66 (80 mundos)


# ---------------- OBJ-033: limiar de efeito ----------------
def _orders():
    rng = np.random.default_rng(0); rows = []
    for o in range(4000):
        items = {p for p in "ABCDEFGH" if rng.random() < 0.15}
        if "A" in items and rng.random() < 0.6:
            items.add("B")                                    # par forte
        if "C" in items and rng.random() < 0.08:
            items.add("D")                                    # par fraco mas significativo com N grande
        rows += [dict(order_id=str(o), product_id=p) for p in items]
    return pd.DataFrame(rows)


def test_basket_effect_threshold_and_reasons():
    s = _orders()
    with pytest.warns(DataQualityWarning, match="limiar de efeito"):
        base = br.basket_pairs(s)
    # v0.10: significancia sem materialidade continua exploratoria, nao elegivel para recomendar.
    assert base["material"].isna().all() and not base.elegivel.any()
    n = base.attrs["n_encomendas"]
    assert np.allclose(base.encomendas_incrementais, base.n_ab - base.n_a * base.n_b / n)
    assert np.allclose(base.encomendas_incrementais, n * base.leverage)
    t = br.basket_pairs(s, min_lift=1.5)
    assert set(t[t.elegivel].index) <= set(t[t.significativo].index)
    ab = t[(t.product_id_x == "A") & (t.product_id_y == "B")].iloc[0]
    assert ab.elegivel and ab.motivo_exclusao == ""
    excl = t[t.significativo & ~t.elegivel]
    assert (excl.motivo_exclusao == "efeito_abaixo_do_limiar").all()
    assert set(br.recommend(t, "C").sugerir) <= set(t[t.elegivel].product_id_y) | set(t[t.elegivel].product_id_x)
    with pytest.raises(ValueError):
        br.basket_pairs(s, min_lift=0)


# ---------------- IVA / semantica fiscal ----------------
@pytest.fixture(scope="module")
def small_world():
    sales, stock, _, _ = synth.make(seed=5, n_cust=300, n_prod=12, days=730)
    return sales, stock


def _dir(tmp_path, sales, opts=None):
    d = tmp_path / "d"; d.mkdir(exist_ok=True); sales.to_csv(d / "sales.csv", index=False)
    if opts is not None:
        json.dump(opts, open(d / "csv_options.json", "w"))
    return d


def test_fiscal_basis_missing_warns_on_monetary_only(tmp_path, small_world):
    d = _dir(tmp_path, small_world[0])
    assert cli.main(["lifecycle", "--data", str(d), "--out", str(tmp_path / "o")]) == 0
    r = json.load(open(tmp_path / "o" / "relatorio_lifecycle.json"))
    assert any("NAO declarada" in a for a in r["qualidade_dados"]["avisos_fiscais"])
    assert cli.main(["basket", "--data", str(d), "--out", str(tmp_path / "b")]) == 0
    assert json.load(open(tmp_path / "b" / "relatorio_basket.json"))["qualidade_dados"]["avisos_fiscais"] == []


def test_fiscal_basis_declared_and_invalid(tmp_path, small_world, capsys):
    d = _dir(tmp_path, small_world[0], {"revenue_basis": "sem_imposto", "currency": "EUR"})
    assert cli.main(["lifecycle", "--data", str(d), "--out", str(tmp_path / "o")]) == 0
    r = json.load(open(tmp_path / "o" / "relatorio_lifecycle.json"))["qualidade_dados"]
    assert r["avisos_fiscais"] == [] and r["semantica_fiscal"] == {"revenue_basis": "sem_imposto", "currency": "EUR"}
    _dir(tmp_path, small_world[0], {"revenue_basis": "iva23"})
    assert cli.main(["lifecycle", "--data", str(d), "--out", str(tmp_path / "x")]) == 2
    assert "revenue_basis" in capsys.readouterr().err


# ---------------- gerador de skills: documentacao alinhada + instalacao executavel ----------------
def test_skill_generator_matches_v09_and_generated_skill_runs(tmp_path, small_world):
    sys.path.insert(0, HERE)
    import build_skills
    names = build_skills.build(str(tmp_path / "skills"))
    fc = open(tmp_path / "skills" / "bi-ml-previsao-procura" / "SKILL.md", encoding="utf-8").read()
    assert "Por omissao usa a media das ultimas 13 semanas" in fc and "guarded" in fc
    assert "escolha de metodo por backtest, em que a media" not in fc
    roi = open(tmp_path / "skills" / "bi-ml-roi-incremental" / "SKILL.md", encoding="utf-8").read()
    assert "pode_decidir_renovacao=true" not in roi and "humana_obrigatoria" in roi
    for n in names:                                       # frontmatter minimo exigido pelo quick_validate
        head = open(tmp_path / "skills" / n / "SKILL.md", encoding="utf-8").read().split("---")[1]
        assert f"name: {n}" in head and "description:" in head and "<" not in head
    d = _dir(tmp_path, small_world[0], {"revenue_basis": "sem_imposto", "currency": "EUR"})
    small_world[1].to_csv(d / "stock.csv", index=False)
    run = tmp_path / "skills" / "bi-ml-previsao-procura" / "scripts" / "run.py"
    p = subprocess.run([sys.executable, str(run), "forecast", "--data", str(d), "--out", str(tmp_path / "so"),
                        "--selection-policy", "baseline"], capture_output=True, text=True, cwd=str(tmp_path), timeout=600)
    # baseline: a skill gerada corre fora da arvore; guarded e testado acima (no CLI e lento: backtest de todos os metodos)
    assert p.returncode == 0, p.stderr
    f = pd.read_csv(tmp_path / "so" / "forecast.csv")
    assert set(f.selection_policy) == {"baseline"} and set(f.method) == {"media_13s"}
