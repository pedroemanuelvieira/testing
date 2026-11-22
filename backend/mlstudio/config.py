"""Configuração da plataforma.

Lida a partir de variáveis de ambiente e, opcionalmente, de um ficheiro YAML
indicado em ``MLSTUDIO_CONFIG``. As variáveis de ambiente têm prioridade.

Variáveis principais
--------------------
MLSTUDIO_HOME                     Pasta de trabalho (projetos, modelos, exportações). Omissão: ./workspace
MLSTUDIO_DEMO                     "1"/"0" — ativa o conector de demonstração (omissão: 1)
MLSTUDIO_MAX_ROWS                 Nº máximo de linhas usadas no treino (amostragem). Omissão: 200000
MLSTUDIO_INTERNAL_CONNECTOR       "pacote.modulo:ClasseOuFabrica" do conector interno Power BI
MLSTUDIO_INTERNAL_CONNECTOR_PATH  Pasta a acrescentar ao sys.path para importar o conector interno
MLSTUDIO_INTERNAL_CONNECTOR_KWARGS JSON com argumentos do construtor do conector interno
MLSTUDIO_INTERNAL_CONNECTOR_METHODS JSON com o mapeamento operação → método do conector interno
PBI_TENANT_ID / PBI_CLIENT_ID / PBI_CLIENT_SECRET  Service principal para a API REST oficial
MLSTUDIO_CHAT_MODEL               Modelo Claude do assistente (omissão: claude-opus-5-5)
MLSTUDIO_CHAT_EFFORT              low | medium | high (omissão: medium)
MLSTUDIO_CHAT_FALLBACKS           "default" ativa o fallback server-side em recusas; "off" desativa
MLSTUDIO_CHAT_OFFLINE             "1" força o modo offline do assistente
ANTHROPIC_API_KEY                 Chave da API Claude (lida pelo SDK)
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    val = os.environ.get(name)
    return val if val not in (None, "") else default


def _json_env(name: str) -> dict[str, Any]:
    raw = _env(name)
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:  # pragma: no cover - configuração inválida
        raise ValueError(f"{name} não contém JSON válido: {exc}") from exc


@dataclass
class Settings:
    home: Path
    demo_enabled: bool = True
    max_rows: int = 200_000
    random_state: int = 42
    internal_connector: Optional[str] = None
    internal_connector_path: Optional[str] = None
    internal_connector_kwargs: dict[str, Any] = field(default_factory=dict)
    internal_connector_methods: dict[str, Any] = field(default_factory=dict)
    internal_connector_name: str = "Power BI (conector interno)"
    pbi_tenant_id: Optional[str] = None
    pbi_client_id: Optional[str] = None
    pbi_client_secret: Optional[str] = None
    pbi_api_base: str = "https://api.powerbi.com/v1.0/myorg"
    chat_model: str = "claude-opus-5-5"
    chat_effort: str = "medium"
    chat_fallbacks: str = "default"
    chat_offline: bool = False
    cors_origins: list[str] = field(default_factory=lambda: ["*"])

    @property
    def projects_dir(self) -> Path:
        return self.home / "projects"

    @property
    def models_dir(self) -> Path:
        return self.home / "models"

    @property
    def exports_dir(self) -> Path:
        return self.home / "exports"

    @property
    def uploads_dir(self) -> Path:
        return self.home / "uploads"

    @property
    def chats_dir(self) -> Path:
        return self.home / "chats"

    @property
    def demo_writes_dir(self) -> Path:
        return self.home / "powerbi_writes"

    def ensure_dirs(self) -> None:
        for d in (self.home, self.projects_dir, self.models_dir, self.exports_dir,
                  self.uploads_dir, self.chats_dir, self.demo_writes_dir):
            d.mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    file_cfg: dict[str, Any] = {}
    cfg_path = _env("MLSTUDIO_CONFIG")
    if cfg_path and Path(cfg_path).exists():
        file_cfg = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8")) or {}
    internal = file_cfg.get("internal_connector", {}) or {}
    pbi = file_cfg.get("powerbi_rest", {}) or {}
    chat = file_cfg.get("chat", {}) or {}

    home = Path(_env("MLSTUDIO_HOME", file_cfg.get("home", "./workspace"))).resolve()
    settings = Settings(
        home=home,
        demo_enabled=_env("MLSTUDIO_DEMO", str(file_cfg.get("demo", "1"))) not in ("0", "false", "False"),
        max_rows=int(_env("MLSTUDIO_MAX_ROWS", str(file_cfg.get("max_rows", 200_000)))),
        internal_connector=_env("MLSTUDIO_INTERNAL_CONNECTOR", internal.get("target")),
        internal_connector_path=_env("MLSTUDIO_INTERNAL_CONNECTOR_PATH", internal.get("path")),
        internal_connector_kwargs=_json_env("MLSTUDIO_INTERNAL_CONNECTOR_KWARGS") or internal.get("kwargs", {}) or {},
        internal_connector_methods=_json_env("MLSTUDIO_INTERNAL_CONNECTOR_METHODS") or internal.get("methods", {}) or {},
        internal_connector_name=internal.get("name", "Power BI (conector interno)"),
        pbi_tenant_id=_env("PBI_TENANT_ID", pbi.get("tenant_id")),
        pbi_client_id=_env("PBI_CLIENT_ID", pbi.get("client_id")),
        pbi_client_secret=_env("PBI_CLIENT_SECRET"),  # segredos apenas via ambiente
        chat_model=_env("MLSTUDIO_CHAT_MODEL", chat.get("model", "claude-opus-5-5")),
        chat_effort=_env("MLSTUDIO_CHAT_EFFORT", chat.get("effort", "medium")),
        chat_fallbacks=_env("MLSTUDIO_CHAT_FALLBACKS", chat.get("fallbacks", "default")),
        chat_offline=_env("MLSTUDIO_CHAT_OFFLINE", "0") in ("1", "true", "True"),
    )
    settings.ensure_dirs()
    return settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
