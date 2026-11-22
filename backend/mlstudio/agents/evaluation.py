"""Agente de Avaliação e Agente de Explicabilidade."""
from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd
from sklearn import metrics as skm

from ..core import agent as B
from ..core.agent import Agent, AgentCard, AgentError, AgentResult
from ..core.context import AgentContext
from ..ml import metrics as M
from ..ml.explain import (
    format_value,
    local_contributions,
    partial_dependence_raw,
    permutation_importance_raw,
    reasons_text,
)
from ..ml.factory import predict_scores, transformed_feature_names
from ..ml.semantic import humanize
from .common import num, pct, score_label


def champion_meta(ctx: AgentContext, version_id: Optional[str] = None) -> dict[str, Any]:
    vid = version_id or ctx.project.champion_version_id
    if not vid:
        raise AgentError("Ainda não existe modelo treinado — execute o passo de Treino.")
    return ctx.registry.get(vid)


def _segment_columns(hold: pd.DataFrame, features: list[str], k: int = 3) -> list[str]:
    cats = [c for c in features if c in hold.columns and not pd.api.types.is_numeric_dtype(hold[c])
            and 2 <= hold[c].nunique() <= 12]
    return cats[:k]


class EvaluationAgent(Agent):
    card = AgentCard(
        id="evaluation", name="Agente de Avaliação", component="Avaliação",
        role="Revisor de modelos", icon="target", step="avaliacao",
        description="Avalia o modelo no conjunto de teste com métricas técnicas e de negócio: curvas ROC/PR, lift, "
                    "ganhos, calibração, matriz de confusão, limiar ótimo pela matriz de custo-benefício, resíduos e "
                    "erro por segmento. Para previsão, segmentação e anomalias resume a qualidade específica.",
        capabilities=["Curvas ROC/PR/ganhos/calibração", "Limiar ótimo por custo-benefício", "Impacto em euros",
                      "Erro por segmento", "Comparação com baseline"],
        inputs=["Modelo campeão", "Conjunto de teste", "Custos de negócio"],
        outputs=["Métricas", "Limiar ótimo", "Impacto de negócio"],
        params=[{"name": "threshold", "label": "Limiar manual", "type": "float"},
                {"name": "capacity", "label": "Capacidade (nº de casos a tratar)", "type": "int"}],
    )

    def run(self, ctx: AgentContext, result: AgentResult, version_id: Optional[str] = None,
            threshold: Optional[float] = None, capacity: Optional[int] = None, **_: Any) -> None:
        meta = champion_meta(ctx, version_id)
        kind = meta.get("kind")
        if kind == "forecast":
            return self._forecast(ctx, result, meta)
        if kind == "clustering":
            return self._clustering(ctx, result, meta)
        if kind == "anomaly":
            return self._anomaly(ctx, result, meta)
        if kind == "association":
            return self._association(ctx, result, meta)
        hold = ctx.registry.holdout(meta["id"])
        task = meta["problem_type"]
        if task == "binary_classification":
            self._binary(ctx, result, meta, hold, threshold, capacity)
        elif task == "multiclass_classification":
            self._multiclass(ctx, result, meta, hold)
        else:
            self._regression(ctx, result, meta, hold)
        result.terms = ["conjunto_teste", "baseline", "matriz_custo_beneficio"]
        result.next_step = "explicabilidade"

    # ------------------------------------------------------------------ binária
    def _binary(self, ctx: AgentContext, result: AgentResult, meta: dict, hold: pd.DataFrame,
                threshold: Optional[float], capacity: Optional[int]) -> None:
        y, p = hold["__y__"].values.astype(int), hold["__p__"].values
        costs = ctx.project.business_costs or meta.get("business_costs") or None
        sweep = M.threshold_sweep(y, p, costs)
        if threshold is not None:
            thr, why = float(threshold), "definido manualmente"
        elif capacity:
            n_pop = ctx.project.data_info.get("rows") or len(y)
            k = int(np.clip(round(capacity * len(y) / n_pop), 1, len(p)))  # capacidade na escala do conjunto de teste
            thr = float(np.sort(p)[::-1][k - 1])
            why = f"capacidade operacional de {capacity} casos (top {pct(capacity / n_pop)} da base)"
        else:
            thr, why = M.best_threshold(sweep, costs)
        m = M.binary_metrics(y, p, thr)
        base = meta.get("baseline_metrics", {})
        pred = (p >= thr).astype(int)
        tn, fp, fn, tp = skm.confusion_matrix(y, pred, labels=[0, 1]).ravel()
        ctx.registry.update(meta["id"], threshold=thr, threshold_reason=why, metrics_test={**meta.get("metrics_test", {}), **m})
        result.blocks.append(B.kpis([
            B.kpi("AUC-ROC", m["roc_auc"], "num", f"baseline {num(base.get('roc_auc', 0.5), 2)}", "auc_roc"),
            B.kpi("PR-AUC", m["pr_auc"], "num", f"aleatório = {pct(y.mean())}", "pr_auc"),
            B.kpi("Lift no 1.º decil", m.get("lift_top_decile"), "num", "× face a escolher ao acaso", "lift"),
            B.kpi("KS / Gini", f"{num(m.get('ks', 0))} / {num(m.get('gini', 0))}", "text", "", "ks_estatistica"),
            B.kpi("Limiar escolhido", thr, "num", why, "limiar_decisao"),
            B.kpi("Precisão / Recall no limiar", f"{pct(m['precision'])} / {pct(m['recall'])}", "text", "", "precisao"),
        ], "Desempenho no conjunto de teste"))
        result.blocks.append(B.heatmap("Matriz de confusão (no limiar escolhido)", ["Previsto: não", "Previsto: sim"],
                                       ["Real: não", "Real: sim"], [[int(tn), int(fp)], [int(fn), int(tp)]],
                                       terms=["matriz_confusao", "falso_positivo"], fmt="0"))
        if costs:
            row = sweep.iloc[(sweep["limiar"] - thr).abs().argmin()]
            profit = float(row["lucro"])
            scale = 1.0
            n_pop = ctx.project.data_info.get("rows")
            if n_pop:
                scale = n_pop / len(y)
            result.blocks.append(B.kpis([
                B.kpi("Valor líquido no teste", profit, "money", f"{len(y)} casos de teste", "matriz_custo_beneficio"),
                B.kpi("Valor extrapolado à população", profit * scale, "money", f"≈ {n_pop or len(y):,} casos".replace(",", " "), "roi"),
                B.kpi("Casos a tratar", int(row["sinalizados"]), "int", f"{pct(row['pct_sinalizados'])} da base"),
                B.kpi("Positivos captados", int(row["vp"]), "int", f"de {int(y.sum())}", "recall"),
                B.kpi("Valor por captar (FN)", float(row["valor_por_captar"]) * scale, "money", "casos positivos não detetados", "falso_positivo"),
            ], "Impacto de negócio (vs. não fazer nada)"))
            result.blocks.append(B.chart("line", "Lucro esperado por limiar",
                                         sweep[["limiar", "lucro"]],
                                         x="limiar", y="lucro", terms=["matriz_custo_beneficio", "limiar_decisao"],
                                         reference_x=thr, fmt="money"))
        result.blocks.append(B.chart("line", "Precisão, recall e F1 por limiar", sweep[["limiar", "precisao", "recall", "f1"]],
                                     x="limiar", y=["precisao", "recall", "f1"], terms=["precisao", "recall", "f1_score"],
                                     reference_x=thr))
        result.blocks.append(B.chart("line", "Curva ROC", M.roc_points(y, p), x="fpr", y=["tpr", "aleatorio"],
                                     terms=["curva_roc", "auc_roc"], numeric_x=True))
        result.blocks.append(B.chart("line", "Curva precisão-recall", M.pr_points(y, p), x="recall", y=["precisao", "base"],
                                     terms=["pr_auc"], numeric_x=True))
        lt = M.lift_table(y, p)
        result.blocks.append(B.chart("bar", "Lift por decil de score", lt[["decil", "lift"]], x="decil", y="lift", terms=["lift"]))
        result.blocks.append(B.chart("line", "Curva de ganhos acumulados",
                                     [{"pct_base": 0, "modelo": 0, "aleatorio": 0}] +
                                     [{"pct_base": float(r.pct_base), "modelo": float(r.ganho_acumulado), "aleatorio": float(r.pct_base)}
                                      for r in lt.itertuples()], x="pct_base", y=["modelo", "aleatorio"],
                                     terms=["curva_ganhos"], numeric_x=True))
        result.blocks.append(B.chart("line", "Calibração (previsto vs observado)", M.calibration_points(y, p),
                                     x="previsto", y=["observado", "perfeito"], terms=["calibracao"], numeric_x=True))
        cal = M.calibration_points(y, p)
        if cal and max(abs(c["previsto"] - c["observado"]) for c in cal) > 0.15:
            result.warn("Probabilidades pouco calibradas", "Use o score para ordenar; se precisar de probabilidades "
                        "reais (ex.: PD), recalibre.", ["calibracao"])
        self._segments(result, meta, hold, lambda g: (skm.roc_auc_score(g["__y__"], g["__p__"])
                                                       if g["__y__"].nunique() > 1 else np.nan), "AUC")
        if m["roc_auc"] < 0.65:
            result.warn("Capacidade de discriminação fraca", "AUC < 0,65 — reveja features e definição do alvo.", ["auc_roc"])
        else:
            result.success("Modelo discrimina bem os casos", f"AUC {num(m['roc_auc'])} e lift {num(m.get('lift_top_decile', 0), 1)}× no 1.º decil.")
        result.summary = (f"AUC {num(m['roc_auc'])}, PR-AUC {num(m['pr_auc'])}. Limiar {num(thr)} ({why}): precisão "
                          f"{pct(m['precision'])}, recall {pct(m['recall'])}.")
        result.outputs = {"metrics": m, "threshold": thr, "threshold_reason": why}

    # ------------------------------------------------------------------ multiclasse
    def _multiclass(self, ctx: AgentContext, result: AgentResult, meta: dict, hold: pd.DataFrame) -> None:
        classes = meta["classes"]
        y = hold["__y__"].values.astype(int)
        proba = hold[[f"__p{k}__" for k in range(len(classes))]].values
        pred = np.argmax(proba, axis=1)
        m = M.multiclass_metrics(y, proba, list(range(len(classes))))
        base = meta.get("baseline_metrics", {})
        result.blocks.append(B.kpis([
            B.kpi("F1-macro", m["f1_macro"], "num", f"baseline {num(base.get('f1_macro', 0))}", "f1_score"),
            B.kpi("Balanced accuracy", m["balanced_accuracy"], "pct", "", "balanced_accuracy"),
            B.kpi("Accuracy", m["accuracy"], "pct", "", "accuracy"),
            B.kpi("Log loss", m["log_loss"], "num", "", "log_loss"),
        ], "Desempenho no conjunto de teste"))
        cm = skm.confusion_matrix(y, pred, labels=list(range(len(classes))))
        result.blocks.append(B.heatmap("Matriz de confusão", [f"Prev.: {c}" for c in classes], [f"Real: {c}" for c in classes],
                                       cm.tolist(), terms=["matriz_confusao"], fmt="0"))
        rep = skm.classification_report(y, pred, labels=list(range(len(classes))), target_names=[str(c) for c in classes],
                                        output_dict=True, zero_division=0)
        result.blocks.append(B.table("Desempenho por classe", [
            {"classe": c, "precisao": rep[str(c)]["precision"], "recall": rep[str(c)]["recall"], "f1": rep[str(c)]["f1-score"],
             "suporte": int(rep[str(c)]["support"])} for c in classes],
            [{"key": "classe", "label": "Classe"}, {"key": "precisao", "label": "Precisão", "fmt": "pct"},
             {"key": "recall", "label": "Recall", "fmt": "pct"}, {"key": "f1", "label": "F1", "fmt": "num"},
             {"key": "suporte", "label": "Casos", "fmt": "int"}], terms=["precisao", "recall"]))
        worst = min(classes, key=lambda c: rep[str(c)]["f1-score"])
        result.info(f"Classe mais difícil: {worst}", f"F1 de {num(rep[str(worst)]['f1-score'])}.")
        result.summary = f"F1-macro {num(m['f1_macro'])}; balanced accuracy {pct(m['balanced_accuracy'])}."
        result.outputs = {"metrics": m}

    # ------------------------------------------------------------------ regressão
    def _regression(self, ctx: AgentContext, result: AgentResult, meta: dict, hold: pd.DataFrame) -> None:
        y, pred = hold["__y__"].values.astype(float), hold["__pred__"].values.astype(float)
        m = M.regression_metrics(y, pred)
        base = meta.get("baseline_metrics", {})
        result.blocks.append(B.kpis([
            B.kpi("MAE", m["mae"], "num", f"baseline {num(base.get('mae', np.nan))}", "mae"),
            B.kpi("RMSE", m["rmse"], "num", "", "rmse"),
            B.kpi("R²", m["r2"], "num", "", "r2"),
            B.kpi("WAPE", m["wape"], "pct", "", "wape"),
            B.kpi("Bias", m["bias"], "pct", "+ = sobrestima", "bias_previsao"),
            B.kpi("Melhoria vs baseline", 1 - m["mae"] / base["mae"] if base.get("mae") else None, "pct", "redução do MAE", "baseline"),
        ], "Desempenho no conjunto de teste"))
        idx = np.random.default_rng(1).choice(len(y), size=min(600, len(y)), replace=False)
        result.blocks.append(B.chart("scatter", "Previsto vs real", [{"real": float(y[i]), "previsto": float(pred[i])} for i in idx],
                                     x="real", y="previsto", terms=["residuo"], diagonal=True))
        res = y - pred
        hist, edges = np.histogram(np.clip(res, np.quantile(res, 0.01), np.quantile(res, 0.99)), bins=25)
        result.blocks.append(B.chart("histogram", "Distribuição dos resíduos (real − previsto)",
                                     [{"residuo": f"{edges[i]:.3g}", "n": int(hist[i])} for i in range(len(hist))],
                                     x="residuo", y="n", terms=["residuo"]))
        dec = pd.qcut(pd.Series(pred), 10, labels=False, duplicates="drop")
        g = pd.DataFrame({"dec": dec + 1, "real": y, "prev": pred}).groupby("dec").mean().reset_index()
        result.blocks.append(B.chart("bar", "Média real vs prevista por decil de previsão", g.rename(columns={"dec": "decil"}),
                                     x="decil", y=["real", "prev"], terms=["calibracao"]))
        self._segments(result, meta, hold, lambda gg: float(np.mean(np.abs(gg["__y__"] - gg["__pred__"]))), "MAE")
        if base.get("mae") and m["mae"] >= base["mae"] * 0.97:
            result.critical("O modelo praticamente não melhora a baseline", "", ["baseline"])
        else:
            result.success("Erro inferior à baseline", f"MAE {num(m['mae'])} vs {num(base.get('mae', np.nan))}.")
        result.summary = f"MAE {num(m['mae'])}, R² {num(m['r2'])}, WAPE {pct(m['wape'])}."
        result.outputs = {"metrics": m}

    def _segments(self, result: AgentResult, meta: dict, hold: pd.DataFrame, fn: Any, label: str) -> None:
        rows = []
        for c in _segment_columns(hold, meta.get("features", [])):
            for val, g in hold.groupby(hold[c].astype(str)):
                if len(g) < 30:
                    continue
                rows.append({"variavel": c, "segmento": val, "n": len(g), "valor": fn(g)})
        if rows:
            result.blocks.append(B.table(f"{label} por segmento", rows, [
                {"key": "variavel", "label": "Variável"}, {"key": "segmento", "label": "Segmento"},
                {"key": "n", "label": "Casos", "fmt": "int"}, {"key": "valor", "label": label, "fmt": "num"}],
                description="Onde o modelo funciona melhor/pior.", terms=["fairness"]))

    # ------------------------------------------------------------------ não supervisionados / previsão
    def _forecast(self, ctx: AgentContext, result: AgentResult, meta: dict) -> None:
        scores = meta.get("backtest_scores", {})
        rows = [{"modelo": ctx.kb.model(k).name if ctx.kb.model(k) else k, **v} for k, v in scores.items()]
        best = meta["model_id"]
        b = scores.get(best, {})
        naive = scores.get("seasonal_naive", {})
        result.blocks.append(B.kpis([
            B.kpi("WAPE (backtest)", b.get("wape"), "pct", meta.get("model_name"), "wape"),
            B.kpi("Bias", b.get("bias"), "pct", "+ = sobrestima", "bias_previsao"),
            B.kpi("MASE", b.get("mase"), "num", "< 1 bate o naive sazonal", "mase"),
            B.kpi("Melhoria vs naive", (1 - b["wape"] / naive["wape"]) if naive.get("wape") and b.get("wape") else None, "pct", "redução do WAPE", "naive_sazonal"),
        ], "Qualidade da previsão (backtesting)"))
        result.blocks.append(B.table("Comparação de modelos (backtesting)", rows, [
            {"key": "modelo", "label": "Modelo"}, {"key": "wape", "label": "WAPE", "fmt": "pct"},
            {"key": "mae", "label": "MAE", "fmt": "num"}, {"key": "rmse", "label": "RMSE", "fmt": "num"},
            {"key": "smape", "label": "sMAPE", "fmt": "pct"}, {"key": "bias", "label": "Bias", "fmt": "pct"},
            {"key": "mase", "label": "MASE", "fmt": "num"}], terms=["backtesting", "wape", "mase"]))
        try:
            bt = ctx.registry.artifact(meta["id"], "backtest")
            bt = bt[bt["modelo"] == best]
            g = bt.groupby("passo").apply(lambda d: np.sum(np.abs(d["y"] - d["yhat"])) / max(np.sum(np.abs(d["y"])), 1e-9),
                                          include_groups=False)
            result.blocks.append(B.chart("line", "WAPE por passo do horizonte", [{"passo": int(k), "wape": float(v)} for k, v in g.items()],
                                         x="passo", y="wape", terms=["horizonte_previsao"], fmt="pct"))
        except KeyError:
            pass
        if b.get("bias") is not None and abs(b["bias"]) > 0.05:
            result.warn("Enviesamento sistemático", f"A previsão {'sobrestima' if b['bias'] > 0 else 'subestima'} "
                        f"{pct(abs(b['bias']))} do volume.", ["bias_previsao"])
        if b.get("mase") is not None and b["mase"] >= 1:
            result.warn("Não bate o naive sazonal", "MASE ≥ 1.", ["mase"])
        result.summary = f"WAPE {pct(b.get('wape', np.nan))} em backtesting com {meta.get('model_name')}."
        result.outputs = {"scores": scores}
        result.next_step = "explicabilidade"

    def _clustering(self, ctx: AgentContext, result: AgentResult, meta: dict) -> None:
        q = meta.get("quality", {})
        result.blocks.append(B.kpis([
            B.kpi("Silhueta", q.get("silhouette"), "num", "> 0,25 razoável; > 0,5 forte", "silhueta"),
            B.kpi("Davies-Bouldin", q.get("davies_bouldin"), "num", "menor é melhor", "davies_bouldin"),
            B.kpi("Nº de segmentos", q.get("n_clusters"), "int", "", "clustering"),
            B.kpi("Maior / menor segmento", f"{pct(q.get('max_share', 0))} / {pct(q.get('min_share', 0))}", "text", ""),
        ], "Qualidade da segmentação"))
        if q.get("silhouette") is not None and q["silhouette"] < 0.2:
            result.warn("Estrutura de segmentos fraca", "Silhueta < 0,2 — experimente outras variáveis ou outro k.", ["silhueta"])
        if q.get("min_share", 1) < 0.03:
            result.warn("Segmento muito pequeno", "Um segmento tem menos de 3% da base — pode ser ruído.", ["clustering"])
        result.summary = f"Silhueta {num(q.get('silhouette', np.nan))} com {q.get('n_clusters')} segmentos."
        result.outputs = {"quality": q}
        result.next_step = "explicabilidade"

    def _anomaly(self, ctx: AgentContext, result: AgentResult, meta: dict) -> None:
        q = meta.get("quality", {})
        items = [B.kpi("% sinalizado", q.get("flagged_rate"), "pct", "", "contaminacao")]
        if q.get("precision_at_k") is not None:
            items += [B.kpi("Precisão no top-k", q["precision_at_k"], "pct", f"k = {q.get('k')}", "precision_at_k"),
                      B.kpi("Recall no top-k", q.get("recall_at_k"), "pct", "", "recall"),
                      B.kpi("PR-AUC do score", q.get("pr_auc"), "num", "", "pr_auc")]
        result.blocks.append(B.kpis(items, "Qualidade da deteção"))
        if q.get("comparison"):
            result.blocks.append(B.table("Comparação de detetores", q["comparison"]))
        result.summary = ("Precisão no top-k " + pct(q["precision_at_k"]) if q.get("precision_at_k") is not None
                          else "Sem rótulos para validar — recomenda-se revisão amostral.")
        result.outputs = {"quality": q}
        result.next_step = "explicabilidade"

    def _association(self, ctx: AgentContext, result: AgentResult, meta: dict) -> None:
        q = meta.get("quality", {})
        result.blocks.append(B.kpis([B.kpi("Regras", q.get("n_rules"), "int", "", "regra_associacao"),
                                     B.kpi("Lift máximo", q.get("max_lift"), "num", "", "lift_associacao"),
                                     B.kpi("Lift mediano", q.get("median_lift"), "num", "", "lift_associacao")]))
        result.summary = f"{q.get('n_rules')} regras com lift mediano {num(q.get('median_lift', np.nan))}."
        result.next_step = "implementacao"


