"""Segmentação (clustering), deteção de anomalias e regras de associação."""
from __future__ import annotations

from itertools import combinations
from typing import Any, Optional

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

from .semantic import humanize


def _signed_log(x: Any) -> Any:
    return np.sign(x) * np.log1p(np.abs(x))


def build_transformer(df: pd.DataFrame, features: list[str], scale: bool = True,
                      log_skewed: bool = True) -> tuple[Pipeline, list[str], list[str]]:
    num = [c for c in features if pd.api.types.is_numeric_dtype(df[c])]
    cat = [c for c in features if c not in num]
    log_cols = []
    if log_skewed:
        for c in num:
            s = df[c].astype(float).dropna()
            if len(s) > 10 and s.min() >= 0 and abs(s.skew()) > 1:
                log_cols.append(c)
    lin = [c for c in num if c not in log_cols]
    parts = []
    if log_cols:
        parts.append(("log", Pipeline([("imp", SimpleImputer(strategy="median")),
                                       ("log", FunctionTransformer(_signed_log, feature_names_out="one-to-one")),
                                       ("esc", StandardScaler() if scale else "passthrough")]), log_cols))
    if lin:
        parts.append(("num", Pipeline([("imp", SimpleImputer(strategy="median")),
                                       ("esc", StandardScaler() if scale else "passthrough")]), lin))
    if cat:
        parts.append(("cat", Pipeline([("imp", SimpleImputer(strategy="most_frequent")),
                                       ("oh", OneHotEncoder(handle_unknown="ignore", max_categories=10,
                                                            sparse_output=False))]), cat))
    ct = ColumnTransformer(parts, verbose_feature_names_out=False)
    return Pipeline([("prep", ct)]), num, log_cols


