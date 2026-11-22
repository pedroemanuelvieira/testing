"""Ferramentas do assistente: definições (JSON Schema) e execução sobre a plataforma."""
from __future__ import annotations

import json
from typing import Any, Callable, Optional

from .. import advisor
from ..advisor.profile import DataProfile, imbalance_level
from ..core.agent import AgentError, jsonable

RUNNABLE_AGENTS = ["framing", "connector", "profiler", "quality", "features", "selection", "advisor", "training",
                   "forecasting", "segmentation", "anomaly", "association", "evaluation", "explainability", "governance",
                   "monitoring", "reporting", "guide"]

TOOLS: list[dict[str, Any]] = [
    {
        "name": "pesquisar_conhecimento",
        "description": "Pesquisa a base de conhecimento da plataforma (glossário, casos de uso, modelos, guias, FAQ, passos do "
                       "percurso). Use sempre que precisar de factos sobre conceitos de ML, métricas, casos de negócio ou "
                       "funcionalidades — antes de responder de memória.",
        "input_schema": {"type": "object", "properties": {
            "consulta": {"type": "string", "description": "Texto a pesquisar, em português."},
            "tipos": {"type": "array", "items": {"type": "string", "enum": ["term", "use_case", "model", "guide", "faq", "step", "area"]},
                      "description": "Restringir a tipos de documento (opcional)."}},
            "required": ["consulta"]},
    },
    {
        "name": "obter_termo_glossario",
        "description": "Devolve a entrada completa do glossário (definição, exemplo, fórmula, armadilhas, termos relacionados) "
                       "a partir do id ou do nome do termo.",
        "input_schema": {"type": "object", "properties": {"termo": {"type": "string"}}, "required": ["termo"]},
    },
    {
        "name": "listar_casos_de_uso",
        "description": "Lista casos de uso de negócio, opcionalmente filtrados por área (comercial, marketing, financas, risco, "
                       "operacoes, logistica, rh, cliente, pricing, manutencao) e tipo de problema.",
        "input_schema": {"type": "object", "properties": {
            "area": {"type": "string"}, "tipo_problema": {"type": "string"}}},
    },
    {
        "name": "obter_caso_de_uso",
        "description": "Detalhe de um caso de uso: pergunta de negócio, alvo, features típicas, modelos recomendados, métricas, "
                       "custos, armadilhas e saída para o Power BI.",
        "input_schema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
    },
    {
        "name": "obter_modelo",
        "description": "Ficha de um algoritmo do catálogo com todos os hiperparâmetros (intervalos, efeito de subir/descer).",
        "input_schema": {"type": "object", "properties": {"id": {"type": "string", "description": "ex.: lightgbm, random_forest, logistic_regression, kmeans"}},
                         "required": ["id"]},
    },
    {
        "name": "recomendar_parametros",
        "description": "Recomenda hiperparâmetros para um modelo, especializados para um caso de uso e para o perfil dos dados. "
                       "Se indicar projeto_id usa o perfil real dos dados do projeto; caso contrário use n_linhas, "
                       "n_variaveis e taxa_positivos.",
        "input_schema": {"type": "object", "properties": {
            "modelo": {"type": "string"}, "caso_de_uso": {"type": "string"}, "projeto_id": {"type": "string"},
            "n_linhas": {"type": "integer"}, "n_variaveis": {"type": "integer"},
            "taxa_positivos": {"type": "number", "description": "Proporção da classe positiva (0–1), para classificação binária."},
            "tarefa": {"type": "string", "description": "binary_classification | multiclass_classification | regression | forecasting | clustering | anomaly_detection"},
            "objetivo": {"type": "string", "enum": ["equilibrado", "performance", "interpretabilidade", "rapidez"]}},
            "required": ["modelo"]},
    },
    {
        "name": "validar_parametros",
        "description": "Valida uma configuração de hiperparâmetros proposta pelo utilizador: erros, avisos de overfitting/"
                       "underfitting e indicador de complexidade.",
        "input_schema": {"type": "object", "properties": {
            "modelo": {"type": "string"}, "parametros": {"type": "object"}, "caso_de_uso": {"type": "string"},
            "projeto_id": {"type": "string"}, "n_linhas": {"type": "integer"}, "n_variaveis": {"type": "integer"},
            "taxa_positivos": {"type": "number"}, "tarefa": {"type": "string"}},
            "required": ["modelo", "parametros"]},
    },
    {
        "name": "listar_projetos",
        "description": "Lista os projetos de ML existentes (id, nome, caso de uso, tipo, progresso).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "estado_projeto",
        "description": "Estado de um projeto: configuração, passos concluídos, resumos dos agentes, métricas do modelo campeão "
                       "e próximo passo recomendado.",
        "input_schema": {"type": "object", "properties": {"projeto_id": {"type": "string"}}, "required": ["projeto_id"]},
    },
    {
        "name": "listar_agentes",
        "description": "Lista os agentes especializados da plataforma e o que cada um faz.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "executar_agente",
        "description": "Executa um agente num projeto (ex.: profiler, quality, training, evaluation, explainability, guide). "
                       "Use apenas quando o utilizador pedir explicitamente para executar/correr uma etapa. Não publica "
                       "dados no Power BI (a implementação é feita na interface).",
        "input_schema": {"type": "object", "properties": {
            "projeto_id": {"type": "string"}, "agente": {"type": "string", "enum": RUNNABLE_AGENTS},
            "parametros": {"type": "object"}}, "required": ["projeto_id", "agente"]},
    },
]


