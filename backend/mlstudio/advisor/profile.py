"""Perfil quantitativo dos dados usado pelo Conselheiro de Hiperparâmetros."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

import numpy as np
import pandas as pd

from ..ml.semantic import infer_roles


def imbalance_level(pos_rate: Optional[float]) -> str:
    if pos_rate is None:
        return "nenhum"
    minority = min(pos_rate, 1 - pos_rate)
    if minority < 0.02:
        return "extremo"
    if minority < 0.10:
        return "forte"
    if minority < 0.30:
        return "moderado"
    return "nenhum"


@dataclass
class DataProfile:
    n_rows: int = 10_000
    n_features: int = 20
    n_numeric: int = 15
    n_categorical: int = 5
    max_cardinality: int = 10
    missing_rate: float = 0.0
    task: str = "binary_classification"
    positive_rate: Optional[float] = None
    n_classes: Optional[int] = None
    imbalance: str = "nenhum"
    skewed_share: float = 0.0
    target_skew: Optional[float] = None
    target_std: Optional[float] = None
    max_abs_corr: Optional[float] = None
    # séries temporais
    freq: Optional[str] = None
    season_length: Optional[int] = None
    n_series: Optional[int] = None
    series_length: Optional[int] = None
    trend_strength: Optional[float] = None
    seasonal_strength: Optional[float] = None
    has_zeros: Optional[bool] = None
    # não supervisionado
    suggested_k: Optional[int] = None
    dbscan_eps: Optional[float] = None
    expected_anomaly_rate: Optional[float] = None
    n_transactions: Optional[int] = None
    n_items: Optional[int] = None
    source: str = "manual"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DataProfile":
        known = {k: v for k, v in (d or {}).items() if k in cls.__dataclass_fields__}
        prof = cls(**known)
        if prof.positive_rate is not None and "imbalance" not in (d or {}):
            prof.imbalance = imbalance_level(prof.positive_rate)
        return prof

    @property
    def positives(self) -> Optional[int]:
        if self.positive_rate is None:
            return None
        return int(round(min(self.positive_rate, 1 - self.positive_rate) * self.n_rows))


def profile_from_frame(df: pd.DataFrame, task: str, target: Optional[str] = None,
                       exclude: Optional[list[str]] = None, positive_class: Any = None,
                       features: Optional[list[str]] = None) -> DataProfile:
    exclude = set(exclude or [])
    roles = infer_roles(df, target=target)
    feats = features or [c for c, r in roles.items()
                         if r in ("numeric", "boolean", "categorical", "datetime") and c not in exclude and c != target]
    feats = [c for c in feats if c in df.columns]
    num = [c for c in feats if roles.get(c) in ("numeric", "boolean")]
    cat = [c for c in feats if roles.get(c) == "categorical"]
    prof = DataProfile(n_rows=int(len(df)), n_features=len(feats), n_numeric=len(num), n_categorical=len(cat),
                       max_cardinality=int(max([df[c].nunique() for c in cat], default=0)),
                       missing_rate=float(df[feats].isna().mean().mean()) if feats else 0.0, task=task,
                       source="projeto")
    skewed = [c for c in num if roles.get(c) == "numeric" and abs(df[c].astype(float).skew()) > 1]
    prof.skewed_share = len(skewed) / max(len(num), 1)
    if len(num) >= 2:
        corr = df[num[:40]].astype(float).corr(method="spearman").abs().to_numpy(copy=True)
        np.fill_diagonal(corr, 0)
        prof.max_abs_corr = float(np.nanmax(corr)) if corr.size else None
    if target and target in df.columns:
        y = df[target].dropna()
        if task == "binary_classification":
            pos = positive_class if positive_class is not None else _guess_positive(y)
            prof.positive_rate = float((y.astype(str) == str(pos)).mean())
            prof.n_classes = 2
            prof.imbalance = imbalance_level(prof.positive_rate)
        elif task == "multiclass_classification":
            vc = y.value_counts(normalize=True)
            prof.n_classes = int(len(vc))
            prof.positive_rate = float(vc.min())
            prof.imbalance = imbalance_level(prof.positive_rate) if len(vc) == 2 else (
                "forte" if vc.min() < 0.05 else "moderado" if vc.min() < 0.15 else "nenhum")
        elif task == "regression":
            yv = pd.to_numeric(y, errors="coerce").dropna()
            prof.target_skew = float(yv.skew())
            prof.target_std = float(yv.std())
    return prof


def _guess_positive(y: pd.Series) -> Any:
    vals = list(pd.unique(y))
    for v in vals:
        if str(v).lower() in ("1", "true", "sim", "yes", "1.0"):
            return v
    vc = y.value_counts()
    return vc.index[-1]
