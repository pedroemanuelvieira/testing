"""Contrato comum dos conectores de dados (Power BI e outros).

Todos os agentes falam com os dados através desta interface, por isso trocar o
conector de demonstração pelo conector interno da empresa (ou pela API REST
oficial) não exige alterações no resto da plataforma.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

import pandas as pd

from . import dax


class ConnectorError(RuntimeError):
    """Erro com mensagem pensada para o utilizador final."""


@dataclass
class Workspace:
    id: str
    name: str
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SemanticModel:
    id: str
    name: str
    workspace_id: str
    description: str = ""
    tables: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Column:
    name: str
    data_type: str = "unknown"
    description: str = ""


@dataclass
class TableInfo:
    name: str
    columns: list[Column] = field(default_factory=list)
    row_count: Optional[int] = None
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "row_count": self.row_count,
            "description": self.description,
            "columns": [asdict(c) for c in self.columns],
        }


@dataclass
class Filter:
    column: str
    op: str  # = != > >= < <= in contains
    value: Any

    @classmethod
    def parse(cls, raw: dict[str, Any]) -> "Filter":
        return cls(column=raw["column"], op=raw.get("op", "="), value=raw.get("value"))


class DataConnector(ABC):
    """Interface de um conector.

    Capacidades (``capabilities``):
      - ``browse``: listar workspaces / modelos semânticos / tabelas
      - ``dax``: executar consultas DAX
      - ``write``: escrever tabelas de resultados (ex.: previsões)
      - ``upload``: aceitar ficheiros carregados pelo utilizador
    """

    id: str = "base"
    name: str = "Conector"
    kind: str = "base"
    description: str = ""
    capabilities: frozenset[str] = frozenset({"browse"})

    def info(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "description": self.description,
            "capabilities": sorted(self.capabilities),
        }

    # -------------------------------------------------------------- obrigatórios
    @abstractmethod
    def test_connection(self) -> dict[str, Any]:
        """Devolve {ok: bool, message: str, details: {...}}."""

    @abstractmethod
    def list_workspaces(self) -> list[Workspace]: ...

    @abstractmethod
    def list_datasets(self, workspace_id: str) -> list[SemanticModel]: ...

    @abstractmethod
    def list_tables(self, workspace_id: str, dataset_id: str) -> list[TableInfo]: ...

    # -------------------------------------------------------------- opcionais
    def execute_dax(self, workspace_id: str, dataset_id: str, query: str,
                    max_rows: Optional[int] = None) -> pd.DataFrame:
        raise ConnectorError(f"O conector '{self.name}' não suporta consultas DAX.")

    def read_table(self, workspace_id: str, dataset_id: str, table: str,
                   columns: Optional[list[str]] = None, top: Optional[int] = None,
                   filters: Optional[list[Filter]] = None) -> pd.DataFrame:
        query = dax.build_table_query(table, columns=columns, top=top, filters=filters)
        return self.execute_dax(workspace_id, dataset_id, query, max_rows=top)

    def write_table(self, workspace_id: str, dataset_name: str, table: str,
                    df: pd.DataFrame, mode: str = "replace") -> dict[str, Any]:
        raise ConnectorError(f"O conector '{self.name}' não suporta escrita de tabelas.")

    def table_info(self, workspace_id: str, dataset_id: str, table: str) -> Optional[TableInfo]:
        for t in self.list_tables(workspace_id, dataset_id):
            if t.name == table:
                return t
        return None


def dtype_to_pbi(dtype: Any) -> str:
    """Converte um dtype pandas para o tipo de coluna Power BI (push datasets)."""
    if pd.api.types.is_bool_dtype(dtype):
        return "Boolean"
    if pd.api.types.is_integer_dtype(dtype):
        return "Int64"
    if pd.api.types.is_float_dtype(dtype):
        return "Double"
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return "DateTime"
    return "String"


def describe_dtype(dtype: Any) -> str:
    if pd.api.types.is_bool_dtype(dtype):
        return "boolean"
    if pd.api.types.is_integer_dtype(dtype):
        return "integer"
    if pd.api.types.is_float_dtype(dtype):
        return "decimal"
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return "datetime"
    return "text"
