"""Agente de Seleção de Modelos e Agente Conselheiro de Hiperparâmetros."""
from __future__ import annotations

from typing import Any, Optional

from .. import advisor
from ..core import agent as B
from ..core.agent import Agent, AgentCard, AgentError, AgentResult
from ..core.context import AgentContext
from ..ml.factory import library_available
from .common import data_profile, model_name

TASK_FAMILY_BONUS = {"boosting": 14, "tree_ensemble": 9, "linear": 3, "tree": 0, "instance": -4, "kernel": -6,
                     "probabilistic": -8, "neural": -4, "ml_ts": 10, "statistical_ts": 6, "baseline_ts": 0,
                     "clustering": 0, "anomaly": 0, "association": 0}


class SelectionAgent(Agent):
    card = AgentCard(
        id="selection", name="Agente de Seleção de Modelos", component="Seleção de algoritmos",
        role="Cientista de dados sénior", icon="list-checks", step="modelos",
        description="Ordena os algoritmos candidatos para o tipo de problema, considerando o caso de uso, o volume "
                    "e a forma dos dados, a necessidade de explicabilidade e as bibliotecas disponíveis. Garante "
                    "sempre uma referência interpretável.",
        capabilities=["Pontuação justificada por modelo", "Penalizações por volume/dimensão",
                      "Garantia de modelo interpretável", "Verificação de bibliotecas"],
        inputs=["Tipo de problema", "Perfil dos dados", "Caso de uso"], outputs=["Modelos selecionados"],
        params=[{"name": "n_models", "label": "Nº de modelos", "type": "int"},
                {"name": "models", "label": "Escolha manual", "type": "models"}],
    )

    def run(self, ctx: AgentContext, result: AgentResult, n_models: int = 3, models: Optional[list[str]] = None,
            **_: Any) -> None:
        p, kb = ctx.project, ctx.kb
        uc = ctx.use_case
        prof = data_profile(ctx)
        task = p.problem_type
        candidates = kb.models_for(task)
        rec_rank = {r.model: i for i, r in enumerate(uc.recommended_models)} if uc else {}
        rec_why = {r.model: r.why for r in uc.recommended_models} if uc else {}
        interp = (uc.profile.get("interpretability") if uc else None) or "média"
        n, nf = prof.n_rows, prof.n_features
        rows = []
        for m in candidates:
            score, reasons = 50.0, []
            if m.id in rec_rank:
                bonus = [30, 22, 15, 10][min(rec_rank[m.id], 3)]
                score += bonus
                reasons.append(f"recomendado para o caso (+{bonus}): {rec_why[m.id]}")
            fam = TASK_FAMILY_BONUS.get(m.family, 0)
            if fam:
                score += fam
                reasons.append(f"família {m.family} ({fam:+d})")
            if interp == "alta":
                b = 6 * m.interpretability - 18
                score += b
                reasons.append(f"interpretabilidade exigida alta ({b:+d})")
            elif interp == "média":
                score += 2 * (m.interpretability - 3)
            if m.id == "svm" and n > 20_000:
                score -= 40; reasons.append("lento com muitas linhas (−40)")
            if m.id == "knn" and (n > 50_000 or nf > 30):
                score -= 25; reasons.append("lento/instável em bases grandes ou com muitas variáveis (−25)")
            if m.id == "mlp" and n < 5000:
                score -= 20; reasons.append("poucos dados para redes neuronais (−20)")
            if m.id == "agglomerative" and n > 10_000:
                score -= 20; reasons.append("memória quadrática em bases grandes (−20)")
            if m.id == "local_outlier_factor" and n > 50_000:
                score -= 20; reasons.append("lento em bases grandes (−20)")
            if m.id == "sarima" and ((prof.n_series or 1) > 5 or (prof.series_length or 0) > 3000):
                score -= 25; reasons.append("muitas séries ou séries longas tornam o SARIMA lento (−25)")
            if m.id == "seasonal_naive":
                score += 15; reasons.append("baseline obrigatória em previsão (+15)")
            if prof.missing_rate > 0.05 and m.handles_missing:
                score += 4; reasons.append("trata valores em falta nativamente (+4)")
            available = library_available(m.library)
            if not available:
                score -= 200; reasons.append(f"biblioteca {m.library} não instalada")
            rows.append({"modelo": m.name, "id": m.id, "pontuacao": round(score, 1), "interpretabilidade": m.interpretability,
                         "rapidez": m.speed, "disponivel": available, "razoes": "; ".join(reasons) or "pontuação base"})
        rows.sort(key=lambda r: -r["pontuacao"])
        if models:
            unknown = [m for m in models if m not in {r["id"] for r in rows}]
            if unknown:
                raise AgentError(f"Modelos não aplicáveis a este problema: {', '.join(unknown)}")
            selected = models
            how = "escolha manual"
        else:
            avail = [r for r in rows if r["disponivel"]]
            selected = [r["id"] for r in avail[:n_models]]
            if p.supervised and not any(kb.model(s).interpretability >= 4 for s in selected):
                interp_m = next((r["id"] for r in avail if kb.model(r["id"]).interpretability >= 4), None)
                if interp_m:
                    selected = selected[:-1] + [interp_m]
                    result.info("Modelo interpretável incluído", f"{model_name(ctx, interp_m)} foi incluído como "
                                "referência explicável.", ["baseline", "explicabilidade"])
            if p.problem_type == "forecasting" and "seasonal_naive" not in selected:
                selected = selected[:-1] + ["seasonal_naive"]
            how = "pontuação automática"
        ctx.save_project(selected_models=selected)
        result.blocks.append(B.table("Classificação dos modelos candidatos", rows, [
            {"key": "modelo", "label": "Modelo"}, {"key": "pontuacao", "label": "Pontuação", "fmt": "num"},
            {"key": "interpretabilidade", "label": "Interpretabilidade", "fmt": "stars"},
            {"key": "rapidez", "label": "Rapidez", "fmt": "stars"}, {"key": "razoes", "label": "Justificação"}],
            terms=["algoritmo", "baseline"]))
        result.success("Modelos selecionados", ", ".join(model_name(ctx, s) for s in selected) + f" ({how}).")
        noun = "modelo selecionado" if len(selected) == 1 else "modelos selecionados"
        result.summary = f"{len(selected)} {noun}: " + ", ".join(model_name(ctx, s) for s in selected) + "."
        result.outputs = {"selected": selected, "ranking": rows}
        result.terms = ["algoritmo", "ensemble", "gradient_boosting", "regressao_logistica"]
        result.next_step = "parametros"


