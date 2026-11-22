"""Inferência do papel semântico de cada coluna (numérica, categórica, data, ID, ...)."""
from __future__ import annotations

import re
from typing import Iterable, Optional

import numpy as np
import pandas as pd

ID_NAME = re.compile(r"(^id$|_id$|^id_|codigo|^cod_|_cod$|^num_|numero|^ref|_ref$|uuid|nif|iban)", re.I)
ROLES = ("numeric", "boolean", "categorical", "datetime", "id", "text", "constant", "target")


def is_textlike(s: pd.Series) -> bool:
    return pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s) or isinstance(s.dtype, pd.CategoricalDtype)


def try_parse_dates(s: pd.Series) -> Optional[pd.Series]:
    sample = s.dropna().astype(str).head(200)
    if sample.empty or not sample.str.match(r"^\d{4}-\d{1,2}-\d{1,2}|^\d{1,2}/\d{1,2}/\d{4}").mean() > 0.9:
        return None
    parsed = pd.to_datetime(s, errors="coerce", dayfirst=bool(sample.str.contains("/").any()))
    return parsed if parsed.notna().mean() > 0.9 * s.notna().mean() else None


def infer_role(s: pd.Series, name: str) -> str:
    n = len(s)
    non_null = s.dropna()
    nunique = int(non_null.nunique())
    if nunique <= 1:
        return "constant"
    if pd.api.types.is_datetime64_any_dtype(s):
        return "datetime"
    if pd.api.types.is_bool_dtype(s):
        return "boolean"
    if pd.api.types.is_numeric_dtype(s):
        if set(np.unique(non_null.values)).issubset({0, 1}):
            return "boolean"
        if (ID_NAME.search(name) and nunique > 0.95 * len(non_null)
                and pd.api.types.is_integer_dtype(s)):
            return "id"
        return "numeric"
    if is_textlike(s):
        if try_parse_dates(s) is not None:
            return "datetime"
        ratio = nunique / max(len(non_null), 1)
        if ratio > 0.9 and nunique > 50:
            avg_len = non_null.astype(str).str.len().mean()
            return "text" if avg_len > 30 and not ID_NAME.search(name) else "id"
        if ID_NAME.search(name) and ratio > 0.5:
            return "id"
        return "categorical"
    return "categorical" if n else "constant"


def infer_roles(df: pd.DataFrame, target: Optional[str] = None, id_columns: Iterable[str] = ()) -> dict[str, str]:
    roles = {}
    ids = set(id_columns)
    for col in df.columns:
        if col == target:
            roles[col] = "target"
        elif col in ids:
            roles[col] = "id"
        else:
            roles[col] = infer_role(df[col], col)
    return roles


def feature_columns(df: pd.DataFrame, roles: dict[str, str], exclude: Iterable[str] = ()) -> list[str]:
    ex = set(exclude)
    return [c for c in df.columns if c not in ex and roles.get(c) in ("numeric", "boolean", "categorical", "datetime")]


def humanize(col: str) -> str:
    return col.replace("_", " ").strip()
