"""Agentes especialistas: Previsão, Segmentação, Anomalias e Cabaz de Compras."""
from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd

from .. import advisor
from ..core import agent as B
from ..core.agent import Agent, AgentCard, AgentError, AgentResult
from ..core.context import AgentContext
from ..ml import timeseries as ts
from ..ml import unsupervised as U
from ..ml.explain import format_value
from ..ml.semantic import humanize
from .common import data_profile, feature_list, model_name, num, pct, roles_for


# =============================================================================== PREVISÃO
class ForecastingAgent(Agent):
    card = AgentCard(
        id="forecasting", name="Agente de Previsão (Séries Temporais)", component="Previsão temporal",
        role="Especialista em forecasting", icon="line-chart", step="treino",
        description="Agrega os dados à frequência certa, analisa tendência e sazonalidade, compara modelos por "
                    "backtesting de origem móvel (naive sazonal, Holt-Winters, SARIMA, LightGBM global com lags e "
                    "feriados portugueses) e produz a previsão com intervalos.",
        capabilities=["Agregação e deteção de frequência", "Força de tendência/sazonalidade (STL)",
                      "Backtesting com origem móvel", "Modelo global multi-série", "Intervalos de previsão"],
        inputs=["Coluna temporal", "Valor (ou contagem)", "Séries", "Horizonte"],
        outputs=["Previsão com intervalos", "Comparação de modelos"],
        params=[{"name": "horizon", "label": "Horizonte", "type": "int"},
                {"name": "folds", "label": "Nº de backtests", "type": "int"}],
        problem_types=["forecasting"],
    )

    def run(self, ctx: AgentContext, result: AgentResult, horizon: Optional[int] = None, folds: int = 3,
            models: Optional[list[str]] = None, **_: Any) -> None:
        p = ctx.project
        df = ctx.data()
        if not p.time_column:
            raise AgentError("Defina a coluna temporal do projeto.")
        ctx.progress(0.03, "A preparar as séries…")
        long, info = ts.prepare_series(df, p.time_column, p.value_column, p.aggregation, p.series_columns, p.freq)
        h = int(horizon or p.horizon or {"D": 28, "W": 8, "M": 6, "H": 48}[info["freq"]])
        season = info["season"]
        total = long.groupby("ds")["y"].sum()
        an = ts.analyze(total.values, season)
        prof = data_profile(ctx)
        models = models or p.selected_models or ["seasonal_naive", "holt_winters", "gbm_lags"]
        models = [m for m in models if ctx.kb.model(m) and "forecasting" in ctx.kb.model(m).tasks]
        if "seasonal_naive" not in models:
            models.append("seasonal_naive")
        params = {m: (p.model_params.get(m) or advisor.recommend(m, prof, p.use_case_id, p.goal)["params"]) for m in models}
        bt = ts.backtest(params, long, h, info["freq"], season, folds,
                         progress=lambda f, msg: ctx.progress(0.08 + 0.7 * f, msg))
        scores = bt["scores"]
        best = min(scores, key=lambda m: scores[m]["wape"] if not np.isnan(scores[m]["wape"]) else 9e9)
        ctx.progress(0.82, f"A gerar a previsão final com {model_name(ctx, best)}…")
        fc = ts.forecast(best, params[best], long, h, info["freq"], season)
        lo, hi = ts.intervals(bt["predictions"], best, h)
        fc["passo"] = fc.groupby("serie").cumcount() + 1
        fc["limite_inferior"] = fc["yhat"] * (1 + lo[fc["passo"] - 1])
        fc["limite_superior"] = fc["yhat"] * (1 + hi[fc["passo"] - 1])
        if (long["y"] >= 0).all():
            fc["limite_inferior"] = fc["limite_inferior"].clip(lower=0)
        gbm_imp = []
        if best == "gbm_lags":
            gbm_imp = ts.GBMLags(params[best], info["freq"]).fit(long).importance()
        forecast_tbl = fc.rename(columns={"ds": "data", "yhat": "previsao"})[["serie", "data", "previsao", "limite_inferior", "limite_superior"]]
        history = long.rename(columns={"ds": "data", "y": "real"})
        meta = ctx.registry.register({
            "project_id": p.id, "project_name": p.name, "use_case_id": p.use_case_id, "problem_type": "forecasting",
            "kind": "forecast", "model_id": best, "model_name": model_name(ctx, best), "params": params[best],
            "all_params": params, "primary_metric": "wape", "metrics_test": scores[best], "backtest_scores": scores,
            "freq": info["freq"], "season": season, "horizon": h, "series": info["series"], "time_column": p.time_column,
            "value_column": p.value_column, "aggregation": info["aggregation"], "series_columns": p.series_columns,
            "analysis": an, "seasonal_profile": ts.seasonal_profile(long, info["freq"]), "gbm_importance": gbm_imp[:20],
            "interval_level": "80%",
        }, obj={"model_id": best, "params": params[best]},
            artifacts={"forecast": forecast_tbl, "history": history, "backtest": bt["predictions"]})
        ctx.registry.set_champion(p.id, meta["id"])
        ctx.save_project(champion_version_id=meta["id"], horizon=h, freq=info["freq"])
        # blocos
        result.blocks.append(B.kpis([
            B.kpi("Frequência", info["freq_label"], "text", f"sazonalidade de {season} períodos", "frequencia_temporal"),
            B.kpi("Séries", info["n_series"], "int", ", ".join(info["series"][:4]), "serie_temporal"),
            B.kpi("Histórico", f"{pd.Timestamp(info['start']).date()} → {pd.Timestamp(info['end']).date()}", "text", f"{info['length']} períodos"),
            B.kpi("Força da tendência", an.get("trend_strength"), "num", "0 = nenhuma, 1 = forte", "tendencia"),
            B.kpi("Força da sazonalidade", an.get("seasonal_strength"), "num", "0 = nenhuma, 1 = forte", "sazonalidade"),
            B.kpi("Horizonte", h, "int", "períodos", "horizonte_previsao"),
        ], "Estrutura das séries"))
        board = sorted(({"modelo": model_name(ctx, m), "id": m, **s} for m, s in scores.items()), key=lambda r: r["wape"])
        result.blocks.append(B.table(f"Backtesting ({bt['folds']} origens × {h} períodos)", board, [
            {"key": "modelo", "label": "Modelo"}, {"key": "wape", "label": "WAPE", "fmt": "pct"},
            {"key": "mae", "label": "MAE", "fmt": "num"}, {"key": "bias", "label": "Bias", "fmt": "pct"},
            {"key": "mase", "label": "MASE", "fmt": "num"}, {"key": "smape", "label": "sMAPE", "fmt": "pct"}],
            terms=["backtesting", "wape", "mase", "bias_previsao"]))
        agg_hist = history.groupby("data")["real"].sum().reset_index().tail(max(4 * h, 3 * season))
        agg_fc = forecast_tbl.groupby("data")[["previsao", "limite_inferior", "limite_superior"]].sum().reset_index()
        chart_data = [{"data": r.data.strftime("%Y-%m-%d"), "real": float(r.real)} for r in agg_hist.itertuples()]
        chart_data += [{"data": r.data.strftime("%Y-%m-%d"), "previsao": float(r.previsao), "limite_inferior": float(r.limite_inferior),
                        "limite_superior": float(r.limite_superior)} for r in agg_fc.itertuples()]
        result.blocks.append(B.chart("line", "Histórico recente e previsão (total, intervalo 80%)", chart_data, x="data",
                                     y=["real", "previsao"], band=["limite_inferior", "limite_superior"],
                                     terms=["intervalo_previsao", "horizonte_previsao"]))
        if info["n_series"] > 1:
            per = forecast_tbl.groupby("serie")["previsao"].sum().sort_values(ascending=False)
            result.blocks.append(B.chart("bar", "Previsão total do horizonte por série",
                                         [{"serie": k, "previsao": float(v)} for k, v in per.items()], x="serie", y="previsao"))
        result.blocks.append(B.chart("bar", "Perfil sazonal", ts.seasonal_profile(long, info["freq"]), x="periodo", y="indice",
                                     terms=["sazonalidade"]))
        result.blocks.append(B.table("Previsão (primeiras linhas)", forecast_tbl.head(60)))
        if info["series_dropped"]:
            result.info("Séries agregadas", f"Foram modeladas as {info['n_series']} séries de maior volume; "
                        f"{info['series_dropped']} séries menores ficaram de fora.")
        naive = scores.get("seasonal_naive", {}).get("wape")
        gain = 1 - scores[best]["wape"] / naive if naive else None
        if best == "seasonal_naive":
            result.warn("O naive sazonal foi o melhor modelo", "A série é muito estável ou os modelos precisam de "
                        "afinação/mais variáveis.", ["naive_sazonal"])
        else:
            result.success(f"{model_name(ctx, best)} é o melhor modelo",
                           f"WAPE {pct(scores[best]['wape'])} ({pct(gain or 0)} melhor que o naive sazonal).", ["wape"])
        result.summary = (f"Previsão {info['freq_label']} a {h} períodos com **{model_name(ctx, best)}** — WAPE "
                          f"{pct(scores[best]['wape'])} em backtesting.")
        result.outputs = {"best": best, "scores": scores, "version_id": meta["id"], "horizon": h}
        result.terms = ["serie_temporal", "backtesting", "wape", "sazonalidade", "intervalo_previsao"]
        result.next_step = "avaliacao"


