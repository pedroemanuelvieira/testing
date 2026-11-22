"""Agente de Treino (supervisionado) — validação cruzada, afinação, leaderboard e registo."""
from __future__ import annotations

import time
import warnings
from typing import Any, Optional

import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.model_selection import ParameterSampler, cross_val_score, cross_validate

from .. import advisor
from ..core import agent as B
from ..core.agent import Agent, AgentCard, AgentError, AgentResult
from ..core.context import AgentContext
from ..ml import metrics as M
from ..ml.drift import reference_stats
from ..ml.factory import build_pipeline, predict_scores, search_space_to_distributions
from ..ml.semantic import infer_roles
from .common import SupervisedData, cv_splitter, data_profile, model_name, split, supervised_data


def ensure_plan(ctx: AgentContext, X: pd.DataFrame) -> dict[str, Any]:
    p = ctx.project
    if p.feature_plan:
        # X já só contém as features escolhidas; o plano apenas acrescenta transformações
        plan = dict(p.feature_plan)
        plan["drop"] = [c for c in plan.get("drop", []) if c in X.columns]
        return plan
    roles = infer_roles(X)
    skewed = [c for c, r in roles.items() if r == "numeric" and X[c].astype(float).min() >= 0 and abs(X[c].astype(float).skew()) > 1]
    return {"drop": [], "datetime": [c for c, r in roles.items() if r == "datetime"], "log": skewed, "ratios": []}


def encode_target(sd: SupervisedData) -> tuple[pd.Series, list[Any]]:
    if sd.task == "multiclass_classification":
        mapping = {c: i for i, c in enumerate(sd.classes)}
        return sd.y.map(mapping).astype(int), sd.classes
    return sd.y, sd.classes


def primary_metric(ctx: AgentContext) -> str:
    uc = ctx.use_case
    m = uc.metrics.primary if uc else ctx.problem.primary_metric
    if M.metric_info(m).scorer is None:  # métricas sem scorer (lift, ks...) → métrica padrão do tipo
        m = ctx.problem.primary_metric
    return m


def test_metrics(task: str, y: np.ndarray, scores: np.ndarray, n_classes: int, threshold: float = 0.5) -> dict[str, float]:
    if task == "binary_classification":
        return M.binary_metrics(np.asarray(y), scores, threshold)
    if task == "multiclass_classification":
        return M.multiclass_metrics(np.asarray(y), scores, list(range(n_classes)))
    return M.regression_metrics(np.asarray(y), scores)


def tune_model(model_id: str, task: str, base: dict[str, Any], prof: advisor.DataProfile, plan: dict[str, Any],
               X: pd.DataFrame, y: pd.Series, cv: Any, scorer: str, n_iter: int, method: str, n_classes: int,
               random_state: int, progress: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    space = advisor.search_space(model_id, prof)
    if not space:
        return base, []
    trials: list[dict[str, Any]] = []

    def evaluate(cand: dict[str, Any]) -> float:
        params = {**base, **cand}
        pipe = build_pipeline(model_id, task, params, plan, X.head(2000), random_state, n_classes)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            s = float(np.mean(cross_val_score(pipe, X, y, cv=cv, scoring=scorer, n_jobs=1)))
        trials.append({**{k: (round(v, 5) if isinstance(v, float) else v) for k, v in cand.items()}, "score": s})
        progress(len(trials) / n_iter, f"Afinação de {model_id}: tentativa {len(trials)}/{n_iter}")
        return s

    if method == "optuna":
        try:
            import optuna

            optuna.logging.set_verbosity(optuna.logging.WARNING)
            spec_hp = {h.name: h for h in advisor.get_kb().model(model_id).hyperparameters}

            def objective(trial: Any) -> float:
                cand = {}
                for name, s in space.items():
                    hp = spec_hp[name]
                    if "choices" in s:
                        cand[name] = trial.suggest_categorical(name, list(s["choices"]))
                    elif hp.type == "int":
                        cand[name] = trial.suggest_int(name, int(s["low"]), int(s["high"]), log=bool(hp.log and s["low"] > 0))
                    else:
                        cand[name] = trial.suggest_float(name, float(s["low"]), float(s["high"]), log=bool(hp.log and s["low"] > 0))
                return evaluate(cand)

            study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=random_state))
            study.optimize(objective, n_trials=n_iter)
            return {**base, **study.best_params}, trials
        except ImportError:
            pass
    dists = search_space_to_distributions(space, model_id)
    best, best_score = base, -np.inf
    for cand in ParameterSampler(dists, n_iter=n_iter, random_state=random_state):
        cand = {k: (v.item() if hasattr(v, "item") else v) for k, v in cand.items()}
        s = evaluate(cand)
        if s > best_score:
            best, best_score = {**base, **cand}, s
    return best, trials


