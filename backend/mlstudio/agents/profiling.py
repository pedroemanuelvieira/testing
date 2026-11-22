"""Agente de Perfil (EDA), Agente de Qualidade de Dados e Agente de Engenharia de Features."""
from __future__ import annotations

import re
from typing import Any, Optional

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.metrics import roc_auc_score

from ..core import agent as B
from ..core.agent import Agent, AgentCard, AgentResult
from ..core.context import AgentContext
from ..ml.features import FeatureBuilder, suggest_ratios
from ..ml.semantic import humanize
from .common import SUPERVISED, feature_list, num, pct, roles_for

LEAK_NAMES = re.compile(r"(data_?(cancel|rescis|saida|fecho|pagamento_efetivo|resolucao)|motivo_?(saida|cancel)|"
                        r"^dias_atraso$|resultado_final|estado_final|valor_recuperado)", re.I)


def cramers_v(x: pd.Series, y: pd.Series) -> float:
    tab = pd.crosstab(x.astype(str), y.astype(str))
    if tab.shape[0] < 2 or tab.shape[1] < 2:
        return 0.0
    chi2 = stats.chi2_contingency(tab, correction=False)[0]
    n = tab.values.sum()
    r, k = tab.shape
    return float(np.sqrt(chi2 / (n * max(1, min(r - 1, k - 1)))))


def single_feature_power(x: pd.Series, y: pd.Series, task: str) -> float:
    """Poder preditivo individual (0–1): AUC simétrica, |ρ| de Spearman ou V de Cramér."""
    mask = x.notna() & y.notna()
    x, y = x[mask], y[mask]
    if len(x) < 30 or x.nunique() < 2:
        return 0.0
    numeric = pd.api.types.is_numeric_dtype(x) and not pd.api.types.is_bool_dtype(x)
    if task == "binary_classification" and numeric:
        try:
            auc = roc_auc_score(y, x.astype(float))
            return float(abs(auc - 0.5) * 2)
        except ValueError:
            return 0.0
    if task == "regression" and numeric:
        return float(abs(stats.spearmanr(x.astype(float), y.astype(float)).statistic))
    if task == "regression":
        groups = [g.astype(float).values for _, g in y.groupby(x.astype(str)) if len(g) > 5]
        if len(groups) < 2:
            return 0.0
        h = stats.kruskal(*groups).statistic
        return float(min(1.0, np.sqrt(h / len(y))))
    xs = pd.qcut(x.astype(float), 10, duplicates="drop").astype(str) if numeric else x
    return cramers_v(xs, y)