# =============================================================================== SEGMENTAÇÃO
class SegmentationAgent(Agent):
    card = AgentCard(
        id="segmentation", name="Agente de Segmentação (Clustering)", component="Segmentação",
        role="Especialista em segmentação", icon="scatter", step="treino",
        description="Prepara as variáveis (log + normalização), escolhe o nº de segmentos pela silhueta e pelo "
                    "cotovelo, treina o algoritmo, descreve e nomeia cada segmento e projeta-os em 2D.",
        capabilities=["Escolha de k (silhueta/cotovelo)", "K-Means, GMM, hierárquico, DBSCAN",
                      "Perfis e nomes automáticos", "Projeção PCA", "Atribuição de novos registos"],
        inputs=["Variáveis de comportamento"], outputs=["Segmentos", "Perfis", "Modelo de atribuição"],
        params=[{"name": "n_clusters", "label": "Nº de segmentos (opcional)", "type": "int"}],
        problem_types=["clustering"],
    )

    def run(self, ctx: AgentContext, result: AgentResult, n_clusters: Optional[int] = None, model: Optional[str] = None,
            **_: Any) -> None:
        from sklearn.decomposition import PCA
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.metrics import davies_bouldin_score, silhouette_score

        p = ctx.project
        df = ctx.data()
        rs = ctx.settings.random_state
        roles = roles_for(ctx, df)
        feats = p.features or [c for c in feature_list(ctx, df, roles) if roles.get(c) in ("numeric", "boolean")]
        if len(feats) < 2:
            raise AgentError("A segmentação precisa de pelo menos 2 variáveis numéricas.")
        if len(df) > 60_000:
            df = df.sample(60_000, random_state=rs)
        ctx.progress(0.1, "A preparar variáveis…")
        transformer, num_cols, log_cols = U.build_transformer(df, feats)
        X = transformer.fit_transform(U._as_str_frame(df, feats))
        ctx.progress(0.25, "A avaliar k de 2 a 10…")
        kscores = U.evaluate_k(X, range(2, 11), rs)
        k_rec, k_reason = U.recommend_k(kscores)
        model_id = model or next((m for m in p.selected_models if m in ("kmeans", "gaussian_mixture", "agglomerative", "dbscan")), "kmeans")
        params = dict(p.model_params.get(model_id) or {})
        key = "n_components" if model_id == "gaussian_mixture" else "n_clusters"
        if n_clusters:
            params[key] = int(n_clusters)
        elif model_id != "dbscan" and model_id not in p.params_locked:
            params[key] = k_rec
        params = {**advisor.recommend(model_id, data_profile(ctx), p.use_case_id)["params"], **params}
        ctx.progress(0.55, f"A treinar {model_name(ctx, model_id)}…")
        fit_df = df if model_id != "agglomerative" or len(df) <= 10_000 else df.sample(10_000, random_state=rs)
        assigner = U.ClusterAssigner(U.build_transformer(fit_df, feats)[0], U.make_clusterer(model_id, params, rs), model_id, feats).fit(fit_df)
        labels = assigner.predict(df) if fit_df is not df else assigner.labels_
        Xall = assigner.transform_features(df)
        valid = labels != -1
        sil = float(silhouette_score(Xall[valid], labels[valid], sample_size=min(3000, int(valid.sum())), random_state=rs)) if len(set(labels[valid])) > 1 else np.nan
        dbi = float(davies_bouldin_score(Xall[valid], labels[valid])) if len(set(labels[valid])) > 1 else np.nan
        summary, z, names = U.segment_profiles(df, labels, feats)
        shares = summary["pct"].values
        # importância das variáveis na separação
        rf = RandomForestClassifier(n_estimators=150, max_depth=8, random_state=rs, n_jobs=-1)
        sample_idx = np.random.default_rng(rs).choice(len(df), size=min(5000, len(df)), replace=False)
        Xs = U._as_str_frame(df.iloc[sample_idx], feats)
        Xs = Xs.apply(lambda s: s.astype("category").cat.codes if not pd.api.types.is_numeric_dtype(s) else s.fillna(s.median()))
        rf.fit(Xs, labels[sample_idx])
        sep_imp = sorted(({"variavel": f, "importancia": float(v)} for f, v in zip(feats, rf.feature_importances_)),
                         key=lambda d: -d["importancia"])
        # PCA
        pca = PCA(n_components=2, random_state=rs).fit(Xall)
        coords = pca.transform(Xall)
        pts_idx = np.random.default_rng(1).choice(len(df), size=min(700, len(df)), replace=False)
        scatter = [{"pc1": float(coords[i, 0]), "pc2": float(coords[i, 1]), "segmento": names.get(labels[i], str(labels[i]))}
                   for i in pts_idx]
        profiles_tbl = summary.copy()
        profiles_tbl["segmento"] = profiles_tbl["segmento"].astype(int)
        assignments = pd.DataFrame({"segmento": labels, "nome_segmento": [names.get(l, str(l)) for l in labels]})
        for c in p.id_columns:
            if c in df.columns:
                assignments.insert(0, c, df[c].values)
        dist = assigner.distance(df)
        if dist is not None:
            assignments["distancia_centro"] = np.round(dist, 4)
        quality = {"silhouette": sil, "davies_bouldin": dbi, "n_clusters": int(len(set(labels[valid]))),
                   "max_share": float(shares.max()), "min_share": float(shares.min()),
                   "noise_share": float((labels == -1).mean())}
        meta = ctx.registry.register({
            "project_id": p.id, "project_name": p.name, "use_case_id": p.use_case_id, "problem_type": "clustering",
            "kind": "clustering", "model_id": model_id, "model_name": model_name(ctx, model_id), "params": params,
            "primary_metric": "silhouette", "metrics_test": {"silhouette": sil, "davies_bouldin": dbi}, "quality": quality,
            "features": feats, "log_features": log_cols, "segment_names": {str(k): v for k, v in names.items()},
            "profiles": profiles_tbl.round(3).to_dict(orient="records"), "separation_importance": sep_imp,
            "id_columns": p.id_columns, "k_scores": kscores.to_dict(orient="records"), "recommended_k": k_rec,
        }, obj=assigner, artifacts={"assignments": assignments})
        ctx.registry.set_champion(p.id, meta["id"])
        ctx.save_project(champion_version_id=meta["id"])
        result.blocks.append(B.kpis([
            B.kpi("Segmentos", quality["n_clusters"], "int", model_name(ctx, model_id), "clustering"),
            B.kpi("Silhueta", sil, "num", "> 0,25 razoável", "silhueta"),
            B.kpi("k recomendado", k_rec, "int", "pela silhueta (3–8)", "cotovelo"),
            B.kpi("Variáveis", len(feats), "int", f"{len(log_cols)} com log", "transformacao_log"),
        ], "Segmentação"))
        result.blocks.append(B.chart("line", "Escolha de k — silhueta e inércia", kscores[["k", "silhueta", "inercia"]], x="k",
                                     y=["silhueta"], secondary=["inercia"], terms=["silhueta", "cotovelo"]))
        result.blocks.append(B.chart("scatter", "Segmentos projetados em 2D (PCA)", scatter, x="pc1", y="pc2", color="segmento",
                                     terms=["pca"]))
        cols = [{"key": "segmento", "label": "#", "fmt": "int"}, {"key": "nome", "label": "Nome sugerido"},
                {"key": "n", "label": "Registos", "fmt": "int"}, {"key": "pct", "label": "% da base", "fmt": "pct"}]
        cols += [{"key": f, "label": humanize(f), "fmt": "num"} for f in feats if f in profiles_tbl.columns]
        result.blocks.append(B.table("Perfil dos segmentos (médias)", profiles_tbl, cols, terms=["perfil_segmento", "centroide"]))
        zf = [f for f in feats if f in z.columns]
        result.blocks.append(B.heatmap("Desvio face à média global (z-score)", [humanize(f) for f in zf],
                                       [f"{int(s)} · {names.get(s, '')}" for s in z.index], z[zf].round(2).values.tolist(),
                                       terms=["perfil_segmento"], diverging=True))
        result.info("Escolha de k", k_reason, ["silhueta"])
        if sil < 0.2:
            result.warn("Segmentos pouco separados", "Silhueta < 0,2: use menos variáveis ou outras métricas de comportamento.", ["silhueta"])
        result.summary = f"{quality['n_clusters']} segmentos com silhueta {num(sil)}: " + "; ".join(
            f"{names[s]} ({pct(summary.loc[summary['segmento'] == s, 'pct'].iloc[0])})" for s in list(names)[:4]) + "."
        result.outputs = {"version_id": meta["id"], "recommended_k": k_rec, "quality": quality}
        result.terms = ["clustering", "kmeans", "silhueta", "perfil_segmento", "standardizacao"]
        result.next_step = "avaliacao"


