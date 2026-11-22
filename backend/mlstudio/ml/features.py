"""Engenharia de features reprodutível (transformador scikit-learn).

O ``FeatureBuilder`` é o primeiro passo de todos os pipelines treinados: recebe
as colunas *originais* do Power BI e aplica o plano de features (datas →
componentes, log de variáveis assimétricas, rácios, remoção de colunas). Assim
o mesmo objeto serve para treino e scoring, sem risco de divergência.
"""
from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin

MISSING = "__em_falta__"


def default_plan() -> dict[str, Any]:
    return {"drop": [], "datetime": [], "log": [], "ratios": [], "categorical": [], "numeric": []}


class FeatureBuilder(BaseEstimator, TransformerMixin):
    def __init__(self, plan: Optional[dict[str, Any]] = None):
        self.plan = plan

    # ------------------------------------------------------------------ sklearn
    def fit(self, X: pd.DataFrame, y: Any = None) -> "FeatureBuilder":
        plan = {**default_plan(), **(self.plan or {})}
        self.plan_ = plan
        self.input_columns_ = [c for c in X.columns if c not in set(plan["drop"])]
        self.raw_types_ = {c: ("dt" if pd.api.types.is_datetime64_any_dtype(X[c]) or c in plan["datetime"] else
                               "num" if pd.api.types.is_numeric_dtype(X[c]) else "cat") for c in X.columns}
        ref = None
        for c in plan["datetime"]:
            if c in X.columns:
                d = pd.to_datetime(X[c], errors="coerce")
                m = d.max()
                if pd.notna(m) and (ref is None or m > ref):
                    ref = m
        self.reference_date_ = ref
        out = self._transform(X)
        self.feature_names_out_ = list(out.columns)
        self.categorical_ = [c for c in out.columns if not pd.api.types.is_numeric_dtype(out[c])]
        self.numeric_ = [c for c in out.columns if c not in self.categorical_]
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        out = self._transform(X)
        for c in self.feature_names_out_:
            if c not in out.columns:
                out[c] = np.nan if c in self.numeric_ else MISSING
        return out[self.feature_names_out_]

    def get_feature_names_out(self, input_features: Any = None) -> np.ndarray:
        return np.array(self.feature_names_out_, dtype=object)

    # ------------------------------------------------------------------ lógica
    def _transform(self, X: pd.DataFrame) -> pd.DataFrame:
        plan = getattr(self, "plan_", None) or {**default_plan(), **(self.plan or {})}
        df = X.copy()
        for c, kind in getattr(self, "raw_types_", {}).items():  # impõe os tipos vistos no treino (scoring robusto)
            if c not in df.columns:
                continue
            if kind == "num" and not pd.api.types.is_numeric_dtype(df[c]):
                df[c] = pd.to_numeric(df[c], errors="coerce")
            elif kind == "dt" and not pd.api.types.is_datetime64_any_dtype(df[c]):
                df[c] = pd.to_datetime(df[c], errors="coerce")
        drop = set(plan["drop"])
        ref = getattr(self, "reference_date_", None)
        for c in plan["datetime"]:
            if c not in df.columns or c in drop:
                continue
            d = pd.to_datetime(df[c], errors="coerce")
            df[f"{c}_ano"] = d.dt.year.astype(float)
            df[f"{c}_mes"] = d.dt.month.astype(float)
            df[f"{c}_dia_semana"] = d.dt.dayofweek.astype(float)
            df[f"{c}_trimestre"] = d.dt.quarter.astype(float)
            df[f"{c}_fim_semana"] = (d.dt.dayofweek >= 5).astype(float)
            if d.dt.hour.fillna(0).astype(bool).any():
                df[f"{c}_hora"] = d.dt.hour.astype(float)
            if ref is not None:
                df[f"{c}_dias_desde"] = (pd.Timestamp(ref) - d).dt.days.astype(float)
            drop.add(c)
        for r in plan["ratios"]:
            a, b, name = r.get("num"), r.get("den"), r.get("name")
            if a in df.columns and b in df.columns:
                num = pd.to_numeric(df[a], errors="coerce")
                den = pd.to_numeric(df[b], errors="coerce")
                df[name or f"{a}_por_{b}"] = num / den.where(den != 0)
        for c in plan["log"]:
            if c in df.columns and c not in drop:
                v = pd.to_numeric(df[c], errors="coerce")
                df[c] = np.sign(v) * np.log1p(np.abs(v))
        df = df.drop(columns=[c for c in drop if c in df.columns])
        for c in df.columns:
            s = df[c]
            if pd.api.types.is_bool_dtype(s):
                df[c] = s.astype(float)
            elif pd.api.types.is_datetime64_any_dtype(s):
                df[c] = (pd.Timestamp(ref) - s).dt.days.astype(float) if ref is not None else s.dt.year.astype(float)
            elif not pd.api.types.is_numeric_dtype(s):
                df[c] = s.astype(object).where(s.notna(), MISSING).astype(str).astype(object)
            else:
                df[c] = s.astype(float)
        return df


def suggest_ratios(columns: list[str]) -> list[dict[str, str]]:
    """Sugere rácios de negócio por padrões de nome (valor/montante ÷ nº de ...)."""
    out = []
    value_prefix = ("valor", "montante", "receita", "salario", "consumo")
    for a in columns:
        if not a.lower().startswith(value_prefix):
            continue
        suffix = a.split("_")[-1]
        for b in columns:
            if b.lower().startswith("n_") and b.split("_")[-1] == suffix and a != b:
                out.append({"num": a, "den": b, "name": f"{a}_por_{b[2:]}"})
    return out[:5]
