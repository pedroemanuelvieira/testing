"""Registo dos agentes especializados — um por componente de ML."""
from __future__ import annotations

from ..core.agent import Agent, AgentCard
from .evaluation import EvaluationAgent, ExplainabilityAgent
from .framing import ConnectorAgent, FramingAgent
from .modeling import AdvisorAgent, SelectionAgent
from .operations import DeploymentAgent, GovernanceAgent, GuideAgent, MonitoringAgent, ReportingAgent
from .profiling import FeatureAgent, ProfilerAgent, QualityAgent
from .specialists import AnomalyAgent, AssociationAgent, ForecastingAgent, SegmentationAgent
from .training import TrainingAgent

_ORDER: list[type[Agent]] = [
    FramingAgent, ConnectorAgent, ProfilerAgent, QualityAgent, FeatureAgent, SelectionAgent, AdvisorAgent,
    TrainingAgent, ForecastingAgent, SegmentationAgent, AnomalyAgent, AssociationAgent, EvaluationAgent,
    ExplainabilityAgent, GovernanceAgent, DeploymentAgent, MonitoringAgent, ReportingAgent, GuideAgent,
]

AGENTS: dict[str, Agent] = {cls.card.id: cls() for cls in _ORDER}

ASSISTANT_CARD = AgentCard(
    id="assistant", name="Assistente (Chatbot)", component="Apoio e esclarecimento de dúvidas",
    role="Tutor de ML e copiloto da plataforma", icon="message-circle", step=None,
    description="Responde a dúvidas em português sobre ML, métricas, parâmetros e a plataforma. Consulta o "
                "glossário, os casos de uso e o catálogo de modelos, aconselha hiperparâmetros, lê o estado do "
                "projeto e pode acionar agentes. Funciona com a API Claude ou em modo offline.",
    capabilities=["Dúvidas sobre conceitos (glossário)", "Aconselhamento de parâmetros", "Estado do projeto",
                  "Acionar agentes", "Modo offline"],
    inputs=["Pergunta"], outputs=["Resposta com fontes"], requires_data=False,
)

# agente responsável pelo passo "treino" de cada tipo de problema
TRAINERS = {
    "binary_classification": "training", "multiclass_classification": "training", "regression": "training",
    "forecasting": "forecasting", "clustering": "segmentation", "anomaly_detection": "anomaly",
    "association_rules": "association",
}


def agent_cards() -> list[dict]:
    return [a.card.to_dict() for a in AGENTS.values()] + [ASSISTANT_CARD.to_dict()]


__all__ = ["AGENTS", "ASSISTANT_CARD", "TRAINERS", "agent_cards"]
