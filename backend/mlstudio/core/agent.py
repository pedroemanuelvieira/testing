"""Contrato dos agentes e formato dos resultados.

Cada agente é especialista numa componente de ML e devolve um ``AgentResult``
com: resumo, insights (com nível de gravidade e termos do glossário),
recomendações, *blocos* de visualização genéricos (KPIs, tabelas, gráficos,
markdown, código) que o frontend desenha sem conhecer o agente, e ``outputs``
estruturados que os agentes seguintes consomem.
"""
from __future__ import annotations

import math
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Optional

import numpy as np
import pandas as pd

if TYPE_CHECKING:  # pragma: no cover
    from .context import AgentContext


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def jsonable(obj: Any) -> Any:
    """Converte recursivamente para tipos serializáveis em JSON (NaN → None)."""
    if obj is None or isinstance(obj, (str, bool)):
        return obj
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        f = float(obj)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, (pd.Timestamp, datetime, date)):
        return obj.isoformat()
    if isinstance(obj, (np.ndarray, pd.Series, pd.Index)):
        return [jsonable(x) for x in obj.tolist()]
    if isinstance(obj, pd.DataFrame):
        return [jsonable(r) for r in obj.to_dict(orient="records")]
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [jsonable(x) for x in obj]
    if obj is pd.NaT:
        return None
    try:
        if pd.isna(obj):
            return None
    except (TypeError, ValueError):
        pass
    return str(obj)


# ------------------------------------------------------------------------------ blocos
def kpi(label: str, value: Any, fmt: str = "auto", hint: str = "", term: Optional[str] = None,
        status: Optional[str] = None) -> dict[str, Any]:
    return {"label": label, "value": jsonable(value), "fmt": fmt, "hint": hint, "term": term, "status": status}


def kpis(items: list[dict[str, Any]], title: str = "") -> dict[str, Any]:
    return {"type": "kpis", "title": title, "items": items}


def table(title: str, rows: list[dict[str, Any]] | pd.DataFrame, columns: Optional[list[dict[str, Any]]] = None,
          description: str = "", terms: Optional[list[str]] = None, max_rows: int = 200) -> dict[str, Any]:
    if isinstance(rows, pd.DataFrame):
        df = rows.head(max_rows)
        rows = df.to_dict(orient="records")
        columns = columns or [{"key": c, "label": str(c)} for c in df.columns]
    rows = rows[:max_rows]
    if columns is None:
        columns = [{"key": k, "label": k} for k in (rows[0].keys() if rows else [])]
    return {"type": "table", "title": title, "description": description, "columns": columns,
            "rows": jsonable(rows), "terms": terms or []}


def chart(kind: str, title: str, data: list[dict[str, Any]] | pd.DataFrame, x: str, y: list[str] | str,
          description: str = "", terms: Optional[list[str]] = None, **opts: Any) -> dict[str, Any]:
    """kind: bar | line | area | scatter | histogram."""
    if isinstance(data, pd.DataFrame):
        data = data.to_dict(orient="records")
    return {"type": "chart", "chart": kind, "title": title, "description": description, "data": jsonable(data),
            "x": x, "y": [y] if isinstance(y, str) else y, "terms": terms or [], "options": jsonable(opts)}


def heatmap(title: str, x_labels: list[str], y_labels: list[str], values: list[list[float]],
            description: str = "", terms: Optional[list[str]] = None, fmt: str = "0.00",
            diverging: bool = False) -> dict[str, Any]:
    return {"type": "heatmap", "title": title, "description": description, "x_labels": jsonable(x_labels),
            "y_labels": jsonable(y_labels), "values": jsonable(values), "terms": terms or [], "fmt": fmt,
            "diverging": diverging}


def markdown(text: str, title: str = "") -> dict[str, Any]:
    return {"type": "markdown", "title": title, "text": text}


def callout(level: str, title: str, text: str, terms: Optional[list[str]] = None) -> dict[str, Any]:
    return {"type": "callout", "level": level, "title": title, "text": text, "terms": terms or []}


def code(language: str, content: str, title: str = "", description: str = "") -> dict[str, Any]:
    return {"type": "code", "language": language, "title": title, "description": description, "code": content}