# =============================================================================== ANOMALIAS
class AnomalyAgent(Agent):
    card = AgentCard(
        id="anomaly", name="Agente de Deteção de Anomalias", component="Deteção de anomalias",
        role="Auditor analítico", icon="radar", step="treino",
        description="Treina e compara detetores (Isolation Forest, LOF, z-score robusto), sinaliza os registos "
                    "mais invulgares com os motivos (variáveis mais desviantes) e, se houver rótulos, mede a "
                    "precisão no top-k.",
        capabilities=["Comparação de detetores", "Score e motivos por registo", "Precisão no top-k com rótulos",
                      "Limiar pela capacidade de revisão"],
        inputs=["Variáveis", "Taxa esperada de anomalias"], outputs=["Lista de revisão priorizada", "Detetor treinado"],
        params=[{"name": "contamination", "label": "Proporção esperada", "type": "float"}],
        problem_types=["anomaly_detection"],
    )

    def run(self, ctx: AgentContext, result: AgentResult, contamination: Optional[float] = None, **_: Any) -> None:
        from sklearn.metrics import average_precision_score

        p = ctx.project
        df = ctx.data().reset_index(drop=True)
        roles = roles_for(ctx, df)
        feats = p.features or [c for c in feature_list(ctx, df, roles) if roles.get(c) in ("numeric", "boolean", "categorical")]
        feats = [c for c in feats if c != p.label_column]
        if not feats:
            raise AgentError("Sem variáveis para a deteção de anomalias.")
        labels = pd.to_numeric(df[p.label_column], errors="coerce").fillna(0).astype(int).values if (
            p.label_column and p.label_column in df.columns) else None
        prof = data_profile(ctx)
        models = [m for m in (p.selected_models or ["isolation_forest", "robust_zscore"])
                  if m in ("isolation_forest", "local_outlier_factor", "robust_zscore")] or ["isolation_forest"]
        comp, fitted = [], {}
        for i, mid in enumerate(models):
            ctx.progress(0.1 + 0.6 * i / len(models), f"A treinar {model_name(ctx, mid)}…")
            params = {**advisor.recommend(mid, prof, p.use_case_id)["params"], **(p.model_params.get(mid) or {})}
            if contamination:
                params["contamination"] = float(contamination)
            fit_df = df if mid != "local_outlier_factor" or len(df) <= 30_000 else df.sample(30_000, random_state=1)
            det = U.AnomalyDetector(mid, params, feats).fit(fit_df)
            scores = det.score(df)
            flags = scores >= det.threshold_
            row = {"detetor": model_name(ctx, mid), "id": mid, "sinalizados": int(flags.sum()), "pct": float(flags.mean())}
            k = max(1, int(flags.sum()))
            if labels is not None and labels.sum() > 0:
                top = np.argsort(-scores)[:k]
                row["precision_at_k"] = float(labels[top].mean())
                row["recall_at_k"] = float(labels[top].sum() / labels.sum())
                row["pr_auc"] = float(average_precision_score(labels, scores))
            comp.append(row)
            fitted[mid] = (det, scores, flags, params)
        key = "pr_auc" if labels is not None and labels.sum() > 0 else None
        best = max(comp, key=lambda r: r[key])["id"] if key else models[0]
        det, scores, flags, params = fitted[best]
        ctx.progress(0.8, "A explicar as anomalias…")
        order = np.argsort(-scores)
        top_idx = order[: min(200, int(flags.sum()) or 50)]
        reasons = det.reasons(df.iloc[top_idx])
        id_cols = [c for c in p.id_columns if c in df.columns]
        rows = []
        driver_count: dict[str, int] = {}
        for j, i in enumerate(top_idx):
            r = {c: df.iloc[i][c] for c in id_cols}
            r["score"] = float(scores[i])
            r["motivos"] = "; ".join(f"{humanize(x['variavel'])} = {format_value(x['valor'])} (z={x['z']:+.1f})" for x in reasons[j])
            if labels is not None:
                r["confirmado"] = int(labels[i])
            rows.append(r)
            for x in reasons[j][:2]:
                driver_count[x["variavel"]] = driver_count.get(x["variavel"], 0) + 1
        drivers = sorted(({"variavel": k, "frequencia": v} for k, v in driver_count.items()), key=lambda d: -d["frequencia"])
        out = df[id_cols].copy() if id_cols else pd.DataFrame(index=df.index)
        out["score_anomalia"] = np.round(scores, 5)
        out["e_anomalia"] = flags
        quality = {"flagged_rate": float(flags.mean()), "comparison": comp, "k": int(flags.sum())}
        best_row = next(r for r in comp if r["id"] == best)
        for kk in ("precision_at_k", "recall_at_k", "pr_auc"):
            if kk in best_row:
                quality[kk] = best_row[kk]
        meta = ctx.registry.register({
            "project_id": p.id, "project_name": p.name, "use_case_id": p.use_case_id, "problem_type": "anomaly_detection",
            "kind": "anomaly", "model_id": best, "model_name": model_name(ctx, best), "params": params,
            "primary_metric": "precision_at_k", "metrics_test": {k: v for k, v in quality.items() if isinstance(v, float)},
            "quality": quality, "features": feats, "id_columns": id_cols, "threshold": det.threshold_,
            "anomaly_drivers": drivers[:15],
        }, obj=det, artifacts={"scores": out})
        ctx.registry.set_champion(p.id, meta["id"])
        ctx.save_project(champion_version_id=meta["id"])
        result.blocks.append(B.kpis([
            B.kpi("Registos analisados", len(df), "int"),
            B.kpi("Sinalizados", int(flags.sum()), "int", pct(flags.mean()), "contaminacao"),
            B.kpi("Detetor escolhido", model_name(ctx, best), "text", "maior PR-AUC" if key else "primeiro selecionado"),
            *([B.kpi("Precisão no top-k", quality["precision_at_k"], "pct", "com rótulos de validação", "precision_at_k")]
              if "precision_at_k" in quality else []),
        ], "Deteção de anomalias"))
        result.blocks.append(B.table("Comparação de detetores", comp, [
            {"key": "detetor", "label": "Detetor"}, {"key": "sinalizados", "label": "Sinalizados", "fmt": "int"},
            {"key": "pct", "label": "%", "fmt": "pct"}, {"key": "precision_at_k", "label": "Precisão top-k", "fmt": "pct"},
            {"key": "recall_at_k", "label": "Recall top-k", "fmt": "pct"}, {"key": "pr_auc", "label": "PR-AUC", "fmt": "num"}],
            terms=["isolation_forest", "lof", "zscore_robusto"]))
        hist, edges = np.histogram(scores, bins=30)
        result.blocks.append(B.chart("histogram", "Distribuição do score de anomalia",
                                     [{"score": f"{edges[i]:.3g}", "n": int(hist[i])} for i in range(len(hist))], x="score", y="n",
                                     reference_x=f"{det.threshold_:.3g}", terms=["anomalia"]))
        result.blocks.append(B.table("Lista de revisão priorizada (mais anómalos primeiro)", rows[:100], terms=["human_in_the_loop"]))
        result.blocks.append(B.chart("bar", "Variáveis que mais explicam as anomalias", drivers[:12], x="variavel", y="frequencia",
                                     horizontal=True))
        result.info("Anomalia ≠ fraude/erro", "Os casos sinalizados devem ser revistos por uma pessoa.", ["human_in_the_loop"])
        result.summary = (f"{int(flags.sum())} registos sinalizados ({pct(flags.mean())}) por {model_name(ctx, best)}"
                          + (f"; precisão no top-k {pct(quality['precision_at_k'])}." if "precision_at_k" in quality else "."))
        result.outputs = {"version_id": meta["id"], "quality": quality}
        result.terms = ["anomalia", "contaminacao", "isolation_forest", "precision_at_k"]
        result.next_step = "avaliacao"


