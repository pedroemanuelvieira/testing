"""Basket analysis (regras de associacao com controlo de multiplicidade) e ROI incremental."""
from __future__ import annotations
import warnings
import numpy as np
import pandas as pd
from .contract import DataQualityWarning, ContractError
from scipy.stats import chi2_contingency, fisher_exact


# ----------------------------------------------------------------------------------------
# BASKET
# ----------------------------------------------------------------------------------------
def basket_pairs(sales: pd.DataFrame, min_count=20, fdr=0.05, max_items_per_order=100,
                 min_lift=None, min_incremental_orders=None):
    """Pares de produtos com support, confidence, lift, leverage e p-valor ajustado (BH).

    Lift > 1 sozinho e enganador com pares raros; filtramos por contagem minima e
    aplicamos Benjamini-Hochberg sobre testes exatos/chi2 de independencia.

    v0.9 (Grok, OBJ-033): com N grande, a significancia sinaliza lifts irrelevantes. Limiar de EFEITO e
    parametro de negocio (nao ha constante universal): `min_lift` e/ou `min_incremental_orders`
    (encomendas associadas incrementais = N x leverage = n_ab - n_a*n_b/N; converter em valor com margem
    e custo da acao). `elegivel` = significativo E material; `motivo_exclusao` explica cada par nao elegivel.
    Sem limiares: material=NA e elegivel=False; os pares ficam disponiveis para exploracao. Associacao, nao uplift.
    Fixar os limiares ANTES de olhar para os pares e validar num periodo posterior.
    """
    for nm, v in (("min_lift", min_lift), ("min_incremental_orders", min_incremental_orders)):
        if v is not None and not (np.isfinite(v) and v > 0):
            raise ValueError(f"basket_pairs: {nm} tem de ser finito e > 0")
    o = sales[["order_id", "product_id"]].drop_duplicates()
    # v0.4 (OBJ-006): o auto-merge e quadratico por encomenda. Encomendas enormes (transferencias, cargas)
    # quase nao informam associacao e podem rebentar a memoria: ficam fora, com aviso.
    size = o.groupby("order_id")["product_id"].transform("size")
    if (size > max_items_per_order).any():
        big = o.loc[size > max_items_per_order, "order_id"].nunique()
        warnings.warn(f"basket: {big} encomendas com mais de {max_items_per_order} produtos distintos excluidas "
                      "(custo quadratico; raramente sao cestos de compra).", DataQualityWarning, stacklevel=2)
        o = o[size <= max_items_per_order]
    n = o["order_id"].nunique()
    cnt = o.groupby("product_id").size()
    m = o.merge(o, on="order_id")
    m = m[m.product_id_x < m.product_id_y]
    pc = m.groupby(["product_id_x", "product_id_y"]).size().rename("n_ab").reset_index()
    pc = pc[pc.n_ab >= min_count]
    if pc.empty:
        return pc
    pc["n_a"] = pc.product_id_x.map(cnt); pc["n_b"] = pc.product_id_y.map(cnt)
    pc["support"] = pc.n_ab / n
    pc["conf_a_b"] = pc.n_ab / pc.n_a
    pc["conf_b_a"] = pc.n_ab / pc.n_b
    pc["lift"] = pc.support / ((pc.n_a / n) * (pc.n_b / n))
    pc["leverage"] = pc.support - (pc.n_a / n) * (pc.n_b / n)
    pv = []
    for r in pc.itertuples():
        tab = [[r.n_ab, r.n_a - r.n_ab], [r.n_b - r.n_ab, n - r.n_a - r.n_b + r.n_ab]]
        pv.append(fisher_exact(tab)[1] if min(map(min, tab)) < 5 else chi2_contingency(tab)[1])
    pc["p"] = pv
    # Benjamini-Hochberg
    order = np.argsort(pc["p"].values)
    ranked = pc["p"].values[order] * len(pc) / (np.arange(len(pc)) + 1)
    adj = np.minimum.accumulate(ranked[::-1])[::-1]
    q = np.empty(len(pc)); q[order] = np.minimum(adj, 1)
    pc["q_bh"] = q
    pc["significativo"] = (pc.q_bh < fdr) & (pc.lift > 1)
    pc["encomendas_incrementais"] = pc.n_ab - pc.n_a * pc.n_b / n
    if min_lift is None and min_incremental_orders is None:
        pc["material"] = pd.NA
        pc["elegivel"] = False
        warnings.warn("basket: sem limiar de efeito de negocio (min_lift/min_incremental_orders); 'significativo' "
                      "com muitas encomendas inclui lifts economicamente irrelevantes. elegivel=False ate declarar "
                      "um limiar; os pares continuam disponiveis para exploracao.", DataQualityWarning, stacklevel=2)
    else:
        mat = pd.Series(True, index=pc.index)
        if min_lift is not None:
            mat &= pc.lift >= min_lift
        if min_incremental_orders is not None:
            mat &= pc.encomendas_incrementais >= min_incremental_orders
        pc["material"] = mat
        pc["elegivel"] = pc["significativo"] & mat
    motivo = np.where(~(pc.lift > 1), "lift<=1",
             np.where(~(pc.q_bh < fdr), "nao_significativo_bh",
             np.where(pc["elegivel"].astype(bool), "",
                      "limiar_material_nao_declarado" if min_lift is None and min_incremental_orders is None
                      else "efeito_abaixo_do_limiar")))
    pc["motivo_exclusao"] = motivo
    pc.attrs["n_encomendas"] = int(n)
    return pc.sort_values("lift", ascending=False).reset_index(drop=True)


