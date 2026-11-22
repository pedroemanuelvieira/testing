"""Adaptador para o conector Power BI desenvolvido internamente.

A plataforma não conhece a API exata do vosso conector, por isso este adaptador:

1. Importa o conector a partir de ``"pacote.modulo:ClasseOuFabrica"``
   (``MLSTUDIO_INTERNAL_CONNECTOR``), opcionalmente acrescentando uma pasta ao
   ``sys.path`` (``MLSTUDIO_INTERNAL_CONNECTOR_PATH``) e passando argumentos ao
   construtor (``MLSTUDIO_INTERNAL_CONNECTOR_KWARGS``).
2. Descobre o método certo para cada operação. Por omissão tenta nomes comuns
   (``list_workspaces``/``get_groups``/``run_dax``/...); pode fixá-los com
   ``MLSTUDIO_INTERNAL_CONNECTOR_METHODS`` (JSON), por exemplo::

       {"list_workspaces": "obter_workspaces", "execute_dax": "executar_consulta"}

3. Passa os argumentos pelo nome quando o método usa nomes conhecidos
   (``workspace_id``/``group_id``/``workspace``, ``dataset_id``/``semantic_model``,
   ``query``/``dax``...) ou por posição caso contrário.
4. Normaliza as respostas: DataFrame, lista de dicionários, JSON da API REST
   ``executeQueries`` (``results[0].tables[0].rows``), respostas ``{"value": [...]}``
   ou objetos com atributos ``id``/``name``.

Se o conector interno não tiver forma de listar tabelas, o adaptador usa as
funções DAX ``INFO.VIEW.TABLES()`` / ``INFO.VIEW.COLUMNS()``.
"""
from __future__ import annotations

import importlib
import inspect
import sys
from typing import Any, Callable, Optional

import pandas as pd

from . import dax
from .base import (
    Column,
    ConnectorError,
    DataConnector,
    Filter,
    SemanticModel,
    TableInfo,
    Workspace,
    describe_dtype,
)

DEFAULT_METHODS: dict[str, list[str]] = {
    "test_connection": ["test_connection", "ping", "health_check", "check_connection", "testar_ligacao"],
    "list_workspaces": ["list_workspaces", "get_workspaces", "workspaces", "list_groups", "get_groups",
                        "listar_workspaces", "obter_workspaces"],
    "list_datasets": ["list_datasets", "get_datasets", "datasets", "list_semantic_models", "get_semantic_models",
                      "listar_datasets", "listar_modelos_semanticos", "obter_datasets"],
    "list_tables": ["list_tables", "get_tables", "tables", "listar_tabelas", "obter_tabelas"],
    "execute_dax": ["execute_dax", "run_dax", "execute_query", "execute_queries", "run_query", "query",
                    "dax_query", "executar_dax", "executar_consulta"],
    "read_table": ["read_table", "get_table", "get_table_data", "fetch_table", "table_to_dataframe",
                   "ler_tabela", "obter_tabela"],
    "write_table": ["write_table", "push_table", "push_dataframe", "upload_dataframe", "write_dataframe",
                    "push_rows", "escrever_tabela", "publicar_tabela"],
}

ARG_ALIASES: dict[str, set[str]] = {
    "workspace_id": {"workspace_id", "group_id", "workspace", "group", "groupid", "workspaceid", "ws", "ws_id"},
    "dataset_id": {"dataset_id", "dataset", "semantic_model_id", "semantic_model", "model_id", "datasetid", "ds_id"},
    "query": {"query", "dax", "dax_query", "consulta", "expression", "statement"},
    "table": {"table", "table_name", "tabela", "nome_tabela"},
    "df": {"df", "dataframe", "data", "frame", "dados", "rows"},
    "dataset_name": {"dataset_name", "nome_dataset", "semantic_model_name"},
    "mode": {"mode", "modo", "if_exists"},
    "max_rows": {"max_rows", "top", "limit", "n_rows"},
    "columns": {"columns", "colunas"},
}