class AdvisorAgent(Agent):
    card = AgentCard(
        id="advisor", name="Agente Conselheiro de Hiperparâmetros", component="Hiperparâmetros",
        role="Especialista em afinação", icon="sliders", step="parametros",
        description="Recomenda e explica os hiperparâmetros de cada modelo para o caso de uso e o perfil dos "
                    "dados (volume, desequilíbrio, assimetria, sazonalidade...), propõe o espaço de pesquisa para "
                    "afinação e avalia o risco de overfitting/underfitting. Respeita parâmetros bloqueados pelo utilizador.",
        capabilities=["Recomendação por modelo × caso × dados", "Explicação de cada parâmetro",
                      "Espaço de pesquisa para tuning", "Indicador de risco de overfitting"],
        inputs=["Modelos selecionados", "Perfil dos dados", "Caso de uso", "Objetivo"],
        outputs=["Hiperparâmetros por modelo", "Espaço de pesquisa"],
        params=[{"name": "goal", "label": "Objetivo", "type": "choice",
                 "choices": ["equilibrado", "performance", "interpretabilidade", "rapidez"]}],
    )

    def run(self, ctx: AgentContext, result: AgentResult, goal: Optional[str] = None, **_: Any) -> None:
        p = ctx.project
        if not p.selected_models:
            raise AgentError("Selecione primeiro os modelos (Agente de Seleção de Modelos).")
        goal = goal or p.goal
        prof = data_profile(ctx)
        params = dict(p.model_params)
        rows = []
        for mid in p.selected_models:
            rec = advisor.recommend(mid, prof, p.use_case_id, goal)
            locked = mid in p.params_locked
            if not locked:
                params[mid] = rec["params"]
            used = params.get(mid, rec["params"])
            val = advisor.validate(mid, used, prof, p.use_case_id)
            result.blocks.append(B.params_block(f"{rec['model_name']}" + (" — parâmetros bloqueados pelo utilizador" if locked else ""),
                                                mid, rec["details"], rec["notes"]))
            rows.append({"modelo": rec["model_name"], "complexidade": val["assessment"]["complexity"],
                         "overfitting": val["assessment"]["overfit_level"], "underfitting": val["assessment"]["underfit_level"],
                         "custo_treino": val["assessment"]["training_cost_level"],
                         "avisos": len([i for i in val["issues"] if i["level"] != "info"])})
            for i in val["issues"]:
                if i["level"] in ("warning", "error"):
                    result.warn(f"{rec['model_name']}: {i['param'] or 'configuração'}", i["message"], [i["term"]] if i.get("term") else [])
        ctx.save_project(model_params=params, goal=goal)
        result.blocks.insert(0, B.table("Avaliação das configurações", rows, [
            {"key": "modelo", "label": "Modelo"}, {"key": "complexidade", "label": "Complexidade", "fmt": "int"},
            {"key": "overfitting", "label": "Risco de overfitting", "fmt": "badge"},
            {"key": "underfitting", "label": "Risco de underfitting", "fmt": "badge"},
            {"key": "custo_treino", "label": "Custo de treino", "fmt": "badge"}, {"key": "avisos", "label": "Avisos", "fmt": "int"}],
            terms=["bias_variancia", "overfitting", "underfitting"]))
        result.blocks.insert(1, B.kpis([
            B.kpi("Linhas", prof.n_rows, "int"), B.kpi("Variáveis", prof.n_features, "int"),
            B.kpi("Desequilíbrio", prof.imbalance, "text", "", "desequilibrio_classes"),
            B.kpi("Objetivo", goal, "text", advisor.GOALS.get(goal, "")),
        ], "Perfil usado pelo conselheiro"))
        result.summary = (f"Hiperparâmetros recomendados para {len(p.selected_models)} modelos (objetivo: {goal}). "
                          "Pode ajustá-los interativamente no Conselheiro.")
        result.outputs = {"params": params, "profile": prof.to_dict(), "goal": goal}
        result.terms = ["hiperparametro", "regularizacao", "learning_rate", "bias_variancia", "tuning"]
        result.next_step = "treino"
