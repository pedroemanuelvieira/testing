"""Testes Claude ciclo 02 (v0.4): cada teste nasce de uma falha reproduzida na v0.3 (ver ciclo02_claude_analise.md)."""
import warnings
import numpy as np, pandas as pd, pytest
from bi_ml import synth, contract, customers, demand, prepare, planning
from bi_ml import stock_and_variance as sv, basket_roi as br
from bi_ml.contract import ContractError, DataQualityWarning


def mk(rows):
    return pd.DataFrame(rows, columns=["date", "order_id", "customer_id", "product_id", "qty", "revenue"])


@pytest.fixture(scope="module")
def world():
    return synth.make(seed=11, n_cust=500, n_prod=20, days=730)


# ---------------- identificadores ----------------
def test_ids_normalised_float_and_spaces():
    s = mk([("2025-01-01", "1", "C1", 123.0, 1, 10), ("2025-01-02", "2", "C1", " 123 ", 1, 10)])
    out = contract.validate_sales(s)
    assert set(out.product_id) == {"123"}


def test_lost_sales_id_mismatch_fails_loudly(world):
    sales, stock, _, _ = world
    st = stock.copy(); st["product_id"] = st["product_id"].str.lower()      # 'p001' vs 'P001'
    with pytest.raises(ContractError, match="so 0% da receita"):
        sv.lost_sales(sales, st)


def test_lost_sales_partial_stock_needs_explicit_opt_in(world):
    sales, stock, _, _ = world
    st = stock[stock.product_id.isin(["P001", "P002"])]
    with pytest.raises(ContractError):
        sv.lost_sales(sales, st)
    with pytest.warns(DataQualityWarning):
        ev, _ = sv.lost_sales(sales, st, allow_partial=True)
    assert set(ev.product_id) <= {"P001", "P002"}


# ---------------- rupturas ----------------
def _flat_world(days=300, out_from=None, out_to=None, gap=None):
    d = pd.date_range("2025-01-01", periods=days)
    rows = [(x, f"O{i}", "C1", "A", 5, 50.0) for i, x in enumerate(d)]
    s = mk(rows)
    stk = pd.DataFrame({"date": d, "product_id": "A", "stock_qty": 100.0})
    if out_from is not None:
        m = (stk.date >= d[out_from]) & (stk.date <= d[out_to]); stk.loc[m, "stock_qty"] = 0.0
        s = s[~((s.date >= d[out_from]) & (s.date <= d[out_to]))]
    if gap is not None:
        stk = stk[~((stk.date >= d[gap[0]]) & (stk.date <= d[gap[1]]))]
    return contract.validate_sales(s), contract.validate_stock(stk)


def test_lost_sales_known_truth_flat_demand():
    s, stk = _flat_world(out_from=100, out_to=109)
    ev, summ = sv.lost_sales(s, stk)
    assert len(ev) == 1 and ev.dias.iloc[0] == 10
    assert abs(ev.unid_perdidas.iloc[0] - 50) < 1.0          # 10 dias x 5 un
    assert not ev.truncado.iloc[0] and not ev.possivel_descontinuado.iloc[0]


def test_discontinued_product_is_capped_and_flagged():
    s, stk = _flat_world(days=400, out_from=150, out_to=399)  # 250 dias sem stock ate ao fim
    ev, summ = sv.lost_sales(s, stk, max_event_days=60)
    assert ev.truncado.iloc[0] and ev.possivel_descontinuado.iloc[0]
    assert ev.unid_perdidas.iloc[0] <= 60 * 5 * 1.05           # nunca > cap x taxa
    assert bool(summ.possivel_descontinuado.iloc[0])


def test_stock_gap_does_not_extend_a_zero():
    # ruptura nos dias 100-104, depois o stock deixa de ser reportado dias 105-200 (buraco)
    d = pd.date_range("2025-01-01", periods=300)
    s, stk = _flat_world(out_from=100, out_to=104)
    stk = stk[~((stk.date >= d[105]) & (stk.date <= d[200]))]
    ev, _ = sv.lost_sales(s, stk, max_ffill_days=7)
    assert ev.dias.max() <= 5 + 7                               # ffill limitado; sem ruptura de ~100 dias


