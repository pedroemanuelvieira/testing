"""Base de conhecimento da plataforma (áreas, casos de uso, modelos, glossário, guias).

Os conteúdos vivem em ficheiros YAML em ``knowledge/data`` para que a equipa de
BI os possa estender sem tocar em código: basta acrescentar um caso de uso, um
termo ou um modelo e reiniciar a aplicação. ``KnowledgeBase.validate()`` verifica
a integridade das referências cruzadas (é corrido nos testes).
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Optional

import yaml

from .schema import (
    FAQ,
    Area,
    Guide,
    GlossaryCategory,
    ModelSpec,
    ProblemType,
    Term,
    UseCase,
    WorkflowStep,
)

DATA_DIR = Path(__file__).parent / "data"


def normalize(text: str) -> str:
    """Minúsculas e sem acentos — para pesquisa tolerante."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.lower()).strip()


def _load(name: str) -> dict:
    with open(DATA_DIR / name, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


class KnowledgeBase:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = data_dir
        self.areas: list[Area] = [Area(**a) for a in _load("areas.yaml")["areas"]]
        self.problem_types: list[ProblemType] = [
            ProblemType(**p) for p in _load("problem_types.yaml")["problem_types"]
        ]
        self.use_cases: list[UseCase] = [UseCase(**u) for u in _load("use_cases.yaml")["use_cases"]]
        self.models: list[ModelSpec] = [ModelSpec(**m) for m in _load("models.yaml")["models"]]
        self.categories: list[GlossaryCategory] = [
            GlossaryCategory(**c) for c in _load("glossary_categories.yaml")["categories"]
        ]
        terms: list[Term] = []
        for path in sorted(self.data_dir.glob("glossary_0*.yaml")):
            with open(path, encoding="utf-8") as fh:
                terms.extend(Term(**t) for t in (yaml.safe_load(fh) or {}).get("terms", []))
        self.terms = terms
        self.workflow: list[WorkflowStep] = sorted(
            (WorkflowStep(**s) for s in _load("workflow.yaml")["steps"]), key=lambda s: s.order
        )
        self.guides: list[Guide] = [Guide(**g) for g in _load("guides.yaml")["guides"]]
        self.faq: list[FAQ] = [FAQ(**f) for f in _load("faq.yaml")["faq"]]

        self._areas = {a.id: a for a in self.areas}
        self._pt = {p.id: p for p in self.problem_types}
        self._uc = {u.id: u for u in self.use_cases}
        self._models = {m.id: m for m in self.models}
        self._terms = {t.id: t for t in self.terms}
        self._steps = {s.id: s for s in self.workflow}
        self._guides = {g.id: g for g in self.guides}
        self._index: Optional[_SearchIndex] = None

    # ------------------------------------------------------------------ lookups
    def area(self, area_id: str) -> Optional[Area]:
        return self._areas.get(area_id)

    def problem_type(self, pt_id: str) -> Optional[ProblemType]:
        return self._pt.get(pt_id)

    def use_case(self, uc_id: Optional[str]) -> Optional[UseCase]:
        return self._uc.get(uc_id) if uc_id else None

    def model(self, model_id: str) -> Optional[ModelSpec]:
        return self._models.get(model_id)

    def term(self, term_id: str) -> Optional[Term]:
        return self._terms.get(term_id)

    def step(self, step_id: str) -> Optional[WorkflowStep]:
        return self._steps.get(step_id)

    def guide(self, guide_id: str) -> Optional[Guide]:
        return self._guides.get(guide_id)

    def use_cases_by(self, area: Optional[str] = None, problem_type: Optional[str] = None) -> list[UseCase]:
        out = self.use_cases
        if area:
            out = [u for u in out if u.area == area or area in u.areas]
        if problem_type:
            out = [u for u in out if u.problem_type == problem_type]
        return out

    def models_for(self, task: str) -> list[ModelSpec]:
        return [m for m in self.models if task in m.tasks]

    def terms_by_category(self, category: str) -> list[Term]:
        return [t for t in self.terms if t.category == category]

    def find_term(self, text: str) -> Optional[Term]:
        """Encontra um termo pelo id, nome ou nome em inglês (tolerante a acentos)."""
        if text in self._terms:
            return self._terms[text]
        n = normalize(text)
        if not n:
            return None
        for t in self.terms:
            names = {normalize(t.term), normalize(t.en), normalize(t.id.replace("_", " "))}
            names |= {normalize(p) for p in re.split(r"[()/,]", t.term) if p.strip()}
            if n in names:
                return t
        # siglas e palavras isoladas (ex.: "auc" → "AUC-ROC", "psi" → "PSI (índice ...)")
        token_hits = [t for t in self.terms
                      if n in re.split(r"[^a-z0-9²]+", normalize(t.term)) or n in re.split(r"[^a-z0-9²]+", normalize(t.en))]
        if token_hits:
            return min(token_hits, key=lambda t: len(t.term))
        return None

    # ------------------------------------------------------------------ search
    def search(self, query: str, kinds: Optional[Iterable[str]] = None, k: int = 8) -> list[dict[str, Any]]:
        if self._index is None:
            self._index = _SearchIndex(self)
        return self._index.search(query, kinds=set(kinds) if kinds else None, k=k)

    # ------------------------------------------------------------------ integrity
    def validate(self) -> list[str]:
        """Devolve uma lista de problemas de integridade (vazia = tudo certo)."""
        errors: list[str] = []
        term_ids = set(self._terms)
        step_ids = set(self._steps)
        cat_ids = {c.id for c in self.categories}
        if len(term_ids) != len(self.terms):
            seen: set[str] = set()
            for t in self.terms:
                if t.id in seen:
                    errors.append(f"termo duplicado: {t.id}")
                seen.add(t.id)

        def check_terms(where: str, ids: Iterable[str]) -> None:
            for tid in ids:
                if tid not in term_ids:
                    errors.append(f"{where}: termo inexistente '{tid}'")

        for t in self.terms:
            if t.category not in cat_ids:
                errors.append(f"termo {t.id}: categoria inexistente '{t.category}'")
            check_terms(f"termo {t.id} (related)", t.related)
            for s in t.steps:
                if s not in step_ids:
                    errors.append(f"termo {t.id}: passo inexistente '{s}'")
        for p in self.problem_types:
            check_terms(f"tipo {p.id}", p.terms)
            for m in p.default_models:
                if m not in self._models:
                    errors.append(f"tipo {p.id}: modelo inexistente '{m}'")
            if p.guide and p.guide not in self._guides:
                errors.append(f"tipo {p.id}: guia inexistente '{p.guide}'")
        for u in self.use_cases:
            if u.area not in self._areas:
                errors.append(f"caso {u.id}: área inexistente '{u.area}'")
            for a in u.areas:
                if a not in self._areas:
                    errors.append(f"caso {u.id}: área inexistente '{a}'")
            if u.problem_type not in self._pt:
                errors.append(f"caso {u.id}: tipo inexistente '{u.problem_type}'")
            for rm in u.recommended_models:
                spec = self._models.get(rm.model)
                if spec is None:
                    errors.append(f"caso {u.id}: modelo inexistente '{rm.model}'")
                elif u.problem_type not in spec.tasks and not (
                    u.problem_type == "binary_classification" and spec.id == "isolation_forest"
                ):
                    errors.append(f"caso {u.id}: modelo '{rm.model}' não suporta {u.problem_type}")
            check_terms(f"caso {u.id}", u.terms)
        for m in self.models:
            for h in m.hyperparameters:
                if h.term:
                    check_terms(f"modelo {m.id}.{h.name}", [h.term])
                if h.type == "choice" and h.default is not None and h.choices and str(h.default) not in [str(c) for c in h.choices]:
                    errors.append(f"modelo {m.id}.{h.name}: default fora das escolhas")
        for s in self.workflow:
            check_terms(f"passo {s.id}", s.terms)
        for g in self.guides:
            for sec in g.sections:
                check_terms(f"guia {g.id}", sec.terms)
        for f in self.faq:
            check_terms(f"faq '{f.q[:30]}'", f.terms)
        return errors

    def stats(self) -> dict[str, int]:
        return {
            "areas": len(self.areas),
            "use_cases": len(self.use_cases),
            "models": len(self.models),
            "terms": len(self.terms),
            "guides": len(self.guides),
            "workflow_steps": len(self.workflow),
            "faq": len(self.faq),
        }


class _SearchIndex:
    """Índice TF-IDF (n-gramas de caracteres, sem acentos) sobre toda a base."""

    def __init__(self, kb: KnowledgeBase):
        from sklearn.feature_extraction.text import TfidfVectorizer

        docs: list[dict[str, Any]] = []
        for t in kb.terms:
            docs.append({
                "kind": "term", "id": t.id, "title": t.term, "snippet": t.short,
                "text": f"{t.term} {t.term} {t.en} {t.short} {t.definition} {t.example}",
            })
        for u in kb.use_cases:
            docs.append({
                "kind": "use_case", "id": u.id, "title": u.name, "snippet": u.summary,
                "text": f"{u.name} {u.name} {u.summary} {u.business_question} {u.decision} {' '.join(u.typical_features)}",
            })
        for m in kb.models:
            docs.append({
                "kind": "model", "id": m.id, "title": m.name, "snippet": m.description,
                "text": f"{m.name} {m.name} {m.description} {m.when_to_use} "
                        + " ".join(f"{h.name} {h.label} {h.description}" for h in m.hyperparameters),
            })
        for s in kb.workflow:
            docs.append({
                "kind": "step", "id": s.id, "title": s.title, "snippet": s.objective,
                "text": f"{s.title} {s.objective} {s.why} {' '.join(s.how)}",
            })
        for g in kb.guides:
            docs.append({
                "kind": "guide", "id": g.id, "title": g.title, "snippet": g.summary,
                "text": f"{g.title} {g.summary} " + " ".join(f"{x.title} {x.content}" for x in g.sections),
            })
        for i, f in enumerate(kb.faq):
            docs.append({"kind": "faq", "id": f"faq_{i}", "title": f.q, "snippet": f.a[:220], "text": f"{f.q} {f.q} {f.a}"})
        for a in kb.areas:
            docs.append({"kind": "area", "id": a.id, "title": a.name, "snippet": a.description,
                         "text": f"{a.name} {a.description} {' '.join(a.kpis)}"})
        self.docs = docs
        self.vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), preprocessor=normalize, sublinear_tf=True)
        self.matrix = self.vec.fit_transform([d["text"] for d in docs])

    def search(self, query: str, kinds: Optional[set[str]], k: int) -> list[dict[str, Any]]:
        if not query.strip():
            return []
        q = self.vec.transform([query])
        scores = (self.matrix @ q.T).toarray().ravel()
        order = scores.argsort()[::-1]
        out = []
        for i in order:
            d = self.docs[i]
            if kinds and d["kind"] not in kinds:
                continue
            if scores[i] <= 0.02:
                break
            out.append({k2: d[k2] for k2 in ("kind", "id", "title", "snippet")} | {"score": round(float(scores[i]), 4)})
            if len(out) >= k:
                break
        return out


@lru_cache(maxsize=1)
def get_kb() -> KnowledgeBase:
    return KnowledgeBase()
