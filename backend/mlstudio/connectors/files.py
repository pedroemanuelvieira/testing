"""Conector para ficheiros carregados (CSV/Excel/Parquet exportados do Power BI ou de outras fontes)."""
from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from .base import Column, ConnectorError, DataConnector, SemanticModel, TableInfo, Workspace, describe_dtype
from .dax import DaxError, LocalDaxEngine

WORKSPACE_ID = "uploads"
DATASET_ID = "ficheiros"


def _safe(name: str) -> str:
    name = re.sub(r"\.(csv|txt|xlsx|xls|parquet)$", "", name, flags=re.I)
    return re.sub(r"[^\w\-]+", "_", name).strip("_") or "tabela"


def read_any(filename: str, content: bytes) -> pd.DataFrame:
    """Lê CSV (separador e decimal detetados), Excel ou Parquet."""
    low = filename.lower()
    if low.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(content))
    if low.endswith(".parquet"):
        return pd.read_parquet(io.BytesIO(content))
    text = content.decode("utf-8-sig", errors="replace")
    sample = text[:5000]
    sep = max([";", ",", "\t", "|"], key=sample.count)
    decimal = "," if sep == ";" and re.search(r"\d,\d", sample) else "."
    df = pd.read_csv(io.StringIO(text), sep=sep, decimal=decimal)
    for col in df.columns:  # tenta converter colunas de data
        if df[col].dtype == object or pd.api.types.is_string_dtype(df[col]):
            s = df[col].dropna().astype(str).head(50)
            if len(s) and s.str.match(r"^\d{4}-\d{2}-\d{2}|^\d{2}/\d{2}/\d{4}").mean() > 0.9:
                df[col] = pd.to_datetime(df[col], errors="coerce", dayfirst=s.str.contains("/").any())
    return df


class FileConnector(DataConnector):
    id = "files"
    name = "Ficheiros carregados"
    kind = "files"
    description = "CSV, Excel ou Parquet carregados manualmente (ex.: exportações do Power BI)."
    capabilities = frozenset({"browse", "dax", "upload"})

    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)

    def test_connection(self) -> dict[str, Any]:
        return {"ok": True, "message": f"{len(list(self.folder.glob('*.parquet')))} ficheiro(s) disponível(eis).",
                "details": {"folder": str(self.folder)}}

    def list_workspaces(self) -> list[Workspace]:
        return [Workspace(WORKSPACE_ID, "Carregamentos", "Ficheiros carregados pela equipa.")]

    def list_datasets(self, workspace_id: str) -> list[SemanticModel]:
        return [SemanticModel(DATASET_ID, "Ficheiros", WORKSPACE_ID, "Tabelas carregadas a partir de ficheiros.",
                              tables=len(list(self.folder.glob("*.parquet"))))]

    def _frame(self, table: str) -> pd.DataFrame:
        path = self.folder / f"{_safe(table)}.parquet"
        if not path.exists():
            raise ConnectorError(f"Ficheiro/tabela inexistente: {table}")
        return pd.read_parquet(path)

    def list_tables(self, workspace_id: str, dataset_id: str) -> list[TableInfo]:
        out = []
        for path in sorted(self.folder.glob("*.parquet")):
            df = pd.read_parquet(path)
            out.append(TableInfo(path.stem, [Column(c, describe_dtype(df[c].dtype)) for c in df.columns], len(df)))
        return out

    def execute_dax(self, workspace_id: str, dataset_id: str, query: str,
                    max_rows: Optional[int] = None) -> pd.DataFrame:
        try:
            return LocalDaxEngine(self._frame).run(query, max_rows=max_rows)
        except (DaxError, KeyError) as exc:
            raise ConnectorError(f"Consulta inválida: {exc}") from exc

    def save_upload(self, filename: str, content: bytes, table_name: Optional[str] = None) -> dict[str, Any]:
        df = read_any(filename, content)
        if df.empty:
            raise ConnectorError("O ficheiro não contém dados.")
        df.columns = [str(c).strip() for c in df.columns]
        name = _safe(table_name or filename)
        df.to_parquet(self.folder / f"{name}.parquet", index=False)
        return {"table": name, "rows": int(len(df)), "columns": list(df.columns),
                "workspace_id": WORKSPACE_ID, "dataset_id": DATASET_ID}