# ---------------- duplicados, balcao, devolucoes ----------------
def test_duplicates_warn():
    s = mk([("2025-01-01", "1", "C1", "A", 1, 10)] * 3 + [("2025-01-02", "2", "C1", "A", 1, 10)])
    with pytest.warns(DataQualityWarning, match="duplicadas"):
        contract.validate_sales(s)


def test_anonymous_customers_flow(world):
    sales, stock, _, _ = world
    s = sales.copy(); anon = s.sample(frac=0.2, random_state=1).index; s.loc[anon, "customer_id"] = np.nan
    s = contract.validate_sales(s)
    with pytest.warns(DataQualityWarning, match="sem customer_id"):
        lc = customers.lifecycle(s)
    assert lc.index.notna().all()
    br.basket_pairs(s)                                          # basket nao precisa de cliente
    demand.forecast_all(s, stock, h=4)                          # previsao tambem nao
    only_anon = s.assign(customer_id=np.nan)
    with pytest.raises(ContractError):
        customers.lifecycle(only_anon)


def test_prepare_sales_splits_returns_and_reports():
    raw = pd.DataFrame({"date": ["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-03"],
                        "order_id": [1, 2, 3, 4], "customer_id": ["C1", None, "C2", "C1"],
                        "product_id": [1.0, 1.0, 2.0, 2.0], "qty": [5, 3, -2, 0], "revenue": [50, 30, -20, 0]})
    sales, rets, rel = prepare.prepare_sales(raw)
    assert len(sales) == 2 and len(rets) == 1
    assert rel["devolucoes_valor"] == 20 and rel["receita_bruta"] == 80
    assert rel["linhas_sem_cliente"] == 1 and rel["linhas_qty_zero_removidas"] == 1
    with pytest.raises(ContractError):
        prepare.prepare_sales(raw, returns="reject")


def test_prepare_stock_negative_and_duplicates():
    raw = pd.DataFrame({"date": ["2025-01-01", "2025-01-01", "2025-01-02"], "product_id": ["A", "A", "A"],
                        "stock_qty": [5, 7, -3]})
    st, rel = prepare.prepare_stock(raw)
    assert rel["stock_negativo_para_zero"] == 1 and rel["duplicados_removidos"] == 1
    assert st.stock_qty.tolist() == [7, 0]
    with pytest.raises(ContractError):
        prepare.prepare_stock(raw, negative="reject")


# ---------------- previsao ----------------
def test_forecast_never_returns_empty_without_reason(world):
    sales, stock, _, _ = world
    s = sales[sales.date < sales.date.min() + pd.Timedelta(days=200)]
    with pytest.warns(DataQualityWarning, match="sem previsao"):
        f = demand.forecast_all(s, stock[stock.date <= s.date.max()])
    assert len(f) == 0 and len(f.attrs["omitidos"]) > 0
    assert all("historico" in v or "sem vendas" in v for v in f.attrs["omitidos"].values())


def test_forecast_new_product_not_treated_as_zero_demand():
    sig = synth.make_signal(seed=3, n_prod=3, years=3.0)
    last = sig.date.max()
    new = sig[(sig.product_id == "S00") & (sig.date > last - pd.Timedelta(days=100))].copy()
    new["product_id"] = "NEW"
    f = demand.forecast_all(pd.concat([sig, new]), None, h=4)
    assert "NEW" not in set(f.product_id)
    assert "desde a 1.a venda" in f.attrs["omitidos"]["NEW"]


@pytest.mark.slow
def test_forecast_selection_finds_real_signal():
    """Com sazonalidade+tendencia a selecao tem de bater a media de 13 semanas com folga
    (medido: WAPE 0,172 vs 0,298 em 2 sementes x 4 origens). Sem sinal custa ~5% (ver analise)."""
    sig = synth.make_signal(seed=1, n_prod=6, years=3.5)
    dall, _ = demand.weekly_demand(sig)
    last = sig.date.max(); err_c = err_b = tot = 0.0
    for k in range(2):
        origin = (last - pd.Timedelta(weeks=5 + 8 * k)).to_period("W-SUN").end_time.normalize()
        fc = demand.forecast_all(sig[sig.date <= origin], None, h=4, selection_policy="adaptive")
        dh, _ = demand.weekly_demand(sig[sig.date <= origin]); fut = dall[dall.index > origin].iloc[:4]
        for r in fc.itertuples():
            a = fut[r.product_id].iloc[r.week_ahead - 1]
            err_c += abs(a - r.forecast); err_b += abs(a - dh[r.product_id].values[-13:].mean()); tot += a
    assert err_c / tot < 0.8 * (err_b / tot)


