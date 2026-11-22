"""Previsão de séries temporais: preparação, análise, modelos, backtesting e intervalos."""
from __future__ import annotations

import warnings
from datetime import date, timedelta
from functools import lru_cache
from typing import Any, Callable, Optional

import numpy as np
import pandas as pd

from .metrics import regression_metrics

FREQ_ALIAS = {"D": "D", "W": "W-SUN", "M": "MS", "H": "h"}
FREQ_LABEL = {"D": "diária", "W": "semanal", "M": "mensal", "H": "horária"}
SEASON = {"D": 7, "W": 52, "M": 12, "H": 24}


# ------------------------------------------------------------------------------ calendário
def _easter(year: int) -> date:
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


@lru_cache(maxsize=64)
def pt_holidays(year: int) -> frozenset[pd.Timestamp]:
    """Feriados nacionais de Portugal (fixos + móveis)."""
    fixed = [(1, 1), (4, 25), (5, 1), (6, 10), (8, 15), (10, 5), (11, 1), (12, 1), (12, 8), (12, 25)]
    easter = _easter(year)
    days = [date(year, m, d) for m, d in fixed] + [easter - timedelta(days=2), easter, easter + timedelta(days=60)]
    return frozenset(pd.Timestamp(d) for d in days)


def is_holiday(dates: pd.DatetimeIndex | pd.Series) -> np.ndarray:
    dates = pd.DatetimeIndex(dates)
    hol: set[pd.Timestamp] = set()
    for y in np.unique(dates.year):
        hol |= pt_holidays(int(y))
    return np.isin(dates.normalize(), list(hol))


# ------------------------------------------------------------------------------ preparação
def detect_freq(dates: pd.Series) -> str:
    d = pd.Series(pd.to_datetime(dates.dropna().unique())).sort_values()
    if len(d) < 3:
        return "D"
    step = d.diff().median()
    if step < pd.Timedelta(hours=20):
        return "H"
    if step <= pd.Timedelta(days=2):
        return "D"
    if step <= pd.Timedelta(days=8):
        return "W"
    return "M"


