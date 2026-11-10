"""Ciclo de vida do cliente + churn com validacao temporal honesta."""
from __future__ import annotations
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from . import contract

FEATURES = ["recency", "freq_30", "freq_90", "freq_180", "freq_total", "monetary_180",
            "aov", "tenure", "mean_gap", "gap_ratio", "n_products", "trend_90_vs_prev"]


def _orders(sales):
    g = sales.groupby(["customer_id", "order_id"], as_index=False).agg(
        date=("date", "min"), revenue=("revenue", "sum"))
    return g


def features_at(sales: pd.DataFrame, cutoff) -> pd.DataFrame:
    """Features de cada cliente usando APENAS dados <= cutoff (sem fuga de futuro)."""
    cutoff = pd.Timestamp(cutoff)
    sales = contract.known_customers(sales, warn=False)
    s = sales[sales["date"] <= cutoff]
    o = _orders(s)
    if o.empty:
        return pd.DataFrame(columns=FEATURES)
    o["age"] = (cutoff - o["date"]).dt.days
    g = o.groupby("customer_id")
    f = pd.DataFrame({
        "recency": g["age"].min(),
        "freq_total": g.size(),
        "tenure": g["age"].max(),
        "aov": g["revenue"].mean(),
    })
    for w in (30, 90, 180):
        f[f"freq_{w}"] = o[o.age < w].groupby("customer_id").size()
    f["monetary_180"] = o[o.age < 180].groupby("customer_id")["revenue"].sum()
    prev = o[(o.age >= 90) & (o.age < 180)].groupby("customer_id").size()
    f["trend_90_vs_prev"] = (f["freq_90"].fillna(0) - prev.reindex(f.index).fillna(0))
    o = o.sort_values(["customer_id", "date"])
    o["gap"] = o.groupby("customer_id")["date"].diff().dt.days
    f["mean_gap"] = o.groupby("customer_id")["gap"].mean()
    f["mean_gap"] = f["mean_gap"].fillna(f["tenure"].clip(lower=30))
    f["gap_ratio"] = f["recency"] / f["mean_gap"].clip(lower=1)
    f["n_products"] = s.groupby("customer_id")["product_id"].nunique()
    f = f.fillna(0)
    return f[FEATURES]


def lifecycle(sales: pd.DataFrame, asof=None, new_days=60, reactivation_days=90) -> pd.DataFrame:
    """Estagios relativos ao ritmo PROPRIO do cliente (nao um limiar global)."""
    sales = contract.known_customers(sales)  # v0.4: balcao/anonimo excluido, com aviso
    asof = pd.Timestamp(asof) if asof is not None else sales["date"].max()
    f = features_at(sales, asof)
    # primeira compra recente
    first = sales.groupby("customer_id")["date"].min()
    f["first_purchase"] = first.reindex(f.index)
    # gap anterior a ultima compra (para reativacao)
    o = _orders(sales[sales["date"] <= asof]).sort_values(["customer_id", "date"])
    o["gap"] = o.groupby("customer_id")["date"].diff().dt.days
    last_gap = o.groupby("customer_id")["gap"].last()
    ref = f["mean_gap"].clip(lower=14)
    stage = np.select(
        [
            (asof - f["first_purchase"]).dt.days <= new_days,
            (f["recency"] <= reactivation_days) & (last_gap.reindex(f.index) > 3 * ref),
            f["recency"] <= 1.5 * ref,
            f["recency"] <= 3 * ref,
        ],
        ["novo", "reativado", "ativo", "em_risco"], default="perdido")
    f["stage"] = stage
    return f


def _label(sales, cutoff, horizon):
    cutoff = pd.Timestamp(cutoff)
    fut = sales[(sales["date"] > cutoff) & (sales["date"] <= cutoff + pd.Timedelta(days=horizon))]
    return set(fut["customer_id"].unique())


def build_dataset(sales, cutoffs, horizon):
    parts = []
    for c in cutoffs:
        f = features_at(sales, c)
        buyers = _label(sales, c, horizon)
        f["churn"] = (~f.index.isin(buyers)).astype(int)
        f["cutoff"] = pd.Timestamp(c)
        parts.append(f)
    return pd.concat(parts)


