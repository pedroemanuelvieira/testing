"""Métricas técnicas e de negócio, curvas e escolha de limiar."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
import pandas as pd
from sklearn import metrics as skm


@dataclass(frozen=True)
class MetricInfo:
    id: str
    name: str
    direction: str  # max | min
    term: Optional[str]
    fmt: str  # pct | num | money
    scorer: Optional[str] = None  # scorer do scikit-learn para validação cruzada


METRICS: dict[str, MetricInfo] = {m.id: m for m in [
    MetricInfo("roc_auc", "AUC-ROC", "max", "auc_roc", "num", "roc_auc"),
    MetricInfo("pr_auc", "PR-AUC", "max", "pr_auc", "num", "average_precision"),
    MetricInfo("f1", "F1", "max", "f1_score", "num", "f1"),
    MetricInfo("precision", "Precisão", "max", "precisao", "pct", "precision"),
    MetricInfo("recall", "Recall", "max", "recall", "pct", "recall"),
    MetricInfo("accuracy", "Accuracy", "max", "accuracy", "pct", "accuracy"),
    MetricInfo("balanced_accuracy", "Balanced accuracy", "max", "balanced_accuracy", "pct", "balanced_accuracy"),
    MetricInfo("log_loss", "Log loss", "min", "log_loss", "num", "neg_log_loss"),
    MetricInfo("brier", "Brier", "min", "brier_score", "num", "neg_brier_score"),
    MetricInfo("mcc", "MCC", "max", "mcc", "num", "matthews_corrcoef"),
    MetricInfo("ks", "KS", "max", "ks_estatistica", "num", None),
    MetricInfo("gini", "Gini", "max", "gini", "num", None),
    MetricInfo("lift_top_decile", "Lift 1.º decil", "max", "lift", "num", None),
    MetricInfo("f1_macro", "F1-macro", "max", "f1_score", "num", "f1_macro"),
    MetricInfo("f1_weighted", "F1-weighted", "max", "f1_score", "num", "f1_weighted"),
    MetricInfo("mae", "MAE", "min", "mae", "num", "neg_mean_absolute_error"),
    MetricInfo("rmse", "RMSE", "min", "rmse", "num", "neg_root_mean_squared_error"),
    MetricInfo("r2", "R²", "max", "r2", "num", "r2"),
    MetricInfo("mape", "MAPE", "min", "mape", "pct", None),
    MetricInfo("smape", "sMAPE", "min", "smape", "pct", None),
    MetricInfo("wape", "WAPE", "min", "wape", "pct", None),
    MetricInfo("mase", "MASE", "min", "mase", "num", None),
    MetricInfo("bias", "Bias", "min", "bias_previsao", "pct", None),
    MetricInfo("silhouette", "Silhueta", "max", "silhueta", "num", None),
    MetricInfo("davies_bouldin", "Davies-Bouldin", "min", "davies_bouldin", "num", None),
    MetricInfo("calinski_harabasz", "Calinski-Harabasz", "max", "davies_bouldin", "num", None),
    MetricInfo("precision_at_k", "Precisão no top-k", "max", "precision_at_k", "pct", None),
    MetricInfo("recall_at_k", "Recall no top-k", "max", "recall", "pct", None),
    MetricInfo("lift", "Lift", "max", "lift_associacao", "num", None),
    MetricInfo("support", "Suporte", "max", "suporte", "pct", None),
    MetricInfo("confidence", "Confiança", "max", "confianca", "pct", None),
]}


def metric_info(metric_id: str) -> MetricInfo:
    return METRICS.get(metric_id, MetricInfo(metric_id, metric_id, "max", None, "num"))


def better(metric_id: str, a: float, b: float) -> bool:
    return a > b if metric_info(metric_id).direction == "max" else a < b


def cv_scorer(metric_id: str, task: str) -> str:
    info = metric_info(metric_id)
    if info.scorer:
        return info.scorer
    return {"binary_classification": "roc_auc", "multiclass_classification": "f1_macro"}.get(task, "neg_mean_absolute_error")


def from_cv_score(metric_id: str, value: float) -> float:
    """Os scorers 'neg_*' do scikit-learn devolvem valores negativos."""
    scorer = metric_info(metric_id).scorer or ""
    return -value if scorer.startswith("neg_") else value


# ------------------------------------------------------------------------------ classificação
def ks_statistic(y: np.ndarray, p: np.ndarray) -> float:
    fpr, tpr, _ = skm.roc_curve(y, p)
    return float(np.max(tpr - fpr))


def lift_table(y: np.ndarray, p: np.ndarray, bins: int = 10) -> pd.DataFrame:
    df = pd.DataFrame({"y": y, "p": p}).sort_values("p", ascending=False).reset_index(drop=True)
    df["decil"] = (np.arange(len(df)) * bins // max(len(df), 1)) + 1
    base = df["y"].mean() if len(df) else 0
    g = df.groupby("decil").agg(n=("y", "size"), positivos=("y", "sum"), taxa=("y", "mean"), score_medio=("p", "mean"))
    g["lift"] = g["taxa"] / base if base else np.nan
    g["ganho_acumulado"] = g["positivos"].cumsum() / max(df["y"].sum(), 1)
    g["pct_base"] = g["n"].cumsum() / len(df)
    return g.reset_index()


def binary_metrics(y: np.ndarray, p: np.ndarray, threshold: float = 0.5) -> dict[str, float]:
    y = np.asarray(y).astype(int)
    pred = (p >= threshold).astype(int)
    out = {
        "roc_auc": skm.roc_auc_score(y, p) if len(np.unique(y)) > 1 else np.nan,
        "pr_auc": skm.average_precision_score(y, p) if y.sum() > 0 else np.nan,
        "f1": skm.f1_score(y, pred, zero_division=0),
        "precision": skm.precision_score(y, pred, zero_division=0),
        "recall": skm.recall_score(y, pred, zero_division=0),
        "accuracy": skm.accuracy_score(y, pred),
        "balanced_accuracy": skm.balanced_accuracy_score(y, pred),
        "log_loss": skm.log_loss(y, np.clip(p, 1e-6, 1 - 1e-6), labels=[0, 1]),
        "brier": skm.brier_score_loss(y, p),
        "mcc": skm.matthews_corrcoef(y, pred),
    }
    if len(np.unique(y)) > 1:
        out["ks"] = ks_statistic(y, p)
        out["gini"] = 2 * out["roc_auc"] - 1
        lt = lift_table(y, p)
        out["lift_top_decile"] = float(lt["lift"].iloc[0]) if len(lt) else np.nan
    return {k: float(v) for k, v in out.items()}


def multiclass_metrics(y: np.ndarray, proba: np.ndarray, classes: list[Any]) -> dict[str, float]:
    pred = np.asarray(classes)[np.argmax(proba, axis=1)]
    out = {
        "f1_macro": skm.f1_score(y, pred, average="macro", zero_division=0),
        "f1_weighted": skm.f1_score(y, pred, average="weighted", zero_division=0),
        "accuracy": skm.accuracy_score(y, pred),
        "balanced_accuracy": skm.balanced_accuracy_score(y, pred),
        "log_loss": skm.log_loss(y, np.clip(proba, 1e-9, 1), labels=classes),
    }
    try:
        out["roc_auc"] = skm.roc_auc_score(y, proba, multi_class="ovr", labels=classes)
    except ValueError:
        pass
    return {k: float(v) for k, v in out.items()}


def roc_points(y: np.ndarray, p: np.ndarray, n: int = 60) -> list[dict[str, float]]:
    fpr, tpr, thr = skm.roc_curve(y, p)
    idx = np.unique(np.linspace(0, len(fpr) - 1, min(n, len(fpr))).astype(int))
    return [{"fpr": float(fpr[i]), "tpr": float(tpr[i]), "aleatorio": float(fpr[i])} for i in idx]


def pr_points(y: np.ndarray, p: np.ndarray, n: int = 60) -> list[dict[str, float]]:
    prec, rec, _ = skm.precision_recall_curve(y, p)
    idx = np.unique(np.linspace(0, len(prec) - 1, min(n, len(prec))).astype(int))
    base = float(np.mean(y))
    return sorted(({"recall": float(rec[i]), "precisao": float(prec[i]), "base": base} for i in idx),
                  key=lambda d: d["recall"])


def calibration_points(y: np.ndarray, p: np.ndarray, bins: int = 10) -> list[dict[str, float]]:
    df = pd.DataFrame({"y": y, "p": p})
    df["bin"] = pd.qcut(df["p"], q=bins, duplicates="drop")
    g = df.groupby("bin", observed=True).agg(previsto=("p", "mean"), observado=("y", "mean"), n=("y", "size"))
    return [{"previsto": float(r.previsto), "observado": float(r.observado), "perfeito": float(r.previsto),
             "n": int(r.n)} for r in g.itertuples()]


def threshold_sweep(y: np.ndarray, p: np.ndarray, costs: Optional[dict[str, float]] = None,
                    steps: int = 99) -> pd.DataFrame:
    y = np.asarray(y).astype(int)
    rows = []
    for t in np.linspace(0.01, 0.99, steps):
        pred = p >= t
        tp = int(np.sum(pred & (y == 1)))
        fp = int(np.sum(pred & (y == 0)))
        fn = int(np.sum(~pred & (y == 1)))
        tn = int(np.sum(~pred & (y == 0)))
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        row = {"limiar": round(float(t), 2), "precisao": prec, "recall": rec, "f1": f1, "vp": tp, "fp": fp,
               "fn": fn, "vn": tn, "sinalizados": tp + fp, "pct_sinalizados": (tp + fp) / len(y)}
        if costs:
            # valor líquido face a "não agir": ganho nos VP menos o custo de agir sobre FP
            row["lucro"] = tp * costs.get("benefit_tp", 0) - fp * costs.get("cost_fp", 0)
            row["valor_por_captar"] = fn * costs.get("cost_fn", 0)
        rows.append(row)
    return pd.DataFrame(rows)


def best_threshold(sweep: pd.DataFrame, costs: Optional[dict[str, float]]) -> tuple[float, str]:
    if costs and "lucro" in sweep and (costs.get("cost_fp") or costs.get("benefit_tp")):
        row = sweep.loc[sweep["lucro"].idxmax()]
        return float(row["limiar"]), "máximo lucro esperado (matriz de custo-benefício)"
    row = sweep.loc[sweep["f1"].idxmax()]
    return float(row["limiar"]), "máximo F1 (sem custos de negócio definidos)"


# ------------------------------------------------------------------------------ regressão
def regression_metrics(y: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    y = np.asarray(y, dtype=float)
    pred = np.asarray(pred, dtype=float)
    err = pred - y
    nz = np.abs(y) > 1e-9
    out = {
        "mae": float(np.mean(np.abs(err))),
        "rmse": float(np.sqrt(np.mean(err ** 2))),
        "r2": float(skm.r2_score(y, pred)) if len(y) > 1 else np.nan,
        "mape": float(np.mean(np.abs(err[nz]) / np.abs(y[nz]))) if nz.any() else np.nan,
        "smape": float(np.mean(2 * np.abs(err) / np.maximum(np.abs(y) + np.abs(pred), 1e-9))),
        "wape": float(np.sum(np.abs(err)) / max(np.sum(np.abs(y)), 1e-9)),
        "bias": float(np.sum(err) / max(np.sum(np.abs(y)), 1e-9)),
        "medae": float(np.median(np.abs(err))),
    }
    return out


def mase(y: np.ndarray, pred: np.ndarray, history: np.ndarray, season: int) -> float:
    history = np.asarray(history, dtype=float)
    if len(history) <= season:
        return np.nan
    scale = np.mean(np.abs(history[season:] - history[:-season]))
    return float(np.mean(np.abs(np.asarray(pred) - np.asarray(y))) / scale) if scale > 0 else np.nan


def format_metric(metric_id: str, value: Any) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "—"
    info = metric_info(metric_id)
    if info.fmt == "pct":
        return f"{100 * value:.1f}%".replace(".", ",")
    return f"{value:,.3f}".replace(",", " ").replace(".", ",")
