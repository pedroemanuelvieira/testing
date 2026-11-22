"""Modelo de conector interno Power BI para o BI ML Studio.

Se o vosso conector já existe, NÃO precisa de o reescrever: o adaptador da
plataforma descobre os métodos automaticamente (ver docs/CONECTOR_POWERBI.md).
Este ficheiro mostra a interface "ideal" — útil para criar uma pequena camada
fina sobre o conector existente quando os nomes ou formatos forem muito
diferentes.

Configuração:
    MLSTUDIO_INTERNAL_CONNECTOR=internal_connector_template:EmpresaPowerBI
    MLSTUDIO_INTERNAL_CONNECTOR_PATH=/caminho/para/esta/pasta
    MLSTUDIO_INTERNAL_CONNECTOR_KWARGS='{"ambiente": "producao"}'

Todos os métodos podem devolver DataFrames, listas de dicionários, o JSON da
API REST (``{"value": [...]}`` / ``{"results": [{"tables": [{"rows": [...]}]}]}``)
ou objetos com atributos ``id``/``name``.
"""
from __future__ import annotations

from typing import Any

import pandas as pd


class EmpresaPowerBI:
    def __init__(self, ambiente: str = "producao"):
        # Aqui inicializa o vosso conector existente (credenciais via cofre / variáveis de ambiente).
        # from empresa.powerbi import Cliente
        # self._c = Cliente(ambiente=ambiente)
        self.ambiente = ambiente

    # ------------------------------------------------------------------ obrigatório
    def list_workspaces(self) -> list[dict[str, Any]]:
        """[{"id": "...", "name": "...", "description": "..."}]"""
        raise NotImplementedError

    def list_datasets(self, workspace_id: str) -> list[dict[str, Any]]:
        """Modelos semânticos do workspace: [{"id": "...", "name": "..."}]"""
        raise NotImplementedError

    def execute_dax(self, workspace_id: str, dataset_id: str, query: str) -> pd.DataFrame:
        """Executa uma consulta DAX (EVALUATE ...) e devolve as linhas.

        Os nomes de colunas no formato da API ('Tabela[coluna]') são limpos
        automaticamente pelo adaptador.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------ opcional
    def list_tables(self, workspace_id: str, dataset_id: str) -> list[dict[str, Any]]:
        """[{"name": "Clientes", "columns": [{"name": "churn", "dataType": "Int64"}], "row_count": 6000}]

        Se não existir, o adaptador usa EVALUATE INFO.VIEW.TABLES() / INFO.VIEW.COLUMNS().
        """
        raise NotImplementedError

    def test_connection(self) -> bool:
        return True

    def write_table(self, workspace_id: str, dataset_name: str, table: str, df: pd.DataFrame,
                    mode: str = "replace") -> dict[str, Any]:
        """Publica a tabela de previsões (ex.: push dataset, lakehouse, dataflow).

        Se não existir, a plataforma exporta CSV/Excel/Parquet para importação manual.
        """
        raise NotImplementedError