def churn_model(sales: pd.DataFrame, horizon=90, step_days=30, min_hist=180, random_state=0,
                min_gain=0.01):
    """Selecao e avaliacao separadas (v0.3, Grok; OBJ-014).

    treino: cutoffs com horizonte fechado antes do cutoff de validacao;
    validacao: penultimo cutoff elegivel -> ESCOLHE o modelo;
    teste: ultimo cutoff -> so REPORTA (nunca escolhe).
    Candidatos por ordem de complexidade: baseline_recencia (logistica so com recencia,
    calibrada) < logistica < gbm. Um modelo mais complexo so substitui o anterior se
    ganhar >= min_gain de AUC na validacao. O baseline e elegivel.
    """
    sales = contract.known_customers(sales)  # v0.4: balcao/anonimo excluido, com aviso
    last = sales["date"].max()
    first = sales["date"].min()
    # minimo exato: treino < validacao < teste, cada separacao >= horizonte (purga) em passos de step_days
    k = int(np.ceil(horizon / step_days)); need = min_hist + 2 * k * step_days + horizon
    have = int((last - first).days)
    if have < need:
        raise contract.ContractError(
            f"churn: historico de {have} dias insuficiente para validacao temporal (minimo {need} dias "
            f"= min_hist {min_hist} + 2 x {k * step_days} de purga + horizonte {horizon}).")
    latest_labelled = last - pd.Timedelta(days=horizon)
    cutoffs = pd.date_range(first + pd.Timedelta(days=min_hist), latest_labelled, freq=f"{step_days}D")
    hz = pd.Timedelta(days=horizon)
    test_cut = cutoffs[-1]
    val_opts = [c for c in cutoffs[:-1] if c + hz <= test_cut]
    if not val_opts:
        raise contract.ContractError("churn: sem cutoff de validacao apos purga; aumentar o historico")
    val_cut = val_opts[-1]
    train_cuts = [c for c in cutoffs if c + hz <= val_cut]
    if not train_cuts:
        raise contract.ContractError("churn: sem cutoffs de treino antes da validacao (purga); aumentar o historico")
    tr = build_dataset(sales, train_cuts, horizon)
    va = build_dataset(sales, [val_cut], horizon)
    te = build_dataset(sales, [test_cut], horizon)
    if tr["churn"].nunique() < 2 or va["churn"].nunique() < 2 or te["churn"].nunique() < 2:
        raise contract.ContractError("churn: uma das janelas tem uma so classe; aumentar historico ou horizonte")

    def make(name):
        if name == "baseline_recencia":
            return make_pipeline(StandardScaler(), LogisticRegression(max_iter=500)), ["recency"]
        if name == "logistica":
            return make_pipeline(StandardScaler(), LogisticRegression(max_iter=500, C=1.0)), FEATURES
        return HistGradientBoostingClassifier(max_depth=4, learning_rate=0.06, max_iter=250,
                                              l2_regularization=1.0, random_state=random_state), FEATURES

    order = ["baseline_recencia", "logistica", "gbm"]
    res = {"validacao": {}, "teste": {}}
    for name in order:
        m, cols = make(name)
        m.fit(tr[cols], tr["churn"])
        res["validacao"][name] = _metrics(va["churn"], m.predict_proba(va[cols])[:, 1])
        # teste: reajusta com treino+validacao (tudo com horizonte fechado antes do teste)
        m2, _ = make(name)
        trva = pd.concat([tr, va])
        m2.fit(trva[cols], trva["churn"])
        res["teste"][name] = _metrics(te["churn"], m2.predict_proba(te[cols])[:, 1])
    best = order[0]
    for name in order[1:]:
        if res["validacao"][name]["auc"] >= res["validacao"][best]["auc"] + min_gain:
            best = name
    # compatibilidade v0.2: chaves de topo = metricas de TESTE
    for name in order:
        res[name] = res["teste"][name]
    res["logistica_compat_nota"] = "chaves de topo = teste; escolha feita so na validacao"
    model, cols = make(best)
    full = build_dataset(sales, list(cutoffs), horizon)
    model.fit(full[cols], full["churn"])
    cur = features_at(sales, last)
    cur["p_churn"] = model.predict_proba(cur[cols])[:, 1]
    cur["decil"] = pd.qcut(cur["p_churn"].rank(method="first"), 10, labels=False) + 1
    res["escolhido"] = best
    res["cutoffs"] = {"treino_ultimo": str(train_cuts[-1].date()), "validacao": str(val_cut.date()),
                      "teste": str(test_cut.date())}
    res["n_treino"] = int(len(tr)); res["n_validacao"] = int(len(va)); res["n_teste"] = int(len(te))
    res["taxa_churn_teste"] = float(te["churn"].mean())
    return cur, res, model


def _metrics(y, p):
    y = np.asarray(y); p = np.asarray(p)
    out = {"auc": float(roc_auc_score(y, p)), "pr_auc": float(average_precision_score(y, p))}
    if p.min() >= 0 and p.max() <= 1:
        out["brier"] = float(brier_score_loss(y, p))
    k = max(1, len(y) // 10)
    top = np.argsort(-p)[:k]
    out["lift_top_decil"] = float(y[top].mean() / max(y.mean(), 1e-9))
    return out


def clv_12m(sales, scores, horizon=90, margin_col=None):
    """HEURISTICA de valor a 12 meses = ritmo de margem dos ultimos 180 dias x sobrevivencia (v0.4: rotulada).

    Validada (sintetico, 455 dias de historico, 822 clientes): total previsto +3% vs realizado (ajustado a
    365 dias), mas o RANKING equivale a 'margem dos ultimos 180 dias x 2' (Spearman 0,63 vs 0,61; top-decil
    24,6% vs 24,8% da margem futura). Usar para priorizar e somar; nao afirmar poder preditivo individual.
    """
    last = sales["date"].max()
    s = sales[sales["date"] > last - pd.Timedelta(days=180)].copy()
    s["m"] = s["revenue"] - s["cost"] if "cost" in s.columns else s["revenue"]
    run = s.groupby("customer_id")["m"].sum() / 180.0
    surv = (1 - scores["p_churn"]).clip(0, 1) ** (365 / horizon)
    out = (run.reindex(scores.index).fillna(0) * 365 * (1 + surv) / 2).rename("clv_12m")
    return out
