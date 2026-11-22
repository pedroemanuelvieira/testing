"""Projetos de ML: estado, snapshot de dados e histórico de execuções dos agentes."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import threading
import uuid
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from pydantic import BaseModel, Field

from .agent import AgentResult, jsonable, now_iso


class DataSource(BaseModel):
    connector_id: str
    workspace_id: Optional[str] = None
    dataset_id: Optional[str] = None
    table: Optional[str] = None
    query: Optional[str] = None  # DAX personalizado
    columns: Optional[list[str]] = None
    filters: list[dict[str, Any]] = Field(default_factory=list)
    top: Optional[int] = None


class StepState(BaseModel):
    status: str = "pending"  # pending | done | warning | skipped | error
    run_id: Optional[str] = None
    updated_at: Optional[str] = None


class Project(BaseModel):
    id: str
    name: str
    description: str = ""
    area_id: Optional[str] = None
    use_case_id: Optional[str] = None
    problem_type: str = "binary_classification"
    source: Optional[DataSource] = None
    data_info: dict[str, Any] = Field(default_factory=dict)
    # configuração do problema
    target: Optional[str] = None
    positive_class: Any = None
    time_column: Optional[str] = None
    id_columns: list[str] = Field(default_factory=list)
    excluded_columns: list[str] = Field(default_factory=list)
    features: list[str] = Field(default_factory=list)  # lista explícita (não supervisionado)
    series_columns: list[str] = Field(default_factory=list)
    value_column: Optional[str] = None
    aggregation: str = "sum"
    freq: Optional[str] = None
    horizon: Optional[int] = None
    transaction_column: Optional[str] = None
    item_column: Optional[str] = None
    label_column: Optional[str] = None
    # artefactos dos agentes
    column_roles: dict[str, str] = Field(default_factory=dict)
    feature_plan: dict[str, Any] = Field(default_factory=dict)
    selected_models: list[str] = Field(default_factory=list)
    model_params: dict[str, dict[str, Any]] = Field(default_factory=dict)
    params_locked: list[str] = Field(default_factory=list)
    tuning: dict[str, Any] = Field(default_factory=lambda: {"enabled": False, "n_iter": 12, "method": "random"})
    cv_folds: int = 5
    business_costs: dict[str, float] = Field(default_factory=dict)
    goal: str = "equilibrado"
    champion_version_id: Optional[str] = None
    production_version_id: Optional[str] = None
    steps: dict[str, StepState] = Field(default_factory=dict)
    latest_runs: dict[str, str] = Field(default_factory=dict)
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)

    def step_status(self, step_id: str) -> str:
        return self.steps.get(step_id, StepState()).status

    @property
    def supervised(self) -> bool:
        return self.problem_type in ("binary_classification", "multiclass_classification", "regression")


def _slug(text: str) -> str:
    import unicodedata

    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:30].strip("-") or "projeto"


class ProjectStore:
    """Guarda projetos em ``<home>/projects/<id>/`` (project.json, data.parquet, runs/)."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, threading.RLock] = {}
        self._data_cache: dict[str, tuple[float, pd.DataFrame]] = {}
        self._glock = threading.Lock()

    def lock(self, project_id: str) -> threading.RLock:
        with self._glock:
            return self._locks.setdefault(project_id, threading.RLock())

    def _dir(self, project_id: str) -> Path:
        if not re.fullmatch(r"[\w\-]+", project_id):
            raise KeyError(project_id)
        return self.root / project_id

    # ------------------------------------------------------------------ CRUD
    def create(self, name: str, **fields: Any) -> Project:
        pid = f"{_slug(name)}-{uuid.uuid4().hex[:6]}"
        project = Project(id=pid, name=name, **fields)
        self._dir(pid).mkdir(parents=True, exist_ok=False)
        (self._dir(pid) / "runs").mkdir()
        self.save(project)
        return project

    def save(self, project: Project) -> Project:
        project.updated_at = now_iso()
        path = self._dir(project.id) / "project.json"
        with self.lock(project.id):
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(jsonable(project.model_dump()), ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(path)
        return project

    def get(self, project_id: str) -> Project:
        path = self._dir(project_id) / "project.json"
        if not path.exists():
            raise KeyError(project_id)
        return Project(**json.loads(path.read_text(encoding="utf-8")))

    def list(self) -> list[Project]:
        out = []
        for p in self.root.glob("*/project.json"):
            try:
                out.append(Project(**json.loads(p.read_text(encoding="utf-8"))))
            except (ValueError, OSError):
                continue
        return sorted(out, key=lambda p: p.updated_at, reverse=True)

    def update(self, project_id: str, **changes: Any) -> Project:
        with self.lock(project_id):
            project = self.get(project_id)
            data = project.model_dump()
            data.update(changes)
            project = Project(**data)
            return self.save(project)

    def delete(self, project_id: str) -> None:
        shutil.rmtree(self._dir(project_id), ignore_errors=True)
        self._data_cache.pop(project_id, None)

    # ------------------------------------------------------------------ dados
    def data_path(self, project_id: str) -> Path:
        return self._dir(project_id) / "data.parquet"

    def save_data(self, project_id: str, df: pd.DataFrame) -> dict[str, Any]:
        df = df.copy()
        df.columns = [str(c) for c in df.columns]
        path = self.data_path(project_id)
        df.to_parquet(path, index=False)
        digest = hashlib.sha1(pd.util.hash_pandas_object(df.head(5000), index=False).values.tobytes()).hexdigest()[:12]
        info = {"rows": int(len(df)), "columns": int(df.shape[1]), "column_names": list(df.columns),
                "loaded_at": now_iso(), "hash": digest, "size_mb": round(path.stat().st_size / 1e6, 2)}
        self._data_cache.pop(project_id, None)
        return info

    def load_data(self, project_id: str) -> pd.DataFrame:
        path = self.data_path(project_id)
        if not path.exists():
            raise FileNotFoundError("O projeto ainda não tem dados carregados. Execute o passo 'Dados'.")
        mtime = path.stat().st_mtime
        cached = self._data_cache.get(project_id)
        if cached and cached[0] == mtime:
            return cached[1].copy()
        df = pd.read_parquet(path)
        self._data_cache[project_id] = (mtime, df)
        return df.copy()

    def has_data(self, project_id: str) -> bool:
        return self.data_path(project_id).exists()

    # ------------------------------------------------------------------ execuções
    def save_run(self, project_id: str, result: AgentResult) -> None:
        path = self._dir(project_id) / "runs" / f"{result.run_id}.json"
        path.write_text(json.dumps(result.to_dict(), ensure_ascii=False), encoding="utf-8")

    def get_run(self, project_id: str, run_id: str) -> dict[str, Any]:
        if not re.fullmatch(r"run_\w+", run_id):
            raise KeyError(run_id)
        path = self._dir(project_id) / "runs" / f"{run_id}.json"
        if not path.exists():
            raise KeyError(run_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def list_runs(self, project_id: str) -> list[dict[str, Any]]:
        out = []
        for p in (self._dir(project_id) / "runs").glob("*.json"):
            d = json.loads(p.read_text(encoding="utf-8"))
            out.append({k: d.get(k) for k in ("run_id", "agent_id", "title", "summary", "status", "created_at", "duration_ms")})
        return sorted(out, key=lambda r: r["created_at"], reverse=True)

    def latest_run(self, project: Project, agent_id: str) -> Optional[dict[str, Any]]:
        run_id = project.latest_runs.get(agent_id)
        if not run_id:
            return None
        try:
            return self.get_run(project.id, run_id)
        except KeyError:
            return None