class TrainingAgent(Agent):
    card = AgentCard(
        id="training", name="Agente de Treino", component="Treino e validação",
        role="Engenheiro de ML", icon="cpu", step="treino",
        description="Treina os modelos selecionados com validação cruzada (estratificada ou temporal), afina "
                    "hiperparâmetros (random search ou Optuna), compara com a baseline, mede o overfitting, "
                    "escolhe o campeão e regista todas as versões no registo de modelos.",
        capabilities=["Validação cruzada estratificada/temporal", "Afinação random search / Optuna",
                      "Leaderboard com baseline", "Diagnóstico de overfitting", "Registo de versões"],
        inputs=["Dados", "Plano de features", "Modelos e hiperparâmetros"], outputs=["Leaderboard", "Modelo campeão"],
        params=[{"name": "tune", "label": "Afinação automática", "type": "bool"},
                {"name": "n_iter", "label": "Tentativas de afinação", "type": "int"},
                {"name": "method", "label": "Método", "type": "choice", "choices": ["random", "optuna"]}],
        problem_types=["binary_classification", "multiclass_classification", "regression"],
    )

    def run(self, ctx: AgentContext, result: AgentResult, tune: Optional[bool] = None, n_iter: Optional[int] = None,
            method: Optional[str] = None, models: Optional[list[str]] = None, cv_folds: Optional[int] = None,
            **_: Any) -> None:
        p = ctx.project
        rs = ctx.settings.random_state
        models = models or p.selected_models
        if not models:
            raise AgentError("Não há modelos selecionados — execute o Agente de Seleção de Modelos.")
        tune = p.tuning.get("enabled", False) if tune is None else tune
        n_iter = int(n_iter or p.tuning.get("n_iter", 12))
        method = method or p.tuning.get("method", "random")
        folds = int(cv_folds or p.cv_folds or 5)
        ctx.progress(0.02, "A preparar dados…")
        sd = supervised_data(ctx)
        y_enc, classes = encode_target(sd)
        n_classes = len(classes) if classes else 2
        tr, te, split_text = split(sd, 0.2, rs)
        X_tr, X_te = sd.X.iloc[tr], sd.X.iloc[te]
        y_tr, y_te = y_enc.iloc[tr], y_enc.iloc[te]
        if sd.task != "regression" and y_tr.nunique() < n_classes:
            raise AgentError("O conjunto de treino não contém todas as classes do alvo.")
        plan = ensure_plan(ctx, sd.X)
        metric = primary_metric(ctx)
        scorer = M.cv_scorer(metric, sd.task)
        cv = cv_splitter(sd, tr, folds, rs)
        if sd.time is not None:
            order = np.argsort(sd.time.iloc[tr].values, kind="stable")
            X_tr, y_tr = X_tr.iloc[order], y_tr.iloc[order]
        prof = data_profile(ctx)
        # baseline
        dummy = (DummyClassifier(strategy="prior") if sd.task != "regression" else DummyRegressor(strategy="mean"))
        dummy.fit(np.zeros((len(y_tr), 1)), y_tr)
        if sd.task == "binary_classification":
            base_scores = dummy.predict_proba(np.zeros((len(y_te), 1)))[:, 1]
        elif sd.task == "multiclass_classification":
            base_scores = dummy.predict_proba(np.zeros((len(y_te), 1)))
        else:
            base_scores = dummy.predict(np.zeros((len(y_te), 1)))
        baseline = test_metrics(sd.task, y_te.values, base_scores, n_classes)
        board, fitted = [], {}
        total = len(models)
        for i, mid in enumerate(models):
            base_p = p.model_params.get(mid) or advisor.recommend(mid, prof, p.use_case_id, p.goal)["params"]
            prog = lambda f, msg, i=i: ctx.progress(0.05 + 0.85 * (i + f) / total, msg)  # noqa: E731
            trials: list[dict[str, Any]] = []
            params = base_p
            t0 = time.perf_counter()
            if tune:
                Xs, ys = X_tr, y_tr
                if len(X_tr) > 20_000 and sd.time is None:
                    Xs = X_tr.sample(20_000, random_state=rs)
                    ys = y_tr.loc[Xs.index]
                params, trials = tune_model(mid, sd.task, base_p, prof, plan, Xs, ys, cv, scorer, n_iter, method,
                                            n_classes, rs, lambda f, msg: prog(0.6 * f, msg))
            prog(0.65, f"Validação cruzada de {model_name(ctx, mid)}…")
            pipe = build_pipeline(mid, sd.task, params, plan, X_tr.head(2000), rs, n_classes)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                cvr = cross_validate(pipe, X_tr, y_tr, cv=cv, scoring=scorer, return_train_score=True, n_jobs=1)
                prog(0.85, f"Treino final de {model_name(ctx, mid)}…")
                pipe.fit(X_tr, y_tr)
            fit_s = time.perf_counter() - t0
            cv_mean = M.from_cv_score(metric, float(np.mean(cvr["test_score"])))
            cv_std = float(np.std(cvr["test_score"]))
            tr_mean = M.from_cv_score(metric, float(np.mean(cvr["train_score"])))
            scores = predict_scores(pipe, X_te, sd.task)
            tm = test_metrics(sd.task, y_te.values, scores, n_classes)
            gap = (tr_mean - cv_mean) if M.metric_info(metric).direction == "max" else (cv_mean - tr_mean)
            rel_gap = gap / max(abs(tr_mean), 1e-9)
            board.append({"modelo": model_name(ctx, mid), "id": mid, "cv": cv_mean, "cv_std": cv_std, "treino": tr_mean,
                          "teste": tm.get(metric), "gap": rel_gap, "segundos": round(fit_s, 1), "afinado": bool(tune),
                          "tentativas": len(trials)})
            fitted[mid] = (pipe, params, tm, scores, trials, {"mean": cv_mean, "std": cv_std, "train": tr_mean})
        direction = M.metric_info(metric).direction
        board.sort(key=lambda r: -r["cv"] if direction == "max" else r["cv"])
        champion_id = board[0]["id"]
        # registo
        ctx.progress(0.93, "A registar versões no registo de modelos…")
        ref = reference_stats(X_tr, sd.features)
        champion_vid = None
        for row in board:
            mid = row["id"]
            pipe, params, tm, scores, trials, cvs = fitted[mid]
            hold = X_te.reset_index(drop=True).copy()
            for extra in (sd.ids, sd.sensitive):
                if extra is not None:
                    for c in extra.columns:
                        if c not in hold.columns:
                            hold[c] = extra.iloc[te][c].values
            hold["__y__"] = y_te.values
            if sd.task == "binary_classification":
                hold["__p__"] = scores
            elif sd.task == "multiclass_classification":
                for k in range(n_classes):
                    hold[f"__p{k}__"] = scores[:, k]
                hold["__pred__"] = np.argmax(scores, axis=1)
            else:
                hold["__pred__"] = scores
            score_ref = None
            if sd.task in ("binary_classification", "regression"):
                edges = np.unique(np.quantile(scores, np.linspace(0, 1, 11)))
                if len(edges) > 2:
                    score_ref = {"edges": edges.tolist(), "props": (np.histogram(scores, bins=edges)[0] / len(scores)).tolist()}
            meta = ctx.registry.register({
                "project_id": p.id, "project_name": p.name, "use_case_id": p.use_case_id, "problem_type": sd.task,
                "kind": "supervised", "model_id": mid, "model_name": model_name(ctx, mid), "params": params,
                "primary_metric": metric, "metrics_cv": cvs, "metrics_test": tm, "baseline_metrics": baseline,
                "threshold": 0.5 if sd.task == "binary_classification" else None, "classes": classes,
                "positive_class": sd.positive_class, "target": p.target, "features": sd.features,
                "id_columns": [c for c in p.id_columns if sd.ids is not None and c in sd.ids.columns],
                "time_column": p.time_column, "feature_plan": plan, "reference_stats": ref, "score_ref": score_ref,
                "train_rows": len(X_tr), "test_rows": len(X_te), "split": split_text, "tuned": bool(trials),
                "tuning_trials": trials[-50:], "sampled_from": sd.sampled_from,
                "business_costs": p.business_costs or None,
            }, obj=pipe, holdout=hold)
            row["version_id"] = meta["id"]
            if mid == champion_id:
                champion_vid = meta["id"]
        ctx.registry.set_champion(p.id, champion_vid)
        ctx.save_project(champion_version_id=champion_vid)
        # blocos
        info = M.metric_info(metric)
        champ = board[0]
        result.blocks.append(B.kpis([
            B.kpi(f"{info.name} (validação cruzada)", champ["cv"], info.fmt, f"± {champ['cv_std']:.3f} — {champ['modelo']}", info.term),
            B.kpi(f"{info.name} (teste)", champ["teste"], info.fmt, "Conjunto nunca visto no treino", "conjunto_teste"),
            B.kpi(f"{info.name} (baseline)", baseline.get(metric), info.fmt, "Modelo trivial", "baseline"),
            B.kpi("Linhas de treino / teste", f"{len(X_tr):,} / {len(X_te):,}".replace(",", " "), "text", split_text, "conjunto_teste"),
        ], "Modelo campeão"))
        result.blocks.append(B.table("Leaderboard", board, [
            {"key": "modelo", "label": "Modelo"}, {"key": "cv", "label": f"{info.name} CV", "fmt": "num"},
            {"key": "cv_std", "label": "± desvio", "fmt": "num"}, {"key": "treino", "label": f"{info.name} treino", "fmt": "num"},
            {"key": "teste", "label": f"{info.name} teste", "fmt": "num"}, {"key": "gap", "label": "Gap treino-CV", "fmt": "pct"},
            {"key": "segundos", "label": "Tempo (s)", "fmt": "num"}, {"key": "tentativas", "label": "Tentativas", "fmt": "int"}],
            terms=["validacao_cruzada", "overfitting", "baseline"]))
        result.blocks.append(B.chart("bar", f"{info.name} por modelo (validação cruzada vs teste)",
                                     [{"modelo": r["modelo"], "CV": r["cv"], "Teste": r["teste"], "Treino": r["treino"]} for r in board],
                                     x="modelo", y=["Treino", "CV", "Teste"], terms=["overfitting"]))
        for r in board:
            if r["gap"] > 0.08:
                result.warn(f"Possível overfitting em {r['modelo']}", f"O desempenho no treino é {100 * r['gap']:.0f}% "
                            "superior ao da validação. Aumente a regularização ou reduza a complexidade no Conselheiro.",
                            ["overfitting", "regularizacao"])
        if direction == "max" and baseline.get(metric) is not None and champ["teste"] is not None and champ["teste"] <= baseline[metric] + 0.01:
            result.critical("O modelo não supera a baseline", "Reveja as features, o alvo e a qualidade dos dados.", ["baseline"])
        if sd.task == "binary_classification" and (champ["teste"] or 0) > 0.97 and metric == "roc_auc":
            result.critical("Desempenho suspeitamente alto", "AUC > 0,97 em dados de negócio é quase sempre data leakage.", ["data_leakage"])
        tuned_trials = fitted[champion_id][4]
        if tuned_trials:
            result.blocks.append(B.chart("line", f"Evolução da afinação — {champ['modelo']}",
                                         [{"tentativa": i + 1, "score": t["score"],
                                           "melhor": max(x["score"] for x in tuned_trials[: i + 1])} for i, t in enumerate(tuned_trials)],
                                         x="tentativa", y=["score", "melhor"], terms=["tuning"]))
        if sd.sampled_from:
            result.info("Dados amostrados", f"Foram usadas {len(sd.X):,} de {sd.sampled_from:,} linhas (limite MLSTUDIO_MAX_ROWS).".replace(",", " "))
        result.success("Campeão registado", f"{champ['modelo']} ({champion_vid}) — estado 'candidato'.", ["registo_modelos"])
        result.summary = (f"Campeão: **{champ['modelo']}** com {info.name} {M.format_metric(metric, champ['cv'])} em validação "
                          f"cruzada e {M.format_metric(metric, champ['teste'])} no teste (baseline "
                          f"{M.format_metric(metric, baseline.get(metric))}).")
        result.outputs = {"leaderboard": board, "champion_version_id": champion_vid, "metric": metric, "baseline": baseline}
        result.terms = ["validacao_cruzada", "overfitting", "conjunto_teste", "tuning", "registo_modelos"]
        result.next_step = "avaliacao"


