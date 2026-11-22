"""Conectores de dados (Power BI Service e ficheiros)."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from ...connectors import ConnectorError, Filter
from ...connectors import dax as daxmod
from ...connectors.files import FileConnector
from ...core.agent import jsonable
from ..deps import orch

router = APIRouter(prefix="/api/connectors", tags=["conectores"])


def _conn(cid: str):
    try:
        return orch().hub.get(cid)
    except ConnectorError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("")
def list_connectors() -> dict[str, Any]:
    hub = orch().hub
    return {"connectors": hub.describe(), "default": hub.default_id()}


@router.get("/{cid}/test")
def test(cid: str) -> dict[str, Any]:
    return _conn(cid).test_connection()


@router.get("/{cid}/workspaces")
def workspaces(cid: str) -> list[dict]:
    try:
        return [w.to_dict() for w in _conn(cid).list_workspaces()]
    except ConnectorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{cid}/workspaces/{ws}/datasets")
def datasets(cid: str, ws: str) -> list[dict]:
    try:
        return [d.to_dict() for d in _conn(cid).list_datasets(ws)]
    except ConnectorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{cid}/workspaces/{ws}/datasets/{ds}/tables")
def tables(cid: str, ws: str, ds: str) -> list[dict]:
    try:
        return [t.to_dict() for t in _conn(cid).list_tables(ws, ds)]
    except ConnectorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class QueryBody(BaseModel):
    workspace_id: str
    dataset_id: str
    table: Optional[str] = None
    query: Optional[str] = None
    columns: Optional[list[str]] = None
    filters: list[dict[str, Any]] = []
    top: int = 100


@router.post("/{cid}/query")
def query(cid: str, body: QueryBody) -> dict[str, Any]:
    conn = _conn(cid)
    top = max(1, min(body.top, 1000))
    try:
        filters = [Filter.parse(f) for f in body.filters]
        if body.query:
            q = body.query
            df = conn.execute_dax(body.workspace_id, body.dataset_id, q, max_rows=top)
        elif body.table:
            q = daxmod.build_table_query(body.table, columns=body.columns, top=top, filters=filters)
            df = conn.read_table(body.workspace_id, body.dataset_id, body.table, columns=body.columns, top=top, filters=filters)
        else:
            raise HTTPException(status_code=400, detail="Indique uma tabela ou uma consulta DAX.")
    except ConnectorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"dax": q, "columns": [{"name": c, "dtype": str(df[c].dtype)} for c in df.columns],
            "rows": jsonable(df.head(top)), "row_count": int(len(df))}


@router.post("/dax/build")
def build_dax(body: QueryBody) -> dict[str, str]:
    if not body.table:
        raise HTTPException(status_code=400, detail="Indique a tabela.")
    return {"dax": daxmod.build_table_query(body.table, columns=body.columns, top=body.top,
                                            filters=[Filter.parse(f) for f in body.filters])}


@router.post("/files/upload")
async def upload(file: UploadFile = File(...), table_name: Optional[str] = Form(None)) -> dict[str, Any]:
    conn = _conn("files")
    assert isinstance(conn, FileConnector)
    content = await file.read()
    if len(content) > 200 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Ficheiro demasiado grande (máx. 200 MB).")
    try:
        return conn.save_upload(file.filename or "ficheiro.csv", content, table_name)
    except (ConnectorError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Não foi possível ler o ficheiro: {exc}") from exc