class ToolExecutor:
    def __init__(self, orchestrator: Any):
        self.o = orchestrator
        self.kb = orchestrator.kb
        self.referenced_terms: list[str] = []
        self.referenced_use_cases: list[str] = []
        self.handlers: dict[str, Callable[..., Any]] = {
            "pesquisar_conhecimento": self.search, "obter_termo_glossario": self.term,
            "listar_casos_de_uso": self.list_use_cases, "obter_caso_de_uso": self.use_case,
            "obter_modelo": self.model, "recomendar_parametros": self.recommend, "validar_parametros": self.validate,
            "listar_projetos": self.projects, "estado_projeto": self.project_state, "listar_agentes": self.agents,
            "executar_agente": self.run_agent,
        }

    def execute(self, name: str, args: dict[str, Any]) -> tuple[str, bool]:
        fn = self.handlers.get(name)
        if fn is None:
            return f"Ferramenta desconhecida: {name}", True
        try:
            out = fn(**(args or {}))
            text = json.dumps(jsonable(out), ensure_ascii=False)
            return (text[:12_000] + "…(truncado)") if len(text) > 12_000 else text, False
        except (AgentError, KeyError, ValueError, TypeError, FileNotFoundError) as exc:
            return f"Erro: {exc}", True

    # ------------------------------------------------------------------ conhecimento
    def search(self, consulta: str, tipos: Optional[list[str]] = None) -> list[dict[str, Any]]:
        hits = self.kb.search(consulta, kinds=tipos, k=8)
        for h in hits:
            if h["kind"] == "term":
                self.referenced_terms.append(h["id"])
        return hits

    def term(self, termo: str) -> dict[str, Any]:
        t = self.kb.find_term(termo) or next((self.kb.term(h["id"]) for h in self.kb.search(termo, kinds=["term"], k=1)), None)
        if t is None:
            raise KeyError(f"Termo não encontrado: {termo}")
        self.referenced_terms.append(t.id)
        return t.model_dump()

    def list_use_cases(self, area: Optional[str] = None, tipo_problema: Optional[str] = None) -> list[dict[str, Any]]:
        return [{"id": u.id, "nome": u.name, "area": u.area, "tipo": u.problem_type, "resumo": u.summary}
                for u in self.kb.use_cases_by(area, tipo_problema)]

    def use_case(self, id: str) -> dict[str, Any]:  # noqa: A002
        uc = self.kb.use_case(id)
        if uc is None:
            hits = self.kb.search(id, kinds=["use_case"], k=1)
            uc = self.kb.use_case(hits[0]["id"]) if hits else None
        if uc is None:
            raise KeyError(f"Caso de uso não encontrado: {id}")
        self.referenced_use_cases.append(uc.id)
        return uc.model_dump()

    def model(self, id: str) -> dict[str, Any]:  # noqa: A002
        spec = self.kb.model(id) or next((self.kb.model(h["id"]) for h in self.kb.search(id, kinds=["model"], k=1)), None)
        if spec is None:
            raise KeyError(f"Modelo não encontrado: {id}")
        return spec.model_dump()

    def _profile(self, projeto_id: Optional[str], n_linhas: Optional[int], n_variaveis: Optional[int],
                 taxa_positivos: Optional[float], tarefa: Optional[str], caso_de_uso: Optional[str], modelo: str) -> tuple[DataProfile, Optional[str]]:
        if projeto_id:
            from ..agents.common import data_profile

            ctx = self.o.context(projeto_id)
            return data_profile(ctx), ctx.project.use_case_id
        spec = self.kb.model(modelo)
        uc = self.kb.use_case(caso_de_uso)
        task = tarefa or (uc.problem_type if uc else (spec.tasks[0] if spec else "binary_classification"))
        prof = DataProfile(n_rows=int(n_linhas or 10_000), n_features=int(n_variaveis or 20), task=task,
                           positive_rate=taxa_positivos, source="manual")
        if taxa_positivos is not None:
            prof.imbalance = imbalance_level(taxa_positivos)
        return prof, caso_de_uso

    def recommend(self, modelo: str, caso_de_uso: Optional[str] = None, projeto_id: Optional[str] = None,
                  n_linhas: Optional[int] = None, n_variaveis: Optional[int] = None, taxa_positivos: Optional[float] = None,
                  tarefa: Optional[str] = None, objetivo: Optional[str] = None) -> dict[str, Any]:
        prof, uc = self._profile(projeto_id, n_linhas, n_variaveis, taxa_positivos, tarefa, caso_de_uso, modelo)
        rec = advisor.recommend(modelo, prof, uc, objetivo)
        for d in rec["details"]:
            if d.get("term"):
                self.referenced_terms.append(d["term"])
        return {"modelo": rec["model_name"], "objetivo": rec["goal"], "notas": rec["notes"], "avaliacao": rec["assessment"],
                "parametros": [{k: d[k] for k in ("name", "value", "reason", "importance", "increase", "decrease", "search")}
                               for d in rec["details"]],
                "perfil": {k: v for k, v in prof.to_dict().items() if v not in (None, [], "")}}

    def validate(self, modelo: str, parametros: dict[str, Any], caso_de_uso: Optional[str] = None,
                 projeto_id: Optional[str] = None, n_linhas: Optional[int] = None, n_variaveis: Optional[int] = None,
                 taxa_positivos: Optional[float] = None, tarefa: Optional[str] = None) -> dict[str, Any]:
        prof, uc = self._profile(projeto_id, n_linhas, n_variaveis, taxa_positivos, tarefa, caso_de_uso, modelo)
        return advisor.validate(modelo, parametros, prof, uc)

    # ------------------------------------------------------------------ projetos e agentes
    def projects(self) -> list[dict[str, Any]]:
        from ..agents.operations import FLOWS

        out = []
        for p in self.o.store.list():
            flow = FLOWS.get(p.problem_type, [])
            done = sum(p.step_status(s) in ("done", "warning") for s in flow)
            out.append({"id": p.id, "nome": p.name, "caso_de_uso": p.use_case_id, "tipo": p.problem_type,
                        "progresso": f"{done}/{len(flow)}"})
        return out

    def project_state(self, projeto_id: str) -> dict[str, Any]:
        from ..agents.operations import FLOWS, GuideAgent

        ctx = self.o.context(projeto_id)
        p = ctx.project
        runs = {aid: {k: r.get(k) for k in ("summary", "status")} | {"insights": [i["title"] for i in r.get("insights", [])[:4]]}
                for aid in p.latest_runs if (r := ctx.latest(aid))}
        champ = ctx.champion()
        pending = GuideAgent.pending_steps(ctx)
        return {"id": p.id, "nome": p.name, "caso_de_uso": p.use_case_id, "tipo": p.problem_type, "alvo": p.target,
                "colunas_excluidas": p.excluded_columns, "modelos_selecionados": p.selected_models,
                "passos": {s: p.step_status(s) for s in FLOWS.get(p.problem_type, [])},
                "proximo_passo": pending[0] if pending else None, "resultados": runs,
                "campeao": {k: champ.get(k) for k in ("id", "model_name", "stage", "metrics_test", "threshold")} if champ else None}

    def agents(self) -> list[dict[str, Any]]:
        from ..agents import agent_cards

        return [{"id": c["id"], "nome": c["name"], "componente": c["component"], "descricao": c["description"]} for c in agent_cards()]

    def run_agent(self, projeto_id: str, agente: str, parametros: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        if agente not in RUNNABLE_AGENTS:
            raise ValueError(f"O agente '{agente}' não pode ser executado a partir do chat.")
        res = self.o.run_agent(projeto_id, agente, parametros or {})
        for t in res.get("terms", []):
            self.referenced_terms.append(t)
        return {"agente": res["title"], "estado": res["status"], "resumo": res["summary"],
                "insights": [f"[{i['level']}] {i['title']}: {i['detail']}" for i in res["insights"][:8]],
                "recomendacoes": res["recommendations"][:5], "proximo_passo": res.get("next_step")}