# =============================================================================== CABAZ
class AssociationAgent(Agent):
    card = AgentCard(
        id="association", name="Agente de Cabaz de Compras", component="Regras de associação",
        role="Especialista em category management", icon="shopping-basket", step="treino",
        description="Analisa transações para encontrar itens comprados em conjunto (Apriori): itemsets frequentes, "
                    "regras com suporte, confiança e lift e matriz de afinidade entre os produtos principais.",
        capabilities=["Itemsets frequentes", "Regras com suporte/confiança/lift", "Matriz de afinidade"],
        inputs=["Coluna de transação", "Coluna de item"], outputs=["Regras de associação"],
        problem_types=["association_rules"],
    )

    def run(self, ctx: AgentContext, result: AgentResult, **_: Any) -> None:
        p = ctx.project
        df = ctx.data()
        if not (p.transaction_column and p.item_column):
            raise AgentError("Defina as colunas de transação e de item.")
        prof = data_profile(ctx)
        params = {**advisor.recommend("apriori", prof, p.use_case_id)["params"], **(p.model_params.get("apriori") or {})}
        ctx.progress(0.2, "A procurar itemsets frequentes…")
        rules, itemsets, info = U.apriori_rules(df, p.transaction_column, p.item_column, float(params["min_support"]),
                                                float(params["min_confidence"]), float(params["min_lift"]), int(params["max_len"]))
        items, lift = U.lift_matrix(df, p.transaction_column, p.item_column)
        quality = {"n_rules": int(len(rules)), "max_lift": float(rules["lift"].max()) if len(rules) else None,
                   "median_lift": float(rules["lift"].median()) if len(rules) else None, **info}
        meta = ctx.registry.register({
            "project_id": p.id, "project_name": p.name, "use_case_id": p.use_case_id, "problem_type": "association_rules",
            "kind": "association", "model_id": "apriori", "model_name": "Apriori", "params": params, "primary_metric": "lift",
            "metrics_test": {k: v for k, v in quality.items() if isinstance(v, (int, float)) and v is not None}, "quality": quality,
        }, artifacts={"rules": rules if len(rules) else pd.DataFrame({"antecedente": [], "consequente": []}), "itemsets": itemsets})
        ctx.registry.set_champion(p.id, meta["id"])
        ctx.save_project(champion_version_id=meta["id"])
        result.blocks.append(B.kpis([
            B.kpi("Transações", info["n_transactions"], "int", "", "itemset"), B.kpi("Itens distintos", info["n_items"], "int"),
            B.kpi("Itens por transação", info["avg_basket"], "num"), B.kpi("Regras encontradas", len(rules), "int", "", "regra_associacao"),
        ], "Análise de cabaz"))
        if len(rules):
            result.blocks.append(B.table("Regras ordenadas por lift", rules.head(60), [
                {"key": "antecedente", "label": "Se compra…"}, {"key": "consequente", "label": "…também compra"},
                {"key": "suporte", "label": "Suporte", "fmt": "pct"}, {"key": "confianca", "label": "Confiança", "fmt": "pct"},
                {"key": "lift", "label": "Lift", "fmt": "num"}], terms=["suporte", "confianca", "lift_associacao"]))
            top = rules.head(15).copy()
            top["regra"] = top["antecedente"] + " → " + top["consequente"]
            result.blocks.append(B.chart("bar", "Top 15 regras por lift", top[["regra", "lift"]], x="regra", y="lift", horizontal=True))
            best = rules.iloc[0]
            result.success("Associação mais forte", f"{best['antecedente']} → {best['consequente']}: confiança "
                           f"{pct(best['confianca'])}, lift {num(best['lift'])}.", ["lift_associacao"])
        else:
            result.warn("Nenhuma regra encontrada", "Reduza o suporte ou a confiança mínimos no Conselheiro.", ["suporte"])
        result.blocks.append(B.heatmap("Matriz de afinidade (lift) entre os 12 itens mais vendidos", items, items, lift,
                                       terms=["lift_associacao"]))
        result.summary = f"{len(rules)} regras em {info['n_transactions']} transações (suporte ≥ {pct(params['min_support'])})."
        result.outputs = {"version_id": meta["id"], "quality": quality}
        result.terms = ["regra_associacao", "suporte", "confianca", "lift_associacao", "apriori"]
        result.next_step = "implementacao"
