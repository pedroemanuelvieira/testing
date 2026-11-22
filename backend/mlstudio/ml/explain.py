"""Explicabilidade agnóstica ao modelo, sempre sobre as colunas originais do Power BI."""
from __future__ import annotations

from typing import Any, Callable, Optional

import numpy as np
import pandas as pd

from .semantic import humanize

PredictFn = Callable[[pd.DataFrame], np.ndarray]


def baseline_row(X: pd.DataFrame) -> dict[str, Any]:
    """Valor de referência por coluna: mediana (numéricas) ou moda (restantes)."""
    base: dict[str, Any] = {}
    for c in X.columns:
        s = X[c]
        if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
            base[c] = s.median()
        elif pd.api.types.is_datetime64_any_dtype(s):
            base[c] = s.dropna().sort_values().iloc[len(s.dropna()) // 2] if s.notna().any() else pd.NaT
        else:
            mode = s.mode(dropna=True)
            base[c] = mode.iloc[0] if len(mode) else np.nan
    return base


def permutation_importance_raw(predict: PredictFn, X: pd.DataFrame, y: np.ndarray,
                               score: Callable[[np.ndarray, np.ndarray], float], higher_is_better: bool = True,
                               n_repeats: int = 3, random_state: int = 42,
                               columns: Optional[list[str]] = None) -> pd.DataFrame:
    rng = np.random.default_rng(random_state)
    base_score = score(y, predict(X))
    rows = []
    for c in columns or list(X.columns):
        drops = []
        for _ in range(n_repeats):
            Xp = X.copy()
            Xp[c] = rng.permutation(Xp[c].values)
            s = score(y, predict(Xp))
            drops.append((base_score - s) if higher_is_better else (s - base_score))
        rows.append({"variavel": c, "importancia": float(np.mean(drops)), "desvio": float(np.std(drops))})
    df = pd.DataFrame(rows).sort_values("importancia", ascending=False).reset_index(drop=True)
    total = df["importancia"].clip(lower=0).sum()
    df["importancia_rel"] = df["importancia"].clip(lower=0) / total if total > 0 else 0.0
    return df


def partial_dependence_raw(predict: PredictFn, X: pd.DataFrame, feature: str, grid_points: int = 15,
                           sample: int = 600, random_state: int = 42) -> list[dict[str, Any]]:
    Xs = X.sample(min(sample, len(X)), random_state=random_state) if len(X) > sample else X
    s = X[feature]
    if pd.api.types.is_numeric_dtype(s) and s.nunique() > grid_points:
        grid = np.unique(np.nanquantile(s.astype(float), np.linspace(0.02, 0.98, grid_points)))
    else:
        grid = s.value_counts().head(grid_points).index.tolist()
    out = []
    for v in grid:
        Xv = Xs.copy()
        Xv[feature] = v
        out.append({"valor": v if not isinstance(v, (np.floating, float)) else round(float(v), 4),
                    "previsao_media": float(np.mean(predict(Xv)))})
    return out


def local_contributions(predict: PredictFn, X_rows: pd.DataFrame, background: pd.DataFrame,
                        top_k: int = 3) -> list[list[dict[str, Any]]]:
    """Contribuição de cada variável por substituição pelo valor de referência (aproximação tipo SHAP).

    Vetorizado: uma previsão por variável sobre todas as linhas.
    """
    base = baseline_row(background)
    p0 = predict(X_rows)
    deltas = {}
    for c in X_rows.columns:
        Xc = X_rows.copy()
        Xc[c] = base[c]
        try:
            deltas[c] = p0 - predict(Xc)
        except Exception:  # noqa: BLE001 - variáveis problemáticas são ignoradas
            continue
    D = pd.DataFrame(deltas, index=X_rows.index)
    out = []
    for i, idx in enumerate(X_rows.index):
        row = D.loc[idx].sort_values(key=np.abs, ascending=False).head(top_k)
        out.append([{"variavel": c, "valor": X_rows.at[idx, c], "contribuicao": float(v)} for c, v in row.items()
                    if abs(v) > 1e-9])
    return out


def format_value(v: Any) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "em falta"
    if isinstance(v, (float, np.floating)):
        return f"{v:,.2f}".replace(",", " ").replace(".", ",").rstrip("0").rstrip(",")
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d")
    return str(v)


def reasons_text(contribs: list[dict[str, Any]], higher_label: str = "risco") -> str:
    parts = []
    for c in contribs:
        arrow = "↑" if c["contribuicao"] > 0 else "↓"
        parts.append(f"{humanize(c['variavel'])} = {format_value(c['valor'])} ({arrow} {higher_label})")
    return "; ".join(parts)
