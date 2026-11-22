"""Construção de consultas DAX e um interpretador mínimo para conectores locais.

``build_table_query`` gera consultas EVALUATE legíveis que a equipa pode copiar
para o DAX Studio / Power BI Desktop. ``LocalDaxEngine`` interpreta o subconjunto
gerado por este módulo (e consultas simples escritas à mão) sobre DataFrames,
para que os conectores de demonstração e de ficheiros se comportem como o
Power BI.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Callable, Optional

import numpy as np
import pandas as pd

if TYPE_CHECKING:  # pragma: no cover
    from .base import Filter

_OPS = {"=": "=", "==": "=", "!=": "<>", "<>": "<>", ">": ">", ">=": ">=", "<": "<", "<=": "<="}


def quote_table(name: str) -> str:
    return "'" + name.replace("'", "''") + "'"


def quote_col(table: str, col: str) -> str:
    return f"{quote_table(table)}[{col.replace(']', ']]')}]"


def literal(value: Any) -> str:
    if value is None:
        return "BLANK()"
    if isinstance(value, bool):
        return "TRUE()" if value else "FALSE()"
    if isinstance(value, (int, float, np.integer, np.floating)):
        return repr(float(value)) if isinstance(value, (float, np.floating)) else str(int(value))
    if isinstance(value, (datetime, date, pd.Timestamp)):
        d = pd.Timestamp(value)
        return f"DATE({d.year}, {d.month}, {d.day})"
    text = str(value).replace('"', '""')
    return f'"{text}"'


def filter_expr(table: str, f: "Filter") -> str:
    col = quote_col(table, f.column)
    op = f.op.lower()
    if op == "in":
        values = f.value if isinstance(f.value, (list, tuple)) else [f.value]
        return f"{col} IN {{{', '.join(literal(v) for v in values)}}}"
    if op == "contains":
        return f"CONTAINSSTRING({col}, {literal(str(f.value))})"
    if op not in _OPS:
        raise ValueError(f"Operador de filtro não suportado: {f.op}")
    return f"{col} {_OPS[op]} {literal(f.value)}"


def build_table_query(table: str, columns: Optional[list[str]] = None, top: Optional[int] = None,
                      filters: Optional[list["Filter"]] = None) -> str:
    """Gera uma consulta EVALUATE para extrair uma tabela de um modelo semântico."""
    base = quote_table(table)
    if filters:
        conds = " && ".join(filter_expr(table, f) for f in filters)
        base = f"FILTER({quote_table(table)}, {conds})"
    if columns:
        cols = ",\n        ".join(f'"{c}", {quote_col(table, c)}' for c in columns)
        base = f"SELECTCOLUMNS(\n    {base},\n        {cols}\n    )"
    if top:
        base = f"TOPN({int(top)}, {base})"
    return f"EVALUATE\n{base}"


def info_tables_query() -> str:
    return "EVALUATE INFO.VIEW.TABLES()"


def info_columns_query() -> str:
    return "EVALUATE INFO.VIEW.COLUMNS()"


def clean_column_name(name: str) -> str:
    """'Clientes[churn]' → 'churn'; '[Total]' → 'Total' (formato da API executeQueries)."""
    m = re.search(r"\[([^\]]+)\]$", name)
    return m.group(1) if m else name


# --------------------------------------------------------------------------- interpretador

class DaxError(ValueError):
    pass


_TOKEN = re.compile(
    r"""\s*(?:
        (?P<table>'(?:[^']|'')+')(?:\[(?P<tcol>(?:[^\]]|\]\])+)\])? |
        \[(?P<col>(?:[^\]]|\]\])+)\] |
        (?P<str>"(?:[^"]|"")*") |
        (?P<num>-?\d+(?:\.\d+)?) |
        (?P<op>&&|\|\||<>|>=|<=|==|=|>|<|,|\(|\)|\{|\}) |
        (?P<word>[A-Za-z_][\w.]*)
    )""",
    re.VERBOSE,
)


def _tokenize(text: str) -> list[tuple[str, Any]]:
    pos, out = 0, []
    text = re.sub(r"//[^\n]*|--[^\n]*", "", text)
    while pos < len(text):
        if text[pos:].strip() == "":
            break
        m = _TOKEN.match(text, pos)
        if not m:
            raise DaxError(f"DAX não suportado perto de: {text[pos:pos + 30]!r}")
        pos = m.end()
        kind = m.lastgroup
        if m.group("table") is not None:
            name = m.group("table")[1:-1].replace("''", "'")
            if m.group("tcol") is not None:
                out.append(("colref", (name, m.group("tcol").replace("]]", "]"))))
            else:
                out.append(("table", name))
        elif kind == "col":
            out.append(("colref", (None, m.group("col").replace("]]", "]"))))
        elif kind == "str":
            out.append(("str", m.group("str")[1:-1].replace('""', '"')))
        elif kind == "num":
            out.append(("num", float(m.group("num"))))
        elif kind == "op":
            out.append(("op", m.group("op")))
        else:
            out.append(("word", m.group("word").upper()))
    return out


class LocalDaxEngine:
    """Interpreta um subconjunto de DAX sobre DataFrames.

    Suporta: EVALUATE, TOPN, FILTER, SELECTCOLUMNS, CALCULATETABLE (com filtros
    booleanos), SUMMARIZECOLUMNS/SUMMARIZE simples com COUNTROWS/SUM/AVERAGE e
    condições com =, <>, >, >=, <, <=, IN, &&, ||, NOT, CONTAINSSTRING, DATE, BLANK.
    """

    def __init__(self, resolver: Callable[[str], pd.DataFrame]):
        self.resolver = resolver

    def run(self, query: str, max_rows: Optional[int] = None) -> pd.DataFrame:
        toks = _tokenize(query)
        self.toks, self.i = toks, 0
        # DEFINE não suportado de propósito (mensagem clara)
        if self._peek() == ("word", "DEFINE"):
            raise DaxError("DEFINE/VAR não é suportado pelo motor local; use EVALUATE <tabela>.")
        self._expect("word", "EVALUATE")
        df = self._table_expr()
        if self.i < len(self.toks):
            word = self._peek()
            if word == ("word", "ORDER"):
                self.i += 1
                self._expect("word", "BY")
                col = self._next()
                asc = True
                if self._peek() in (("word", "DESC"), ("word", "ASC")):
                    asc = self._next()[1] == "ASC"
                df = df.sort_values(col[1][1], ascending=asc)
            else:
                raise DaxError(f"Token inesperado: {word}")
        if max_rows:
            df = df.head(max_rows)
        return df.reset_index(drop=True)

    # ------------------------------------------------------------------ parsing helpers
    def _peek(self) -> Optional[tuple[str, Any]]:
        return self.toks[self.i] if self.i < len(self.toks) else None

    def _next(self) -> tuple[str, Any]:
        tok = self._peek()
        if tok is None:
            raise DaxError("Fim inesperado da consulta DAX.")
        self.i += 1
        return tok

    def _expect(self, kind: str, value: Any = None) -> tuple[str, Any]:
        tok = self._next()
        if tok[0] != kind or (value is not None and tok[1] != value):
            raise DaxError(f"Esperava {value or kind}, encontrei {tok[1]!r}")
        return tok

    # ------------------------------------------------------------------ table expressions
    def _table_expr(self) -> pd.DataFrame:
        tok = self._next()
        if tok[0] == "table":
            df = self.resolver(tok[1]).copy()
            df.attrs["__table__"] = tok[1]
            return df
        if tok[0] != "word":
            raise DaxError(f"Expressão de tabela inválida: {tok[1]!r}")
        fn = tok[1]
        self._expect("op", "(")
        if fn == "TOPN":
            n = int(self._expect("num")[1])
            self._expect("op", ",")
            df = self._table_expr()
            order_col, asc = None, False
            if self._peek() == ("op", ","):
                self.i += 1
                order_col = self._next()[1][1]
                if self._peek() == ("op", ","):
                    self.i += 1
                    asc = self._next()[1] in ("ASC", 1.0)
            self._expect("op", ")")
            if order_col:
                df = df.sort_values(order_col, ascending=asc)
            return df.head(n)
        if fn in ("FILTER", "CALCULATETABLE"):
            df = self._table_expr()
            table = df.attrs.get("__table__")
            while self._peek() == ("op", ","):
                self.i += 1
                mask = self._bool_expr(df)
                df = df[mask.values]
                df.attrs["__table__"] = table
            self._expect("op", ")")
            return df
        if fn == "SELECTCOLUMNS":
            df = self._table_expr()
            out = {}
            while self._peek() == ("op", ","):
                self.i += 1
                name = self._expect("str")[1]
                self._expect("op", ",")
                out[name] = self._value_expr(df)
            self._expect("op", ")")
            res = pd.DataFrame({k: (v.values if isinstance(v, pd.Series) else v) for k, v in out.items()}, index=df.index)
            res.attrs["__table__"] = df.attrs.get("__table__")
            return res
        if fn in ("SUMMARIZECOLUMNS", "SUMMARIZE"):
            return self._summarize(fn)
        if fn == "DISTINCT":
            df = self._table_expr()
            self._expect("op", ")")
            return df.drop_duplicates()
        raise DaxError(f"Função DAX não suportada pelo motor local: {fn}")

    def _summarize(self, fn: str) -> pd.DataFrame:
        base: Optional[pd.DataFrame] = None
        if fn == "SUMMARIZE":
            base = self._table_expr()
            self._expect("op", ",")
        groups: list[str] = []
        aggs: dict[str, tuple[str, Optional[str]]] = {}
        table_name = None
        while True:
            tok = self._peek()
            if tok and tok[0] == "colref":
                self.i += 1
                table_name = tok[1][0] or table_name
                groups.append(tok[1][1])
            elif tok and tok[0] == "str":
                self.i += 1
                name = tok[1]
                self._expect("op", ",")
                agg = self._expect("word")[1]
                self._expect("op", "(")
                inner = self._next()
                if inner[0] == "table":
                    table_name = table_name or inner[1]
                    col = None
                else:
                    table_name = inner[1][0] or table_name
                    col = inner[1][1]
                self._expect("op", ")")
                aggs[name] = (agg, col)
            else:
                raise DaxError("SUMMARIZECOLUMNS: argumento inválido")
            if self._peek() == ("op", ","):
                self.i += 1
                continue
            break
        self._expect("op", ")")
        if base is None:
            if not table_name:
                raise DaxError("SUMMARIZECOLUMNS sem tabela identificável")
            base = self.resolver(table_name)
        g = base.groupby(groups, dropna=False) if groups else None
        result = {}
        for name, (agg, col) in aggs.items():
            fn_map = {"COUNTROWS": "size", "SUM": "sum", "AVERAGE": "mean", "MIN": "min", "MAX": "max",
                      "DISTINCTCOUNT": "nunique", "COUNT": "count"}
            if agg not in fn_map:
                raise DaxError(f"Agregação não suportada: {agg}")
            if g is None:
                series = base[col] if col else base.iloc[:, 0]
                result[name] = [len(base) if agg == "COUNTROWS" else getattr(series, fn_map[agg])()]
            elif agg == "COUNTROWS":
                result[name] = g.size()
            else:
                result[name] = getattr(g[col], fn_map[agg])()
        if g is None:
            return pd.DataFrame(result)
        out = pd.DataFrame(result).reset_index()
        return out

    # ------------------------------------------------------------------ expressions
    def _bool_expr(self, df: pd.DataFrame) -> pd.Series:
        left = self._bool_term(df)
        while self._peek() == ("op", "||") or self._peek() == ("word", "OR"):
            self.i += 1
            left = left | self._bool_term(df)
        return left

    def _bool_term(self, df: pd.DataFrame) -> pd.Series:
        left = self._bool_factor(df)
        while self._peek() == ("op", "&&") or self._peek() == ("word", "AND"):
            self.i += 1
            left = left & self._bool_factor(df)
        return left

    def _bool_factor(self, df: pd.DataFrame) -> pd.Series:
        tok = self._peek()
        if tok == ("word", "NOT"):
            self.i += 1
            self._expect("op", "(")
            inner = self._bool_expr(df)
            self._expect("op", ")")
            return ~inner
        if tok == ("op", "("):
            self.i += 1
            inner = self._bool_expr(df)
            self._expect("op", ")")
            return inner
        if tok == ("word", "CONTAINSSTRING"):
            self.i += 1
            self._expect("op", "(")
            col = self._value_expr(df)
            self._expect("op", ",")
            needle = str(self._value_expr(df))
            self._expect("op", ")")
            return col.astype(str).str.contains(needle, case=False, regex=False)
        left = self._value_expr(df)
        op = self._next()
        if op == ("word", "IN"):
            self._expect("op", "{")
            values = []
            while True:
                values.append(self._value_expr(df))
                if self._peek() == ("op", ","):
                    self.i += 1
                    continue
                break
            self._expect("op", "}")
            return left.isin(values)
        if op[0] != "op" or op[1] not in ("=", "==", "<>", ">", ">=", "<", "<="):
            raise DaxError(f"Operador inválido: {op[1]!r}")
        right = self._value_expr(df)
        if isinstance(left, pd.Series) and pd.api.types.is_datetime64_any_dtype(left) and not isinstance(right, pd.Series):
            right = pd.Timestamp(right)
        ops = {"=": lambda a, b: a == b, "==": lambda a, b: a == b, "<>": lambda a, b: a != b,
               ">": lambda a, b: a > b, ">=": lambda a, b: a >= b, "<": lambda a, b: a < b, "<=": lambda a, b: a <= b}
        res = ops[op[1]](left, right)
        if not isinstance(res, pd.Series):
            res = pd.Series([bool(res)] * len(df), index=df.index)
        return res.fillna(False)

    def _value_expr(self, df: pd.DataFrame) -> Any:
        tok = self._next()
        kind, val = tok
        if kind == "colref":
            col = val[1]
            if col not in df.columns:
                raise DaxError(f"Coluna inexistente: [{col}]")
            return df[col]
        if kind == "str":
            return val
        if kind == "num":
            return int(val) if float(val).is_integer() else val
        if kind == "word":
            if val in ("TRUE", "FALSE", "BLANK"):
                self._expect("op", "(")
                self._expect("op", ")")
                return {"TRUE": True, "FALSE": False, "BLANK": None}[val]
            if val == "DATE":
                self._expect("op", "(")
                y = int(self._expect("num")[1]); self._expect("op", ",")
                m = int(self._expect("num")[1]); self._expect("op", ",")
                d = int(self._expect("num")[1]); self._expect("op", ")")
                return pd.Timestamp(year=y, month=m, day=d)
        raise DaxError(f"Valor inesperado: {val!r}")