class ProfilerAgent(Agent):
    card = AgentCard(
        id="profiler", name="Agente de Perfil (EDA)", component="Análise exploratória",
        role="Analista de dados", icon="bar-chart", step="perfil",
        description="Perfila cada coluna (tipo, distribuição, nulos, estatísticas), analisa a relação de cada "
                    "variável com o alvo e as correlações, e gera as primeiras hipóteses de negócio.",
        capabilities=["Estatísticas e histogramas por coluna", "Análise do alvo", "Poder preditivo individual",
                      "Correlações (Spearman/Cramér)"],
        inputs=["Snapshot de dados", "Alvo"], outputs=["Perfil de colunas", "Análise do alvo", "Correlações"],
    )

    def run(self, ctx: AgentContext, result: AgentResult, **_: Any) -> None:
        p = ctx.project
        df = ctx.data()
        roles = roles_for(ctx, df)
        ctx.progress(0.1, "A calcular estatísticas por coluna…")
        prof_rows = []
        for c in df.columns:
            s = df[c]
            row = {"coluna": c, "papel": roles.get(c), "nulos": float(s.isna().mean()), "distintos": int(s.nunique())}
            if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
                v = s.astype(float)
                row.update(media=v.mean(), mediana=v.median(), desvio=v.std(), minimo=v.min(), maximo=v.max(),
                           assimetria=v.skew())
            elif pd.api.types.is_datetime64_any_dtype(s):
                row.update(minimo=str(s.min().date()) if s.notna().any() else None,
                           maximo=str(s.max().date()) if s.notna().any() else None)
            else:
                top = s.astype(str).value_counts().head(1)
                row["moda"] = f"{top.index[0]} ({pct(top.iloc[0] / len(s))})" if len(top) else None
            prof_rows.append(row)
        result.blocks.append(B.table("Perfil das colunas", prof_rows, [
            {"key": "coluna", "label": "Coluna"}, {"key": "papel", "label": "Papel"},
            {"key": "nulos", "label": "% nulos", "fmt": "pct"}, {"key": "distintos", "label": "Distintos", "fmt": "int"},
            {"key": "media", "label": "Média", "fmt": "num"}, {"key": "mediana", "label": "Mediana", "fmt": "num"},
            {"key": "desvio", "label": "Desvio", "fmt": "num"}, {"key": "minimo", "label": "Mín."},
            {"key": "maximo", "label": "Máx."}, {"key": "assimetria", "label": "Assimetria", "fmt": "num"},
            {"key": "moda", "label": "Valor mais frequente"}], terms=["distribuicao", "media_mediana", "assimetria"]))

        num_cols = [c for c, r in roles.items() if r == "numeric"]
        skewed = [r["coluna"] for r in prof_rows if r.get("assimetria") is not None and abs(r["assimetria"]) > 1]
        for c in num_cols[:6]:
            v = df[c].astype(float).dropna()
            if v.empty:
                continue
            hist, edges = np.histogram(np.clip(v, v.quantile(0.005), v.quantile(0.995)), bins=20)
            result.blocks.append(B.chart("histogram", f"Distribuição — {humanize(c)}",
                                         [{"intervalo": f"{edges[i]:.3g}", "n": int(hist[i])} for i in range(len(hist))],
                                         x="intervalo", y="n", terms=["distribuicao"]))
        if skewed:
            result.info("Variáveis com forte assimetria", ", ".join(skewed[:8]) + ". O Agente de Features aplica "
                        "transformação logarítmica.", ["assimetria", "transformacao_log"])

        # análise do alvo
        powers = []
        if p.problem_type in SUPERVISED and p.target in df.columns:
            ctx.progress(0.4, "A analisar a relação com o alvo…")
            y_raw = df[p.target]
            if p.problem_type == "binary_classification":
                pos = p.positive_class if p.positive_class is not None else y_raw.value_counts().index[-1]
                y = (y_raw.astype(str) == str(pos)).astype(int)
                vc = y_raw.astype(str).value_counts()
                result.blocks.append(B.chart("bar", f"Distribuição do alvo — {p.target}",
                                             [{"classe": k, "n": int(v)} for k, v in vc.items()], x="classe", y="n",
                                             terms=["desequilibrio_classes"]))
            elif p.problem_type == "multiclass_classification":
                y = y_raw.astype(str)
                vc = y.value_counts()
                result.blocks.append(B.chart("bar", f"Distribuição do alvo — {p.target}",
                                             [{"classe": k, "n": int(v)} for k, v in vc.items()], x="classe", y="n"))
            else:
                y = pd.to_numeric(y_raw, errors="coerce")
                hist, edges = np.histogram(y.dropna().clip(y.quantile(0.005), y.quantile(0.995)), bins=25)
                result.blocks.append(B.chart("histogram", f"Distribuição do alvo — {p.target}",
                                             [{"intervalo": f"{edges[i]:.3g}", "n": int(hist[i])} for i in range(len(hist))],
                                             x="intervalo", y="n", terms=["assimetria"]))
            feats = feature_list(ctx, df, roles)
            task = p.problem_type if p.problem_type != "multiclass_classification" else "multiclass"
            for c in feats:
                if roles.get(c) == "datetime":
                    continue
                powers.append({"variavel": c, "poder": single_feature_power(df[c], y, task if task != "multiclass" else "multiclass")})
            powers.sort(key=lambda r: -r["poder"])
            result.blocks.append(B.chart("bar", "Poder preditivo individual de cada variável",
                                         [{"variavel": r["variavel"], "poder": round(r["poder"], 4)} for r in powers[:20]],
                                         x="variavel", y="poder", horizontal=True,
                                         description="0 = sem relação; 1 = separa perfeitamente o alvo. Valores muito "
                                                     "próximos de 1 indicam possível leakage.",
                                         terms=["auc_roc", "cramers_v", "correlacao", "data_leakage"]))
            # efeito das principais variáveis no alvo
            if p.problem_type == "multiclass_classification":
                focus = y.value_counts().index[-1]
                y_num, label = (y == focus).astype(float), f"Taxa de '{focus}'"
            else:
                y_num = pd.to_numeric(y, errors="coerce")
                label = "Média do alvo" if p.problem_type == "regression" else "Taxa do alvo"
            for r in powers[:3]:
                c = r["variavel"]
                s = df[c]
                if pd.api.types.is_numeric_dtype(s) and s.nunique() > 10:
                    groups = pd.qcut(s.astype(float), 5, duplicates="drop").astype(str)
                    g = pd.DataFrame({"g": groups, "y": y_num}).groupby("g", sort=False)["y"].mean()
                    g = g.reindex(sorted(g.index, key=lambda t: float(re.findall(r"-?[\d.]+", t)[0]) if re.findall(r"-?[\d.]+", t) else 0))
                else:
                    g = (pd.DataFrame({"g": s.astype(str), "y": y_num}).groupby("g")["y"].mean()
                         .sort_values(ascending=False).head(12))
                result.blocks.append(B.chart("bar", f"{label} por {humanize(c)}",
                                             [{"grupo": k, "valor": float(v)} for k, v in g.items()], x="grupo", y="valor"))
            if powers and powers[0]["poder"] > 0.94:
                result.critical(f"Possível data leakage em '{powers[0]['variavel']}'",
                                "Esta variável sozinha separa quase perfeitamente o alvo. Confirme que está disponível "
                                "no momento da previsão.", ["data_leakage"])
            elif powers:
                result.success("Principais drivers potenciais", ", ".join(humanize(r["variavel"]) for r in powers[:5]),
                               ["importancia_features"])

        # correlações
        if len(num_cols) >= 2:
            ctx.progress(0.75, "A calcular correlações…")
            top = sorted(num_cols, key=lambda c: -df[c].astype(float).std() / (abs(df[c].astype(float).mean()) + 1e-9))[:14]
            top = [c for c in num_cols if c in top]
            corr = df[top].astype(float).corr(method="spearman")
            result.blocks.append(B.heatmap("Correlação de Spearman entre variáveis numéricas", top, top,
                                           corr.round(2).values.tolist(), terms=["correlacao", "multicolinearidade"],
                                           diverging=True))
            pairs = [(a, b, corr.loc[a, b]) for i, a in enumerate(top) for b in top[i + 1:] if abs(corr.loc[a, b]) > 0.85]
            if pairs:
                result.warn("Variáveis muito correlacionadas", "; ".join(f"{a} ↔ {b} ({num(v)})" for a, b, v in pairs[:5]),
                            ["multicolinearidade"])
        result.summary = (f"{df.shape[1]} colunas perfiladas: {len(num_cols)} numéricas, "
                          f"{sum(r == 'categorical' for r in roles.values())} categóricas, "
                          f"{sum(r == 'datetime' for r in roles.values())} de data."
                          + (f" Principal driver potencial: {powers[0]['variavel']}." if powers else ""))
        result.outputs = {"roles": roles, "feature_power": powers[:30], "skewed": skewed}
        p.column_roles = roles
        ctx.save_project()
        result.terms = ["distribuicao", "correlacao", "assimetria", "desequilibrio_classes"]
        result.next_step = "qualidade"


