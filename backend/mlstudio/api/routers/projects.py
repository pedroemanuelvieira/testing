"""Projetos, execução de agentes, piloto automático e tarefas assíncronas."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...agents import AGENTS, TRAINERS, agent_cards
from ...agents.operations import FLOWS
from ...core.agent import jsonable
from ...core.project import DataSource
from ..deps import USER_ERRORS, bad_request, not_found, orch

router = APIRouter(prefix="/api", tags=["projetos"])

EDITABLE = {"name", "description", "area_id", "use_case_id", "problem_type", "source", "target", "positive_class",
            "time_column", "id_columns", "excluded_columns", "features", "series_columns", "value_column", "aggregation",
            "freq", "horizon", "transaction_column", "item_column", "label_column", "selected_models", "model_params",
            "params_locked", "tuning", "cv_folds", "business_costs", "goal", "feature_plan"}


class CreateProject(BaseModel):
    name: Optional[str] = None
    use_case_id: Optional[str] = None
    connector_id: Optional[str] = None
    source: Optional[dict[str, Any]] = None
    problem_type: Optional[str] = None
    description: Optional[str] = None
    area_id: Optional[str] = None


class RunAgent(BaseModel):
    params: dict[str, Any] = {}
    run_async: bool = True


class Autopilot(BaseModel):
    until: Optional[str] = None
    include_deployment: bool = False
    tune: bool = False


def _project_view(project_id: str) -> dict[str, Any]:
    o = orch()
    try:
        p = o.store.get(project_id)
    except KeyError as exc:
        raise not_found("Projeto") from exc
    flow = FLOWS.get(p.problem_type, FLOWS["binary_classification"])
    steps = []
    for sid in flow:
        st = o.kb.step(sid)
        agent_id = TRAINERS.get(p.problem_type, "training") if sid == "treino" else st.agent
        steps.append({"id": sid, "order": st.order, "title": st.title, "agent_id": agent_id,
                      "agent_name": AGENTS[agent_id].card.name, "status": p.step_status(sid),
                      "run_id": p.steps[sid].run_id if sid in p.steps else None})
    champion = None
    if p.champion_version_id:
        try:
            m = o.registry.get(p.champion_version_id)
            champion = {k: m.get(k) for k in ("id", "model_id", "model_name", "stage", "metrics_test", "primary_metric",
                                              "threshold", "kind", "created_at", "version")}
        except KeyError:
            pass
    done = sum(s["status"] in ("done", "warning") for s in steps)
    uc = o.kb.use_case(p.use_case_id)
    return {"project": jsonable(p.model_dump()), "steps": steps, "progress": done / len(steps) if steps else 0,
            "champion": champion, "use_case": uc.model_dump() if uc else None,
            "has_data": o.store.has_data(p.id), "jobs": [j.to_dict(False) for j in o.jobs.list(p.id)[:5]]}


@router.get("/projects")
def list_projects() -> list[dict[str, Any]]:
    o = orch()
    out = []
    for p in o.store.list():
        flow = FLOWS.get(p.problem_type, [])
        done = sum(p.step_status(s) in ("done", "warning") for s in flow)
        uc = o.kb.use_case(p.use_case_id)
        out.append({"id": p.id, "name": p.name, "use_case_id": p.use_case_id, "use_case_name": uc.name if uc else None,
                    "area_id": p.area_id, "problem_type": p.problem_type, "progress": done / len(flow) if flow else 0,
                    "updated_at": p.updated_at, "created_at": p.created_at, "rows": p.data_info.get("rows"),
                    "champion_version_id": p.champion_version_id, "production_version_id": p.production_version_id})
    return out


@router.post("/projects")
def create_project(body: CreateProject) -> dict[str, Any]:
    fields = {k: v for k, v in body.model_dump().items() if v is not None and k not in ("name", "use_case_id", "connector_id", "source")}
    try:
        p = orch().create_project(body.name or "", use_case_id=body.use_case_id, connector_id=body.connector_id,
                                  source=body.source, **fields)
    except USER_ERRORS as exc:
        raise bad_request(exc) from exc
    return _project_view(p.id)


@router.get("/projects/{project_id}")
def get_project(project_id: str) -> dict[str, Any]:
    return _project_view(project_id)


@router.patch("/projects/{project_id}")
def update_project(project_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    unknown = set(changes) - EDITABLE
    if unknown:
        raise HTTPException(status_code=400, detail=f"Campos não editáveis: {', '.join(sorted(unknown))}")
    if "source" in changes and changes["source"] is not None:
        changes["source"] = DataSource(**changes["source"]).model_dump()
    try:
        orch().store.update(project_id, **changes)
    except KeyError as exc:
        raise not_found("Projeto") from exc
    except ValueError as exc:
        raise bad_request(exc) from exc
    return _project_view(project_id)


@router.delete("/projects/{project_id}")
def delete_project(project_id: str) -> dict[str, str]:
    orch().delete_project(project_id)
    return {"status": "apagado"}


@router.get("/projects/{project_id}/data/preview")
def data_preview(project_id: str, limit: int = 50) -> dict[str, Any]:
    o = orch()
    try:
        df = o.store.load_data(project_id)
    except (KeyError, FileNotFoundError) as exc:
        raise not_found("Dados do projeto") from exc
    return {"columns": [{"name": c, "dtype": str(df[c].dtype)} for c in df.columns], "rows": jsonable(df.head(min(limit, 500))),
            "row_count": int(len(df))}


@router.get("/projects/{project_id}/runs")
def runs(project_id: str) -> list[dict[str, Any]]:
    try:
        return orch().store.list_runs(project_id)
    except KeyError as exc:
        raise not_found("Projeto") from exc


@router.get("/projects/{project_id}/runs/{run_id}")
def run(project_id: str, run_id: str) -> dict[str, Any]:
    try:
        return orch().store.get_run(project_id, run_id)
    except KeyError as exc:
        raise not_found("Execução") from exc


@router.get("/projects/{project_id}/latest")
def latest(project_id: str) -> dict[str, Any]:
    o = orch()
    try:
        p = o.store.get(project_id)
    except KeyError as exc:
        raise not_found("Projeto") from exc
    out = {}
    for aid in p.latest_runs:
        r = o.store.latest_run(p, aid)
        if r:
            out[aid] = r
    return out


@router.post("/projects/{project_id}/agents/{agent_id}/run")
def run_agent(project_id: str, agent_id: str, body: RunAgent) -> dict[str, Any]:
    o = orch()
    if agent_id not in AGENTS:
        raise not_found("Agente")
    try:
        o.store.get(project_id)
    except KeyError as exc:
        raise not_found("Projeto") from exc
    if body.run_async:
        return {"job": o.submit_agent(project_id, agent_id, body.params).to_dict()}
    try:
        return {"result": o.run_agent(project_id, agent_id, body.params)}
    except USER_ERRORS as exc:
        raise bad_request(exc) from exc


@router.post("/projects/{project_id}/autopilot")
def autopilot(project_id: str, body: Autopilot) -> dict[str, Any]:
    o = orch()
    try:
        o.store.get(project_id)
    except KeyError as exc:
        raise not_found("Projeto") from exc
    return {"job": o.submit_autopilot(project_id, until=body.until, include_deployment=body.include_deployment,
                                      tune=body.tune).to_dict()}


@router.get("/projects/{project_id}/models")
def project_models(project_id: str) -> list[dict[str, Any]]:
    return [_model_summary(m) for m in orch().registry.list(project_id)]


def _model_summary(m: dict[str, Any]) -> dict[str, Any]:
    keys = ("id", "project_id", "project_name", "use_case_id", "problem_type", "kind", "model_id", "model_name", "version",
            "stage", "is_champion", "primary_metric", "metrics_test", "metrics_cv", "baseline_metrics", "threshold",
            "created_at", "promoted_at", "last_scoring", "train_rows", "test_rows", "params", "tuned")
    out = {k: m.get(k) for k in keys}
    out["monitoring"] = (m.get("monitoring") or [])[-1:] or None
    return out


@router.get("/jobs")
def jobs(project_id: Optional[str] = None) -> list[dict[str, Any]]:
    return [j.to_dict(False) for j in orch().jobs.list(project_id)[:50]]


@router.get("/jobs/{job_id}")
def job(job_id: str) -> dict[str, Any]:
    try:
        return orch().jobs.get(job_id).to_dict()
    except KeyError as exc:
        raise not_found("Tarefa") from exc


@router.get("/agents")
def agents() -> dict[str, Any]:
    o = orch()
    return {"agents": agent_cards(), "trainers": TRAINERS,
            "flows": {pt: o.flow(pt) for pt in TRAINERS}}
