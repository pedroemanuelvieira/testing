"""Fábrica de pipelines: FeatureBuilder → pré-processamento → algoritmo.

Converte os hiperparâmetros do catálogo (YAML) para os argumentos das
bibliotecas (scikit-learn, LightGBM, XGBoost) e escolhe automaticamente a
codificação de categóricas e a normalização conforme o modelo.
"""
from __future__ import annotations

import importlib.util
from typing import Any, Optional

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler, TargetEncoder

from ..knowledge import get_kb
from .features import MISSING, FeatureBuilder

SUPERVISED = ("binary_classification", "multiclass_classification", "regression")


def library_available(library: str) -> bool:
    mapping = {"lightgbm": "lightgbm", "xgboost": "xgboost", "statsmodels": "statsmodels"}
    mod = mapping.get(library)
    return True if mod is None else importlib.util.find_spec(mod) is not None


def model_available(model_id: str) -> bool:
    spec = get_kb().model(model_id)
    return spec is not None and library_available(spec.library)


# ------------------------------------------------------------------------------ parâmetros
def _num(v: Any) -> Any:
    if isinstance(v, str):
        try:
            return float(v) if "." in v else int(v)
        except ValueError:
            return v
    return v


def coerce_params(model_id: str, params: dict[str, Any]) -> dict[str, Any]:
    """Valida tipos segundo o catálogo e preenche omissões."""
    spec = get_kb().model(model_id)
    if spec is None:
        raise ValueError(f"Modelo desconhecido: {model_id}")
    out: dict[str, Any] = {}
    for hp in spec.hyperparameters:
        v = params.get(hp.name, hp.default)
        if v is None:
            out[hp.name] = None
            continue
        if hp.type == "int":
            v = int(round(float(v)))
        elif hp.type == "float":
            v = float(v)
        elif hp.type == "bool":
            v = v if isinstance(v, bool) else str(v).lower() in ("true", "1", "sim", "yes")
        else:
            v = str(v)
        out[hp.name] = v
    return out


def _class_weight(v: Any) -> Any:
    return None if v in (None, "none", "None", "") else v


def _max_features(v: Any) -> Any:
    v = _num(v)
    return v if not isinstance(v, (int, float)) else float(v)


