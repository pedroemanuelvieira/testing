"""Conector de demonstração que imita o Power BI Service com dados sintéticos.

Suporta navegação (workspaces → modelos semânticos → tabelas), consultas DAX
(subconjunto, via ``LocalDaxEngine``) e escrita de tabelas de resultados, que
aparecem num modelo semântico "Resultados ML" — exatamente como acontecerá com
o conector interno em produção.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from . import demo_data
from .base import Column, ConnectorError, DataConnector, SemanticModel, TableInfo, Workspace, describe_dtype
from .dax import DaxError, LocalDaxEngine

RESULTS_DATASET = "ds-resultados-ml"


def _safe(name: str) -> str:
    return re.sub(r"[^\w\-]+", "_", name)


class DemoConnector(DataConnector):
    id = "demo"
    name = "Power BI (demonstração)"
    kind = "demo"
    description = (
        "Workspaces e modelos semânticos sintéticos que imitam o Power BI Service, "
        "para aprender e testar o fluxo completo sem dados reais."
    )
    capabilities = frozenset({"browse", "dax", "write"})

    def __init__(self, writes_dir: Path):
        self.writes_dir = Path(writes_dir)
        self.writes_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ navegação
    def test_connection(self) -> dict[str, Any]:
        n_tables = sum(len(ds["tables"]) for ws in demo_data.DEMO_CATALOG.values() for ds in ws["datasets"].values())
        return {"ok": True, "message": "Ligação de demonstração ativa.",
                "details": {"workspaces": len(demo_data.DEMO_CATALOG), "tables": n_tables}}

    def list_workspaces(self) -> list[Workspace]:
        return [Workspace(id=k, name=v["name"], description=v["description"]) for k, v in demo_data.DEMO_CATALOG.items()]

    def _written(self, workspace_id: str) -> list[Path]:
        folder = self.writes_dir / _safe(workspace_id)
        return sorted(folder.glob("*.parquet")) if folder.exists() else []

    def list_datasets(self, workspace_id: str) -> list[SemanticModel]:
        ws = demo_data.DEMO_CATALOG.get(workspace_id)
        if ws is None:
            raise ConnectorError(f"Workspace inexistente: {workspace_id}")
        out = [SemanticModel(id=k, name=v["name"], workspace_id=workspace_id, description=v["description"],
                             tables=len(v["tables"])) for k, v in ws["datasets"].items()]
        written = self._written(workspace_id)
        if written:
            out.append(SemanticModel(id=RESULTS_DATASET, name="Resultados ML", workspace_id=workspace_id,
                                     description="Tabelas de previsões publicadas pela plataforma.",
                                     tables=len(written)))
        return out

    def _dataset(self, workspace_id: str, dataset_id: str) -> dict:
        ws = demo_data.DEMO_CATALOG.get(workspace_id)
        if ws is None or dataset_id not in ws["datasets"]:
            raise ConnectorError(f"Modelo semântico inexistente: {workspace_id}/{dataset_id}")
        return ws["datasets"][dataset_id]

    def _frame(self, workspace_id: str, dataset_id: str, table: str) -> pd.DataFrame:
        if dataset_id == RESULTS_DATASET:
            path = self.writes_dir / _safe(workspace_id) / f"{_safe(table)}.parquet"
            if not path.exists():
                raise ConnectorError(f"Tabela inexistente: {table}")
            return pd.read_parquet(path)
        ds = self._dataset(workspace_id, dataset_id)
        if table not in ds["tables"]:
            raise ConnectorError(f"Tabela '{table}' não existe em '{ds['name']}'.")
        return demo_data.get_table(table)

    def list_tables(self, workspace_id: str, dataset_id: str) -> list[TableInfo]:
        if dataset_id == RESULTS_DATASET:
            names = [p.stem for p in self._written(workspace_id)]
        else:
            names = list(self._dataset(workspace_id, dataset_id)["tables"])
        out = []
        for name in names:
            df = self._frame(workspace_id, dataset_id, name)
            out.append(TableInfo(name=name, row_count=len(df),
                                 columns=[Column(c, describe_dtype(df[c].dtype)) for c in df.columns]))
        return out

    # ------------------------------------------------------------------ dados
    def execute_dax(self, workspace_id: str, dataset_id: str, query: str,
                    max_rows: Optional[int] = None) -> pd.DataFrame:
        engine = LocalDaxEngine(lambda t: self._frame(workspace_id, dataset_id, t))
        try:
            return engine.run(query, max_rows=max_rows)
        except (DaxError, KeyError) as exc:
            raise ConnectorError(f"Consulta DAX inválida para o conector de demonstração: {exc}") from exc

    def write_table(self, workspace_id: str, dataset_name: str, table: str, df: pd.DataFrame,
                    mode: str = "replace") -> dict[str, Any]:
        folder = self.writes_dir / _safe(workspace_id)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{_safe(table)}.parquet"
        if mode == "append" and path.exists():
            df = pd.concat([pd.read_parquet(path), df], ignore_index=True)
        df.to_parquet(path, index=False)
        return {"ok": True, "rows": int(len(df)), "workspace_id": workspace_id, "dataset": "Resultados ML",
                "dataset_id": RESULTS_DATASET, "table": table,
                "message": f"Tabela '{table}' publicada no modelo semântico 'Resultados ML' ({len(df)} linhas)."}
