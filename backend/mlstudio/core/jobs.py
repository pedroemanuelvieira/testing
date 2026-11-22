"""Execução assíncrona de tarefas longas (treino, piloto automático) com progresso."""
from __future__ import annotations

import logging
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .agent import jsonable, now_iso

log = logging.getLogger(__name__)


@dataclass
class Job:
    id: str
    kind: str
    project_id: Optional[str] = None
    status: str = "queued"  # queued | running | done | error
    progress: float = 0.0
    message: str = "Em fila"
    log: list[dict[str, Any]] = field(default_factory=list)
    result: Any = None
    error: Optional[str] = None
    created_at: str = field(default_factory=now_iso)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None

    def to_dict(self, include_result: bool = True) -> dict[str, Any]:
        d = {k: getattr(self, k) for k in ("id", "kind", "project_id", "status", "progress", "message", "log",
                                           "error", "created_at", "started_at", "finished_at")}
        if include_result:
            d["result"] = self.result
        return jsonable(d)


class JobManager:
    def __init__(self, max_workers: int = 2):
        self.pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="mlstudio-job")
        self.jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def submit(self, kind: str, fn: Callable[..., Any], *args: Any, project_id: Optional[str] = None,
               **kwargs: Any) -> Job:
        job = Job(id="job_" + uuid.uuid4().hex[:10], kind=kind, project_id=project_id)
        with self._lock:
            self.jobs[job.id] = job
            if len(self.jobs) > 500:  # limpa os mais antigos
                for old in sorted(self.jobs.values(), key=lambda j: j.created_at)[:100]:
                    self.jobs.pop(old.id, None)

        def progress(p: float, msg: str) -> None:
            job.progress = max(0.0, min(1.0, float(p)))
            job.message = msg
            job.log.append({"t": now_iso(), "p": round(job.progress, 3), "msg": msg})

        def runner() -> None:
            job.status, job.started_at = "running", now_iso()
            try:
                job.result = jsonable(fn(*args, progress=progress, **kwargs))
                job.status, job.progress, job.message = "done", 1.0, "Concluído"
            except Exception as exc:  # noqa: BLE001
                log.error("Job %s falhou: %s\n%s", job.id, exc, traceback.format_exc())
                job.status, job.error, job.message = "error", str(exc), f"Erro: {exc}"
            finally:
                job.finished_at = now_iso()

        self.pool.submit(runner)
        return job

    def get(self, job_id: str) -> Job:
        if job_id not in self.jobs:
            raise KeyError(job_id)
        return self.jobs[job_id]

    def list(self, project_id: Optional[str] = None) -> list[Job]:
        jobs = [j for j in self.jobs.values() if project_id is None or j.project_id == project_id]
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)
