"""Registo de modelos, scoring online, conselheiro de hiperparâmetros e exportações."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ... import advisor
from ...advisor.profile import DataProfile
from ...agents.common import data_profile
from ...agents.operations import score_frame
from ...core.agent import jsonable
from ..deps import USER_ERRORS, bad_request, not_found, orch
from .projects import _model_summary

router = APIRouter(prefix="/api", tags=["modelos"])


# ------------------------------------------------------------------------------ registo
@router.get("/models")
def list_models(project_id: Optional[str] = None) -> list[dict[str, Any]]:
    return [_model_summary(m) for m in orch().registry.list(project_id)]


@router.get("/models/{version_id}")
def get_model(version_id: str) -> dict[str, Any]:
    try:
        m = orch().registry.get(version_id)
    except KeyError as exc:
        raise not_found("Modelo") from exc
    m.pop("reference_stats", None)
    return m


@router.post("/models/{version_id}/promote")
def promote(version_id: str) -> dict[str, Any]:
    o = orch()
    try:
        meta = o.registry.promote(version_id)
        o.store.update(meta["project_id"], production_version_id=version_id)
    except KeyError as exc:
        raise not_found("Modelo") from exc
    return _model_summary(meta)


@router.post("/models/{version_id}/champion")
def set_champion(version_id: str) -> dict[str, Any]:
    o = orch()
    try:
        meta = o.registry.get(version_id)
        o.registry.set_champion(meta["project_id"], version_id)
        o.store.update(meta["project_id"], champion_version_id=version_id)
    except KeyError as exc:
        raise not_found("Modelo") from exc
    return _model_summary(o.registry.get(version_id))


@router.delete("/models/{version_id}")
def delete_model(version_id: str) -> dict[str, str]:
    orch().registry.delete(version_id)
    return {"status": "apagado"}


class PredictBody(BaseModel):
    rows: list[dict[str, Any]]
    reasons: bool = True


@router.post("/models/{version_id}/predict")
def predict(version_id: str, body: PredictBody) -> dict[str, Any]:
    o = orch()
    try:
        meta = o.registry.get(version_id)
        ctx = o.context(meta["project_id"])
    except KeyError as exc:
        raise not_found("Modelo") from exc
    if not body.rows:
        raise HTTPException(status_code=400, detail="Envie pelo menos uma linha em 'rows'.")
    df = pd.DataFrame(body.rows)
    for f in meta.get("features", []):
        if f not in df.columns:
            df[f] = None
    try:
        out = score_frame(ctx, meta, df, reasons=body.reasons)
    except USER_ERRORS as exc:
        raise bad_request(exc) from exc
    return {"version_id": version_id, "predictions": jsonable(out)}


@router.get("/models/{version_id}/artifacts/{name}")
def artifact(version_id: str, name: str, limit: int = 500) -> dict[str, Any]:
    try:
        df = orch().registry.artifact(version_id, name)
    except KeyError as exc:
        raise not_found("Artefacto") from exc
    return {"columns": list(df.columns), "rows": jsonable(df.head(min(limit, 5000))), "row_count": int(len(df))}


# ------------------------------------------------------------------------------ conselheiro
class AdvisorBody(BaseModel):
    model_id: str
    use_case_id: Optional[str] = None
    project_id: Optional[str] = None
    profile: Optional[dict[str, Any]] = None
    goal: Optional[str] = None
    params: Optional[dict[str, Any]] = None


def _profile(body: AdvisorBody) -> tuple[DataProfile, Optional[str]]:
    o = orch()
    if body.project_id:
        try:
            ctx = o.context(body.project_id)
        except KeyError as exc:
            raise not_found("Projeto") from exc
        try:
            prof = data_profile(ctx)
        except USER_ERRORS as exc:
            raise bad_request(exc) from exc
        return prof, body.use_case_id or ctx.project.use_case_id
    prof = DataProfile.from_dict(body.profile or {})
    if body.profile and "task" not in body.profile:
        spec = o.kb.model(body.model_id)
        uc = o.kb.use_case(body.use_case_id)
        prof.task = uc.problem_type if uc else (spec.tasks[0] if spec else prof.task)
    return prof, body.use_case_id


@router.get("/advisor/goals")
def goals() -> dict[str, str]:
    return advisor.GOALS


@router.post("/advisor/profile")
def profile(body: AdvisorBody) -> dict[str, Any]:
    prof, _ = _profile(body)
    return prof.to_dict()


@router.post("/advisor/recommend")
def recommend(body: AdvisorBody) -> dict[str, Any]:
    prof, uc = _profile(body)
    try:
        rec = advisor.recommend(body.model_id, prof, uc, body.goal)
        rec["search_space"] = advisor.search_space(body.model_id, prof)
        return jsonable(rec)
    except ValueError as exc:
        raise bad_request(exc) from exc


@router.post("/advisor/validate")
def validate(body: AdvisorBody) -> dict[str, Any]:
    prof, uc = _profile(body)
    try:
        return jsonable(advisor.validate(body.model_id, body.params or {}, prof, uc))
    except ValueError as exc:
        raise bad_request(exc) from exc


@router.post("/advisor/compare")
def compare(body: AdvisorBody) -> dict[str, Any]:
    """Validação cruzada rápida: configuração do utilizador vs recomendada (tarefa assíncrona)."""
    if not body.project_id:
        raise HTTPException(status_code=400, detail="A comparação exige um projeto com dados.")
    o = orch()
    from ...agents.training import quick_cv

    def task(progress: Any) -> dict[str, Any]:
        ctx = o.context(body.project_id)
        prof = data_profile(ctx)
        rec = advisor.recommend(body.model_id, prof, ctx.project.use_case_id, body.goal)
        progress(0.1, "A avaliar a configuração recomendada…")
        a = quick_cv(ctx, body.model_id, rec["params"])
        progress(0.55, "A avaliar a sua configuração…")
        b = quick_cv(ctx, body.model_id, {**rec["params"], **(body.params or {})})
        return {"recommended": a | {"params": rec["params"]}, "custom": b | {"params": {**rec["params"], **(body.params or {})}}}

    return {"job": o.jobs.submit("advisor:compare", task, project_id=body.project_id).to_dict()}


class ApplyBody(BaseModel):
    project_id: str
    model_id: str
    params: dict[str, Any]
    lock: bool = True


@router.post("/advisor/apply")
def apply(body: ApplyBody) -> dict[str, Any]:
    o = orch()
    try:
        p = o.store.get(body.project_id)
    except KeyError as exc:
        raise not_found("Projeto") from exc
    prof = data_profile(o.context(body.project_id))
    val = advisor.validate(body.model_id, body.params, prof, p.use_case_id)
    if not val["valid"]:
        raise HTTPException(status_code=400, detail="; ".join(i["message"] for i in val["issues"] if i["level"] == "error"))
    params = dict(p.model_params)
    params[body.model_id] = val["params"]
    locked = set(p.params_locked)
    (locked.add if body.lock else locked.discard)(body.model_id)
    selected = p.selected_models if body.model_id in p.selected_models else p.selected_models + [body.model_id]
    o.store.update(body.project_id, model_params=params, params_locked=sorted(locked), selected_models=selected)
    return {"status": "aplicado", "params": val["params"], "locked": body.lock, "issues": val["issues"]}


# ------------------------------------------------------------------------------ exportações
@router.get("/exports/{path:path}")
def export_file(path: str) -> FileResponse:
    base = orch().settings.exports_dir.resolve()
    target = (base / path).resolve()
    if base not in target.parents or not target.is_file():
        raise not_found("Ficheiro")
    return FileResponse(target, filename=Path(path).name)