def params_block(title: str, model_id: str, details: list[dict[str, Any]], notes: Optional[list[str]] = None) -> dict[str, Any]:
    return {"type": "params", "title": title, "model_id": model_id, "details": jsonable(details), "notes": notes or []}


def download(title: str, files: list[dict[str, str]]) -> dict[str, Any]:
    return {"type": "download", "title": title, "files": files}


# ------------------------------------------------------------------------------ resultados
@dataclass
class Insight:
    level: str  # info | success | warning | critical
    title: str
    detail: str = ""
    terms: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"level": self.level, "title": self.title, "detail": self.detail, "terms": self.terms}


@dataclass
class AgentResult:
    agent_id: str
    project_id: Optional[str] = None
    title: str = ""
    summary: str = ""
    status: str = "ok"  # ok | warning | error
    insights: list[Insight] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    blocks: list[dict[str, Any]] = field(default_factory=list)
    outputs: dict[str, Any] = field(default_factory=dict)
    next_step: Optional[str] = None
    terms: list[str] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)
    run_id: str = field(default_factory=lambda: "run_" + uuid.uuid4().hex[:10])
    created_at: str = field(default_factory=now_iso)
    duration_ms: int = 0

    def info(self, title: str, detail: str = "", terms: Optional[list[str]] = None) -> None:
        self.insights.append(Insight("info", title, detail, terms or []))

    def success(self, title: str, detail: str = "", terms: Optional[list[str]] = None) -> None:
        self.insights.append(Insight("success", title, detail, terms or []))

    def warn(self, title: str, detail: str = "", terms: Optional[list[str]] = None) -> None:
        self.insights.append(Insight("warning", title, detail, terms or []))
        if self.status == "ok":
            self.status = "warning"

    def critical(self, title: str, detail: str = "", terms: Optional[list[str]] = None) -> None:
        self.insights.append(Insight("critical", title, detail, terms or []))
        if self.status in ("ok", "warning"):
            self.status = "warning"

    def to_dict(self) -> dict[str, Any]:
        return jsonable({
            "run_id": self.run_id, "agent_id": self.agent_id, "project_id": self.project_id, "title": self.title,
            "summary": self.summary, "status": self.status, "insights": [i.to_dict() for i in self.insights],
            "recommendations": self.recommendations, "blocks": self.blocks, "outputs": self.outputs,
            "next_step": self.next_step, "terms": self.terms, "params": self.params,
            "created_at": self.created_at, "duration_ms": self.duration_ms,
        })

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AgentResult":
        res = cls(agent_id=d["agent_id"])
        for k, v in d.items():
            if k == "insights":
                res.insights = [Insight(**i) for i in v]
            elif hasattr(res, k):
                setattr(res, k, v)
        return res


@dataclass
class AgentCard:
    id: str
    name: str
    component: str
    role: str
    description: str
    icon: str = "bot"
    step: Optional[str] = None
    problem_types: list[str] = field(default_factory=list)  # vazio = todos
    capabilities: list[str] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    params: list[dict[str, Any]] = field(default_factory=list)
    requires_data: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


class AgentError(RuntimeError):
    """Erro de agente com mensagem para o utilizador."""


class Agent(ABC):
    card: AgentCard

    def applies_to(self, problem_type: Optional[str]) -> bool:
        return not self.card.problem_types or (problem_type in self.card.problem_types)

    def execute(self, ctx: "AgentContext", **params: Any) -> AgentResult:
        t0 = time.perf_counter()
        result = AgentResult(agent_id=self.card.id, project_id=ctx.project.id if ctx.project else None,
                             title=self.card.name, params=jsonable(params))
        self.run(ctx, result, **params)
        result.duration_ms = int((time.perf_counter() - t0) * 1000)
        return result

    @abstractmethod
    def run(self, ctx: "AgentContext", result: AgentResult, **params: Any) -> None:
        """Preenche ``result``. Lança ``AgentError`` para erros explicáveis."""


ProgressFn = Callable[[float, str], None]


def noop_progress(_: float, __: str) -> None:
    return None