def _load_target(target: str, path: Optional[str] = None) -> Any:
    if path and path not in sys.path:
        sys.path.insert(0, path)
    if ":" not in target:
        raise ConnectorError("MLSTUDIO_INTERNAL_CONNECTOR deve ter o formato 'pacote.modulo:ClasseOuFabrica'.")
    module_name, attr = target.split(":", 1)
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise ConnectorError(f"Não foi possível importar o conector interno '{module_name}': {exc}") from exc
    obj = module
    for part in attr.split("."):
        obj = getattr(obj, part, None)
        if obj is None:
            raise ConnectorError(f"'{attr}' não existe em '{module_name}'.")
    return obj


def _get(item: Any, *keys: str, default: Any = None) -> Any:
    for k in keys:
        if isinstance(item, dict) and k in item and item[k] is not None:
            return item[k]
        if not isinstance(item, dict) and getattr(item, k, None) is not None:
            return getattr(item, k)
    return default


def _as_list(result: Any) -> list[Any]:
    if result is None:
        return []
    if isinstance(result, pd.DataFrame):
        return result.to_dict(orient="records")
    if isinstance(result, dict):
        for key in ("value", "items", "results", "data"):
            if isinstance(result.get(key), list):
                return result[key]
        return [result]
    if isinstance(result, (list, tuple, set)):
        return list(result)
    return [result]


def to_dataframe(result: Any) -> pd.DataFrame:
    """Normaliza o resultado de uma consulta para DataFrame."""
    if isinstance(result, pd.DataFrame):
        df = result
    elif isinstance(result, dict) and "results" in result:  # formato executeQueries
        try:
            rows = result["results"][0]["tables"][0]["rows"]
        except (KeyError, IndexError, TypeError) as exc:
            errors = result.get("error") or result.get("results", [{}])[0].get("error")
            raise ConnectorError(f"Resposta DAX sem linhas: {errors or exc}") from exc
        df = pd.DataFrame(rows)
    elif isinstance(result, dict) and "rows" in result:
        df = pd.DataFrame(result["rows"], columns=result.get("columns"))
    elif isinstance(result, (list, tuple)):
        df = pd.DataFrame(list(result))
    elif hasattr(result, "to_pandas"):
        df = result.to_pandas()
    else:
        raise ConnectorError(f"Formato de resposta não reconhecido: {type(result).__name__}")
    df = df.rename(columns={c: dax.clean_column_name(str(c)) for c in df.columns})
    for col in df.columns:
        if df[col].dtype == object or pd.api.types.is_string_dtype(df[col]):
            sample = df[col].dropna().astype(str).head(20)
            if len(sample) and sample.str.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}").all():
                df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