def make_estimator(model_id: str, task: str, params: dict[str, Any], random_state: int = 42,
                   n_classes: int = 2) -> Any:
    p = coerce_params(model_id, params)
    clf = task != "regression"
    rs = random_state
    if model_id == "logistic_regression":
        from sklearn.linear_model import LogisticRegression

        penalty = p["penalty"]
        kw: dict[str, Any] = {"C": p["C"], "max_iter": p["max_iter"], "class_weight": _class_weight(p["class_weight"]),
                              "random_state": rs}
        if penalty == "l2":
            kw["solver"] = "lbfgs"
        else:
            kw["solver"] = "saga"
            kw["l1_ratio"] = 1.0 if penalty == "l1" else p["l1_ratio"]
        return LogisticRegression(**kw)
    if model_id == "linear_regression":
        from sklearn.linear_model import LinearRegression

        return LinearRegression(fit_intercept=p["fit_intercept"])
    if model_id == "ridge":
        from sklearn.linear_model import Ridge

        return Ridge(alpha=p["alpha"], random_state=rs)
    if model_id == "lasso":
        from sklearn.linear_model import Lasso

        return Lasso(alpha=p["alpha"], random_state=rs, max_iter=5000)
    if model_id == "elastic_net":
        from sklearn.linear_model import ElasticNet

        return ElasticNet(alpha=p["alpha"], l1_ratio=p["l1_ratio"], random_state=rs, max_iter=5000)
    if model_id == "decision_tree":
        from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor

        crit = p["criterion"]
        if clf:
            crit = crit if crit in ("gini", "entropy", "log_loss") else "gini"
            return DecisionTreeClassifier(max_depth=p["max_depth"] or None, min_samples_leaf=p["min_samples_leaf"],
                                          criterion=crit, class_weight=_class_weight(p["class_weight"]),
                                          ccp_alpha=p["ccp_alpha"], random_state=rs)
        crit = crit if crit in ("squared_error", "absolute_error") else "squared_error"
        return DecisionTreeRegressor(max_depth=p["max_depth"] or None, min_samples_leaf=p["min_samples_leaf"],
                                     criterion=crit, ccp_alpha=p["ccp_alpha"], random_state=rs)
    if model_id in ("random_forest", "extra_trees"):
        from sklearn.ensemble import ExtraTreesClassifier, ExtraTreesRegressor, RandomForestClassifier, RandomForestRegressor

        cls = {("random_forest", True): RandomForestClassifier, ("random_forest", False): RandomForestRegressor,
               ("extra_trees", True): ExtraTreesClassifier, ("extra_trees", False): ExtraTreesRegressor}[(model_id, clf)]
        kw = {"n_estimators": p["n_estimators"], "max_depth": p["max_depth"] or None,
              "min_samples_leaf": p["min_samples_leaf"], "max_features": _max_features(p["max_features"]),
              "n_jobs": -1, "random_state": rs}
        if "bootstrap" in p:
            kw["bootstrap"] = p["bootstrap"]
        if clf:
            kw["class_weight"] = _class_weight(p.get("class_weight"))
        return cls(**kw)
    if model_id == "hist_gradient_boosting":
        from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor

        es = {"auto": "auto", "true": True, "false": False}.get(str(p["early_stopping"]).lower(), "auto")
        kw = {"learning_rate": p["learning_rate"], "max_iter": p["max_iter"], "max_leaf_nodes": p["max_leaf_nodes"],
              "min_samples_leaf": p["min_samples_leaf"], "l2_regularization": p["l2_regularization"],
              "early_stopping": es, "random_state": rs}
        if clf:
            return HistGradientBoostingClassifier(class_weight=_class_weight(p["class_weight"]), **kw)
        return HistGradientBoostingRegressor(**kw)
    if model_id == "lightgbm":
        import lightgbm as lgb

        kw = {"n_estimators": p["n_estimators"], "learning_rate": p["learning_rate"], "num_leaves": p["num_leaves"],
              "max_depth": p["max_depth"], "min_child_samples": p["min_child_samples"], "subsample": p["subsample"],
              "subsample_freq": 1 if p["subsample"] < 1 else 0, "colsample_bytree": p["colsample_bytree"],
              "reg_lambda": p["reg_lambda"], "reg_alpha": p["reg_alpha"], "random_state": rs, "verbosity": -1,
              "n_jobs": -1}
        if clf:
            return lgb.LGBMClassifier(class_weight=_class_weight(p["class_weight"]), **kw)
        return lgb.LGBMRegressor(**kw)
    if model_id == "xgboost":
        import xgboost as xgb

        kw = {"n_estimators": p["n_estimators"], "learning_rate": p["learning_rate"], "max_depth": p["max_depth"],
              "min_child_weight": p["min_child_weight"], "subsample": p["subsample"],
              "colsample_bytree": p["colsample_bytree"], "gamma": p["gamma"], "reg_lambda": p["reg_lambda"],
              "random_state": rs, "n_jobs": -1, "tree_method": "hist", "verbosity": 0}
        if clf:
            if n_classes == 2:
                kw["scale_pos_weight"] = p["scale_pos_weight"]
            return xgb.XGBClassifier(eval_metric="logloss", **kw)
        return xgb.XGBRegressor(**kw)
    if model_id == "knn":
        from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor

        cls = KNeighborsClassifier if clf else KNeighborsRegressor
        return cls(n_neighbors=p["n_neighbors"], weights=p["weights"], p=p["p"], n_jobs=-1)
    if model_id == "svm":
        from sklearn.svm import SVC, SVR

        gamma = _num(p["gamma"])
        if clf:
            return SVC(C=p["C"], kernel=p["kernel"], gamma=gamma, class_weight=_class_weight(p["class_weight"]),
                       probability=True, random_state=rs)
        return SVR(C=p["C"], kernel=p["kernel"], gamma=gamma)
    if model_id == "naive_bayes":
        from sklearn.naive_bayes import GaussianNB

        return GaussianNB(var_smoothing=p["var_smoothing"])
    if model_id == "mlp":
        from sklearn.neural_network import MLPClassifier, MLPRegressor

        layers = tuple(int(x) for x in str(p["hidden_layer_sizes"]).split(",") if x.strip())
        cls = MLPClassifier if clf else MLPRegressor
        return cls(hidden_layer_sizes=layers, alpha=p["alpha"], learning_rate_init=p["learning_rate_init"],
                   max_iter=p["max_iter"], early_stopping=p["early_stopping"], random_state=rs)
    raise ValueError(f"O modelo '{model_id}' não é um modelo supervisionado tabular.")


