"""Modelos pydantic que validam os ficheiros YAML da base de conhecimento."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="allow")


class Area(_Base):
    id: str
    name: str
    icon: str = "circle"
    color: str = "#2563eb"
    description: str
    kpis: list[str] = []
    typical_sources: list[str] = []
    stakeholders: list[str] = []
    decisions: list[str] = []
    risks: list[str] = []


class ProblemType(_Base):
    id: str
    name: str
    short: str
    description: str
    learning: str
    training_agent: str
    primary_metric: str
    metrics: list[str]
    default_models: list[str]
    guide: Optional[str] = None
    terms: list[str] = []


class TargetDef(_Base):
    column: Optional[str] = None
    definition: str = ""
    positive_class: Any = None


class RecommendedModel(_Base):
    model: str
    why: str


class Metrics(_Base):
    primary: str
    secondary: list[str] = []
    business: str = ""


class BusinessCosts(_Base):
    cost_fp: float = 0.0
    cost_fn: float = 0.0
    benefit_tp: float = 0.0
    note: str = ""


class DaxMeasure(_Base):
    name: str
    dax: str


class PowerBIOutput(_Base):
    table: str
    columns: list[str] = []
    visuals: list[str] = []
    measures: list[DaxMeasure] = []


class UseCase(_Base):
    id: str
    name: str
    area: str
    areas: list[str] = []
    problem_type: str
    maturity: str = "intermédio"
    summary: str
    business_question: str
    decision: str
    unit: str
    target: TargetDef
    horizon: str = ""
    typical_features: list[str] = []
    data_requirements: list[str] = []
    demo: dict[str, Any] = {}
    recommended_models: list[RecommendedModel] = []
    metrics: Metrics
    profile: dict[str, Any] = {}
    business_costs: Optional[BusinessCosts] = None
    pitfalls: list[str] = []
    powerbi_output: Optional[PowerBIOutput] = None
    ai_act_risk: str = "mínimo"
    sensitive_attributes: list[str] = []
    terms: list[str] = []


class Hyperparameter(_Base):
    name: str
    label: str
    type: Literal["int", "float", "choice", "bool"]
    default: Any = None
    min: Optional[float] = None
    max: Optional[float] = None
    log: bool = False
    choices: list[Any] = []
    importance: Literal["alta", "média", "baixa"] = "média"
    description: str = ""
    increase: str = ""
    decrease: str = ""
    search: dict[str, Any] = {}
    term: Optional[str] = None


class ModelSpec(_Base):
    id: str
    name: str
    family: str
    tasks: list[str]
    library: str
    description: str
    how_it_works: str = ""
    strengths: list[str] = []
    weaknesses: list[str] = []
    when_to_use: str = ""
    interpretability: int = 3
    speed: int = 3
    needs_scaling: bool = False
    handles_missing: bool = False
    handles_categorical: bool = False
    hyperparameters: list[Hyperparameter] = []

    def hp(self, name: str) -> Optional[Hyperparameter]:
        return next((h for h in self.hyperparameters if h.name == name), None)


class GlossaryCategory(_Base):
    id: str
    name: str
    icon: str = "book"
    description: str = ""


class Term(_Base):
    id: str
    term: str
    en: str = ""
    category: str
    level: Literal["básico", "intermédio", "avançado"] = "básico"
    short: str
    definition: str
    example: str = ""
    formula: str = ""
    pitfalls: list[str] = []
    related: list[str] = []
    steps: list[str] = []


class WorkflowStep(_Base):
    id: str
    order: int
    title: str
    agent: str
    objective: str
    why: str
    how: list[str] = []
    checklist: list[str] = []
    mistakes: list[str] = []
    terms: list[str] = []
    outputs: list[str] = []


class GuideSection(_Base):
    title: str
    content: str
    terms: list[str] = []


class Guide(_Base):
    id: str
    title: str
    audience: str = ""
    duration: str = ""
    problem_type: Optional[str] = None
    summary: str = ""
    sections: list[GuideSection] = Field(default_factory=list)


class FAQ(_Base):
    q: str
    a: str
    terms: list[str] = []