class InternalConnectorAdapter(DataConnector):
    id = "internal"
    kind = "internal"
    description = "Conector Power BI desenvolvido internamente, ligado através de um adaptador configurável."

    def __init__(self, target: Any, *, name: str = "Power BI (conector interno)", path: Optional[str] = None,
                 kwargs: Optional[dict[str, Any]] = None, methods: Optional[dict[str, Any]] = None):
        self.name = name
        self.target_repr = target if isinstance(target, str) else type(target).__name__
        obj = _load_target(target, path) if isinstance(target, str) else target
        if inspect.isclass(obj) or (callable(obj) and inspect.isfunction(obj)):
            obj = obj(**(kwargs or {}))
        self.client = obj
        self.overrides = methods or {}
        self.resolved: dict[str, Optional[str]] = {op: self._resolve_name(op) for op in DEFAULT_METHODS}
        caps = {"browse"}
        if self.resolved["execute_dax"] or self.resolved["read_table"]:
            caps.add("dax")
        if self.resolved["write_table"]:
            caps.add("write")
        self.capabilities = frozenset(caps)
        missing = [op for op in ("list_workspaces", "list_datasets") if not self.resolved[op]]
        if missing:
            raise ConnectorError(
                "O conector interno não expõe métodos para: " + ", ".join(missing)
                + ". Configure MLSTUDIO_INTERNAL_CONNECTOR_METHODS com os nomes corretos.")
        if not self.resolved["execute_dax"] and not self.resolved["read_table"]:
            raise ConnectorError("O conector interno precisa de um método para executar DAX ou ler tabelas.")

    def info(self) -> dict[str, Any]:
        return super().info() | {"target": self.target_repr, "methods": self.resolved}

    # ------------------------------------------------------------------ resolução de métodos
    def _resolve_name(self, op: str) -> Optional[str]:
        override = self.overrides.get(op)
        if override:
            if not callable(getattr(self.client, override, None)):
                raise ConnectorError(f"Método configurado '{override}' para '{op}' não existe no conector interno.")
            return override
        for name in DEFAULT_METHODS[op]:
            if callable(getattr(self.client, name, None)):
                return name
        return None

    def _call(self, op: str, **values: Any) -> Any:
        name = self.resolved.get(op)
        if not name:
            raise ConnectorError(f"Operação '{op}' não disponível no conector interno.")
        fn: Callable[..., Any] = getattr(self.client, name)
        order = ["workspace_id", "dataset_id", "dataset_name", "table", "query", "df", "mode", "max_rows", "columns"]
        args: list[Any] = []
        kwargs: dict[str, Any] = {}
        try:
            params = [p for p in inspect.signature(fn).parameters.values() if p.name != "self"]
        except (TypeError, ValueError):
            params = None
        if params is None:  # sem assinatura (ex.: objetos nativos) → posição canónica
            args = [values[k] for k in order if k in values]
        else:
            remaining = dict(values)
            fixed = [p for p in params if p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)]
            bound: dict[str, Any] = {}
            # 1) parâmetros cujo nome é um alias conhecido
            for p in fixed:
                key = next((k for k, al in ARG_ALIASES.items() if k in remaining and p.name.lower() in al), None)
                if key:
                    bound[p.name] = remaining.pop(key)
            # 2) parâmetros obrigatórios com nomes desconhecidos → valores restantes pela ordem canónica
            for p in fixed:
                if p.name not in bound and p.default is p.empty and remaining:
                    key = next(k for k in order if k in remaining)
                    bound[p.name] = remaining.pop(key)
            if remaining and any(p.kind == p.VAR_KEYWORD for p in params):
                bound.update(remaining)
            for p in fixed:  # parâmetros só-posicionais não aceitam nome
                if p.kind == p.POSITIONAL_ONLY and p.name in bound:
                    args.append(bound.pop(p.name))
            kwargs = bound
        try:
            return fn(*args, **kwargs)
        except ConnectorError:
            raise
        except Exception as exc:  # noqa: BLE001 - mensagem clara para o utilizador
            raise ConnectorError(f"Erro no conector interno ({name}): {exc}") from exc

    # ------------------------------------------------------------------ interface
    def test_connection(self) -> dict[str, Any]:
        try:
            if self.resolved["test_connection"]:
                res = self._call("test_connection")
                ok = bool(res if not isinstance(res, dict) else res.get("ok", True))
                return {"ok": ok, "message": "Conector interno respondeu.", "details": {"methods": self.resolved}}
            ws = self.list_workspaces()
            return {"ok": True, "message": f"Ligação OK — {len(ws)} workspace(s) acessível(eis).",
                    "details": {"methods": self.resolved}}
        except ConnectorError as exc:
            return {"ok": False, "message": str(exc), "details": {"methods": self.resolved}}

    def list_workspaces(self) -> list[Workspace]:
        items = _as_list(self._call("list_workspaces"))
        return [Workspace(id=str(_get(i, "id", "workspace_id", "groupId", default=_get(i, "name"))),
                          name=str(_get(i, "name", "displayName", "nome", default=_get(i, "id"))),
                          description=str(_get(i, "description", "descricao", default="")))
                for i in items]

    def list_datasets(self, workspace_id: str) -> list[SemanticModel]:
        items = _as_list(self._call("list_datasets", workspace_id=workspace_id))
        return [SemanticModel(id=str(_get(i, "id", "dataset_id", "datasetId", default=_get(i, "name"))),
                              name=str(_get(i, "name", "displayName", "nome", default=_get(i, "id"))),
                              workspace_id=workspace_id,
                              description=str(_get(i, "description", "descricao", default="")))
                for i in items]

    def list_tables(self, workspace_id: str, dataset_id: str) -> list[TableInfo]:
        if self.resolved["list_tables"]:
            items = _as_list(self._call("list_tables", workspace_id=workspace_id, dataset_id=dataset_id))
            out = []
            for i in items:
                if isinstance(i, str):
                    out.append(TableInfo(name=i))
                    continue
                cols = []
                for c in _get(i, "columns", "colunas", default=[]) or []:
                    if isinstance(c, str):
                        cols.append(Column(c))
                    else:
                        cols.append(Column(str(_get(c, "name", "nome")), str(_get(c, "dataType", "data_type", "type", default="unknown"))))
                out.append(TableInfo(name=str(_get(i, "name", "nome", "Name")), columns=cols,
                                     row_count=_get(i, "row_count", "rows", "rowCount")))
            return out
        # fallback: funções INFO do DAX
        tables = self.execute_dax(workspace_id, dataset_id, dax.info_tables_query())
        try:
            cols: Optional[pd.DataFrame] = self.execute_dax(workspace_id, dataset_id, dax.info_columns_query())
        except ConnectorError:
            cols = None
        return parse_info_tables(tables, cols)

    def execute_dax(self, workspace_id: str, dataset_id: str, query: str,
                    max_rows: Optional[int] = None) -> pd.DataFrame:
        if not self.resolved["execute_dax"]:
            raise ConnectorError("O conector interno não suporta DAX livre; use a leitura de tabelas.")
        df = to_dataframe(self._call("execute_dax", workspace_id=workspace_id, dataset_id=dataset_id, query=query))
        return df.head(max_rows) if max_rows else df

    def read_table(self, workspace_id: str, dataset_id: str, table: str, columns: Optional[list[str]] = None,
                   top: Optional[int] = None, filters: Optional[list[Filter]] = None) -> pd.DataFrame:
        if self.resolved["read_table"] and not filters:
            df = to_dataframe(self._call("read_table", workspace_id=workspace_id, dataset_id=dataset_id, table=table))
            if columns:
                df = df[[c for c in columns if c in df.columns]]
            return df.head(top) if top else df
        return super().read_table(workspace_id, dataset_id, table, columns=columns, top=top, filters=filters)

    def write_table(self, workspace_id: str, dataset_name: str, table: str, df: pd.DataFrame,
                    mode: str = "replace") -> dict[str, Any]:
        res = self._call("write_table", workspace_id=workspace_id, dataset_name=dataset_name, table=table, df=df, mode=mode)
        info = res if isinstance(res, dict) else {}
        return {"ok": bool(info.get("ok", True)), "rows": int(len(df)), "table": table, "dataset": dataset_name,
                "message": info.get("message", f"Tabela '{table}' enviada através do conector interno."), "raw": info}