# ---------------- PVM ----------------
def test_pvm_unequal_durations_warns_and_per_day_fixes_it():
    d1 = pd.date_range("2025-06-01", periods=30); d0 = pd.date_range("2025-01-01", periods=120)
    cur = pd.DataFrame({"date": d1, "product_id": "A", "qty": 10.0, "revenue": 100.0})
    ref = pd.DataFrame({"date": d0, "product_id": "A", "qty": 10.0, "revenue": 100.0})
    with pytest.warns(DataQualityWarning, match="duracao diferente"):
        sv.pvm(cur, ref)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        t = sv.pvm(cur, ref, per_day=True)
    assert abs(t.efeito_volume.sum()) < 1e-9 and abs(t.efeito_preco.sum()) < 1e-9   # mesma taxa diaria


# ---------------- ROI: diagnosticos ----------------
def _roi(seed, K=3, contam=0.0, seasonal=False, n=160, k=130):
    rng = np.random.default_rng(seed); t = np.arange(n)
    ph = rng.uniform(0, 6.28); season = np.sin(2 * np.pi * t / 52 + ph) if seasonal else 0 * t
    C = 20 + rng.normal(0, 3, (n, K)) + 8 * season[:, None]
    load = rng.uniform(1.5, 3.5, K)
    y = 100 + 0.5 * t + C @ load / K + 40 * season + rng.normal(0, 5, n)
    y[k:] += 20.0
    C = C.copy(); C[k:, 0] += contam
    return y, C, k


def test_roi_loo_flags_contaminated_control_not_clean_seasonal():
    flag_c = np.mean([not planning.controlled_incremental_ci(*_roi(s, contam=8))["valido"] for s in range(40)])
    flag_clean = np.mean([planning.controlled_incremental_ci(*_roi(s, seasonal=True))["loo_flag"] for s in range(40)])
    assert flag_c >= 0.80          # medido 0,88 (so LOO) e mais com z
    assert flag_clean <= 0.10      # medido 0,00 (K=3)


def test_roi_corrected_z_false_alarm_rate_iid():
    zs = [planning._control_shift_z(_roi(s, K=1)[1][:, 0], 130) for s in range(150)]
    assert np.mean(np.abs(zs) > 3) <= 0.04      # v0.3: 0,08; medido 0,01


def test_roi_verificavel_requires_redundant_controls_and_long_pre():
    assert planning.controlled_incremental_ci(*_roi(1, K=3))["verificavel"]
    r = planning.controlled_incremental_ci(*_roi(1, K=1))
    assert not r["verificavel"] and any("identificacao fraca" in a for a in r["avisos"])
    y, C, k = _roi(1, K=12, n=100, k=70)
    assert not planning.controlled_incremental_ci(y, C, k)["verificavel"]   # 70 < 8x14


# ---------------- ROI -> decisao ----------------
def test_roi_decision_rules():
    base = dict(incremental=1000.0, ic=(800.0, 1200.0), valido=True, verificavel=True, avisos=[])
    # v0.6 (Grok, OBJ-003): decisao causal so com desenho declarado; sem ele, indicio_estatistico_*
    D = "aleatorizado"; H = {**base, "holdout": True, "ic_racio": (700.0, 1240.0)}     # v0.7 holdout; v0.9: racio concordante (0.4*1240=496<500)
    assert planning.roi_decision(H, spend=500, margin_rate=0.4, desenho=D)["decisao"] == "negativo"   # 0.4*1200=480<500
    assert planning.roi_decision({**H, "incremental": 3000.0, "ic": (2500.0, 3500.0), "ic_racio": (2400.0, 3600.0)}, 500, 0.4, desenho=D)["decisao"] == "positivo"
    assert planning.roi_decision({**base, "incremental": 3000.0, "ic": (2500.0, 3500.0)}, 500, 0.4)["decisao"] == "indicio_estatistico_positivo"
    assert planning.roi_decision({**base, "ic": (100.0, 3000.0)}, 500, 0.4)["decisao"] == "inconclusivo"
    assert planning.roi_decision({**base, "valido": False}, 500, 0.4)["decisao"] == "nao_afirmar"
    with pytest.raises(ContractError):
        planning.roi_decision(base, spend=0, margin_rate=0.4)