class ExplainabilityAgent(Agent):
    card = AgentCard(
        id="explainability", name="Agente de Explicabilidade", component="Explicabilidade (XAI)",
        role="Tradutor modelo → negócio", icon="lightbulb", step="explicabilidade",
        description="Explica o modelo nas colunas originais do Power BI: importância por permutação, dependência "
                    "parcial dos principais fatores, coeficientes/odds ratios em modelos lineares e motivos "
                    "individuais para os casos de maior risco — com narrativa em linguagem de negócio.",
        capabilities=["Importância por permutação", "Dependência parcial (PDP)", "Odds ratios", "Motivos individuais",
                      "Narrativa automática"],
        inputs=["Modelo campeão", "Conjunto de teste"], outputs=["Drivers", "Explicações locais"],
        params=[{"name": "n_local", "label": "Nº de casos a explicar", "type": "int"}],
    )

    def run(self, ctx: AgentContext, result: AgentResult, version_id: Optional[str] = None, n_local: int = 5,
            **_: Any) -> None:
        meta = champion_meta(ctx, version_id)
        kind = meta.get("kind")
        if kind != "supervised":
            return self._unsupervised(ctx, result, meta)
        task = meta["problem_type"]
        pipe = ctx.registry.load(meta["id"])
        hold = ctx.registry.holdout(meta["id"])
        feats = [f for f in meta["features"] if f in hold.columns]
        X = hold[feats]
        sample = X.sample(min(1500, len(X)), random_state=1) if len(X) > 1500 else X
        y = hold.loc[sample.index, "__y__"].values
        ctx.progress(0.1, "Importância por permutação…")
        if task == "binary_classification":
            predict = lambda d: predict_scores(pipe, d, task)  # noqa: E731
            score = lambda yt, pr: skm.roc_auc_score(yt, pr)  # noqa: E731
            hib, label = True, score_label(ctx)
        elif task == "multiclass_classification":
            predict = lambda d: pipe.predict_proba(d)  # noqa: E731
            score = lambda yt, pr: skm.f1_score(yt, np.argmax(pr, axis=1), average="macro")  # noqa: E731
            hib, label = True, "probabilidade"
        else:
            predict = lambda d: pipe.predict(d)  # noqa: E731
            score = lambda yt, pr: float(np.mean(np.abs(yt - pr)))  # noqa: E731
            hib, label = False, "valor"
        imp = permutation_importance_raw(predict, sample, y, score, hib, n_repeats=3)
        result.blocks.append(B.chart("bar", "Importância das variáveis (permutação, colunas originais)",
                                     imp.head(20)[["variavel", "importancia"]], x="variavel", y="importancia", horizontal=True,
                                     description="Quanto piora o modelo quando a variável é baralhada.",
                                     terms=["permutation_importance", "importancia_features"]))
        top = imp[imp["importancia"] > 0]["variavel"].head(4).tolist()
        # PDP
        if task != "multiclass_classification":
            ctx.progress(0.45, "Dependência parcial…")
            for f in top:
                pdp = partial_dependence_raw(predict, X, f)
                is_num = pd.api.types.is_numeric_dtype(X[f]) and X[f].nunique() > 15
                result.blocks.append(B.chart("line" if is_num else "bar", f"Efeito de {humanize(f)} na previsão",
                                             [{"valor": format_value(d["valor"]) if not is_num else d["valor"],
                                               "previsao": d["previsao_media"]} for d in pdp],
                                             x="valor", y="previsao", terms=["pdp"], numeric_x=is_num))
        # coeficientes de modelos lineares
        est = pipe.named_steps["model"]
        if hasattr(est, "coef_"):
            names = transformed_feature_names(pipe)
            coef = np.atleast_2d(est.coef_)[0]
            if len(names) == len(coef):
                rows = sorted(({"feature": n, "coeficiente": float(c), "odds_ratio": float(np.exp(c)) if task == "binary_classification" else None}
                               for n, c in zip(names, coef)), key=lambda r: -abs(r["coeficiente"]))[:20]
                cols = [{"key": "feature", "label": "Feature"}, {"key": "coeficiente", "label": "Coeficiente (escala normalizada)", "fmt": "num"}]
                if task == "binary_classification":
                    cols.append({"key": "odds_ratio", "label": "Odds ratio (por 1 desvio padrão)", "fmt": "num"})
                result.blocks.append(B.table("Coeficientes do modelo linear", rows, cols, terms=["odds_ratio", "regressao_logistica"]))
        # explicações locais
        ctx.progress(0.75, "Explicações individuais…")
        if task == "binary_classification":
            order = np.argsort(-hold["__p__"].values)[:n_local]
            pred_col = hold["__p__"].values
        elif task == "regression":
            order = np.argsort(-hold["__pred__"].values)[:n_local]
            pred_col = hold["__pred__"].values
        else:
            order = np.arange(min(n_local, len(hold)))
            pred_col = np.max(hold[[c for c in hold.columns if c.startswith("__p") and c.endswith("__") and c[3:-2].isdigit()]].values, axis=1)
        rows_local = X.iloc[order]
        bg = X.sample(min(800, len(X)), random_state=2)
        pf = predict if task != "multiclass_classification" else (lambda d: np.max(pipe.predict_proba(d), axis=1))
        contribs = local_contributions(pf, rows_local, bg, top_k=3)
        id_cols = [c for c in meta.get("id_columns", []) if c in hold.columns]
        local_rows = []
        for j, i in enumerate(order):
            rid = " / ".join(str(hold.iloc[i][c]) for c in id_cols) if id_cols else f"linha {i}"
            local_rows.append({"registo": rid, "previsao": float(pred_col[i]), "real": hold.iloc[i]["__y__"],
                               "motivos": reasons_text(contribs[j], label)})
        result.blocks.append(B.table("Motivos individuais dos casos de maior previsão", local_rows, [
            {"key": "registo", "label": "Registo"}, {"key": "previsao", "label": "Previsão", "fmt": "num"},
            {"key": "real", "label": "Real"}, {"key": "motivos", "label": "Principais motivos"}],
            terms=["explicacao_local", "shap"]))
        # narrativa
        narrative = self._narrative(ctx, imp, X, top, predict, task)
        result.blocks.insert(0, B.markdown(narrative, "Resumo para o negócio"))
        uc = ctx.use_case
        if top:
            result.success("Principais drivers", ", ".join(humanize(t) for t in top[:3]), ["importancia_features"])
        if imp.iloc[0]["importancia_rel"] > 0.6 if len(imp) else False:
            result.warn("Uma variável domina o modelo", f"{imp.iloc[0]['variavel']} explica > 60% da importância — "
                        "confirme que não há leakage.", ["data_leakage"])
        result.info("Importância ≠ causalidade", "Os drivers indicam associação; valide efeitos de intervenções com testes.",
                    ["causalidade"])
        result.summary = "Principais fatores: " + ", ".join(humanize(t) for t in top[:4]) + "." if top else "Sem fatores dominantes."
        result.outputs = {"importance": imp.head(25).to_dict(orient="records"), "top": top}
        result.terms = ["importancia_features", "permutation_importance", "pdp", "explicacao_local", "causalidade"]
        result.next_step = "governanca" if (uc is None or uc.ai_act_risk != "mínimo" or uc.sensitive_attributes) else "implementacao"

    def _narrative(self, ctx: AgentContext, imp: pd.DataFrame, X: pd.DataFrame, top: list[str], predict: Any,
                   task: str) -> str:
        if not top:
            return "O modelo não depende fortemente de nenhuma variável isolada."
        lines = [f"O modelo baseia-se sobretudo em **{humanize(top[0])}**"
                 + (f", **{humanize(top[1])}**" if len(top) > 1 else "")
                 + (f" e **{humanize(top[2])}**" if len(top) > 2 else "") + "."]
        if task != "multiclass_classification":
            for f in top[:3]:
                s = X[f]
                if pd.api.types.is_numeric_dtype(s) and s.nunique() > 15:
                    lo, hi = s.quantile(0.1), s.quantile(0.9)
                    a, b = X.copy(), X.copy()
                    a[f], b[f] = lo, hi
                    pa, pb = float(np.mean(predict(a.head(500)))), float(np.mean(predict(b.head(500))))
                    word = "aumenta" if pb > pa else "diminui"
                    unit = "a probabilidade" if task == "binary_classification" else "o valor previsto"
                    fmt = (lambda v: pct(v)) if task == "binary_classification" else (lambda v: num(v))
                    lines.append(f"- Quando **{humanize(f)}** passa de {format_value(lo)} para {format_value(hi)}, "
                                 f"{unit} {word} de {fmt(pa)} para {fmt(pb)} (em média).")
        lines.append("\n_Estas relações são associações aprendidas nos dados históricos, não necessariamente causas._")
        return "\n".join(lines)

    def _unsupervised(self, ctx: AgentContext, result: AgentResult, meta: dict) -> None:
        kind = meta.get("kind")
        if kind == "forecast":
            seas = meta.get("seasonal_profile", [])
            if seas:
                result.blocks.append(B.chart("bar", "Perfil sazonal (índice face à média)", seas, x="periodo", y="indice",
                                             terms=["sazonalidade"]))
            an = meta.get("analysis", {})
            result.blocks.append(B.kpis([
                B.kpi("Força da tendência", an.get("trend_strength"), "num", "0–1", "tendencia"),
                B.kpi("Força da sazonalidade", an.get("seasonal_strength"), "num", "0–1", "sazonalidade"),
                B.kpi("Tendência por período", an.get("trend_per_period_pct"), "num", "% do nível médio", "tendencia"),
            ], "Estrutura da série"))
            imp = meta.get("gbm_importance", [])
            if imp:
                result.blocks.append(B.chart("bar", "Importância das variáveis do modelo global", imp[:15], x="variavel",
                                             y="importancia", horizontal=True, terms=["lag", "modelo_global"]))
            result.summary = "Estrutura temporal explicada (tendência, sazonalidade e variáveis do modelo)."
        elif kind == "clustering":
            imp = meta.get("separation_importance", [])
            if imp:
                result.blocks.append(B.chart("bar", "Variáveis que mais distinguem os segmentos", imp[:15], x="variavel",
                                             y="importancia", horizontal=True, terms=["perfil_segmento"]))
            prof = meta.get("profiles", [])
            if prof:
                result.blocks.append(B.table("Perfil dos segmentos", prof, terms=["perfil_segmento", "centroide"]))
            result.summary = "Segmentos explicados pelas variáveis que mais os distinguem."
        elif kind == "anomaly":
            drivers = meta.get("anomaly_drivers", [])
            if drivers:
                result.blocks.append(B.chart("bar", "Variáveis mais frequentes nos motivos das anomalias", drivers, x="variavel",
                                             y="frequencia", horizontal=True, terms=["zscore_robusto"]))
            result.summary = "Motivos mais frequentes das anomalias identificados."
        else:
            result.summary = "Regras de associação são explicáveis por natureza (antecedente → consequente)."
        result.next_step = "implementacao"
