"""Perda de vendas por falta de stock + desvios de vendas (PVM e anomalias)."""
from __future__ import annotations
import warnings
import numpy as np
import pandas as pd
from . import contract


# ----------------------------------------------------------------------------------------
# 1. PERDA DE VENDAS POR RUPTURA
# ----------------------------------------------------------------------------------------
def lost_sales(sales: pd.DataFrame, stock: pd.DataFrame, window=28, min_days_in_stock=14,
               min_overlap=0.5, allow_partial=False, max_event_days=60, max_ffill_days=7):
    """Estima unidades/valor perdidos nos dias com stock<=0.

    v0.4: (a) check_id_overlap: ids vendas/stock que nao casam FALHAM (antes: 0 rupturas silencioso);
    (b) rupturas > max_event_days: perda contada so nos primeiros max_event_days e marcada
    `truncado`; se a ruptura chega ao fim dos dados, `possivel_descontinuado` (antes: um produto
    descontinuado gerava 'perdas' crescentes); (c) buracos no stock > max_ffill_days ficam
    DESCONHECIDOS (antes: ffill propagava um 0 por buracos arbitrariamente longos).

    Contrafactual = nivel local (dias COM stock, janela centrada) x fator do dia da semana.
    Limitacao assumida: snapshot de fim de dia. Stock 0 no fim do dia nao prova ruptura o dia todo,
    logo a estimativa e um LIMITE SUPERIOR para o dia de inicio da ruptura.
    """
    contract.check_id_overlap(sales, stock, min_overlap=min_overlap, allow_partial=allow_partial)
    daily = sales.groupby(["product_id", "date"])["qty"].sum().unstack(0)
    st = stock.pivot(index="date", columns="product_id", values="stock_qty")
    idx = pd.date_range(min(daily.index.min(), st.index.min()), max(daily.index.max(), st.index.max()))
    daily = daily.reindex(idx).fillna(0)
    st = st.reindex(idx).ffill(limit=max_ffill_days)
    price = (sales.groupby("product_id").apply(lambda g: g["revenue"].sum() / g["qty"].sum(), include_groups=False))
    margin = None
    if "cost" in sales.columns:
        margin = sales.groupby("product_id").apply(
            lambda g: (g["revenue"].sum() - g["cost"].sum()) / g["qty"].sum(), include_groups=False)

    events = []
    for p in daily.columns:
        if p not in st.columns:
            continue
        out = (st[p] <= 0).values            # NaN (stock desconhecido) -> False: nao e ruptura
        known = st[p].notna().values
        if not out.any() or (~out & known).sum() < min_days_in_stock:
            continue
        y = daily[p].values.astype(float)
        ok = np.where(~out & known, y, np.nan)
        dow = idx.dayofweek.values
        dow_f = np.array([np.nanmean(ok[dow == d]) if np.isfinite(ok[dow == d]).any() else np.nan for d in range(7)])
        dow_f = dow_f / np.nanmean(dow_f)
        dow_f = np.nan_to_num(dow_f, nan=1.0)
        deseason = ok / dow_f[dow]
        level = pd.Series(deseason).rolling(window * 2 + 1, center=True, min_periods=7).mean().values
        level = pd.Series(level).ffill().bfill().values
        expected = level * dow_f[dow]
        lost = np.where(out, np.clip(expected - y, 0, None), 0.0)
        # eventos = sequencias consecutivas de ruptura
        i = 0
        while i < len(out):
            if out[i]:
                j = i
                while j + 1 < len(out) and out[j + 1]:
                    j += 1
                dias = j - i + 1
                trunc = dias > max_event_days
                u = float(lost[i:i + min(dias, max_event_days)].sum())
                events.append({"product_id": p, "inicio": idx[i], "fim": idx[j],
                               "dias": dias, "truncado": bool(trunc),
                               "possivel_descontinuado": bool(trunc and j == len(out) - 1),
                               "unid_perdidas": u,
                               "receita_perdida": u * price.get(p, np.nan),
                               "margem_perdida": u * margin.get(p, np.nan) if margin is not None else np.nan})
                i = j + 1
            else:
                i += 1
    ev = pd.DataFrame(events)
    if ev.empty:
        return ev, pd.DataFrame()
    summ = ev.groupby("product_id").agg(dias=("dias", "sum"), unid_perdidas=("unid_perdidas", "sum"),
                                        receita_perdida=("receita_perdida", "sum"),
                                        margem_perdida=("margem_perdida", "sum"),
                                        eventos_truncados=("truncado", "sum"),
                                        possivel_descontinuado=("possivel_descontinuado", "max"))
    return ev, summ.sort_values("receita_perdida", ascending=False)