# ---------------- CLI ponta a ponta com dados sujos ----------------
@pytest.mark.slow
def test_cli_end_to_end_dirty_extract(tmp_path, world):
    import json
    from bi_ml import cli
    sales, stock, camp, _ = world
    s = sales.copy()
    s["product_id"] = s["product_id"].str[1:].astype(int)            # ids numericos
    s["customer_id"] = s["customer_id"].str[1:]
    s.loc[s.sample(frac=0.1, random_state=3).index, "customer_id"] = np.nan          # balcao
    neg = s.sample(40, random_state=4).copy(); neg["qty"] *= -1; neg["revenue"] *= -1; s = pd.concat([s, neg, s.head(30)])  # devolucoes+duplicados
    st = stock.copy(); st["product_id"] = st["product_id"].str[1:].astype(int); st.loc[st.index[:20], "stock_qty"] = -3
    d = tmp_path / "dados"; d.mkdir()
    s.to_csv(d / "sales.csv", index=False); st.to_csv(d / "stock.csv", index=False)
    out = tmp_path / "saida"
    assert cli.main(["all", "--data", str(d), "--out", str(out)]) == 0
    rel = json.load(open(out / "relatorio_all.json"))
    assert all("erro" not in v for k, v in rel.items() if isinstance(v, dict) and k not in ("qualidade_dados",)), rel
    q = json.load(open(out / "qualidade_dados.json"))
    assert q["vendas"]["devolucoes_linhas"] == 40 and q["vendas"]["devolucoes_valor"] > 0
    assert q["vendas"]["linhas_sem_cliente"] > 0 and q["stock"]["stock_negativo_para_zero"] == 20
    assert any("duplicadas" in a for a in q["avisos"])
    for f in ("lifecycle.csv", "churn_scores.csv", "forecast.csv", "rupturas_eventos.csv", "pvm.csv", "basket_pares.csv",
              "cohort_retention.csv", "forecast_omitidos.csv"):
        assert (out / f).exists(), f


def test_cli_returns_exit_2_with_message_on_bad_stock_ids(tmp_path, world, capsys):
    from bi_ml import cli
    sales, stock, _, _ = world
    d = tmp_path / "d"; d.mkdir(); sales.to_csv(d / "sales.csv", index=False)
    stock.assign(product_id=stock.product_id.str.lower()).to_csv(d / "stock.csv", index=False)
    assert cli.main(["stockout", "--data", str(d), "--out", str(tmp_path / "o")]) == 2
    assert "ERRO DE DADOS" in capsys.readouterr().err


def test_cli_roi_series(tmp_path):
    from bi_ml import cli
    import json
    y, C, k = _roi(5, K=3)
    df = pd.DataFrame({"date": pd.date_range("2022-01-03", periods=len(y), freq="W"), "outcome": y})
    for j in range(C.shape[1]):
        df[f"control_{j+1}"] = C[:, j]
    df.to_csv(tmp_path / "serie.csv", index=False)
    d = tmp_path / "d"; d.mkdir(); synth_sales = pd.DataFrame([("2025-01-01", "1", "C1", "A", 1, 10.0)],
        columns=["date", "order_id", "customer_id", "product_id", "qty", "revenue"]); synth_sales.to_csv(d / "sales.csv", index=False)
    rc = cli.main(["roi-series", "--data", str(d), "--out", str(tmp_path / "o"), "--series", str(tmp_path / "serie.csv"),
                   "--intervention-date", str(df.date.iloc[k].date()), "--spend", "1000", "--margin-rate", "0.3"])
    assert rc == 0
    r = json.load(open(tmp_path / "o" / "relatorio_roi-series.json"))
    assert r["decisao"] in ("indicio_estatistico_positivo", "indicio_estatistico_negativo", "inconclusivo", "nao_afirmar") and "roi_ic" in r
    assert r["causal"] is False and r["pode_decidir_renovacao"] is False   # v0.6: sem --desenho nunca e causal


