"""Previsao de procura com backtest rolling-origin e escolha do modelo por produto.

Metodo: diario -> semanal (menos ruido). Candidatos: naive sazonal, media movel,
Croston/SBA (intermitente) e GBM com lags + sazonalidade. Escolha por WAPE em backtest.
Intervalos por quantis dos residuos do backtest (empiricos, nao assumem normalidade).
"""
from __future__ import annotations
import warnings
import numpy as np
import pandas as pd
from .contract import DataQualityWarning
from sklearn.ensemble import HistGradientBoostingRegressor


def weekly_demand(sales, stock=None):
    """Procura semanal por produto. Se houver stock, semanas com ruptura sao marcadas
    (a procura observada subestima a verdadeira)."""
    s = sales.copy()
    s["week"] = s["date"].dt.to_period("W-SUN").dt.start_time
    d = s.groupby(["product_id", "week"])["qty"].sum().unstack(0).fillna(0)
    full = pd.date_range(d.index.min(), d.index.max(), freq="7D")
    d = d.reindex(full).fillna(0)
    cens = None
    if stock is not None:
        st = stock.copy()
        st["week"] = st["date"].dt.to_period("W-SUN").dt.start_time
        z = st.assign(z=(st.stock_qty <= 0).astype(int)).groupby(["product_id", "week"])["z"].sum()
        cens = (z.unstack(0).reindex(full).fillna(0) > 0)
    return d, cens


def croston_sba(y, alpha=0.1):
    y = np.asarray(y, float)
    nz = np.flatnonzero(y > 0)
    if len(nz) == 0:
        return 0.0
    z, p, q = y[nz[0]], nz[0] + 1.0, 1
    for t in range(nz[0] + 1, len(y)):
        if y[t] > 0:
            z += alpha * (y[t] - z)
            p += alpha * (q - p)
            q = 1
        else:
            q += 1
    return float((1 - alpha / 2) * z / max(p, 1.0))


def _gbm_fit_predict(y_train, h, season=52):
    y = np.asarray(y_train, float)
    n = len(y)
    L = [1, 2, 3, 4, 8, 13, 26, 52]
    maxlag = max(L)
    if n < maxlag + 20:
        L = [l for l in L if l < n - 20] or [1]
        maxlag = max(L)
    def feats(hist, t):
        row = [hist[t - l] for l in L]
        row += [np.mean(hist[max(0, t - 4):t]), np.mean(hist[max(0, t - 13):t])]
        row += [np.sin(2 * np.pi * t / season), np.cos(2 * np.pi * t / season)]
        return row
    X = np.array([feats(y, t) for t in range(maxlag, n)])
    Y = y[maxlag:n]
    m = HistGradientBoostingRegressor(loss="poisson" if (Y >= 0).all() else "squared_error",
                                      max_depth=3, learning_rate=0.06, max_iter=150,
                                      l2_regularization=1.0, random_state=0)
    m.fit(X, Y)
    hist = list(y)
    for _ in range(h):  # previsao recursiva
        t = len(hist)
        hist.append(float(max(m.predict(np.array([feats(np.array(hist), t)]))[0], 0)))
    return np.array(hist[n:])


def _predict(method, train, h):
    if method == "naive_sazonal":
        if len(train) >= 52:
            return np.array([train[-52 + (i % 52)] for i in range(h)])
        return np.repeat(train[-4:].mean(), h)
    if method == "media_13s":
        return np.repeat(train[-13:].mean(), h)
    if method == "croston_sba":
        return np.repeat(croston_sba(train), h)
    if method == "gbm":
        return _gbm_fit_predict(train, h)
    raise KeyError(method)


METHODS = ["naive_sazonal", "media_13s", "croston_sba", "gbm"]


def wape(y, f):
    y, f = np.asarray(y), np.asarray(f)
    return float(np.abs(y - f).sum() / max(np.abs(y).sum(), 1e-9))


def backtest(series, h=4, n_folds=4, step=4, methods=METHODS, fold_errors=None):
    """Media do WAPE por dobra. v0.9: se `fold_errors` (dict) for dado, recebe o WAPE de cada dobra por metodo."""
    y = np.asarray(series, float)
    err = {m: [] for m in methods}
    resid = {m: [] for m in methods}
    for k in range(n_folds, 0, -1):
        cut = len(y) - h - (k - 1) * step
        if cut < 30:
            continue
        for m in methods:
            try:
                f = _predict(m, y[:cut], h)
            except Exception:
                continue
            err[m].append(wape(y[cut:cut + h], f))
            resid[m].extend(list(y[cut:cut + h] - f))
    score = {m: float(np.mean(v)) for m, v in err.items() if v}
    if fold_errors is not None:
        fold_errors.update({m: list(v) for m, v in err.items()})
    return score, resid


def _conformal_bounds(r, lo_q=0.1, hi_q=0.9):
    """Quantis com correcao de amostra finita (conformal split): com poucos residuos,
    np.quantile(0.1/0.9) subcobre. Grok v0.3: cobertura medida 0,558 vs nominal 0,80 na v0.2."""
    r = np.sort(np.asarray(r, float))
    n = len(r)
    if n == 0:
        return 0.0, 0.0
    k_hi = min(n, int(np.ceil((n + 1) * hi_q))) - 1
    k_lo = max(0, int(np.floor((n + 1) * lo_q)) - 1)
    return float(r[k_lo]), float(r[k_hi])