def quick_cv(ctx: AgentContext, model_id: str, params: dict[str, Any], folds: int = 3,
             max_rows: int = 15_000) -> dict[str, Any]:
    """Validação cruzada rápida de uma configuração (usada pelo Conselheiro interativo)."""
    sd = supervised_data(ctx, max_rows=max_rows)
    y_enc, classes = encode_target(sd)
    plan = ensure_plan(ctx, sd.X)
    metric = primary_metric(ctx)
    scorer = M.cv_scorer(metric, sd.task)
    cv = cv_splitter(sd, np.arange(len(sd.X)), folds, ctx.settings.random_state)
    X, y = sd.X, y_enc
    if sd.time is not None:
        order = np.argsort(sd.time.values, kind="stable")
        X, y = X.iloc[order], y.iloc[order]
    pipe = build_pipeline(model_id, sd.task, params, plan, X.head(2000), ctx.settings.random_state,
                          len(classes) if classes else 2)
    t0 = time.perf_counter()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        cvr = cross_validate(pipe, X, y, cv=cv, scoring=scorer, return_train_score=True, n_jobs=1)
    return {"metric": metric, "metric_name": M.metric_info(metric).name,
            "cv": M.from_cv_score(metric, float(np.mean(cvr["test_score"]))), "cv_std": float(np.std(cvr["test_score"])),
            "train": M.from_cv_score(metric, float(np.mean(cvr["train_score"]))), "seconds": round(time.perf_counter() - t0, 2),
            "rows": len(X), "folds": folds}