class QualityAgent(Agent):
    card = AgentCard(
        id="quality", name="Agente de Qualidade de Dados", component="Qualidade de dados",
        role="Data steward", icon="shield-check", step="qualidade",
        description="Deteta valores em falta, duplicados, constantes, identificadores, alta cardinalidade, outliers, "
                    "desequilíbrio e — sobretudo — data leakage. Calcula um score de qualidade e corrige "
                    "automaticamente o que é seguro (exclusão de IDs, constantes e suspeitas de leakage).",
        capabilities=["Score de qualidade 0–100", "Deteção de leakage", "Outliers (IQR)", "Correções automáticas"],
        inputs=["Snapshot de dados", "Alvo"], outputs=["Score", "Problemas por gravidade", "Colunas excluídas"],
        params=[{"name": "apply", "label": "Aplicar correções automáticas", "type": "bool"}],
    )

    def run(self, ctx: AgentContext, result: AgentResult, apply: bool = True, **_: Any) -> None:
        p = ctx.project
        df = ctx.data()
        roles = roles_for(ctx, df)
        issues: list[dict[str, Any]] = []
        exclude: dict[str, str] = {}
        penalty = 0.0

        def add(col: str, problem: str, severity: str, rec: str, term: Optional[str] = None) -> None:
            nonlocal penalty
            issues.append({"coluna": col, "problema": problem, "gravidade": severity, "recomendacao": rec, "termo": term})
            penalty += {"crítico": 12, "alto": 6, "médio": 3, "baixo": 1}[severity]

        n = len(df)
        dup = int(df.duplicated().sum())
        if dup:
            add("(todas)", f"{dup} linhas duplicadas ({pct(dup / n)})", "alto" if dup / n > 0.01 else "médio",
                "Remover duplicados — verifique joins muitos-para-muitos no modelo semântico.", "duplicados")
        for c in p.id_columns:
            if c in df.columns and df[c].duplicated().any():
                k = int(df[c].duplicated().sum())
                add(c, f"Identificador repetido em {k} linhas", "médio", "Confirme a granularidade da tabela.", "granularidade")
        target = p.target if p.problem_type in SUPERVISED else None
        y = None
        if target and target in df.columns:
            if df[target].isna().any():
                add(target, f"Alvo em falta em {pct(df[target].isna().mean())} das linhas", "alto",
                    "Linhas sem alvo serão ignoradas no treino.", "target")
            if p.problem_type == "binary_classification":
                pos = p.positive_class if p.positive_class is not None else df[target].value_counts().index[-1]
                y = (df[target].astype(str) == str(pos)).astype(int)
                rate = y.mean()
                if min(rate, 1 - rate) < 0.1:
                    add(target, f"Desequilíbrio de classes ({pct(rate)} positivos)", "médio",
                        "Usar PR-AUC/recall, pesos de classe e limiar por custo.", "desequilibrio_classes")
            elif p.problem_type == "regression":
                y = pd.to_numeric(df[target], errors="coerce")
            else:
                y = df[target].astype(str)
        uc = ctx.use_case
        for c in df.columns:
            if c == target:
                continue
            s = df[c]
            role = roles.get(c)
            miss = s.isna().mean()
            if miss > 0.4:
                add(c, f"{pct(miss)} de valores em falta", "alto", "Considere remover a coluna ou criar indicador de ausência.", "valores_em_falta")
            elif miss > 0.05:
                add(c, f"{pct(miss)} de valores em falta", "baixo", "Imputação automática (mediana/categoria 'em falta') no pipeline.", "imputacao")
            if role == "constant":
                add(c, "Coluna constante", "médio", "Excluída — não tem informação.", "variavel_constante")
                exclude[c] = "constante"
                continue
            top_freq = s.value_counts(normalize=True, dropna=False).iloc[0] if n else 0
            if top_freq >= 0.99 and role != "constant":
                add(c, f"Quase constante ({pct(top_freq)} com o mesmo valor)", "baixo", "Excluída.", "variavel_constante")
                exclude[c] = "quase constante"
            if role == "id" and c not in p.id_columns:
                add(c, "Parece um identificador", "médio", "Excluída das features (mantida para ligar previsões).", "identificador")
                exclude[c] = "identificador"
            if role == "text":
                add(c, "Texto livre", "baixo", "Excluída (texto livre requer processamento próprio).", None)
                exclude[c] = "texto livre"
            if role == "categorical" and s.nunique() > 50:
                add(c, f"Alta cardinalidade ({s.nunique()} valores)", "baixo", "Será usada codificação por target encoding.", "cardinalidade")
            if role == "numeric":
                v = s.astype(float).dropna()
                q1, q3 = v.quantile(0.25), v.quantile(0.75)
                iqr = q3 - q1
                if iqr > 0:
                    out = ((v < q1 - 3 * iqr) | (v > q3 + 3 * iqr)).mean()
                    if out > 0.01:
                        add(c, f"{pct(out)} de outliers extremos (3×IQR)", "baixo",
                            "Os modelos de árvores são robustos; verifique se são erros de registo.", "outlier")
            # leakage
            if LEAK_NAMES.search(c) and c not in p.excluded_columns:
                add(c, "Nome sugere informação posterior ao evento", "crítico", "Excluída por suspeita de data leakage.", "data_leakage")
                exclude[c] = "suspeita de leakage (nome)"
            elif y is not None and role in ("numeric", "boolean", "categorical") and c not in p.excluded_columns:
                power = single_feature_power(s, y, p.problem_type if p.problem_type != "multiclass_classification" else "multiclass")
                if power > 0.94:
                    add(c, f"Associação quase perfeita com o alvo (poder = {num(power)})", "crítico",
                        "Excluída por suspeita de data leakage. Reverta se tiver a certeza de que está disponível no momento da previsão.",
                        "data_leakage")
                    exclude[c] = f"suspeita de leakage (poder {num(power)})"
        if uc and uc.demo:
            for c in uc.demo.get("exclude", []) or []:
                if c in df.columns and c not in p.excluded_columns:
                    exclude[c] = "definida no caso de uso (leakage/alvo alternativo)"
        if p.time_column and p.time_column in df.columns and p.problem_type == "forecasting":
            d = pd.to_datetime(df[p.time_column], errors="coerce").dropna().sort_values()
            if d.nunique() > 3:
                step = d.drop_duplicates().diff().median()
                gaps = int((d.drop_duplicates().diff() > step * 1.5).sum())
                if gaps:
                    add(p.time_column, f"{gaps} interrupções na série temporal", "baixo", "Os períodos em falta serão preenchidos.", "serie_temporal")
        score = max(0.0, 100.0 - penalty)
        applied = []
        if apply:
            new = [c for c in exclude if c not in p.excluded_columns and c not in p.id_columns]
            if new:
                p.excluded_columns = p.excluded_columns + new
                applied = new
            ctx.save_project()
        sev = pd.Series([i["gravidade"] for i in issues]).value_counts() if issues else pd.Series(dtype=int)
        result.blocks.append(B.kpis([
            B.kpi("Score de qualidade", round(score), "score", "100 = sem problemas", None,
                  "ok" if score >= 80 else "warning" if score >= 60 else "critical"),
            B.kpi("Problemas críticos", int(sev.get("crítico", 0)), "int", "", "data_leakage",
                  "critical" if sev.get("crítico", 0) else "ok"),
            B.kpi("Problemas altos/médios", int(sev.get("alto", 0) + sev.get("médio", 0)), "int"),
            B.kpi("Colunas excluídas agora", len(applied), "int", ", ".join(applied[:4])),
        ], "Qualidade dos dados"))
        order = {"crítico": 0, "alto": 1, "médio": 2, "baixo": 3}
        issues.sort(key=lambda i: order[i["gravidade"]])
        result.blocks.append(B.table("Problemas encontrados", issues, [
            {"key": "gravidade", "label": "Gravidade", "fmt": "badge"}, {"key": "coluna", "label": "Coluna"},
            {"key": "problema", "label": "Problema"}, {"key": "recomendacao", "label": "Recomendação"},
            {"key": "termo", "label": "Glossário", "fmt": "term"}]))
        miss = df.isna().mean().sort_values(ascending=False)
        miss = miss[miss > 0].head(15)
        if len(miss):
            result.blocks.append(B.chart("bar", "Valores em falta por coluna",
                                         [{"coluna": k, "pct": float(v)} for k, v in miss.items()], x="coluna", y="pct",
                                         horizontal=True, terms=["valores_em_falta"], fmt="pct"))
        if any(i["gravidade"] == "crítico" for i in issues):
            result.critical("Foram encontradas suspeitas de data leakage",
                            "As colunas foram excluídas automaticamente. Reveja a lista antes de treinar.", ["data_leakage"])
        if exclude:
            result.blocks.append(B.table("Colunas a excluir do treino", [{"coluna": k, "motivo": v} for k, v in exclude.items()]))
        result.summary = f"Score de qualidade {score:.0f}/100 com {len(issues)} problema(s); {len(applied)} coluna(s) excluída(s)."
        result.outputs = {"score": score, "issues": issues, "excluded": list(exclude), "applied": applied}
        result.terms = ["data_leakage", "valores_em_falta", "outlier", "identificador"]
        result.next_step = "features" if p.problem_type in SUPERVISED else "modelos"