POLICIES = ("baseline", "guarded", "adaptive")


def forecast_all(sales, stock=None, h=8, min_weeks=60, min_gain=0.05, n_folds=8, selection_policy="baseline",
                 guarded_gain=0.15, guarded_fold_share=2 / 3):
    """Forecast with baseline default (v0.8, OBJ-032).

    baseline: always mean of last 13 prepared weeks; no model selection advantage claimed.
    adaptive: explicit experimental selection, using requested horizon h on training folds.
    guarded (v0.9, Grok, OBJ-032): candidate replaces media_13s only if its mean backtest WAPE is at least
    `guarded_gain` (15%) better AND it beats media_13s in at least `guarded_fold_share` (2/3) of the folds.
    Measured at H=8 (4 origins, gap 4): null worlds (seeds 7/11) WAPE identical to baseline (0.4612/0.4525,
    switches in 2%/0% of series) while adaptive is ~1% worse (0.4652/0.4585); signal worlds (make_signal
    seeds 1/2) 0.182/0.220 vs baseline 0.396/0.367. Not the default: baseline stays default until all 3 reviewers agree.
    Holdout is disjoint from selection, with censored targets excluded. Empirical residual
    bounds are pooled across horizons and are not a universal coverage guarantee.
    """
    if selection_policy not in POLICIES:
        raise ValueError("selection_policy deve ser baseline, guarded ou adaptive")
    if not isinstance(h, int) or h < 1:
        raise ValueError("h deve ser inteiro positivo")
    d, cens = weekly_demand(sales, stock)
    rows, omitidos = [], {}
    for p in d.columns:
        y_obs = d[p].values.copy()
        c = cens[p].values if (cens is not None and p in cens.columns) else np.zeros(len(y_obs), bool)
        if y_obs.sum() == 0:
            omitidos[p] = "sem vendas"; continue
        # v0.4 (OBJ-022): semanas antes da 1.a venda sao pre-lancamento, nao procura nula
        first = int(np.argmax(y_obs > 0))
        y_obs, c = y_obs[first:], c[first:]
        if len(y_obs) < min_weeks:
            omitidos[p] = f"historico {len(y_obs)} semanas < {min_weeks} (desde a 1.a venda)"; continue
        y = y_obs.copy()
        if c.any():
            base = pd.Series(np.where(c, np.nan, y)).shift(1).rolling(8, min_periods=2).mean().values
            y = np.where(c & ~np.isnan(base), base, y)
        hold = h
        fe = {}
        score, resid = backtest(y[:-hold], h=hold, n_folds=n_folds,
                                methods=["media_13s"] if selection_policy == "baseline" else METHODS, fold_errors=fe)
        if not score or "media_13s" not in score:
            omitidos[p] = "backtest sem dobras validas"; continue
        cand = min(score, key=score.get)
        ref = score["media_13s"]
        if selection_policy == "adaptive":
            best = cand if score[cand] <= (1 - min_gain) * ref else "media_13s"
        elif selection_policy == "guarded" and cand != "media_13s":
            wins = np.mean(np.asarray(fe[cand]) < np.asarray(fe["media_13s"]))
            best = cand if (score[cand] <= (1 - guarded_gain) * ref and wins >= guarded_fold_share) else "media_13s"
        else:
            best = "media_13s"
        mask = ~c[-hold:]
        if mask.any():
            holdout_wape = wape(y_obs[-hold:][mask], _predict(best, y[:-hold], hold)[mask])
            holdout_baseline = wape(y_obs[-hold:][mask], _predict("media_13s", y[:-hold], hold)[mask])
        else:
            holdout_wape = holdout_baseline = np.nan
        f = _predict(best, y, h)
        r = np.array(resid[best]) if resid[best] else np.array([0.0])
        lo, hi = _conformal_bounds(r)
        for i in range(h):
            rows.append({"product_id": p, "week_ahead": i + 1,
                         "forecast": float(max(f[i], 0)),
                         "p10": float(max(f[i] + lo, 0)), "p90": float(max(f[i] + hi, 0)),
                         "method": best, "selection_policy": selection_policy, "selection_horizon": hold, "candidato_backtest": cand,
                         "wape_holdout": holdout_wape,
                         "wape_holdout_media_13s": holdout_baseline, "wape_backtest": score[best],
                         "wape_media_13s": ref, "semanas_holdout_censuradas": int((~mask).sum())})
    out = pd.DataFrame(rows)
    out.attrs["omitidos"] = omitidos      # produto -> motivo (nunca devolver tabela vazia sem explicar)
    if omitidos:
        motivos = pd.Series(omitidos).str.replace(r"\d+", "N", regex=True).value_counts().to_dict()
        warnings.warn(f"previsao: {len(omitidos)} produtos sem previsao ({motivos}). Ver attrs['omitidos'].",
                      DataQualityWarning, stacklevel=2)
    return out