# ---------------- skills: formato valido E executavel de forma isolada ----------------
@pytest.mark.slow
def test_skills_are_valid_and_run_standalone(tmp_path, world):
    import os, re, subprocess, sys, importlib.util
    yaml = pytest.importorskip("yaml")
    spec = importlib.util.spec_from_file_location("build_skills", os.path.join(os.path.dirname(__file__), "..", "build_skills.py"))
    bs = importlib.util.module_from_spec(spec); spec.loader.exec_module(bs)
    dist = tmp_path / "dist"; names = bs.build(str(dist))
    assert len(names) == 10                             # v0.6: + bi-ml-abc-xyz
    for n in names:                                     # regras do validador oficial (OBJ-009: a v0.3 falhava todas)
        txt = (dist / n / "SKILL.md").read_text(encoding="utf-8")
        fm = yaml.safe_load(re.match(r"^---\n(.*?)\n---", txt, re.S).group(1))
        assert set(fm) <= {"name", "description"} and re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", fm["name"]) and len(fm["name"]) <= 64
        assert 0 < len(fm["description"]) <= 1024 and "<" not in fm["description"] and ">" not in fm["description"]
        assert len(list((dist / n).rglob("SKILL.md"))) == 1
    sales, stock, _, _ = world
    d = tmp_path / "dados"; d.mkdir()
    sales.to_csv(d / "sales.csv", index=False); stock.to_csv(d / "stock.csv", index=False)
    for skill, cmd, out_file in [("bi-ml-qualidade-dados", "check", "relatorio_check.json"),
                                 ("bi-ml-basket", "basket", "basket_pares.csv"),
                                 ("bi-ml-perda-ruptura", "stockout", "rupturas_resumo.csv")]:
        out = tmp_path / ("o_" + skill)
        r = subprocess.run([sys.executable, str(dist / skill / "scripts" / "run.py"), cmd, "--data", str(d), "--out", str(out)],
                           capture_output=True, text=True, cwd=str(tmp_path))     # cwd fora do pacote: prova autocontencao
        assert r.returncode == 0, r.stderr[-500:]
        assert (out / out_file).exists() and (out / "qualidade_dados.json").exists()


def test_plan_variance_ids_normalised_and_no_overlap_fails():
    sales = mk([("2025-01-05", "1", "C1", "00123", 4, 40.0), ("2025-02-05", "2", "C1", "00123", 6, 60.0)])
    plan = pd.DataFrame({"period": ["2025-01-01", "2025-02-01"], "product_id": ["00123 ", "00123"],
                         "planned_qty": [5, 5], "planned_revenue": [50.0, 50.0]})
    r = planning.plan_variance(sales, plan, "2025-03-01")
    assert (r.status == "matched").all() and r.delta_qty.tolist() == [-1.0, 1.0]
    bad = plan.assign(product_id="123")                      # zeros a esquerda perdidos: nao adivinhar
    with pytest.raises(ContractError, match="nenhum product_id"):
        planning.plan_variance(sales, bad, "2025-03-01")


def test_churn_minimum_history_is_exact_and_explained(world):
    sales = world[0]
    short = sales[sales.date <= sales.date.min() + pd.Timedelta(days=440)]
    with pytest.raises(ContractError, match="minimo 450 dias"):
        customers.churn_model(short)


def test_basket_excludes_giant_orders_with_warning(world):
    sales = world[0]
    giant = pd.DataFrame({"date": pd.Timestamp("2025-06-01"), "order_id": "GIANT", "customer_id": "C1",
                          "product_id": [f"X{i}" for i in range(500)], "qty": 1, "revenue": 1.0})
    s = pd.concat([sales, giant])
    with pytest.warns(DataQualityWarning, match="excluidas"):
        bp = br.basket_pairs(s, min_count=30)
    assert not bp.product_id_x.str.startswith("X").any() and bp.significativo.sum() >= 3   # pares plantados mantem-se