# ----------------------------------------------------------------------------------------
# 2. DESVIOS: PVM (preco / volume / mix)
# ----------------------------------------------------------------------------------------
def _span_days(df):
    return int((df["date"].max() - df["date"].min()).days + 1) if ("date" in df.columns and len(df)) else None


def pvm(cur: pd.DataFrame, ref: pd.DataFrame, by="product_id", per_day=False, days_cur=None, days_ref=None):
    """Decomposicao exata, fecha POR LINHA e no total:
    Rec1 - Rec0 = Volume + Mix + Preco (novos produtos entram no mix; descontinuados no mix/volume).

    cur/ref: DataFrames com colunas [by, qty, revenue] (ja filtrados ao periodo).
    """
    dc = days_cur or _span_days(cur); dr = days_ref or _span_days(ref)
    if dc and dr and abs(dc - dr) / max(dc, dr) > 0.10:   # v0.4 (OBJ-021)
        if per_day:
            cur = cur.assign(qty=cur["qty"] / dc, revenue=cur["revenue"] / dc)
            ref = ref.assign(qty=ref["qty"] / dr, revenue=ref["revenue"] / dr)
        else:
            warnings.warn(f"pvm: periodos de duracao diferente ({dc} vs {dr} dias): o efeito volume mistura "
                          "duracao com procura. Usar per_day=True (taxas diarias).",
                          contract.DataQualityWarning, stacklevel=2)
    elif per_day and dc and dr:
        cur = cur.assign(qty=cur["qty"] / dc, revenue=cur["revenue"] / dc)
        ref = ref.assign(qty=ref["qty"] / dr, revenue=ref["revenue"] / dr)
    a = cur.groupby(by).agg(q1=("qty", "sum"), r1=("revenue", "sum"))
    b = ref.groupby(by).agg(q0=("qty", "sum"), r0=("revenue", "sum"))
    t = a.join(b, how="outer").fillna(0)
    t["p1"] = np.where(t.q1 > 0, t.r1 / t.q1.replace(0, np.nan), np.nan)
    t["p0"] = np.where(t.q0 > 0, t.r0 / t.q0.replace(0, np.nan), np.nan)
    t["p0"] = t["p0"].fillna(t["p1"])      # novo produto: sem efeito preco
    t["p1"] = t["p1"].fillna(t["p0"])      # produto descontinuado
    Q0, Q1 = t.q0.sum(), t.q1.sum()
    s0 = t.q0 / Q0 if Q0 > 0 else 0.0           # peso de cada produto no periodo de referencia
    t["efeito_preco"] = t.q1 * (t.p1 - t.p0)
    t["efeito_volume"] = (Q1 - Q0) * s0 * t.p0   # variacao do volume total ao mix e precos de referencia
    t["efeito_mix"] = (t.q1 - Q1 * s0) * t.p0    # desvio da composicao face ao mix de referencia
    t["desvio_total"] = t.r1 - t.r0
    chk = (t[["efeito_preco", "efeito_volume", "efeito_mix"]].sum(axis=1) - t["desvio_total"]).abs().max()
    assert chk < 1e-6 * max(1.0, abs(t.r0.sum())), f"PVM nao fecha ({chk})"
    return t.sort_values("desvio_total")


def anomalies(sales: pd.DataFrame, lookback=13, z_thr=3.5):
    """Desvios semanais vs mediana das ultimas N semanas (robusto: MAD, nao desvio-padrao)."""
    s = sales.copy()
    s["week"] = s["date"].dt.to_period("W-SUN").dt.start_time
    w = s.groupby(["product_id", "week"])["revenue"].sum().unstack(0).fillna(0)
    med = w.shift(1).rolling(lookback, min_periods=8).median()
    mad = (w.shift(1) - med).abs().rolling(lookback, min_periods=8).median()
    z = (w - med) / (1.4826 * mad.replace(0, np.nan))
    flag = z.abs() > z_thr
    out = []
    for p in w.columns:
        for t in w.index[flag[p].fillna(False).values]:
            out.append({"product_id": p, "semana": t, "receita": w.loc[t, p],
                        "esperado": med.loc[t, p], "z_robusto": z.loc[t, p]})
    return pd.DataFrame(out)
