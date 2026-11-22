"""Estatísticas de referência e deteção de drift (PSI, KS, qui-quadrado)."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

EPS = 1e-4


def reference_stats(df: pd.DataFrame, columns: list[str], bins: int = 10) -> dict[str, Any]:
    """Guarda a distribuição de cada coluna no treino (para comparar mais tarde)."""
    ref: dict[str, Any] = {}
    for c in columns:
        if c not in df.columns:
            continue
        s = df[c]
        if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s) and s.nunique() > 10:
            v = s.astype(float).dropna()
            edges = np.unique(np.quantile(v, np.linspace(0, 1, bins + 1)))
            if len(edges) < 3:
                edges = np.array([v.min() - 1, v.median(), v.max() + 1])
            counts = np.histogram(np.clip(v, edges[0], edges[-1]), bins=edges)[0]
            ref[c] = {"kind": "numeric", "edges": edges.tolist(), "props": (counts / max(counts.sum(), 1)).tolist(),
                      "missing": float(s.isna().mean()), "mean": float(v.mean()), "std": float(v.std()),
                      "sample": v.sample(min(2000, len(v)), random_state=1).round(6).tolist()}
        elif pd.api.types.is_datetime64_any_dtype(s):
            continue
        else:
            vc = s.astype(str).value_counts(normalize=True)
            top = vc.head(20)
            props = top.to_dict()
            if len(vc) > 20:
                props["__outros__"] = float(vc.iloc[20:].sum())
            ref[c] = {"kind": "categorical", "props": props, "missing": float(s.isna().mean())}
    return ref


def psi(expected: np.ndarray, actual: np.ndarray) -> float:
    e = np.clip(np.asarray(expected, dtype=float), EPS, None)
    a = np.clip(np.asarray(actual, dtype=float), EPS, None)
    e, a = e / e.sum(), a / a.sum()
    return float(np.sum((a - e) * np.log(a / e)))


def psi_level(value: float) -> str:
    return "estável" if value < 0.1 else ("moderado" if value < 0.25 else "significativo")


def compare(ref: dict[str, Any], current: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for c, r in ref.items():
        if c not in current.columns:
            rows.append({"variavel": c, "tipo": r["kind"], "psi": np.nan, "nivel": "em falta",
                         "teste": "—", "p_value": np.nan, "detalhe": "Coluna ausente nos dados atuais"})
            continue
        s = current[c]
        if r["kind"] == "numeric":
            v = pd.to_numeric(s, errors="coerce").dropna()
            edges = np.array(r["edges"])
            counts = np.histogram(np.clip(v, edges[0], edges[-1]), bins=edges)[0]
            act = counts / max(counts.sum(), 1)
            value = psi(np.array(r["props"]), act)
            ks = stats.ks_2samp(np.array(r["sample"]), v.sample(min(2000, len(v)), random_state=1)) if len(v) else None
            delta = (v.mean() - r["mean"]) / r["std"] if r.get("std") else np.nan
            rows.append({"variavel": c, "tipo": "numérica", "psi": value, "nivel": psi_level(value),
                         "teste": f"KS = {ks.statistic:.3f}" if ks else "—",
                         "p_value": float(ks.pvalue) if ks else np.nan,
                         "detalhe": f"média {r['mean']:.3g} → {v.mean():.3g} ({delta:+.2f} σ)"})
        else:
            vc = s.astype(str).value_counts(normalize=True)
            keys = [k for k in r["props"] if k != "__outros__"]
            act = [float(vc.get(k, 0.0)) for k in keys]
            exp = [float(r["props"][k]) for k in keys]
            outros_act = float(vc[~vc.index.isin(keys)].sum())
            if "__outros__" in r["props"] or outros_act > 0:
                act.append(outros_act)
                exp.append(float(r["props"].get("__outros__", 0.0)))
            value = psi(np.array(exp), np.array(act))
            obs = np.array(act) * len(s)
            expected = np.clip(np.array(exp), EPS, None)
            expected = expected / expected.sum() * obs.sum()
            chi = stats.chisquare(obs, expected) if obs.sum() > 0 else None
            new = [k for k in vc.index[:5] if k not in r["props"]]
            rows.append({"variavel": c, "tipo": "categórica", "psi": value, "nivel": psi_level(value),
                         "teste": f"χ² = {chi.statistic:.1f}" if chi else "—",
                         "p_value": float(chi.pvalue) if chi else np.nan,
                         "detalhe": ("novas categorias: " + ", ".join(new)) if new else ""})
    return pd.DataFrame(rows).sort_values("psi", ascending=False, na_position="first").reset_index(drop=True)


def score_distribution(scores: np.ndarray, edges: np.ndarray) -> np.ndarray:
    counts = np.histogram(np.clip(scores, edges[0], edges[-1]), bins=edges)[0]
    return counts / max(counts.sum(), 1)
