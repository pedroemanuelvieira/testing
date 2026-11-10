"""Contrato de dados: unico ponto de contacto entre os dados reais e os modulos.

Os modulos so dependem de DataFrames com estas colunas. Mapear a fonte real
(SQL, Power BI export, ficheiros) para este contrato e a unica adaptacao necessaria.
"""
from __future__ import annotations
import re
import warnings
import pandas as pd
import numpy as np


class DataQualityWarning(UserWarning):
    """Problema de qualidade de dados que NAO bloqueia mas altera resultados.
    Nunca silenciar em producao: o runner regista-os em relatorio.json."""

SALES = {  # 1 linha = 1 linha de documento de venda
    "required": ["date", "order_id", "customer_id", "product_id", "qty", "revenue"],
    "optional": ["cost", "channel", "returned_qty"],
    "nullable": ["customer_id"],  # v0.4: vendas de balcao sem cliente sao normais; modulos de cliente excluem-nas (known_customers)
}
STOCK = {  # 1 linha = 1 produto por dia (snapshot fim de dia)
    "required": ["date", "product_id", "stock_qty"],
    "optional": [],
}
INVEST = {  # 1 linha = 1 campanha/investimento
    "required": ["campaign_id", "start", "end", "spend"],
    "optional": ["product_id", "customer_ids_target", "channel"],
}
BUDGET = {  # orcamento/objetivo por periodo e produto (ou total)
    "required": ["period", "product_id", "planned_qty", "planned_revenue"],  # v0.3: alinhado com planning.plan_variance
    "optional": [],
}


class ContractError(ValueError):
    pass


_FLOATISH = re.compile(r"^(\d+)\.0+$")


def _norm_one(v):
    if v is None or v is pd.NA or (isinstance(v, float) and np.isnan(v)):
        return None
    t = str(v).strip()
    m = _FLOATISH.match(t)
    if m:
        t = m.group(1)
    return None if (t == "" or t.lower() in ("nan", "none", "null", "<na>")) else t


def normalize_ids(s: pd.Series) -> pd.Series:
    """Ruido deterministico de identificadores -> forma canonica (v0.4, OBJ-018).

    str, sem espacos laterais, '123.0' (float do pandas por causa de NaN) -> '123'.
    Vazios/'nan'/'None' -> None. NAO altera maiusculas nem zeros a esquerda: isso seria adivinhar
    semantica (codigos distintos). Divergencias reais apanha-as check_id_overlap."""
    return pd.Series([_norm_one(v) for v in s], index=s.index, dtype="object")


def validate(df: pd.DataFrame, spec: dict, name: str) -> pd.DataFrame:
    missing = [c for c in spec["required"] if c not in df.columns]
    if missing:
        raise ContractError(f"{name}: faltam colunas {missing}")
    out = df.copy()
    for c in out.columns:
        if c.endswith("_id"):
            out[c] = normalize_ids(out[c])
    for c in ("date", "start", "end"):
        if c in out.columns:
            out[c] = pd.to_datetime(out[c]).dt.normalize()
    for c in ("qty", "revenue", "cost", "stock_qty", "spend", "returned_qty",
              "planned_qty", "planned_revenue"):
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    must = [c for c in spec["required"] if c not in spec.get("nullable", [])]
    nulls = out[must].isna().sum()
    bad = nulls[nulls > 0]
    if len(bad):
        raise ContractError(f"{name}: nulos em {bad.to_dict()}")
    numeric = out.select_dtypes(include="number")
    if numeric.shape[1] and not np.isfinite(numeric.to_numpy(dtype=float, na_value=np.nan)).all():
        raise ContractError(f"{name}: valores numericos nao finitos")
    return out


def validate_sales(df):
    out = validate(df, SALES, "sales")
    if (out["qty"] <= 0).any():
        raise ContractError("sales: qty<=0 (separar devolucoes em returned_qty)")
    if "returned_qty" in out and out["returned_qty"].ne(0).any():
        raise ContractError("sales: devolucoes exigem normalizacao explicita de quantidades e receita; nao sao suportadas nesta versao")
    if out.empty:
        raise ContractError("sales: tabela vazia")
    dup = out.duplicated(keep="first")
    if dup.any():  # v0.4 (OBJ-019): duplicados exatos inflacionam receita e procura sem erro
        share = float(out.loc[dup, "revenue"].sum() / max(out["revenue"].sum(), 1e-12))
        warnings.warn(f"sales: {int(dup.sum())} linhas duplicadas exatas ({share:.1%} da receita). "
                      "Podem ser linhas legitimas repetidas ou extracao duplicada; confirmar. "
                      "prepare.prepare_sales(duplicates='drop') remove-as.", DataQualityWarning, stacklevel=2)
    return out


def known_customers(sales: pd.DataFrame, warn: bool = True) -> pd.DataFrame:
    """Linhas com cliente identificado. Os modulos de cliente (ciclo de vida, churn, coortes)
    so podem usar estas; basket, previsao, ruturas e desvios usam todas as linhas."""
    anon = sales["customer_id"].isna()
    if anon.any() and warn:
        share = float(sales.loc[anon, "revenue"].sum() / max(sales["revenue"].sum(), 1e-12))
        warnings.warn(f"{int(anon.sum())} linhas sem customer_id ({share:.1%} da receita) excluidas "
                      "dos modulos de cliente.", DataQualityWarning, stacklevel=3)
    out = sales.loc[~anon]
    if out.empty:
        raise ContractError("sales: nenhuma linha com customer_id; modulos de cliente nao aplicaveis")
    return out


def check_id_overlap(sales: pd.DataFrame, stock: pd.DataFrame, min_overlap: float = 0.5,
                     allow_partial: bool = False) -> dict:
    """Cobertura de identificadores entre vendas e stock (v0.4, OBJ-018).

    Sem isto, IDs com formatos diferentes davam '0 rupturas' em vez de erro: o pior resultado
    possivel para um gestor. Mede a quota de RECEITA (nao de produtos) com serie de stock."""
    ps, pk = set(sales["product_id"].dropna()), set(stock["product_id"].dropna())
    rev = sales.groupby("product_id")["revenue"].sum()
    cov = float(rev[rev.index.isin(pk)].sum() / max(rev.sum(), 1e-12))
    only_sales = sorted(ps - pk)[:5]; only_stock = sorted(pk - ps)[:5]
    info = {"cobertura_receita": cov, "produtos_vendas": len(ps), "produtos_stock": len(pk),
            "so_em_vendas_exemplos": only_sales, "so_em_stock_exemplos": only_stock}
    if cov < min_overlap and not allow_partial:
        raise ContractError(
            f"stock: so {cov:.0%} da receita tem serie de stock (minimo {min_overlap:.0%}). "
            f"Ids so em vendas: {only_sales}; so em stock: {only_stock}. Formatos de codigo diferentes "
            "(zeros a esquerda, maiusculas, prefixos)? Se o stock cobre mesmo so parte do catalogo, "
            "usar allow_partial=True.")
    if cov < 1.0:
        warnings.warn(f"stock: {1 - cov:.0%} da receita sem serie de stock (ex.: {only_sales}); "
                      "esses produtos nao entram na analise de ruturas.", DataQualityWarning, stacklevel=2)
    return info


def validate_stock(df):
    out = validate(df, STOCK, "stock")
    if (out["stock_qty"] < 0).any():
        raise ContractError("stock: stock negativo")
    if out.duplicated(["date", "product_id"]).any():
        raise ContractError("stock: duplicados (date, product_id)")
    return out