def describe_columns(df: pd.DataFrame) -> list[Column]:
    return [Column(c, describe_dtype(df[c].dtype)) for c in df.columns]


def parse_info_tables(tables: pd.DataFrame, cols: Optional[pd.DataFrame]) -> list[TableInfo]:
    """Converte o resultado de INFO.VIEW.TABLES()/COLUMNS() em ``TableInfo``."""
    name_col = next((c for c in tables.columns if c.lower() == "name"), tables.columns[0])
    hidden_col = next((c for c in tables.columns if c.lower() in ("ishidden", "is_hidden")), None)
    if hidden_col is not None:
        tables = tables[~tables[hidden_col].astype(bool)]
    by_table: dict[str, list[Column]] = {}
    if cols is not None and not cols.empty:
        tcol = next((c for c in cols.columns if c.lower() == "table"), None)
        ccol = next((c for c in cols.columns if c.lower() in ("explicitname", "name")), None)
        dcol = next((c for c in cols.columns if c.lower() in ("datatype", "data_type")), None)
        if tcol and ccol:
            for _, r in cols.iterrows():
                if str(r[ccol]).startswith("RowNumber"):
                    continue
                by_table.setdefault(str(r[tcol]), []).append(Column(str(r[ccol]), str(r[dcol]) if dcol else "unknown"))
    return [TableInfo(name=str(n), columns=by_table.get(str(n), [])) for n in tables[name_col]
            if not str(n).startswith(("DateTableTemplate", "LocalDateTable"))]