# ------------------------------------------------------------------------------ pré-processamento
def build_preprocessor(X_feat: pd.DataFrame, numeric: list[str], categorical: list[str], scale: bool,
                       supervised: bool, task: str, max_onehot: int = 15) -> ColumnTransformer:
    low = [c for c in categorical if X_feat[c].nunique() <= max_onehot]
    high = [c for c in categorical if c not in low]
    transformers = []
    if numeric:
        steps: list[tuple[str, Any]] = [("imputar", SimpleImputer(strategy="median", add_indicator=True,
                                                                  keep_empty_features=True))]
        if scale:
            steps.append(("escalar", StandardScaler()))
        transformers.append(("num", Pipeline(steps), numeric))
    if low:
        transformers.append(("cat", Pipeline([
            ("imputar", SimpleImputer(strategy="constant", fill_value=MISSING)),
            ("onehot", OneHotEncoder(handle_unknown="infrequent_if_exist", min_frequency=0.005, sparse_output=False)),
        ]), low))
    if high:
        if supervised:
            target_type = "binary" if task == "binary_classification" else (
                "multiclass" if task == "multiclass_classification" else "continuous")
            enc: Any = TargetEncoder(target_type=target_type, random_state=42)
        else:
            enc = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
        steps = [("imputar", SimpleImputer(strategy="constant", fill_value=MISSING)), ("target_enc", enc)]
        if scale:
            steps.append(("escalar", StandardScaler()))
        transformers.append(("cat_alta", Pipeline(steps), high))
    return ColumnTransformer(transformers, remainder="drop", verbose_feature_names_out=False)


def build_pipeline(model_id: str, task: str, params: dict[str, Any], plan: dict[str, Any], X_sample: pd.DataFrame,
                   random_state: int = 42, n_classes: int = 2) -> Pipeline:
    spec = get_kb().model(model_id)
    fb = FeatureBuilder(plan).fit(X_sample)
    X_feat = fb.transform(X_sample)
    pre = build_preprocessor(X_feat, fb.numeric_, fb.categorical_, scale=bool(spec and spec.needs_scaling),
                             supervised=task in SUPERVISED, task=task)
    est = make_estimator(model_id, task, params, random_state=random_state, n_classes=n_classes)
    return Pipeline([("features", FeatureBuilder(plan)), ("prep", pre), ("model", est)])


def transformed_feature_names(pipe: Pipeline) -> list[str]:
    try:
        return list(pipe.named_steps["prep"].get_feature_names_out())
    except Exception:  # noqa: BLE001
        return []


def predict_scores(pipe: Pipeline, X: pd.DataFrame, task: str) -> np.ndarray:
    """Probabilidade da classe positiva (binária), matriz de probabilidades (multiclasse) ou valor (regressão)."""
    if task == "binary_classification":
        return pipe.predict_proba(X)[:, 1]
    if task == "multiclass_classification":
        return pipe.predict_proba(X)
    return pipe.predict(X)


def search_space_to_distributions(space: dict[str, dict[str, Any]], model_id: str) -> dict[str, Any]:
    """Converte o espaço de pesquisa do conselheiro em distribuições do scikit-learn/scipy."""
    from scipy.stats import loguniform, randint, uniform

    spec = get_kb().model(model_id)
    dists: dict[str, Any] = {}
    for name, s in space.items():
        hp = spec.hp(name) if spec else None
        if "choices" in s:
            dists[name] = list(s["choices"])
        elif hp is not None and hp.type == "int":
            lo, hi = int(s["low"]), int(s["high"])
            dists[name] = randint(lo, hi + 1)
        else:
            lo, hi = float(s["low"]), float(s["high"])
            if hp is not None and hp.log and lo > 0:
                dists[name] = loguniform(lo, hi)
            else:
                dists[name] = uniform(lo, hi - lo)
    return dists


def estimator_kind(model_id: str) -> Optional[str]:
    spec = get_kb().model(model_id)
    return spec.family if spec else None
