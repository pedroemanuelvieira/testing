"""Conector de referência para a API REST oficial do Power BI.

Usado quando o conector interno não está configurado mas existe um service
principal com acesso aos workspaces. Autentica com MSAL (client credentials) e
usa ``executeQueries`` para DAX e a API de push datasets para escrever
resultados.
"""
from __future__ import annotations

import math
import time
from typing import Any, Optional

import pandas as pd
import requests

from . import dax
from .base import ConnectorError, DataConnector, SemanticModel, TableInfo, Workspace, dtype_to_pbi
from .internal import parse_info_tables, to_dataframe

SCOPE = ["https://analysis.windows.net/powerbi/api/.default"]
MAX_PUSH_ROWS = 10_000


class PowerBIRestConnector(DataConnector):
    id = "rest"
    name = "Power BI (API REST oficial)"
    kind = "rest"
    description = "API REST do Power BI Service com service principal (executeQueries + push datasets)."
    capabilities = frozenset({"browse", "dax", "write"})

    def __init__(self, tenant_id: str, client_id: str, client_secret: str,
                 api_base: str = "https://api.powerbi.com/v1.0/myorg", session: Optional[requests.Session] = None,
                 token_provider: Optional[Any] = None):
        self.tenant_id, self.client_id, self.client_secret = tenant_id, client_id, client_secret
        self.api_base = api_base.rstrip("/")
        self.session = session or requests.Session()
        self._token_provider = token_provider
        self._token: Optional[str] = None
        self._token_exp = 0.0

    # ------------------------------------------------------------------ http
    def _get_token(self) -> str:
        if self._token_provider is not None:
            return self._token_provider()
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        import msal  # import tardio: só necessário com este conector

        app = msal.ConfidentialClientApplication(
            self.client_id, authority=f"https://login.microsoftonline.com/{self.tenant_id}",
            client_credential=self.client_secret)
        res = app.acquire_token_for_client(scopes=SCOPE)
        if "access_token" not in res:
            raise ConnectorError(f"Falha de autenticação no Azure AD: {res.get('error_description', res)}")
        self._token, self._token_exp = res["access_token"], time.time() + float(res.get("expires_in", 3600))
        return self._token

    def _request(self, method: str, path: str, **kw: Any) -> Any:
        url = f"{self.api_base}{path}"
        for attempt in range(4):
            resp = self.session.request(method, url, headers={"Authorization": f"Bearer {self._get_token()}"},
                                        timeout=120, **kw)
            if resp.status_code == 429 and attempt < 3:
                time.sleep(float(resp.headers.get("Retry-After", 2 ** attempt)))
                continue
            if resp.status_code >= 400:
                try:
                    detail = resp.json().get("error", {}).get("message") or resp.text
                except ValueError:
                    detail = resp.text
                raise ConnectorError(f"Power BI API {resp.status_code}: {detail[:400]}")
            return resp.json() if resp.content else {}
        raise ConnectorError("Power BI API: demasiados pedidos (429).")

    # ------------------------------------------------------------------ interface
    def test_connection(self) -> dict[str, Any]:
        try:
            ws = self.list_workspaces()
            return {"ok": True, "message": f"Autenticado — {len(ws)} workspace(s) acessível(eis).", "details": {}}
        except ConnectorError as exc:
            return {"ok": False, "message": str(exc), "details": {}}

    def list_workspaces(self) -> list[Workspace]:
        data = self._request("GET", "/groups")
        return [Workspace(id=g["id"], name=g.get("name", g["id"])) for g in data.get("value", [])]

    def list_datasets(self, workspace_id: str) -> list[SemanticModel]:
        data = self._request("GET", f"/groups/{workspace_id}/datasets")
        return [SemanticModel(id=d["id"], name=d.get("name", d["id"]), workspace_id=workspace_id,
                              description=d.get("description", "") or "") for d in data.get("value", [])]

    def list_tables(self, workspace_id: str, dataset_id: str) -> list[TableInfo]:
        try:
            tables = self.execute_dax(workspace_id, dataset_id, dax.info_tables_query())
        except ConnectorError:
            data = self._request("GET", f"/groups/{workspace_id}/datasets/{dataset_id}/tables")  # push datasets
            return [TableInfo(name=t["name"]) for t in data.get("value", [])]
        try:
            cols: Optional[pd.DataFrame] = self.execute_dax(workspace_id, dataset_id, dax.info_columns_query())
        except ConnectorError:
            cols = None
        return parse_info_tables(tables, cols)

    def execute_dax(self, workspace_id: str, dataset_id: str, query: str,
                    max_rows: Optional[int] = None) -> pd.DataFrame:
        body = {"queries": [{"query": query}], "serializerSettings": {"includeNulls": True}}
        data = self._request("POST", f"/groups/{workspace_id}/datasets/{dataset_id}/executeQueries", json=body)
        df = to_dataframe(data)
        return df.head(max_rows) if max_rows else df

    def write_table(self, workspace_id: str, dataset_name: str, table: str, df: pd.DataFrame,
                    mode: str = "replace") -> dict[str, Any]:
        datasets = {d.name: d.id for d in self.list_datasets(workspace_id)}
        schema = {"name": table, "columns": [{"name": c, "dataType": dtype_to_pbi(df[c].dtype)} for c in df.columns]}
        if dataset_name not in datasets:
            created = self._request("POST", f"/groups/{workspace_id}/datasets?defaultRetentionPolicy=basicFIFO",
                                    json={"name": dataset_name, "defaultMode": "Push", "tables": [schema]})
            dataset_id = created["id"]
        else:
            dataset_id = datasets[dataset_name]
            self._request("PUT", f"/groups/{workspace_id}/datasets/{dataset_id}/tables/{table}", json=schema)
            if mode == "replace":
                self._request("DELETE", f"/groups/{workspace_id}/datasets/{dataset_id}/tables/{table}/rows")
        out = df.copy()
        for c in out.columns:
            if pd.api.types.is_datetime64_any_dtype(out[c]):
                out[c] = out[c].dt.strftime("%Y-%m-%dT%H:%M:%S")
        records = out.astype(object).where(out.notna(), None).to_dict(orient="records")
        for i in range(math.ceil(len(records) / MAX_PUSH_ROWS)):
            chunk = records[i * MAX_PUSH_ROWS:(i + 1) * MAX_PUSH_ROWS]
            self._request("POST", f"/groups/{workspace_id}/datasets/{dataset_id}/tables/{table}/rows", json={"rows": chunk})
        return {"ok": True, "rows": len(records), "dataset": dataset_name, "dataset_id": dataset_id, "table": table,
                "message": f"{len(records)} linhas enviadas para '{dataset_name}'/{table}."}
