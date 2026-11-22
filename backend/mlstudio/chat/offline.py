"""Assistente em modo offline: deteção de intenção + pesquisa na base de conhecimento.

Garante que a equipa tem sempre resposta, mesmo sem acesso à API Claude, usando
o glossário, os casos de uso, o catálogo de modelos, o conselheiro de
hiperparâmetros e o estado do projeto.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from ..knowledge import normalize
from .tools import ToolExecutor

MODEL_ALIASES = {
    "lightgbm": "lightgbm", "light gbm": "lightgbm", "lgbm": "lightgbm", "xgboost": "xgboost", "xgb": "xgboost",
    "random forest": "random_forest", "floresta aleatoria": "random_forest", "extra trees": "extra_trees",
    "regressao logistica": "logistic_regression", "logistica": "logistic_regression", "logistic": "logistic_regression",
    "arvore de decisao": "decision_tree", "arvore": "decision_tree", "hist gradient": "hist_gradient_boosting",
    "histgradient": "hist_gradient_boosting", "knn": "knn", "vizinhos": "knn", "svm": "svm", "naive bayes": "naive_bayes",
    "rede neuronal": "mlp", "mlp": "mlp", "ridge": "ridge", "lasso": "lasso", "elastic net": "elastic_net",
    "regressao linear": "linear_regression", "k-means": "kmeans", "kmeans": "kmeans", "k means": "kmeans",
    "gmm": "gaussian_mixture", "mistura gaussiana": "gaussian_mixture", "dbscan": "dbscan", "hierarquico": "agglomerative",
    "isolation forest": "isolation_forest", "lof": "local_outlier_factor", "z-score": "robust_zscore",
    "holt-winters": "holt_winters", "holt winters": "holt_winters", "ets": "holt_winters", "sarima": "sarima",
    "arima": "sarima", "naive sazonal": "seasonal_naive", "gbm com lags": "gbm_lags", "apriori": "apriori",
}

PARAM_WORDS = re.compile(r"(parametr|hiperparam|afina|configur|tuning|que valor|quantas arvores|learning rate|"
                         r"num_leaves|max_depth|n_estimators|regulariz)")
DEFINE_WORDS = re.compile(r"^(o que (e|sao|significa)|que (e|significa)|defin|explica|explique|significado|para que serve|"
                          r"qual a diferenca|diferenca entre|como funciona)")
PROJECT_WORDS = re.compile(r"(meu projeto|neste projeto|o projeto|proximo passo|o que faco|o que devo fazer|em que passo|estado do)")
USE_CASE_WORDS = re.compile(r"(caso de uso|casos de uso|quero prever|como prever|preciso de prever|que problema|"
                            r"exemplos de|aplicac)")
GREETING = re.compile(r"^(ola|bom dia|boa tarde|boa noite|ajuda|help|o que consegues|o que podes)")


def _detect_model(text: str) -> Optional[str]:
    for alias in sorted(MODEL_ALIASES, key=len, reverse=True):
        if alias in text:
            return MODEL_ALIASES[alias]
    return None


def _strip_question(text: str) -> str:
    t = re.sub(r"^(o que (e|sao|significa)( um| uma| o| a| os| as)?|que (e|significa)|defin[ea]?|explica(r)?( me)?( o| a)?|"
               r"significado de|para que serve( o| a)?|como funciona( o| a)?)\s*", "", text)
    return t.strip(" ?.!")


class OfflineAssistant:
    def __init__(self, tools: ToolExecutor):
        self.tools = tools
        self.kb = tools.kb

    def answer(self, message: str, project_id: Optional[str] = None) -> dict[str, Any]:
        text = normalize(message)
        tool_trace: list[dict[str, Any]] = []
        if GREETING.search(text):
            return self._reply(self._help(), tool_trace)
        model_id = _detect_model(text)
        if model_id and PARAM_WORDS.search(text):
            return self._params(model_id, text, project_id, tool_trace)
        if project_id and PROJECT_WORDS.search(text):
            return self._project(project_id, tool_trace)
        if "diferenca entre" in text or " vs " in text or "versus" in text:
            parts = re.split(r"\s(?:e|vs|versus)\s", _strip_question(re.sub(r".*diferenca entre", "", text)))
            terms = [self.kb.find_term(p.strip()) or next((self.kb.term(h["id"]) for h in self.kb.search(p, ["term"], 1)), None)
                     for p in parts[:2] if p.strip()]
            terms = [t for t in terms if t]
            if len(terms) == 2:
                tool_trace.append({"name": "obter_termo_glossario", "input": {"termo": [t.id for t in terms]}})
                self.tools.referenced_terms += [t.id for t in terms]
                md = "\n\n".join(f"**{t.term}** — {t.definition}" + (f"\n\n_Exemplo:_ {t.example}" if t.example else "") for t in terms)
                return self._reply(md, tool_trace)
        if DEFINE_WORDS.search(text) or len(text.split()) <= 4:
            term = self.kb.find_term(_strip_question(text))
            if term is None:
                hits = self.kb.search(_strip_question(text) or text, kinds=["term"], k=1)
                term = self.kb.term(hits[0]["id"]) if hits and hits[0]["score"] > 0.12 else None
            if term:
                tool_trace.append({"name": "obter_termo_glossario", "input": {"termo": term.id}})
                return self._reply(self._term_md(term), tool_trace)
        if USE_CASE_WORDS.search(text):
            hits = self.kb.search(message, kinds=["use_case"], k=3)
            tool_trace.append({"name": "pesquisar_conhecimento", "input": {"consulta": message, "tipos": ["use_case"]}})
            if hits:
                lines = ["Estes casos de uso encaixam na sua pergunta:", ""]
                for h in hits:
                    uc = self.kb.use_case(h["id"])
                    self.tools.referenced_use_cases.append(uc.id)
                    pt = self.kb.problem_type(uc.problem_type)
                    models = ", ".join(self.kb.model(r.model).name for r in uc.recommended_models[:3])
                    lines.append(f"- **{uc.name}** ({pt.name}) — {uc.business_question} Modelos recomendados: {models}.")
                lines.append("\nPode criar um projeto a partir de qualquer um deles na página **Casos de uso**.")
                return self._reply("\n".join(lines), tool_trace)
        if model_id:
            spec = self.kb.model(model_id)
            tool_trace.append({"name": "obter_modelo", "input": {"id": model_id}})
            hp = "\n".join(f"- `{h.name}` ({h.label}) — {h.description}" for h in spec.hyperparameters if h.importance == "alta")
            md = (f"**{spec.name}** — {spec.description}\n\n**Como funciona:** {spec.how_it_works}\n\n"
                  f"**Pontos fortes:** {', '.join(spec.strengths)}.\n\n**Limitações:** {', '.join(spec.weaknesses)}.\n\n"
                  f"**Quando usar:** {spec.when_to_use}\n\n**Hiperparâmetros mais importantes:**\n{hp}\n\n"
                  "Peça-me _\"que parâmetros uso no " + spec.name + " para o caso X?\"_ para uma recomendação concreta.")
            return self._reply(md, tool_trace)
        # pesquisa geral
        hits = self.kb.search(message, k=6)
        tool_trace.append({"name": "pesquisar_conhecimento", "input": {"consulta": message}})
        if not hits:
            return self._reply("Não encontrei informação sobre isso na base de conhecimento. Experimente reformular ou "
                               "consulte o **Glossário**.", tool_trace)
        top = hits[0]
        md = self._doc_md(top)
        others = [h for h in hits[1:4]]
        if others:
            md += "\n\n**Também pode interessar:** " + "; ".join(f"{h['title']}" for h in others) + "."
        for h in hits:
            if h["kind"] == "term":
                self.tools.referenced_terms.append(h["id"])
        return self._reply(md, tool_trace)

    # ------------------------------------------------------------------ respostas
    def _reply(self, md: str, trace: list[dict[str, Any]]) -> dict[str, Any]:
        return {"text": md, "tools": trace}

    def _help(self) -> str:
        return ("Olá! Sou o assistente da plataforma (modo offline). Posso ajudar a:\n\n"
                "- **Explicar conceitos** — _\"o que é a AUC?\"_, _\"diferença entre precisão e recall\"_\n"
                "- **Aconselhar hiperparâmetros** — _\"que parâmetros uso no LightGBM para churn?\"_\n"
                "- **Sugerir casos de uso** — _\"quero prever atrasos nas entregas\"_\n"
                "- **Orientar o projeto** — _\"qual é o próximo passo?\"_ (dentro de um projeto)\n\n"
                "Com a API Claude configurada consigo ainda conversar livremente e executar agentes por si.")

    def _term_md(self, t: Any) -> str:
        self.tools.referenced_terms.append(t.id)
        md = f"**{t.term}**" + (f" (_{t.en}_)" if t.en else "") + f"\n\n{t.definition}"
        if t.formula:
            md += f"\n\n**Fórmula:** `{t.formula}`"
        if t.example:
            md += f"\n\n**Exemplo:** {t.example}"
        if t.pitfalls:
            md += "\n\n**Atenção:** " + "; ".join(t.pitfalls)
        rel = [self.kb.term(r) for r in t.related if self.kb.term(r)]
        if rel:
            md += "\n\n**Relacionados:** " + ", ".join(r.term for r in rel)
            self.tools.referenced_terms += [r.id for r in rel]
        return md

    def _doc_md(self, hit: dict[str, Any]) -> str:
        kind = hit["kind"]
        if kind == "term":
            return self._term_md(self.kb.term(hit["id"]))
        if kind == "faq":
            f = self.kb.faq[int(hit["id"].split("_")[1])]
            self.tools.referenced_terms += f.terms
            return f"**{f.q}**\n\n{f.a}"
        if kind == "use_case":
            uc = self.kb.use_case(hit["id"])
            self.tools.referenced_use_cases.append(uc.id)
            return f"**{uc.name}** — {uc.summary}\n\n**Pergunta:** {uc.business_question}\n\n**Decisão:** {uc.decision}"
        if kind == "model":
            spec = self.kb.model(hit["id"])
            return f"**{spec.name}** — {spec.description}\n\n**Quando usar:** {spec.when_to_use}"
        if kind == "step":
            s = self.kb.step(hit["id"])
            return f"**Passo {s.order}. {s.title}** — {s.objective}\n\n" + "\n".join(f"{i + 1}. {h}" for i, h in enumerate(s.how))
        if kind == "guide":
            g = self.kb.guide(hit["id"])
            return f"**{g.title}** — {g.summary}\n\n" + "\n".join(f"- {s.title}" for s in g.sections)
        return f"**{hit['title']}** — {hit['snippet']}"

    def _use_case_from_text(self, text: str) -> Optional[str]:
        best, best_hits = None, 0
        for uc in self.kb.use_cases:
            words = {w for w in re.split(r"[_\W]+", normalize(uc.id + " " + uc.name)) if len(w) >= 4}
            words -= {"previsao", "risco", "clientes", "deteccao", "analise", "valor", "tempo", "taxa"}
            hits = sum(1 for w in words if re.search(rf"\b{w}", text))
            if hits > best_hits:
                best, best_hits = uc.id, hits
        if best:
            return best
        hits = self.kb.search(text, kinds=["use_case"], k=1)
        return hits[0]["id"] if hits and hits[0]["score"] > 0.08 else None

    def _params(self, model_id: str, text: str, project_id: Optional[str], trace: list[dict[str, Any]]) -> dict[str, Any]:
        uc_id = self._use_case_from_text(text)
        goal = next((g for g in ("performance", "interpretabilidade", "rapidez") if g in text), None)
        args: dict[str, Any] = {"modelo": model_id, "caso_de_uso": uc_id, "objetivo": goal}
        nums = re.findall(r"(\d[\d .]*)\s*(mil|k)?\s*(linhas|registos|clientes|transacoes|observacoes)", text)
        rate = re.findall(r"(\d+[,.]?\d*)\s*%", text)
        if nums:
            v = float(nums[0][0].replace(" ", "").replace(".", ""))
            args["n_linhas"] = int(v * (1000 if nums[0][1] else 1))
        if rate:
            args["taxa_positivos"] = float(rate[0].replace(",", ".")) / 100
        if project_id and not (nums or rate):  # números explícitos na pergunta têm prioridade sobre o projeto
            args["projeto_id"] = project_id
        trace.append({"name": "recomendar_parametros", "input": {k: v for k, v in args.items() if v is not None}})
        rec = self.tools.recommend(**{k: v for k, v in args.items() if v is not None})
        lines = [f"**Recomendação para {rec['modelo']}**" + (f" no caso _{self.kb.use_case(uc_id).name}_" if uc_id else "")
                 + f" (objetivo: {rec['objetivo']}):", "", "| Parâmetro | Valor | Porquê |", "|---|---|---|"]
        for d in rec["parametros"]:
            if d["importance"] != "baixa":
                lines.append(f"| `{d['name']}` | **{d['value']}** | {d['reason']} |")
        a = rec["avaliacao"]
        lines += ["", f"Risco de overfitting **{a['overfit_level']}**, de underfitting **{a['underfit_level']}** (indicativo)."]
        if rec["notas"]:
            lines += [""] + [f"- {n}" for n in rec["notas"]]
        lines.append("\nPode experimentar outros valores no **Conselheiro de parâmetros** — valido-os em tempo real.")
        return self._reply("\n".join(lines), trace)

    def _project(self, project_id: str, trace: list[dict[str, Any]]) -> dict[str, Any]:
        trace.append({"name": "estado_projeto", "input": {"projeto_id": project_id}})
        st = self.tools.project_state(project_id)
        nxt = st["proximo_passo"]
        lines = [f"**Projeto {st['nome']}** ({st['tipo']})", ""]
        done = [s for s, v in st["passos"].items() if v in ("done", "warning")]
        lines.append(f"Passos concluídos: {len(done)} de {len(st['passos'])}.")
        if st.get("campeao"):
            c = st["campeao"]
            lines.append(f"Modelo campeão: **{c['model_name']}** ({c['stage']}).")
        if nxt:
            step = self.kb.step(nxt)
            lines += ["", f"**Próximo passo: {step.order}. {step.title}** — {step.objective}", ""]
            lines += [f"{i + 1}. {h}" for i, h in enumerate(step.how)]
            self.tools.referenced_terms += step.terms[:4]
        else:
            lines.append("\nTodos os passos estão concluídos — mantenha a monitorização regular.")
        return self._reply("\n".join(lines), trace)