def recommend(pairs: pd.DataFrame, product_id: str, top=5):
    """Cross-sell: apenas pares cuja significancia E materialidade foram avaliadas."""
    if pairs.empty:
        return pd.DataFrame(columns=["sugerir", "confianca", "lift"])
    if "elegivel" not in pairs.columns:
        raise ContractError("recommend: recalcular basket_pairs com limiar de negocio; falta elegivel")
    p = pairs[pairs["elegivel"].fillna(False).astype(bool)]
    a = p[p.product_id_x == product_id][["product_id_y", "conf_a_b", "lift"]].rename(
        columns={"product_id_y": "sugerir", "conf_a_b": "confianca"})
    b = p[p.product_id_y == product_id][["product_id_x", "conf_b_a", "lift"]].rename(
        columns={"product_id_x": "sugerir", "conf_b_a": "confianca"})
    return pd.concat([a, b]).sort_values("confianca", ascending=False).head(top)


# ----------------------------------------------------------------------------------------
# ROI INCREMENTAL
# ----------------------------------------------------------------------------------------
def campaign_roi(sales: pd.DataFrame, invest: pd.DataFrame, pre_days=120, n_placebo=200,
                 seed=0, use_margin=True):
    """ROI incremental com contrafactual por produtos de controlo + intervalo por placebos.

    Contrafactual: venda diaria do produto alvo = beta x venda diaria dos controlos, com beta
    estimado no periodo pre. Incerteza: repete o mesmo procedimento em janelas falsas
    (placebo) sem campanha e usa a distribuicao do erro relativo -> IC empirico.
    ROI = (margem incremental - gasto) / gasto. O pre/post ingenuo e reportado para contraste.
    """
    rng = np.random.default_rng(seed)
    d = sales.copy()
    d["m"] = d["revenue"] - d["cost"] if (use_margin and "cost" in d.columns) else d["revenue"]
    dr = d.groupby(["date", "product_id"])[["m", "revenue"]].sum()
    idx = pd.date_range(d.date.min(), d.date.max())
    all_targets = set(invest["product_id"].dropna())
    out = []
    mat_rev = dr["revenue"].unstack(1).reindex(idx).fillna(0)
    mat_m = dr["m"].unstack(1).reindex(idx).fillna(0)
    controls = [c for c in mat_rev.columns if c not in all_targets]
    ctrl = mat_rev[controls].sum(axis=1)

    def counterfactual(p, start, end):
        pre = (idx >= start - pd.Timedelta(days=pre_days)) & (idx < start)
        if pre.sum() < 30 or ctrl[pre].sum() == 0:
            return None
        beta = mat_rev.loc[pre, p].sum() / ctrl[pre].sum()
        win = (idx >= start) & (idx <= end)
        return beta * ctrl[win].sum(), mat_rev.loc[win, p].sum(), pre

    # distribuicao de erro relativo em placebos
    errs = {}
    for p in all_targets:
        errs[p] = []
        for _ in range(n_placebo):
            L = rng.integers(14, 35)
            s = idx[rng.integers(pre_days + 5, len(idx) - L - 1)]
            e = s + pd.Timedelta(days=int(L))
            # janela placebo nao pode sobrepor campanha real do produto
            clash = ((invest.product_id == p) & (invest.start <= e) & (invest.end >= s)).any()
            if clash:
                continue
            r = counterfactual(p, s, e)
            if r and r[0] > 0:
                errs[p].append((r[1] - r[0]) / r[0])

    for k in invest.itertuples():
        p = k.product_id
        r = counterfactual(p, k.start, k.end)
        if r is None:
            out.append({"campaign_id": k.campaign_id, "erro": "historico pre insuficiente"})
            continue
        cf_rev, act_rev, pre = r
        win = (idx >= k.start) & (idx <= k.end)
        mrate = mat_m.loc[pre, p].sum() / max(mat_rev.loc[pre, p].sum(), 1e-9) if use_margin else 1.0
        inc_rev = act_rev - cf_rev
        e = np.array(errs.get(p, []))
        if len(e) >= 20:
            q_lo, q_hi = np.quantile(e, [0.05, 0.95])
            lo_rev, hi_rev = act_rev - cf_rev * (1 + q_hi), act_rev - cf_rev * (1 + q_lo)
        else:
            lo_rev = hi_rev = np.nan
        inc_m = inc_rev * mrate
        naive_pre = mat_rev.loc[(idx >= k.start - pd.Timedelta(days=(k.end - k.start).days + 1)) & (idx < k.start), p].sum()
        out.append({
            "campaign_id": k.campaign_id, "product_id": p, "gasto": k.spend,
            "receita_real": act_rev, "receita_contrafactual": cf_rev,
            "receita_incremental": inc_rev, "ic90_receita_inc": (lo_rev, hi_rev),
            "margem_incremental": inc_m,
            "roi_incremental": (inc_m - k.spend) / k.spend,
            "roi_ic90": ((lo_rev * mrate - k.spend) / k.spend, (hi_rev * mrate - k.spend) / k.spend),
            "roi_ingenuo_pre_post": ((act_rev - naive_pre) * mrate - k.spend) / k.spend,
            "n_placebos": int(len(e)),
        })
    return pd.DataFrame(out)
