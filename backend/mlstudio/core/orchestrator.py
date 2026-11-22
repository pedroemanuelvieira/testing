"""Orquestrador: liga projetos, agentes, conectores, registo de modelos e tarefas assíncronas."""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, Optional

from ..config import Settings, get_settings
from ..connectors import ConnectorHub
from ..knowledge import KnowledgeBase, get_kb
from .agent import AgentError, ProgressFn, noop_progress, now_iso
from .context import AgentContext
from .jobs import JobManager
from .project import DataSource, Project, ProjectStore, StepState
from .registry import ModelRegistry

log = logging.getLogger(__name__)


class Orchestrator:
    def __init__(self, settings: Settings, hub: Optional[ConnectorHub] = None, kb: Optional[KnowledgeBase] = None):
        self.settings = settings
        self.hub = hub or ConnectorHub(settings)
        self.kb = kb or get_kb()
        self.store = ProjectStore(settings.projects_dir)
        self.registry = ModelRegistry(settings.models_dir)
        self.jobs = JobManager()

    # ------------------------------------------------------------------ projetos
    def create_project(self, name: str, use_case_id: Optional[str] = None, connector_id: Optional[str] = None,
                       source: Optional[dict[str, Any]] = None, **fields: Any) -> Project:
        uc = self.kb.use_case(use_case_id)
        if use_case_id and uc is None:
            raise AgentError(f"Caso de uso inexistente: {use_case_id}")
        data: dict[str, Any] = dict(fields)
        if uc:
            data.setdefault("area_id", uc.area)
            data.setdefault("problem_type", uc.problem_type)
            data.setdefault("description", uc.summary)
            data["use_case_id"] = uc.id
        if source:
            data["source"] = DataSource(**source)
        elif uc and uc.demo and (connector_id in (None, "demo")) and "demo" in self.hub.connectors:
            demo = uc.demo
            data["source"] = DataSource(connector_id="demo", workspace_id=demo["workspace"], dataset_id=demo["dataset"],
                                        table=demo["table"])
        elif connector_id:
            data["source"] = DataSource(connector_id=connector_id)
        project = self.store.create(name or (uc.name if uc else "Novo projeto"), **data)
        return project

    def delete_project(self, project_id: str) -> None:
        self.registry.delete_project(project_id)
        self.store.delete(project_id)

    def context(self, project_id: str, progress: ProgressFn = noop_progress) -> AgentContext:
        project = self.store.get(project_id)
        return AgentContext(project=project, store=self.store, registry=self.registry, hub=self.hub, kb=self.kb,
                            settings=self.settings, progress=progress)

    # ------------------------------------------------------------------ agentes
    def run_agent(self, project_id: str, agent_id: str, params: Optional[dict[str, Any]] = None,
                  progress: ProgressFn = noop_progress, ctx: Optional[AgentContext] = None) -> dict[str, Any]:
        from ..agents import AGENTS

        agent = AGENTS.get(agent_id)
        if agent is None:
            raise AgentError(f"Agente desconhecido: {agent_id}")
        with self.store.lock(project_id):
            ctx = ctx or self.context(project_id, progress)
            if not agent.applies_to(ctx.project.problem_type):
                raise AgentError(f"O {agent.card.name} não se aplica a problemas do tipo '{ctx.project.problem_type}'.")
            step = agent.card.step
            try:
                result = agent.execute(ctx, **(params or {}))
            except AgentError:
                if step:
                    self._mark(ctx, step, "error", None)
                raise
            self.store.save_run(ctx.project.id, result)
            ctx.project.latest_runs[agent_id] = result.run_id
            if step:
                self._mark(ctx, step, "warning" if result.status == "warning" else "done", result.run_id, save=False)
            self.store.save(ctx.project)
            return result.to_dict()

    def _mark(self, ctx: AgentContext, step: str, status: str, run_id: Optional[str], save: bool = True) -> None:
        ctx.project.steps[step] = StepState(status=status, run_id=run_id, updated_at=now_iso())
        if save:
            self.store.save(ctx.project)

    def flow(self, problem_type: str) -> list[str]:
        """Sequência de agentes do piloto automático para um tipo de problema."""
        from ..agents import TRAINERS

        trainer = TRAINERS.get(problem_type, "training")
        seq = ["framing", "connector", "profiler", "quality"]
        if problem_type in ("binary_classification", "multiclass_classification", "regression"):
            seq.append("features")
        if problem_type == "association_rules":
            seq.remove("quality")
        seq += ["selection", "advisor", trainer, "evaluation"]
        if problem_type != "association_rules":
            seq.append("explainability")
        if problem_type not in ("forecasting", "association_rules"):
            seq.append("governance")
        return seq

    def autopilot(self, project_id: str, progress: ProgressFn = noop_progress, until: Optional[str] = None,
                  include_deployment: bool = False, tune: bool = False) -> dict[str, Any]:
        project = self.store.get(project_id)
        seq = self.flow(project.problem_type)
        if include_deployment:
            seq.append("deployment")
        seq.append("reporting")
        if until and until in seq:
            seq = seq[: seq.index(until) + 1]
        summary = []
        ctx = self.context(project_id)
        for i, aid in enumerate(seq):
            from ..agents import AGENTS

            name = AGENTS[aid].card.name
            base = i / len(seq)

            def sub(f: float, msg: str, base: float = base, name: str = name) -> None:
                progress(base + f / len(seq), f"{name}: {msg}")

            progress(base, f"{name}…")
            ctx = self.context(project_id, sub)
            params: dict[str, Any] = {"tune": True} if (aid == "training" and tune) else {}
            if aid == "connector" and self.store.has_data(project_id):
                summary.append({"agent_id": aid, "name": name, "status": "skipped", "summary": "Dados já carregados."})
                self._mark(ctx, "dados", "done", ctx.project.latest_runs.get("connector"))
                continue
            try:
                res = self.run_agent(project_id, aid, params, sub, ctx)
                summary.append({"agent_id": aid, "name": name, "status": res["status"], "summary": res["summary"],
                                "run_id": res["run_id"]})
            except AgentError as exc:
                summary.append({"agent_id": aid, "name": name, "status": "error", "summary": str(exc)})
                break
        progress(1.0, "Piloto automático concluído")
        return {"project_id": project_id, "steps": summary}

    # ------------------------------------------------------------------ assíncrono
    def submit_agent(self, project_id: str, agent_id: str, params: Optional[dict[str, Any]] = None):
        return self.jobs.submit(f"agent:{agent_id}", lambda progress: self.run_agent(project_id, agent_id, params, progress),
                                project_id=project_id)

    def submit_autopilot(self, project_id: str, **kw: Any):
        return self.jobs.submit("autopilot", lambda progress: self.autopilot(project_id, progress, **kw), project_id=project_id)


@lru_cache(maxsize=1)
def get_orchestrator() -> Orchestrator:
    return Orchestrator(get_settings())
