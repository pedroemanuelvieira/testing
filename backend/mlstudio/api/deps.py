"""Dependências partilhadas da API."""
from __future__ import annotations

from functools import lru_cache

from fastapi import HTTPException

from ..chat import Assistant
from ..connectors import ConnectorError
from ..core.agent import AgentError
from ..core.orchestrator import Orchestrator, get_orchestrator


def orch() -> Orchestrator:
    return get_orchestrator()


@lru_cache(maxsize=1)
def assistant() -> Assistant:
    return Assistant(get_orchestrator())


def not_found(what: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{what} não encontrado(a).")


def bad_request(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


USER_ERRORS = (AgentError, ConnectorError, ValueError, FileNotFoundError)
