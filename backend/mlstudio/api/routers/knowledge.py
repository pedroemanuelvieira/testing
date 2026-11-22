"""Base de conhecimento: áreas, casos de uso, modelos, glossário, guias, percurso."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter

from ...knowledge import get_kb, normalize
from ..deps import not_found

router = APIRouter(prefix="/api/knowledge", tags=["conhecimento"])


@router.get("/summary")
def summary() -> dict:
    kb = get_kb()
    return {"stats": kb.stats(), "areas": [a.model_dump() for a in kb.areas],
            "problem_types": [p.model_dump() for p in kb.problem_types], "categories": [c.model_dump() for c in kb.categories]}


@router.get("/areas")
def areas() -> list[dict]:
    kb = get_kb()
    return [a.model_dump() | {"use_cases": len(kb.use_cases_by(area=a.id))} for a in kb.areas]


@router.get("/problem-types")
def problem_types() -> list[dict]:
    return [p.model_dump() for p in get_kb().problem_types]


@router.get("/use-cases")
def use_cases(area: Optional[str] = None, problem_type: Optional[str] = None, q: Optional[str] = None) -> list[dict]:
    kb = get_kb()
    items = kb.use_cases_by(area, problem_type)
    if q:
        ids = {h["id"] for h in kb.search(q, kinds=["use_case"], k=30)}
        items = [u for u in items if u.id in ids]
    return [u.model_dump() for u in items]


@router.get("/use-cases/{uc_id}")
def use_case(uc_id: str) -> dict:
    kb = get_kb()
    uc = kb.use_case(uc_id)
    if uc is None:
        raise not_found("Caso de uso")
    d = uc.model_dump()
    d["models"] = [kb.model(r.model).model_dump() | {"why": r.why} for r in uc.recommended_models if kb.model(r.model)]
    d["glossary"] = [kb.term(t).model_dump() for t in uc.terms if kb.term(t)]
    return d


@router.get("/models")
def models(task: Optional[str] = None) -> list[dict]:
    from ...ml.factory import library_available

    kb = get_kb()
    items = kb.models_for(task) if task else kb.models
    return [m.model_dump() | {"available": library_available(m.library)} for m in items]


@router.get("/models/{model_id}")
def model(model_id: str) -> dict:
    m = get_kb().model(model_id)
    if m is None:
        raise not_found("Modelo")
    return m.model_dump()


@router.get("/glossary/categories")
def glossary_categories() -> list[dict]:
    kb = get_kb()
    return [c.model_dump() | {"count": len(kb.terms_by_category(c.id))} for c in kb.categories]


@router.get("/glossary")
def glossary(q: Optional[str] = None, category: Optional[str] = None, level: Optional[str] = None,
             step: Optional[str] = None) -> list[dict]:
    kb = get_kb()
    terms = kb.terms
    if category:
        terms = [t for t in terms if t.category == category]
    if level:
        terms = [t for t in terms if t.level == level]
    if step:
        terms = [t for t in terms if step in t.steps]
    if q:
        nq = normalize(q)
        direct = [t for t in terms if nq in normalize(t.term) or nq in normalize(t.en) or nq in t.id]
        hits = [kb.term(h["id"]) for h in kb.search(q, kinds=["term"], k=40)]
        allowed = {t.id for t in terms}
        ordered = direct + [t for t in hits if t and t.id in allowed and t not in direct]
        terms = ordered
    else:
        terms = sorted(terms, key=lambda t: normalize(t.term))
    return [t.model_dump() for t in terms]


@router.get("/glossary/{term_id}")
def term(term_id: str) -> dict:
    kb = get_kb()
    t = kb.term(term_id) or kb.find_term(term_id)
    if t is None:
        raise not_found("Termo")
    d = t.model_dump()
    d["related_terms"] = [kb.term(r).model_dump() for r in t.related if kb.term(r)]
    d["used_in_steps"] = [kb.step(s).model_dump() for s in t.steps if kb.step(s)]
    d["used_by_models"] = [{"id": m.id, "name": m.name, "param": h.name} for m in kb.models for h in m.hyperparameters if h.term == t.id]
    d["use_cases"] = [{"id": u.id, "name": u.name} for u in kb.use_cases if t.id in u.terms]
    return d


@router.get("/workflow")
def workflow() -> list[dict]:
    from ...agents import AGENTS

    out = []
    for s in get_kb().workflow:
        d = s.model_dump()
        d["agent_name"] = AGENTS[s.agent].card.name if s.agent in AGENTS else s.agent
        out.append(d)
    return out


@router.get("/guides")
def guides() -> list[dict]:
    return [g.model_dump() for g in get_kb().guides]


@router.get("/guides/{guide_id}")
def guide(guide_id: str) -> dict:
    g = get_kb().guide(guide_id)
    if g is None:
        raise not_found("Guia")
    return g.model_dump()


@router.get("/faq")
def faq() -> list[dict]:
    return [f.model_dump() for f in get_kb().faq]


@router.get("/search")
def search(q: str, kinds: Optional[str] = None, k: int = 10) -> list[dict]:
    return get_kb().search(q, kinds=kinds.split(",") if kinds else None, k=min(k, 30))
