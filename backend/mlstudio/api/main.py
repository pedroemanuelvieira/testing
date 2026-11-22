"""Aplicação FastAPI: API REST + frontend (SPA) servido a partir de frontend/dist."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .. import __version__
from ..config import get_settings
from ..connectors import ConnectorError
from ..core.agent import AgentError
from ..knowledge import get_kb
from ..ml.factory import library_available
from .deps import assistant, orch
from .routers import chat, connectors, knowledge, models, projects

logging.basicConfig(level=os.environ.get("MLSTUDIO_LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="BI ML Studio", version=__version__,
              description="Plataforma de machine learning com agentes especializados para equipas de BI (Power BI).")
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins, allow_methods=["*"], allow_headers=["*"])

for r in (knowledge.router, connectors.router, projects.router, models.router, chat.router):
    app.include_router(r)


@app.exception_handler(AgentError)
@app.exception_handler(ConnectorError)
async def user_error(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/meta")
def meta() -> dict[str, Any]:
    o = orch()
    kb = get_kb()
    return {"version": __version__, "knowledge": kb.stats(), "connectors": o.hub.describe(),
            "default_connector": o.hub.default_id(), "assistant": assistant().status(),
            "libraries": {lib: library_available(lib) for lib in ("lightgbm", "xgboost", "statsmodels")},
            "optuna": _has("optuna"), "max_rows": o.settings.max_rows}


def _has(module: str) -> bool:
    import importlib.util

    return importlib.util.find_spec(module) is not None


# ------------------------------------------------------------------------------ frontend
DIST = Path(os.environ.get("MLSTUDIO_FRONTEND_DIST", Path(__file__).resolve().parents[3] / "frontend" / "dist"))

if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Rota inexistente."})  # type: ignore[return-value]
        candidate = (DIST / full_path).resolve()
        if full_path and DIST in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(DIST / "index.html")
