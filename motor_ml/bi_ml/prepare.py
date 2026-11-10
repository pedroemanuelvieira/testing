"""Adaptador tolerante de extratos de ERP para o contrato (v0.4, OBJ-011/018/019/020).

Principio: normalizar RUIDO deterministico e tornar EXPLICITAS as decisoes de negocio
(devolucoes, balcao, duplicados). Nunca inventa dados nem adivinha semantica silenciosamente.
Devolve sempre (dados, relatorio) para que o relatorio apareca no relatorio.json.
"""
from __future__ import annotations
import warnings
import numpy as np
import pandas as pd
from . import contract
from .contract import ContractError

SALES_NUM = ["qty", "revenue", "cost"]


def prepare_sales(df: pd.DataFrame, returns: str = "separate", duplicates: str = "keep",
                  zero_qty: str = "drop", exclude_products=None):
    """returns: 'separate' (linhas qty<0/revenue<0 saem das vendas para a tabela de devolucoes;
    vendas ficam BRUTAS), 'reject'. duplicates: 'keep' (avisa no validate), 'drop'.

    exclude_products (v0.7): ids de linhas que NAO sao produtos (ex. 'PORTES', 'EMBALAGEM'); saem das vendas
    e ficam reportadas em rel['nao_produto_valor'] (a reconciliacao mantem-se exata). Sem esta lista, linhas
    presentes em >=60% das encomendas geram aviso (rel['possivel_nao_produto']) mas NAO sao removidas.

    Devolve (sales, returns_df, relatorio)."""
    if returns not in ("separate", "reject") or duplicates not in ("keep", "drop") or zero_qty not in ("drop", "reject"):
        raise ContractError("prepare_sales: politica invalida")
    missing = [c for c in contract.SALES["required"] if c not in df.columns]
    if missing:
        raise ContractError(f"sales: faltam colunas {missing}")
    d = df.copy()
    rel = {"linhas_entrada": int(len(d))}
    d["date"] = parse_dates(d["date"])
    if getattr(d["date"].dt, "tz", None) is not None:
        d["date"] = d["date"].dt.tz_localize(None); rel["timezone_removido"] = True
    for c in SALES_NUM:
        if c in d.columns:
            before = d[c].notna().sum()
            d[c] = pd.to_numeric(d[c], errors="coerce")
            lost = int(before - d[c].notna().sum())
            if lost:
                rel[f"{c}_nao_numerico"] = lost
    bad_date = int(d["date"].isna().sum())
    if bad_date:
        raise ContractError(f"sales: {bad_date} datas nao interpretaveis")
    # v0.6 (Grok, OBJ-030): separar TRES naturezas em vez de "negativo => devolucao".
    #  - devolucao: qty < 0 (unidades voltam);
    #  - ajuste de valor: qty >= 0 com revenue < 0 (desconto/nota de credito em linha) ou qty == 0 com revenue != 0
    #    (nota de credito/debito so de valor). Nao movem unidades e NAO sao vendas de unidades.
    #  - qty == 0 e revenue == 0: linha vazia, removida.
    # Reconciliacao exata: soma(revenue de entrada) == receita_bruta - devolucoes_valor + ajustes_valor_liquido.
    total_in = float(d["revenue"].sum())
    is_ret = d["qty"] < 0
    is_adj = (~is_ret) & (((d["qty"] > 0) & (d["revenue"] < 0)) | ((d["qty"] == 0) & (d["revenue"] != 0)))
    is_empty = (d["qty"] == 0) & (d["revenue"] == 0)
    ret = d[is_ret].copy()
    adj = d[is_adj].copy()
    if len(ret) or len(adj):
        if returns == "reject":
            raise ContractError(f"sales: {len(ret)} devolucoes e {len(adj)} ajustes de valor. Usar returns='separate'.")
    if len(ret):
        rel["devolucoes_linhas"] = int(len(ret))
        rel["devolucoes_unidades"] = float(ret["qty"].abs().sum())
        rel["devolucoes_valor"] = float(-ret["revenue"].sum())   # valor creditado (positivo se revenue<0)
        ret["qty"] = ret["qty"].abs(); ret["revenue"] = -ret["revenue"]
    if len(adj):
        rel["ajustes_valor_linhas"] = int(len(adj))
        rel["ajustes_valor_liquido"] = float(adj["revenue"].sum())  # negativo = notas de credito/descontos
    if is_empty.any():
        if zero_qty == "reject":
            raise ContractError(f"sales: {int(is_empty.sum())} linhas com qty=0 e revenue=0")
        rel["linhas_qty_zero_removidas"] = int(is_empty.sum())
    d = d[~(is_ret | is_adj | is_empty)]
    if "customer_id" in d.columns:
        d["customer_id"] = contract.normalize_ids(d["customer_id"])
        rel["linhas_sem_cliente"] = int(d["customer_id"].isna().sum())
    if (d["revenue"] == 0).any():
        rel["linhas_receita_zero"] = int((d["revenue"] == 0).sum())  # brindes/amostras: mantidas
    if exclude_products:
        ex = d["product_id"].astype(str).isin({str(x) for x in exclude_products})
        rel["nao_produto_linhas"] = int(ex.sum()); rel["nao_produto_valor"] = float(d.loc[ex, "revenue"].sum())
        d = d[~ex]
    elif "order_id" in d.columns and d["order_id"].nunique() >= 50:
        share = d.groupby("product_id")["order_id"].nunique() / d["order_id"].nunique()
        sus = sorted(str(k) for k in share[share >= 0.60].index)
        if sus:
            rel["possivel_nao_produto"] = sus
            warnings.warn(f"sales: produtos presentes em >=60% das encomendas {sus}: possiveis linhas nao-produto "
                          "(portes, embalagem). Distorcem ABC/basket; usar exclude_products=[...].", contract.DataQualityWarning)
    if duplicates == "drop":
        n0 = len(d); dd = d.drop_duplicates(); rel["duplicados_removidos"] = int(n0 - len(dd))
        rel["duplicados_valor"] = float(d["revenue"].sum() - dd["revenue"].sum()); d = dd
    sales = contract.validate_sales(d.reset_index(drop=True))
    rel["receita_bruta"] = float(sales["revenue"].sum())
    rel["receita_liquida"] = float(sales["revenue"].sum() - rel.get("devolucoes_valor", 0.0)
                                   + rel.get("ajustes_valor_liquido", 0.0))
    # reconciliacao: soma(revenue entrada) == receita_liquida + nao_produto_valor + duplicados_valor + (devolucoes tratadas acima)
    # receita_liquida + nao_produto_valor + duplicados_valor deve igualar a soma do extrato (exato)
    explicado = rel["receita_liquida"] + rel.get("nao_produto_valor", 0.0) + rel.get("duplicados_valor", 0.0)
    if not np.isclose(explicado, total_in, rtol=1e-9, atol=1e-6):
        raise ContractError(f"sales: reconciliacao falhou ({explicado} vs {total_in})")
    rel["reconciliado_com_entrada"] = True
    rel["linhas_saida"] = int(len(sales))
    rets = ret.reset_index(drop=True) if len(ret) else pd.DataFrame(columns=d.columns)
    rets.attrs["ajustes_valor"] = adj.reset_index(drop=True)
    return sales, rets, rel