def prepare_series(df: pd.DataFrame, time_col: str, value_col: Optional[str], agg: str = "sum",
                   series_cols: Optional[list[str]] = None, freq: Optional[str] = None,
                   top_n: int = 8) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Agrega para formato longo [serie, ds, y] com frequência regular."""
    if time_col not in df.columns:
        raise ValueError(f"Coluna temporal inexistente: {time_col}")
    data = df.copy()
    data[time_col] = pd.to_datetime(data[time_col], errors="coerce")
    data = data.dropna(subset=[time_col])
    freq = freq or detect_freq(data[time_col])
    series_cols = [c for c in (series_cols or []) if c in data.columns]
    if series_cols:
        data["__serie__"] = data[series_cols].astype(str).agg(" | ".join, axis=1)
    else:
        data["__serie__"] = "Total"
    if agg == "count" or not value_col or value_col not in data.columns or not pd.api.types.is_numeric_dtype(data[value_col]):
        data["__y__"] = 1.0
        agg_fn = "sum"
        agg = "count"
    else:
        data["__y__"] = pd.to_numeric(data[value_col], errors="coerce")
        agg_fn = "mean" if agg == "mean" else "sum"
    grouped = (data.groupby(["__serie__", pd.Grouper(key=time_col, freq=FREQ_ALIAS[freq])])["__y__"]
               .agg(agg_fn).reset_index().rename(columns={"__serie__": "serie", time_col: "ds", "__y__": "y"}))
    volumes = grouped.groupby("serie")["y"].sum().sort_values(ascending=False)
    kept = volumes.head(top_n).index.tolist()
    dropped = len(volumes) - len(kept)
    grouped = grouped[grouped["serie"].isin(kept)]
    full = []
    for s, g in grouped.groupby("serie"):
        idx = pd.date_range(g["ds"].min(), g["ds"].max(), freq=FREQ_ALIAS[freq])
        g = g.set_index("ds").reindex(idx)
        g["serie"] = s
        g["y"] = g["y"].interpolate(limit_direction="both") if agg == "mean" else g["y"].fillna(0.0)
        full.append(g.rename_axis("ds").reset_index())
    long = pd.concat(full, ignore_index=True)[["serie", "ds", "y"]]
    info = {"freq": freq, "freq_label": FREQ_LABEL[freq], "season": SEASON[freq], "n_series": len(kept),
            "series": kept, "series_dropped": dropped, "aggregation": agg,
            "start": long["ds"].min(), "end": long["ds"].max(),
            "length": int(long.groupby("serie").size().min())}
    return long, info


def analyze(y: np.ndarray, season: int) -> dict[str, float]:
    """Força de tendência e sazonalidade (decomposição STL, Hyndman & Athanasopoulos)."""
    y = np.asarray(y, dtype=float)
    out = {"length": int(len(y)), "zeros_pct": float(np.mean(y == 0)),
           "cv": float(np.std(y) / np.mean(y)) if np.mean(y) else np.nan}
    if len(y) < 2 * season + 2 or season < 2:
        out.update(trend_strength=np.nan, seasonal_strength=np.nan, acf_season=np.nan)
        return out
    from statsmodels.tsa.seasonal import STL

    res = STL(y, period=season, robust=True).fit()
    var_r = np.var(res.resid)
    out["trend_strength"] = float(max(0.0, 1 - var_r / max(np.var(res.trend + res.resid), 1e-12)))
    out["seasonal_strength"] = float(max(0.0, 1 - var_r / max(np.var(res.seasonal + res.resid), 1e-12)))
    yc = y - y.mean()
    denom = float(np.sum(yc ** 2))
    out["acf_season"] = float(np.sum(yc[season:] * yc[:-season]) / denom) if denom else np.nan
    slope = np.polyfit(np.arange(len(y)), y, 1)[0]
    out["trend_per_period_pct"] = float(slope / np.mean(y) * 100) if np.mean(y) else np.nan
    return out


def seasonal_profile(long: pd.DataFrame, freq: str) -> list[dict[str, Any]]:
    d = long.groupby("ds")["y"].sum().reset_index()
    if freq == "D":
        names = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
        g = d.groupby(d["ds"].dt.dayofweek)["y"].mean()
    elif freq in ("W", "M"):
        names = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
        g = d.groupby(d["ds"].dt.month)["y"].mean()
        g.index = g.index - 1
    else:
        names = [f"{h}h" for h in range(24)]
        g = d.groupby(d["ds"].dt.hour)["y"].mean()
    base = g.mean() if g.mean() else 1
    return [{"periodo": names[int(i)], "indice": float(v / base)} for i, v in g.items()]


# ------------------------------------------------------------------------------ modelos locais
def _future_dates(last: pd.Timestamp, h: int, freq: str) -> pd.DatetimeIndex:
    return pd.date_range(last, periods=h + 1, freq=FREQ_ALIAS[freq])[1:]


def seasonal_naive(y: np.ndarray, h: int, season: int) -> np.ndarray:
    season = max(1, min(season, len(y)))
    last = y[-season:]
    return np.array([last[i % season] for i in range(h)], dtype=float)


def holt_winters(y: np.ndarray, h: int, params: dict[str, Any], season: int) -> np.ndarray:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    trend = None if params.get("trend", "add") in ("none", None) else params.get("trend")
    seasonal = None if params.get("seasonal", "add") in ("none", None) else params.get("seasonal")
    sp = int(params.get("seasonal_periods", season) or season)
    if np.any(y <= 0):
        trend = "add" if trend == "mul" else trend
        seasonal = "add" if seasonal == "mul" else seasonal
    if seasonal and len(y) < 2 * sp + 2:
        seasonal = None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = ExponentialSmoothing(y, trend=trend, damped_trend=bool(params.get("damped_trend", True)) if trend else False,
                                     seasonal=seasonal, seasonal_periods=sp if seasonal else None,
                                     initialization_method="estimated")
        fit = model.fit(optimized=True)
        return np.asarray(fit.forecast(h), dtype=float)


def sarima(y: np.ndarray, h: int, params: dict[str, Any], season: int, max_history: int = 400) -> np.ndarray:
    from statsmodels.tsa.statespace.sarimax import SARIMAX

    y = y[-max_history:]
    s = int(params.get("s", season) or 0)
    order = (int(params.get("p", 1)), int(params.get("d", 1)), int(params.get("q", 1)))
    seasonal = (int(params.get("P", 1)), int(params.get("D", 1)), int(params.get("Q", 1)), s) if s > 1 else (0, 0, 0, 0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fit = SARIMAX(y, order=order, seasonal_order=seasonal, enforce_stationarity=False,
                      enforce_invertibility=False).fit(disp=False, maxiter=30)
        return np.asarray(fit.forecast(h), dtype=float)


# ------------------------------------------------------------------------------ modelo global
def _parse_ints(v: Any, default: list[int]) -> list[int]:
    if v is None:
        return default
    if isinstance(v, (list, tuple)):
        return [int(x) for x in v]
    return [int(x) for x in str(v).split(",") if str(x).strip()]


class GBMLags:
    """LightGBM global com lags, médias móveis e calendário; previsão recursiva."""

    def __init__(self, params: dict[str, Any], freq: str):
        self.params = params
        self.freq = freq
        self.lags = sorted(set(_parse_ints(params.get("lags"), [1, 7, 14, 28])))
        self.windows = sorted(set(_parse_ints(params.get("rolling_windows"), [7, 28])))
        self.max_lag = max(self.lags + self.windows)

    def _calendar(self, ds: pd.Series) -> dict[str, np.ndarray]:
        ds = pd.to_datetime(ds)
        cal = {"mes": ds.dt.month.values, "ano_frac": (ds.dt.dayofyear.values / 366.0)}
        if self.freq in ("D", "H"):
            cal.update(dia_semana=ds.dt.dayofweek.values, dia_mes=ds.dt.day.values,
                       fim_mes=ds.dt.is_month_end.values.astype(int), feriado=is_holiday(ds).astype(int))
        if self.freq == "W":
            cal["semana"] = ds.dt.isocalendar().week.values.astype(int)
        if self.freq == "H":
            cal["hora"] = ds.dt.hour.values
        return cal

    def _features(self, hist: np.ndarray, ds: pd.Series, serie_code: int) -> dict[str, Any]:
        row: dict[str, Any] = {f"lag_{l}": hist[-l] if len(hist) >= l else np.nan for l in self.lags}
        for w in self.windows:
            row[f"media_{w}"] = float(np.mean(hist[-w:])) if len(hist) >= 1 else np.nan
        row["serie"] = serie_code
        return row

    def fit(self, long: pd.DataFrame) -> "GBMLags":
        self.series_ = sorted(long["serie"].unique())
        self.codes_ = {s: i for i, s in enumerate(self.series_)}
        self.nonneg_ = bool((long["y"] >= 0).all())
        frames = []
        for s, g in long.groupby("serie"):
            g = g.sort_values("ds")
            y = np.log1p(g["y"].values) if self.nonneg_ else g["y"].values
            yy = pd.Series(y)
            feats = {f"lag_{l}": yy.shift(l).values for l in self.lags}
            for w in self.windows:
                feats[f"media_{w}"] = yy.shift(1).rolling(w, min_periods=1).mean().values
            feats.update(self._calendar(g["ds"]))
            feats["serie"] = self.codes_[s]
            feats["__y__"] = y
            frames.append(pd.DataFrame(feats))
        data = pd.concat(frames, ignore_index=True).dropna(subset=[f"lag_{min(self.lags)}"])
        self.columns_ = [c for c in data.columns if c != "__y__"]
        X, yv = data[self.columns_], data["__y__"].values
        try:
            import lightgbm as lgb

            self.model_ = lgb.LGBMRegressor(n_estimators=int(self.params.get("n_estimators", 400)),
                                            learning_rate=float(self.params.get("learning_rate", 0.05)),
                                            num_leaves=int(self.params.get("num_leaves", 31)),
                                            min_child_samples=10, subsample=0.9, subsample_freq=1,
                                            colsample_bytree=0.9, verbosity=-1, random_state=42)
            self.model_.fit(X, yv, categorical_feature=["serie"])
        except ImportError:  # pragma: no cover - fallback sem LightGBM
            from sklearn.ensemble import HistGradientBoostingRegressor

            self.model_ = HistGradientBoostingRegressor(max_iter=int(self.params.get("n_estimators", 400)),
                                                        learning_rate=float(self.params.get("learning_rate", 0.05)))
            self.model_.fit(X.fillna(-1), yv)
        self.history_ = {s: (np.log1p(g.sort_values("ds")["y"].values) if self.nonneg_ else g.sort_values("ds")["y"].values)
                         for s, g in long.groupby("serie")}
        self.last_ = {s: g["ds"].max() for s, g in long.groupby("serie")}
        return self

    def predict(self, h: int) -> pd.DataFrame:
        hist = {s: list(v) for s, v in self.history_.items()}
        out = []
        future = {s: _future_dates(self.last_[s], h, self.freq) for s in self.series_}
        for step in range(h):
            rows, keys = [], []
            for s in self.series_:
                arr = np.array(hist[s])
                feats = self._features(arr, None, self.codes_[s])
                ds = pd.Series([future[s][step]])
                feats.update({k: v[0] for k, v in self._calendar(ds).items()})
                rows.append(feats)
                keys.append(s)
            X = pd.DataFrame(rows)[self.columns_]
            pred = self.model_.predict(X)
            for s, p in zip(keys, pred):
                hist[s].append(float(p))
                val = float(np.expm1(p)) if self.nonneg_ else float(p)
                out.append({"serie": s, "ds": future[s][step], "yhat": max(val, 0.0) if self.nonneg_ else val})
        return pd.DataFrame(out)

    def importance(self) -> list[dict[str, Any]]:
        imp = getattr(self.model_, "feature_importances_", None)
        if imp is None:
            return []
        total = float(np.sum(imp)) or 1.0
        return sorted(({"variavel": c, "importancia": float(v) / total} for c, v in zip(self.columns_, imp)),
                      key=lambda d: -d["importancia"])


# ------------------------------------------------------------------------------ execução
def forecast(model_id: str, params: dict[str, Any], long: pd.DataFrame, h: int, freq: str,
             season: int) -> pd.DataFrame:
    if model_id == "gbm_lags":
        return GBMLags(params, freq).fit(long).predict(h)
    rows = []
    for s, g in long.groupby("serie"):
        g = g.sort_values("ds")
        y = g["y"].values.astype(float)
        if model_id == "seasonal_naive":
            yhat = seasonal_naive(y, h, int(params.get("season_length", season) or season))
        elif model_id == "holt_winters":
            try:
                yhat = holt_winters(y, h, params, season)
            except Exception:  # noqa: BLE001 - série difícil → naive
                yhat = seasonal_naive(y, h, season)
        elif model_id == "sarima":
            try:
                yhat = sarima(y, h, params, season)
            except Exception:  # noqa: BLE001
                yhat = seasonal_naive(y, h, season)
        else:
            raise ValueError(f"Modelo de previsão desconhecido: {model_id}")
        if (y >= 0).all():
            yhat = np.maximum(yhat, 0)
        for d, v in zip(_future_dates(g["ds"].max(), h, freq), yhat):
            rows.append({"serie": s, "ds": d, "yhat": float(v)})
    return pd.DataFrame(rows)


def backtest(models: dict[str, dict[str, Any]], long: pd.DataFrame, h: int, freq: str, season: int,
             folds: int = 3, progress: Optional[Callable[[float, str], None]] = None) -> dict[str, Any]:
    length = int(long.groupby("serie").size().min())
    max_folds = max(1, (length - 2 * season - h) // h)
    folds = max(1, min(folds, max_folds))
    last = long["ds"].max()
    step = pd.tseries.frequencies.to_offset(FREQ_ALIAS[freq])
    preds, scores = [], {}
    total = len(models) * folds
    done = 0
    for mid, params in models.items():
        fold_rows = []
        for k in range(folds, 0, -1):
            cutoff = last - step * (h * k)
            train = long[long["ds"] <= cutoff]
            test = long[(long["ds"] > cutoff) & (long["ds"] <= cutoff + step * h)]
            if progress:
                progress(done / max(total, 1), f"Backtesting {mid} (origem {pd.Timestamp(cutoff).date()})")
            fc = forecast(mid, params, train, h, freq, season)
            merged = test.merge(fc, on=["serie", "ds"], how="inner")
            merged["modelo"], merged["fold"] = mid, folds - k + 1
            merged["passo"] = merged.groupby("serie").cumcount() + 1
            # escala MASE por série
            scale = {}
            for s, g in train.groupby("serie"):
                yv = g.sort_values("ds")["y"].values
                scale[s] = np.mean(np.abs(yv[season:] - yv[:-season])) if len(yv) > season else np.nan
            merged["mase_scale"] = merged["serie"].map(scale)
            fold_rows.append(merged)
            done += 1
        allp = pd.concat(fold_rows, ignore_index=True)
        preds.append(allp)
        m = regression_metrics(allp["y"].values, allp["yhat"].values)
        mase_vals = (allp.groupby("serie").apply(lambda g: np.mean(np.abs(g["y"] - g["yhat"])) / g["mase_scale"].iloc[0]
                                                 if g["mase_scale"].iloc[0] else np.nan, include_groups=False))
        m["mase"] = float(np.nanmean(mase_vals)) if len(mase_vals) else np.nan
        scores[mid] = m
    return {"folds": folds, "scores": scores, "predictions": pd.concat(preds, ignore_index=True) if preds else pd.DataFrame()}


def intervals(bt_preds: pd.DataFrame, model_id: str, h: int, lower_q: float = 0.1,
              upper_q: float = 0.9) -> tuple[np.ndarray, np.ndarray]:
    p = bt_preds[bt_preds["modelo"] == model_id]
    rel = (p["y"] - p["yhat"]) / np.maximum(np.abs(p["yhat"]), 1e-9)
    lo, hi = np.full(h, rel.quantile(lower_q) if len(rel) else -0.2), np.full(h, rel.quantile(upper_q) if len(rel) else 0.2)
    for step in range(1, h + 1):
        r = rel[p["passo"].between(max(1, step - 2), step + 2)]
        if len(r) >= 20:
            lo[step - 1], hi[step - 1] = r.quantile(lower_q), r.quantile(upper_q)
    return np.clip(lo, -0.95, 0), np.clip(hi, 0, 5)