def _as_str_frame(df: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    out = df[features].copy()
    for c in out.columns:
        if not pd.api.types.is_numeric_dtype(out[c]):
            out[c] = out[c].astype(object).where(out[c].notna(), "__em_falta__").astype(str)
        elif pd.api.types.is_bool_dtype(out[c]):
            out[c] = out[c].astype(float)
    return out


# ------------------------------------------------------------------------------ clustering
def evaluate_k(X: np.ndarray, k_values: range, random_state: int = 42, sample: int = 4000) -> pd.DataFrame:
    from sklearn.cluster import KMeans
    from sklearn.metrics import calinski_harabasz_score, davies_bouldin_score, silhouette_score

    rng = np.random.default_rng(random_state)
    idx = rng.choice(len(X), size=min(sample, len(X)), replace=False)
    Xs = X[idx]
    rows = []
    for k in k_values:
        km = KMeans(n_clusters=k, n_init=5, random_state=random_state).fit(Xs)
        labels = km.labels_
        rows.append({"k": k, "silhueta": float(silhouette_score(Xs, labels, sample_size=min(2500, len(Xs)),
                                                                random_state=random_state)),
                     "inercia": float(km.inertia_), "davies_bouldin": float(davies_bouldin_score(Xs, labels)),
                     "calinski_harabasz": float(calinski_harabasz_score(Xs, labels))})
    return pd.DataFrame(rows)


def recommend_k(scores: pd.DataFrame) -> tuple[int, str]:
    s = scores[(scores["k"] >= 3) & (scores["k"] <= 8)]
    if s.empty:
        s = scores
    best = s.loc[s["silhueta"].idxmax()]
    near = s[s["silhueta"] >= best["silhueta"] - 0.02].sort_values("k")
    chosen = near.iloc[0]
    fmt = lambda v: f"{v:.2f}".replace(".", ",")  # noqa: E731
    reason = (f"k = {int(chosen['k'])} tem silhueta {fmt(chosen['silhueta'])} (a melhor entre 3 e 8 é "
              f"{fmt(best['silhueta'])} com k = {int(best['k'])}); prefere-se o menor k com qualidade equivalente, "
              "por ser mais fácil de operacionalizar.")
    return int(chosen["k"]), reason


class ClusterAssigner(BaseEstimator):
    """Envolve um algoritmo de clustering e garante ``predict`` para novos registos."""

    def __init__(self, transformer: Pipeline, model: Any, model_id: str, features: list[str]):
        self.transformer = transformer
        self.model = model
        self.model_id = model_id
        self.features = features

    def fit(self, df: pd.DataFrame) -> "ClusterAssigner":
        X = self.transformer.fit_transform(_as_str_frame(df, self.features))
        if self.model_id in ("agglomerative", "dbscan"):
            labels = self.model.fit_predict(X)
            from sklearn.neighbors import KNeighborsClassifier

            self.assigner_ = KNeighborsClassifier(n_neighbors=5).fit(X, labels)
        else:
            self.model.fit(X)
            labels = self.model.predict(X)
            self.assigner_ = None
        self.labels_ = np.asarray(labels)
        self.X_ = X
        return self

    def transform_features(self, df: pd.DataFrame) -> np.ndarray:
        return self.transformer.transform(_as_str_frame(df, self.features))

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        X = self.transform_features(df)
        return self.assigner_.predict(X) if self.assigner_ is not None else self.model.predict(X)

    def distance(self, df: pd.DataFrame) -> Optional[np.ndarray]:
        if self.model_id != "kmeans":
            return None
        X = self.transform_features(df)
        return np.min(self.model.transform(X), axis=1)


def make_clusterer(model_id: str, params: dict[str, Any], random_state: int = 42) -> Any:
    from sklearn.cluster import DBSCAN, AgglomerativeClustering, KMeans
    from sklearn.mixture import GaussianMixture

    if model_id == "kmeans":
        return KMeans(n_clusters=int(params.get("n_clusters", 5)), n_init=int(params.get("n_init", 10)),
                      random_state=random_state)
    if model_id == "gaussian_mixture":
        return GaussianMixture(n_components=int(params.get("n_components", 5)),
                               covariance_type=params.get("covariance_type", "full"), random_state=random_state)
    if model_id == "agglomerative":
        return AgglomerativeClustering(n_clusters=int(params.get("n_clusters", 5)), linkage=params.get("linkage", "ward"))
    if model_id == "dbscan":
        return DBSCAN(eps=float(params.get("eps", 0.5)), min_samples=int(params.get("min_samples", 10)))
    raise ValueError(f"Algoritmo de clustering desconhecido: {model_id}")


def segment_profiles(df: pd.DataFrame, labels: np.ndarray, features: list[str]) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    num = [c for c in features if pd.api.types.is_numeric_dtype(df[c])]
    data = df[num].astype(float).copy()
    data["segmento"] = labels
    overall_mean, overall_std = data[num].mean(), data[num].std().replace(0, 1)
    prof = data.groupby("segmento")[num].mean()
    z = (prof - overall_mean) / overall_std
    sizes = data["segmento"].value_counts().sort_index()
    names = {}
    for seg in prof.index:
        if seg == -1:
            names[seg] = "Ruído / atípicos"
            continue
        top = z.loc[seg].abs().sort_values(ascending=False).head(2).index
        parts = [("↑ " if z.loc[seg, c] > 0 else "↓ ") + humanize(c) for c in top]
        names[seg] = " · ".join(parts)
    summary = pd.DataFrame({"segmento": prof.index, "nome": [names[s] for s in prof.index],
                            "n": [int(sizes.get(s, 0)) for s in prof.index],
                            "pct": [float(sizes.get(s, 0) / len(data)) for s in prof.index]})
    for c in num:
        summary[c] = prof[c].values
    return summary, z, names


# ------------------------------------------------------------------------------ anomalias
class RobustZScore(BaseEstimator):
    def __init__(self, threshold: float = 3.5):
        self.threshold = threshold

    def fit(self, X: np.ndarray, y: Any = None) -> "RobustZScore":
        X = np.asarray(X, dtype=float)
        self.median_ = np.nanmedian(X, axis=0)
        mad = np.nanmedian(np.abs(X - self.median_), axis=0)
        self.mad_ = np.where(mad > 0, mad, np.nanstd(X, axis=0) / 1.4826 + 1e-9)
        return self

    def zscores(self, X: np.ndarray) -> np.ndarray:
        return 0.6745 * (np.asarray(X, dtype=float) - self.median_) / self.mad_

    def score_samples(self, X: np.ndarray) -> np.ndarray:
        return -np.nanmax(np.abs(self.zscores(X)), axis=1)

    def predict(self, X: np.ndarray) -> np.ndarray:
        return np.where(-self.score_samples(X) > self.threshold, -1, 1)


class AnomalyDetector(BaseEstimator):
    """Pipeline de anomalias: transformação + detetor; ``score`` alto = mais anómalo.

    O z-score robusto usa só variáveis numéricas (com log nas assimétricas). Os
    motivos combinam o z-score robusto das numéricas com a raridade das
    categorias observadas.
    """

    def __init__(self, model_id: str, params: dict[str, Any], features: list[str], random_state: int = 42):
        self.model_id = model_id
        self.params = params
        self.features = features
        self.random_state = random_state

    def fit(self, df: pd.DataFrame) -> "AnomalyDetector":
        from sklearn.ensemble import IsolationForest
        from sklearn.neighbors import LocalOutlierFactor

        self.numeric_ = [c for c in self.features if pd.api.types.is_numeric_dtype(df[c])]
        self.categorical_ = [c for c in self.features if c not in self.numeric_]
        model_feats = self.numeric_ if self.model_id == "robust_zscore" else self.features
        if not model_feats:
            raise ValueError("O z-score robusto precisa de variáveis numéricas.")
        self.model_features_ = model_feats
        self.transformer_, _, _ = build_transformer(df, model_feats, scale=self.model_id == "local_outlier_factor")
        X = self.transformer_.fit_transform(_as_str_frame(df, model_feats))
        p = self.params
        contamination = float(p.get("contamination", 0.02))
        if self.model_id == "isolation_forest":
            ms = p.get("max_samples", "auto")
            ms = ms if ms == "auto" else (float(ms) if "." in str(ms) else int(ms))
            self.model_ = IsolationForest(n_estimators=int(p.get("n_estimators", 300)), contamination=contamination,
                                          max_samples=ms, max_features=float(p.get("max_features", 1.0)),
                                          random_state=self.random_state, n_jobs=-1).fit(X)
        elif self.model_id == "local_outlier_factor":
            self.model_ = LocalOutlierFactor(n_neighbors=int(p.get("n_neighbors", 35)), contamination=contamination,
                                             novelty=True).fit(X)
        elif self.model_id == "robust_zscore":
            self.model_ = RobustZScore(threshold=float(p.get("threshold", 3.5))).fit(X)
        else:
            raise ValueError(f"Detetor desconhecido: {self.model_id}")
        train_scores = self.score(df)
        if self.model_id == "robust_zscore":
            # limiar do z-score, mas nunca acima da capacidade de revisão (contaminação)
            self.threshold_ = max(float(p.get("threshold", 3.5)), float(np.quantile(train_scores, 1 - contamination)))
        else:
            self.threshold_ = float(np.quantile(train_scores, 1 - contamination))
        # referência para os motivos
        self.reason_tf_, _, self.log_cols_ = build_transformer(df, self.numeric_, scale=False) if self.numeric_ else (None, [], [])
        if self.reason_tf_ is not None:
            self.robust_ = RobustZScore().fit(self.reason_tf_.fit_transform(_as_str_frame(df, self.numeric_)))
            self.reason_cols_ = list(self.reason_tf_.named_steps["prep"].get_feature_names_out())
        self.cat_freq_ = {c: df[c].astype(str).value_counts(normalize=True).to_dict() for c in self.categorical_}
        return self

    def score(self, df: pd.DataFrame) -> np.ndarray:
        X = self.transformer_.transform(_as_str_frame(df, self.model_features_))
        return -self.model_.score_samples(X)

    def is_anomaly(self, df: pd.DataFrame) -> np.ndarray:
        return self.score(df) >= self.threshold_

    def reasons(self, df: pd.DataFrame, top_k: int = 3) -> list[list[dict[str, Any]]]:
        n = len(df)
        cand: list[list[dict[str, Any]]] = [[] for _ in range(n)]
        if self.reason_tf_ is not None:
            z = self.robust_.zscores(self.reason_tf_.transform(_as_str_frame(df, self.numeric_)))
            for i in range(n):
                for j, col in enumerate(self.reason_cols_):
                    cand[i].append({"variavel": col, "valor": df.iloc[i][col], "z": float(z[i, j])})
        for c in self.categorical_:
            freqs = self.cat_freq_[c]
            vals = df[c].astype(str).values
            for i in range(n):
                f = freqs.get(vals[i], 0.0)
                if f < 0.02:  # categoria rara → pseudo z-score
                    cand[i].append({"variavel": c, "valor": vals[i], "z": float(min(10.0, -2 * np.log10(max(f, 1e-4))))})
        return [sorted(r, key=lambda d: -abs(d["z"]))[:top_k] for r in cand]


# ------------------------------------------------------------------------------ associação
def apriori_rules(df: pd.DataFrame, tx_col: str, item_col: str, min_support: float = 0.01,
                  min_confidence: float = 0.2, min_lift: float = 1.2, max_len: int = 3,
                  max_items: int = 300) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    baskets = df[[tx_col, item_col]].dropna().drop_duplicates()
    n_tx = baskets[tx_col].nunique()
    item_counts = baskets[item_col].value_counts()
    items = item_counts[item_counts / n_tx >= min_support].head(max_items).index.tolist()
    if not items:
        return pd.DataFrame(), pd.DataFrame(), {"n_transactions": n_tx, "n_items": int(item_counts.size),
                                                "avg_basket": 0.0}
    mat = pd.crosstab(baskets[tx_col], baskets[item_col]).reindex(columns=items, fill_value=0).astype(bool)
    M = mat.values
    support: dict[frozenset, float] = {}
    for j, it in enumerate(items):
        support[frozenset([it])] = float(M[:, j].mean())
    current = [frozenset([it]) for it in items]
    col_idx = {it: j for j, it in enumerate(items)}
    for size in range(2, max_len + 1):
        cands = set()
        cur_list = sorted(current, key=lambda s: sorted(s))
        for a, b in combinations(cur_list, 2):
            u = a | b
            if len(u) == size and all(frozenset(sub) in support for sub in combinations(u, size - 1)):
                cands.add(u)
        nxt = []
        for c in cands:
            sup = float(np.all(M[:, [col_idx[i] for i in c]], axis=1).mean())
            if sup >= min_support:
                support[c] = sup
                nxt.append(c)
        if not nxt:
            break
        current = nxt
    rules = []
    for itemset, sup in support.items():
        if len(itemset) < 2:
            continue
        for cons in itemset:
            ante = itemset - {cons}
            conf = sup / support[ante]
            lift = conf / support[frozenset([cons])]
            if conf >= min_confidence and lift >= min_lift:
                rules.append({"antecedente": " + ".join(sorted(ante)), "consequente": cons, "suporte": sup,
                              "confianca": conf, "lift": lift,
                              "leverage": sup - support[ante] * support[frozenset([cons])],
                              "n_itens": len(itemset)})
    rules_df = pd.DataFrame(rules).sort_values(["lift", "confianca"], ascending=False).reset_index(drop=True) if rules else pd.DataFrame()
    itemsets = pd.DataFrame([{"itens": " + ".join(sorted(k)), "tamanho": len(k), "suporte": v} for k, v in support.items()])
    itemsets = itemsets.sort_values("suporte", ascending=False).reset_index(drop=True)
    info = {"n_transactions": int(n_tx), "n_items": int(item_counts.size),
            "avg_basket": float(baskets.groupby(tx_col).size().mean()), "frequent_items": len(items)}
    return rules_df, itemsets, info


def lift_matrix(df: pd.DataFrame, tx_col: str, item_col: str, top: int = 12) -> tuple[list[str], list[list[float]]]:
    baskets = df[[tx_col, item_col]].dropna().drop_duplicates()
    top_items = baskets[item_col].value_counts().head(top).index.tolist()
    mat = pd.crosstab(baskets[tx_col], baskets[item_col]).reindex(columns=top_items, fill_value=0).astype(bool)
    M = mat.values.astype(float)
    sup = M.mean(axis=0)
    co = (M.T @ M) / len(M)
    lift = co / np.outer(sup, sup)
    np.fill_diagonal(lift, np.nan)
    return top_items, lift.tolist()