def prepare_stock(df: pd.DataFrame, negative: str = "clip", duplicates: str = "last"):
    """negative: 'clip' (stock<0 -> 0, sinalizado; negativos de ERP sao quase sempre
    movimentos nao registados), 'reject'. duplicates: 'last' (fica o ultimo registo do dia), 'reject'."""
    if negative not in ("clip", "reject") or duplicates not in ("last", "reject"):
        raise ContractError("prepare_stock: politica invalida")
    d = df.copy(); rel = {"linhas_entrada": int(len(d))}
    d["stock_qty"] = pd.to_numeric(d["stock_qty"], errors="coerce")
    d["date"] = parse_dates(d["date"])
    if getattr(d["date"].dt, "tz", None) is not None:
        d["date"] = d["date"].dt.tz_localize(None)
    d["product_id"] = contract.normalize_ids(d["product_id"])
    neg = d["stock_qty"] < 0
    if neg.any():
        if negative == "reject":
            raise ContractError(f"stock: {int(neg.sum())} valores negativos")
        rel["stock_negativo_para_zero"] = int(neg.sum()); d.loc[neg, "stock_qty"] = 0.0
    dup = d.duplicated(["date", "product_id"], keep=False)
    if dup.any():
        if duplicates == "reject":
            raise ContractError(f"stock: {int(dup.sum())} linhas duplicadas (date, product_id)")
        n0 = len(d); d = d.drop_duplicates(["date", "product_id"], keep="last")
        rel["duplicados_removidos"] = int(n0 - len(d))
    return contract.validate_stock(d.reset_index(drop=True)), rel


def parse_dates(values, date_format=None):
    """Fail closed on slash dates unless a format is provided. No locale guessing."""
    if date_format is None and values.astype(str).str.contains("/", regex=False).any():
        raise ContractError("datas com barras exigem date_format explicito; normalizar para ISO YYYY-MM-DD")
    try:
        result = pd.to_datetime(values, format=date_format, errors="raise")
    except (ValueError, TypeError) as exc:
        raise ContractError("datas invalidas ou formato inconsistente") from exc
    return result


def read_erp_csv(path, sep=",", decimal=".", encoding="utf-8", date_format=None):
    """Explicit CSV dialect. Preserve IDs before pandas numeric inference.
    Values already read as integers cannot have lost leading zeros recovered.
    """
    ids = {c:str for c in ("order_id","product_id","customer_id","campaign_id")}
    try:
        d=pd.read_csv(path,sep=sep,decimal=decimal,encoding=encoding,dtype=ids)
        if "date" in d: d["date"]=parse_dates(d["date"],date_format)
        return d
    except (UnicodeError,ValueError) as exc:
        raise ContractError("CSV: confirmar separador, decimal, encoding e date_format") from exc
