"""Conectores de dados e o hub que os gere."""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from ..config import Settings, get_settings
from .base import ConnectorError, DataConnector, Filter, SemanticModel, TableInfo, Workspace
from .demo import DemoConnector
from .files import FileConnector

log = logging.getLogger(__name__)

__all__ = ["ConnectorError", "ConnectorHub", "DataConnector", "Filter", "SemanticModel", "TableInfo",
           "Workspace", "get_hub"]


class ConnectorHub:
    """Regista os conectores disponíveis segundo a configuração."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.connectors: dict[str, DataConnector] = {}
        self.errors: dict[str, str] = {}
        if settings.internal_connector:
            try:
                from .internal import InternalConnectorAdapter

                self.connectors["internal"] = InternalConnectorAdapter(
                    settings.internal_connector, name=settings.internal_connector_name,
                    path=settings.internal_connector_path, kwargs=settings.internal_connector_kwargs,
                    methods=settings.internal_connector_methods)
            except ConnectorError as exc:
                self.errors["internal"] = str(exc)
                log.warning("Conector interno indisponível: %s", exc)
        if settings.pbi_tenant_id and settings.pbi_client_id and settings.pbi_client_secret:
            from .rest import PowerBIRestConnector

            self.connectors["rest"] = PowerBIRestConnector(settings.pbi_tenant_id, settings.pbi_client_id,
                                                           settings.pbi_client_secret, settings.pbi_api_base)
        if settings.demo_enabled:
            self.connectors["demo"] = DemoConnector(settings.demo_writes_dir)
        self.connectors["files"] = FileConnector(settings.uploads_dir)

    def register(self, connector: DataConnector) -> None:
        self.connectors[connector.id] = connector

    def get(self, connector_id: str) -> DataConnector:
        if connector_id not in self.connectors:
            reason = self.errors.get(connector_id)
            raise ConnectorError(reason or f"Conector '{connector_id}' não está configurado.")
        return self.connectors[connector_id]

    def default_id(self) -> str:
        for cid in ("internal", "rest", "demo", "files"):
            if cid in self.connectors:
                return cid
        return "files"

    def describe(self) -> list[dict[str, Any]]:
        out = [c.info() | {"default": cid == self.default_id(), "status": "ok"} for cid, c in self.connectors.items()]
        for cid, err in self.errors.items():
            out.append({"id": cid, "name": cid, "kind": cid, "status": "error", "error": err, "capabilities": []})
        return out


@lru_cache(maxsize=1)
def get_hub() -> ConnectorHub:
    return ConnectorHub(get_settings())
