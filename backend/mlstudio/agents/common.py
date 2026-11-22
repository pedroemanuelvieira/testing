"""Utilitários partilhados pelos agentes supervisionados."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import pandas as pd
from sklearn.model_selection import KFold, StratifiedKFold, TimeSeriesSplit, train_test_split

from ..advisor.profile import DataProfile, _guess_positive, profile_from_frame
from ..core.agent import AgentError
from ..core.context import AgentContext
from ..ml.semantic import infer_roles

SUPERVISED = ("binary_classification", "multiclass_classification", "regression")
SENSITIVE = re.compile(r"(^|_)(g[eé]nero|sexo|idade|faixa_etaria|nacionalidade|estado_civil|religiao|etnia|ra[cç]a|"
                       r"deficiencia|orientacao_sexual|saude|gravidez|sindicato)($|_)", re.I)


def sensitive_columns(ctx: AgentContext, df: pd.DataFrame) -> list[str]:
    uc = ctx.use_case
    declared = set(uc.sensitive_attributes) if uc else set()
    not_people = re.compile(r"equip|produto|veiculo|viatura|ativo|maquina|frota|conta|contrato|loja|stock", re.I)
    return [c for c in df.columns if (c in declared or (SENSITIVE.search(c) and not not_people.search(c)))
            and c != ctx.project.target]


@dataclass
class SupervisedData:
    X: pd.DataFrame
    y: pd.Series
    features: list[str]
    task: str
    classes: list[Any] = field(default_factory=list)
    positive_class: Any = None
    time: Optional[pd.Series] = None
    ids: Optional[pd.DataFrame] = None
    sampled_from: Optional[int] = None
    sensitive: Optional[pd.DataFrame] = None


def roles_for(ctx: AgentContext, df: pd.DataFrame) -> dict[str, str]:
    p = ctx.project
    roles = dict(p.column_roles) if p.column_roles else infer_roles(df, target=p.target, id_columns=p.id_columns)
    for c in df.columns:
        roles.setdefault(c, infer_roles(df[[c]]).get(c, "categorical"))
    for c in p.id_columns:
        roles[c] = "id"
    if p.target:
        roles[p.target] = "target"
    return roles


def feature_list(ctx: AgentContext, df: pd.DataFrame, roles: Optional[dict[str, str]] = None,
                 include_time: bool = False) -> list[str]:
    p = ctx.project
    roles = roles or roles_for(ctx, df)
    exclude = set(p.excluded_columns) | set(p.id_columns) | {p.target, p.label_column}
    if p.time_column and not include_time:
        exclude.add(p.time_column)
    if p.features:
        return [c for c in p.features if c in df.columns and c not in exclude]
    return [c for c in df.columns if c not in exclude and roles.get(c) in ("numeric", "boolean", "categorical", "datetime")]


def supervised_data(ctx: AgentContext, max_rows: Optional[int] = None) -> SupervisedData:
    p = ctx.project
    if p.problem_type not in SUPERVISED:
        raise AgentError("Este agente aplica-se a problemas supervisionados (classificação/regressão).")
    df = ctx.data()
    if not p.target or p.target not in df.columns:
        raise AgentError("Defina a coluna alvo (target) do projeto no passo de Enquadramento.")
    df = df.dropna(subset=[p.target]).reset_index(drop=True)
    if p.problem_type == "regression":
        df[p.target] = pd.to_numeric(df[p.target], errors="coerce")
        df = df.dropna(subset=[p.target]).reset_index(drop=True)
    roles = roles_for(ctx, df)
    feats = feature_list(ctx, df, roles)
    if not feats:
        raise AgentError("Não há variáveis explicativas disponíveis depois das exclusões.")
    sampled_from = None
    limit = max_rows or ctx.settings.max_rows
    if len(df) > limit:
        sampled_from = len(df)
        strat = df[p.target] if p.problem_type != "regression" else None
        df, _ = train_test_split(df, train_size=limit, stratify=strat, random_state=ctx.settings.random_state)
        df = df.reset_index(drop=True)
    raw_y = df[p.target]
    classes: list[Any] = []
    pos = None
    if p.problem_type == "binary_classification":
        if raw_y.nunique() != 2:
            raise AgentError(f"Classificação binária exige 2 classes no alvo; '{p.target}' tem {raw_y.nunique()}.")
        pos = p.positive_class if p.positive_class is not None else _guess_positive(raw_y)
        y = (raw_y.astype(str) == str(pos)).astype(int)
        classes = [0, 1]
    elif p.problem_type == "multiclass_classification":
        y = raw_y.astype(str)
        classes = sorted(y.unique().tolist())
        if len(classes) < 3:
            raise AgentError("Classificação multiclasse exige 3 ou mais classes — use classificação binária.")
    else:
        y = raw_y.astype(float)
    time = pd.to_datetime(df[p.time_column], errors="coerce") if p.time_column and p.time_column in df.columns else None
    ids = df[[c for c in p.id_columns if c in df.columns]] if p.id_columns else None
    sens_cols = [c for c in sensitive_columns(ctx, df) if c not in feats]
    return SupervisedData(X=df[feats], y=y, features=feats, task=p.problem_type, classes=classes,
                          positive_class=pos, time=time, ids=ids, sampled_from=sampled_from,
                          sensitive=df[sens_cols] if sens_cols else None)


def split(sd: SupervisedData, test_size: float = 0.2, random_state: int = 42) -> tuple[np.ndarray, np.ndarray, str]:
    n = len(sd.X)
    idx = np.arange(n)
    if sd.time is not None and sd.time.notna().mean() > 0.9:
        order = np.argsort(sd.time.fillna(sd.time.min()).values, kind="stable")
        cut = int(n * (1 - test_size))
        return order[:cut], order[cut:], (f"Divisão temporal: treino até {sd.time.iloc[order[cut - 1]].date()}, "
                                          f"teste depois (os {100 * test_size:.0f}% mais recentes).")
    strat = sd.y if sd.task != "regression" else None
    tr, te = train_test_split(idx, test_size=test_size, stratify=strat, random_state=random_state)
    return tr, te, ("Divisão aleatória estratificada 80/20 (mantém a proporção do alvo)." if strat is not None
                    else "Divisão aleatória 80/20.")


def cv_splitter(sd: SupervisedData, train_idx: np.ndarray, folds: int = 5, random_state: int = 42) -> Any:
    if sd.time is not None and sd.time.notna().mean() > 0.9:
        return TimeSeriesSplit(n_splits=folds)
    if sd.task != "regression":
        return StratifiedKFold(n_splits=folds, shuffle=True, random_state=random_state)
    return KFold(n_splits=folds, shuffle=True, random_state=random_state)


def data_profile(ctx: AgentContext) -> DataProfile:
    """Perfil dos dados do projeto para o conselheiro (com cache por execução)."""
    if "profile" in ctx.cache:
        return ctx.cache["profile"]
    p = ctx.project
    df = ctx.data()
    if p.problem_type in SUPERVISED:
        roles = roles_for(ctx, df)
        prof = profile_from_frame(df, p.problem_type, target=p.target, positive_class=p.positive_class,
                                  features=feature_list(ctx, df, roles))
    else:
        roles = roles_for(ctx, df)
        prof = profile_from_frame(df, p.problem_type, features=feature_list(ctx, df, roles))
    seg = ctx.latest("segmentation")
    if seg and seg.get("outputs", {}).get("recommended_k"):
        prof.suggested_k = int(seg["outputs"]["recommended_k"])
    uc = ctx.use_case
    if p.problem_type == "anomaly_detection":
        if p.label_column and p.label_column in df.columns:
            prof.expected_anomaly_rate = float(pd.to_numeric(df[p.label_column], errors="coerce").mean())
        elif uc and uc.profile.get("expected_anomaly_rate"):
            prof.expected_anomaly_rate = float(uc.profile["expected_anomaly_rate"])
    if p.problem_type == "association_rules" and p.transaction_column in df.columns:
        prof.n_transactions = int(df[p.transaction_column].nunique())
        prof.n_items = int(df[p.item_column].nunique()) if p.item_column in df.columns else None
    if p.problem_type == "forecasting" and p.time_column:
        from ..ml import timeseries as ts

        try:
            long, info = ts.prepare_series(df, p.time_column, p.value_column, p.aggregation, p.series_columns, p.freq)
            total = long.groupby("ds")["y"].sum().values
            an = ts.analyze(total, info["season"])
            prof.freq, prof.season_length = info["freq"], info["season"]
            prof.n_series, prof.series_length = info["n_series"], info["length"]
            prof.trend_strength = an.get("trend_strength")
            prof.seasonal_strength = an.get("seasonal_strength")
            prof.has_zeros = bool((long["y"] == 0).any())
            prof.n_rows = int(len(long))
        except Exception:  # noqa: BLE001 - perfil parcial é aceitável
            pass
    ctx.cache["profile"] = prof
    return prof


def model_name(ctx: AgentContext, model_id: str) -> str:
    spec = ctx.kb.model(model_id)
    return spec.name if spec else model_id


def pct(x: float) -> str:
    return f"{100 * x:.1f}%".replace(".", ",")


def num(x: float, d: int = 2) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "—"
    return f"{x:,.{d}f}".replace(",", " ").replace(".", ",")


RISK_CASES = ("churn", "fraude", "risco", "atraso", "rutura", "attrition", "manutencao", "incumprimento")


def score_label(ctx: AgentContext) -> str:
    """Palavra usada nos motivos individuais: 'risco' em casos de risco, 'probabilidade' nos restantes."""
    uc = ctx.use_case
    return "risco" if uc and any(k in uc.id for k in RISK_CASES) else "probabilidade"