class FeatureAgent(Agent):
    card = AgentCard(
        id="features", name="Agente de Engenharia de Features", component="Feature engineering",
        role="Engenheiro de features", icon="wrench", step="features",
        description="Constrói o plano de features (datas → componentes, log de variáveis assimétricas, rácios de "
                    "negócio, codificação por cardinalidade) e mede o poder preditivo das features resultantes por "
                    "informação mútua.",
        capabilities=["Features de calendário", "Transformações log", "Rácios de negócio (ex.: ticket médio)",
                      "Codificação one-hot / target encoding", "Ranking por informação mútua"],
        inputs=["Snapshot", "Tipos de colunas", "Exclusões"], outputs=["Plano de features", "Ranking de features"],
        problem_types=["binary_classification", "multiclass_classification", "regression"],
    )

    def run(self, ctx: AgentContext, result: AgentResult, ratios: Optional[list[dict[str, str]]] = None,
            log_columns: Optional[list[str]] = None, **_: Any) -> None:
        from sklearn.feature_selection import mutual_info_classif, mutual_info_regression

        p = ctx.project
        df = ctx.data()
        roles = roles_for(ctx, df)
        feats = feature_list(ctx, df, roles)
        dates = [c for c in feats if roles.get(c) == "datetime"]
        numeric = [c for c in feats if roles.get(c) == "numeric"]
        skewed = log_columns if log_columns is not None else [
            c for c in numeric if df[c].astype(float).min() >= 0 and abs(df[c].astype(float).skew()) > 1]
        rat = ratios if ratios is not None else suggest_ratios(feats)
        drop = [c for c in df.columns if c not in feats]
        plan = {"drop": drop, "datetime": dates, "log": skewed, "ratios": rat,
                "categorical": [c for c in feats if roles.get(c) == "categorical"],
                "numeric": [c for c in feats if roles.get(c) in ("numeric", "boolean")]}
        p.feature_plan = plan
        ctx.save_project()
        ctx.progress(0.3, "A construir features de pré-visualização…")
        sample = df.sample(min(len(df), 6000), random_state=1) if len(df) > 6000 else df
        fb = FeatureBuilder(plan).fit(sample)
        Xf = fb.transform(sample)
        rows = [{"transformacao": "Datas → ano, mês, dia da semana, trimestre, fim de semana, dias desde",
                 "colunas": ", ".join(dates) or "—", "termo": "features_data"},
                {"transformacao": "Log(1 + x) em variáveis assimétricas", "colunas": ", ".join(skewed) or "—",
                 "termo": "transformacao_log"},
                {"transformacao": "Rácios de negócio", "colunas": ", ".join(r["name"] for r in rat) or "—", "termo": "feature_engineering"},
                {"transformacao": "One-hot (≤ 15 categorias)", "colunas": ", ".join(c for c in fb.categorical_ if Xf[c].nunique() <= 15) or "—",
                 "termo": "one_hot_encoding"},
                {"transformacao": "Target encoding (> 15 categorias)", "colunas": ", ".join(c for c in fb.categorical_ if Xf[c].nunique() > 15) or "—",
                 "termo": "target_encoding"},
                {"transformacao": "Imputação (mediana / 'em falta') e indicadores de ausência", "colunas": "todas", "termo": "imputacao"},
                {"transformacao": "Normalização (só para modelos que precisam)", "colunas": "numéricas", "termo": "standardizacao"},
                {"transformacao": "Excluídas", "colunas": ", ".join(drop), "termo": "identificador"}]
        result.blocks.append(B.table("Plano de features", rows, [
            {"key": "transformacao", "label": "Transformação"}, {"key": "colunas", "label": "Colunas"},
            {"key": "termo", "label": "Glossário", "fmt": "term"}]))
        mi_rows = []
        if p.problem_type in SUPERVISED and p.target in sample.columns:
            ctx.progress(0.6, "A medir informação mútua…")
            yraw = sample[p.target]
            ok = yraw.notna()
            X = Xf[ok].copy()
            disc = []
            for c in X.columns:
                if c in fb.categorical_:
                    X[c] = X[c].astype("category").cat.codes
                    disc.append(True)
                else:
                    X[c] = X[c].fillna(X[c].median())
                    disc.append(False)
            if p.problem_type == "regression":
                mi = mutual_info_regression(X, pd.to_numeric(yraw[ok]), discrete_features=disc, random_state=1)
            else:
                mi = mutual_info_classif(X, yraw[ok].astype(str), discrete_features=disc, random_state=1)
            mi_rows = sorted(({"feature": c, "informacao_mutua": float(v)} for c, v in zip(X.columns, mi)),
                             key=lambda r: -r["informacao_mutua"])
            result.blocks.append(B.chart("bar", "Informação mútua com o alvo (features finais)", mi_rows[:20],
                                         x="feature", y="informacao_mutua", horizontal=True, terms=["informacao_mutua"]))
            weak = [r["feature"] for r in mi_rows if r["informacao_mutua"] < 0.001]
            if weak:
                result.info("Features com informação quase nula", ", ".join(weak[:8]) + " — não prejudicam modelos "
                            "de árvores mas podem ser removidas para simplificar.", ["selecao_features"])
        result.blocks.append(B.table("Pré-visualização das features finais", Xf.head(10)))
        if rat:
            result.success("Rácios de negócio criados", ", ".join(r["name"] for r in rat), ["feature_engineering"])
        result.summary = (f"{len(Xf.columns)} features finais a partir de {len(feats)} colunas "
                          f"({len(dates)} datas expandidas, {len(skewed)} log, {len(rat)} rácios).")
        result.outputs = {"plan": plan, "n_features": len(Xf.columns), "mutual_information": mi_rows[:30]}
        result.terms = ["feature_engineering", "one_hot_encoding", "target_encoding", "informacao_mutua"]
        result.next_step = "modelos"
