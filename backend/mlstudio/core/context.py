"""Contexto partilhado passado a cada agente."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

from ..config import Settings
from ..connectors import ConnectorHub
from ..knowledge import KnowledgeBase
from ..knowledge.schema import ProblemType, UseCase
from .agent import AgentError, ProgressFn, noop_progress
from .project import Project, ProjectStore
from .registry import ModelRegistry


@dataclass
class AgentContext:
    project: Project
    store: ProjectStore
    registry: ModelRegistry
    hub: ConnectorHub
    kb: KnowledgeBase
    settings: Settings
    progress: ProgressFn = noop_progress
    cache: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------ atalhos
    def data(self, required: bool = True) -> Optional[pd.DataFrame]:
        if "data" not in self.cache:
            if not self.store.has_data(self.project.id):
                if required:
                    raise AgentError("O projeto ainda não tem dados. Execute primeiro o Agente de Dados (passo 2).")
                return None
            self.cache["data"] = self.store.load_data(self.project.id)
        return self.cache["data"].copy()

    @property
    def use_case(self) -> Optional[UseCase]:
        return self.kb.use_case(self.project.use_case_id)

    @property
    def problem(self) -> ProblemType:
        pt = self.kb.problem_type(self.project.problem_type)
        if pt is None:
            raise AgentError(f"Tipo de problema desconhecido: {self.project.problem_type}")
        return pt

    def latest(self, agent_id: str) -> Optional[dict[str, Any]]:
        return self.store.latest_run(self.project, agent_id)

    def save_project(self, **changes: Any) -> Project:
        for k, v in changes.items():
            setattr(self.project, k, v)
        self.store.save(self.project)
        return self.project

    def champion(self) -> Optional[dict[str, Any]]:
        vid = self.project.champion_version_id
        if not vid:
            return None
        try:
            return self.registry.get(vid)
        except KeyError:
            return None
