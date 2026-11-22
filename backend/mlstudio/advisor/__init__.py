"""Conselheiro de hiperparâmetros.

Recomenda valores por modelo × caso de uso × perfil dos dados × objetivo, explica
cada recomendação, propõe o espaço de pesquisa para afinação, valida
configurações escritas pelo utilizador e estima o risco de overfitting /
underfitting de forma indicativa.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional

from ..knowledge import get_kb
from ..knowledge.schema import ModelSpec, UseCase
from .profile import DataProfile, imbalance_level

GOALS = {
    "equilibrado": "Equilíbrio entre desempenho, estabilidade e tempo de treino.",
    "performance": "Máximo desempenho preditivo (aceita mais tempo de treino e menor interpretabilidade).",
    "interpretabilidade": "Modelos mais simples e fáceis de explicar ao negócio/regulador.",
    "rapidez": "Treino e scoring rápidos (iterações rápidas, bases grandes).",
}


@dataclass
class Advice:
    params: dict[str, Any] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def set(self, name: str, value: Any, reason: str) -> None:
        self.params[name] = value
        self.reasons[name] = reason


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _fmt(n: float) -> str:
    return f"{n:,.0f}".replace(",", " ")


def _boost_budget(n: int, goal: str) -> tuple[float, int]:
    """Taxa de aprendizagem e nº de árvores: menos capacidade em bases pequenas (sem early stopping)."""
    if n < 5_000:
        lr, trees = 0.03, 400
    elif n < 20_000:
        lr, trees = 0.05, 400
    elif n < 200_000:
        lr, trees = 0.05, 600
    else:
        lr, trees = 0.1, 500
    if goal == "performance":
        lr, trees = round(lr * 0.6, 3), int(trees * 1.6)
    elif goal == "rapidez":
        lr, trees = min(0.15, lr * 2), max(150, trees // 2)
    return lr, trees


def _goal(goal: Optional[str], uc: Optional[UseCase]) -> str:
    if goal in GOALS:
        return goal  # type: ignore[return-value]
    if uc and uc.profile.get("goal") in GOALS:
        return uc.profile["goal"]
    return "equilibrado"


def _interp(uc: Optional[UseCase]) -> str:
    return (uc.profile.get("interpretability") if uc else None) or "média"


def _regulated(uc: Optional[UseCase]) -> bool:
    return bool(uc and (uc.profile.get("regulated") or uc.ai_act_risk == "alto"))


def _ranking_metric(uc: Optional[UseCase]) -> bool:
    return bool(uc and uc.metrics.primary in ("pr_auc", "roc_auc", "lift", "precision_at_k"))


# =============================================================================== regras por modelo
def _rules(model: ModelSpec, prof: DataProfile, uc: Optional[UseCase], goal: str) -> Advice:
    a = Advice()
    n, p = prof.n_rows, max(prof.n_features, 1)
    clf = prof.task in ("binary_classification", "multiclass_classification")
    imb = prof.imbalance if clf else "nenhum"
    interp = _interp(uc)
    mid = model.id

    def class_weight_rule(choices_balanced: str = "balanced") -> None:
        if not clf:
            return
        if _regulated(uc) and uc and uc.metrics.primary in ("roc_auc",) and "brier" in uc.metrics.secondary:
            a.set("class_weight", "none", "Caso regulado em que a probabilidade é usada como valor (ex.: PD): "
                  "pesos de classe descalibram as probabilidades — trate o desequilíbrio no limiar.")
        elif imb in ("forte", "extremo"):
            a.set("class_weight", choices_balanced, f"Desequilíbrio {imb} (classe minoritária ≈ "
                  f"{100 * min(prof.positive_rate or 0, 1 - (prof.positive_rate or 0)):.1f}%): dar mais peso aos "
                  "positivos aumenta o recall. As probabilidades ficam inflacionadas — use-as para ordenar.")
        elif imb == "moderado":
            a.set("class_weight", "none", "Desequilíbrio moderado: normalmente basta escolher bem o limiar "
                  "de decisão no passo de avaliação.")
        else:
            a.set("class_weight", "none", "Classes equilibradas — não é necessário reponderar.")

    # ------------------------------------------------------------------ lineares
    if mid == "logistic_regression":
        if p > n / 20:
            a.set("C", 0.1, f"Muitas variáveis ({p}) face às linhas ({_fmt(n)}): regularização mais forte evita overfitting.")
        elif goal == "interpretabilidade" or interp == "alta":
            a.set("C", 0.3, "Regularização um pouco mais forte produz coeficientes mais estáveis e fáceis de explicar.")
        else:
            a.set("C", 1.0, "Valor de referência: regularização moderada, adequada à maioria dos casos.")
        if goal == "interpretabilidade" or p > 40:
            a.set("penalty", "l1", "L1 anula coeficientes de variáveis pouco úteis → modelo esparso e mais explicável.")
        else:
            a.set("penalty", "l2", "L2 encolhe todos os coeficientes e lida bem com variáveis correlacionadas.")
        a.set("l1_ratio", 0.5, "Só é usado com penalização elasticnet.")
        class_weight_rule()
        a.set("max_iter", 2000 if n > 100_000 else 1000, "Iterações suficientes para o otimizador convergir.")
        if prof.max_abs_corr and prof.max_abs_corr > 0.9:
            a.notes.append(f"Há variáveis muito correlacionadas (|ρ| = {prof.max_abs_corr:.2f}): os coeficientes "
                           "individuais podem ser instáveis — interprete-os em conjunto.")
    elif mid == "linear_regression":
        a.set("fit_intercept", True, "Mantém o valor base (constante) do modelo.")
        if prof.max_abs_corr and prof.max_abs_corr > 0.9:
            a.notes.append("Multicolinearidade elevada: prefira Ridge/Elastic Net para coeficientes estáveis.")
    elif mid == "ridge":
        a.set("alpha", 10.0 if p > n / 20 else 1.0,
              "Mais regularização com muitas variáveis face às linhas." if p > n / 20 else
              "Regularização moderada; o espaço de pesquisa explora 0,01 a 100.")
    elif mid in ("lasso", "elastic_net"):
        scale = prof.target_std or 1.0
        alpha = round(max(1e-4, 0.01 * scale), 5)
        a.set("alpha", alpha, f"A força do Lasso depende da escala do alvo (desvio padrão ≈ {scale:,.2f}): "
              "≈ 1% do desvio padrão é um bom ponto de partida.")
        if mid == "elastic_net":
            a.set("l1_ratio", 0.5, "Meio-termo entre seleção de variáveis (L1) e estabilidade (L2).")
    # ------------------------------------------------------------------ árvores
    elif mid == "decision_tree":
        depth = 4 if (goal == "interpretabilidade" or interp == "alta") else int(_clamp(round(math.log2(max(n, 2) / 50)), 3, 10))
        a.set("max_depth", depth, "Árvores com 3–5 níveis dão regras legíveis; mais profundidade capta mais "
              f"detalhe mas aumenta o overfitting (base com {_fmt(n)} linhas).")
        leaf = int(_clamp(round(n * 0.005), 5, 200))
        a.set("min_samples_leaf", leaf, f"Cada regra final cobre ≥ {leaf} registos (≈ 0,5% da base) — regras robustas.")
        a.set("criterion", "gini" if clf else "squared_error", "Critério padrão e eficiente.")
        class_weight_rule()
        a.set("ccp_alpha", 0.0, "A poda é controlada pela profundidade e pelo mínimo por folha.")
    elif mid in ("random_forest", "extra_trees"):
        trees = 200 if goal == "rapidez" else (300 if n < 20_000 else 500)
        a.set("n_estimators", trees, f"{trees} árvores estabilizam as previsões; mais árvores não causam overfitting, só custam tempo.")
        if interp == "alta" or goal == "interpretabilidade":
            a.set("max_depth", 10, "Limitar a profundidade torna a importância de variáveis mais estável e o modelo mais leve.")
        elif n < 5000:
            a.set("max_depth", 12, f"Base pequena ({_fmt(n)} linhas): limitar a profundidade reduz o overfitting.")
        else:
            a.set("max_depth", 0, "Sem limite: com dados suficientes a média de muitas árvores controla a variância.")
        leaf = 3 if n < 2000 else (2 if n < 50_000 else 1)
        if imb == "extremo":
            leaf = 1
        a.set("min_samples_leaf", leaf, "Folhas pequenas captam detalhe; com bases pequenas convém um mínimo maior "
              "para suavizar o ruído." if leaf > 1 else "Com muitos dados ou classes muito raras, folhas pequenas permitem isolar os positivos.")
        if clf:
            a.set("max_features", "sqrt", "√(nº de variáveis) por divisão: referência para classificação — árvores diversas.")
        else:
            a.set("max_features", "0.5", "50% das variáveis por divisão: em regressão costuma superar o √ e o 100%.")
        class_weight_rule("balanced_subsample")
        if mid == "random_forest":
            a.set("bootstrap", True, "Amostragem bootstrap: base do bagging.")
        if n > 300_000:
            a.notes.append("Base muito grande: os Random Forest ficam pesados em memória — considere LightGBM.")
    elif mid == "hist_gradient_boosting":
        lr = 0.1 if (n > 100_000 or goal == "rapidez") else 0.05
        a.set("learning_rate", lr, f"Taxa {lr}: com early stopping, o nº de iterações ajusta-se automaticamente.")
        a.set("max_iter", 1000, "Limite superior; o early stopping pára quando a validação interna deixa de melhorar.")
        leaves = 15 if n < 5000 else (31 if n < 50_000 else 63)
        if interp == "alta":
            leaves = min(leaves, 15)
        a.set("max_leaf_nodes", leaves, f"Complexidade por árvore adequada a {_fmt(n)} linhas.")
        a.set("min_samples_leaf", int(_clamp(round(n * 0.001), 20, 200)), "Regulariza as folhas proporcionalmente ao volume.")
        a.set("l2_regularization", 1.0 if n < 10_000 else 0.0, "Regularização extra em bases pequenas." if n < 10_000 else "Sem necessidade de regularização L2 adicional.")
        a.set("early_stopping", "true", "Evita overfitting e encontra o nº ótimo de árvores.")
        class_weight_rule()
    elif mid == "lightgbm":
        lr, trees = _boost_budget(n, goal)
        a.set("learning_rate", lr, f"Taxa {lr} com {trees} árvores (regra: metade da taxa → dobro das árvores). "
              f"Objetivo '{goal}'.")
        a.set("n_estimators", trees, f"Capacidade total (taxa × árvores = {lr * trees:.0f}) adequada ao volume.")
        leaves = 15 if n < 2000 else 24 if n < 10_000 else 31 if n < 100_000 else 63
        if goal == "interpretabilidade" or interp == "alta":
            leaves = min(leaves, 15)
        a.set("num_leaves", leaves, f"Principal controlo de complexidade; {leaves} folhas para {_fmt(n)} linhas "
              "(bases pequenas exigem árvores mais simples).")
        a.set("max_depth", -1 if n >= 10_000 else 6, "Sem limite (o num_leaves controla)." if n >= 10_000 else
              "Base pequena: limitar a profundidade complementa o num_leaves.")
        mcs = int(_clamp(round(n * 0.005), 20, 200))
        if imb == "extremo" and prof.positives:
            mcs = int(_clamp(round(prof.positives * 0.05), 5, 20))
            reason = (f"Classe positiva muito rara (≈ {prof.positives} casos): folhas pequenas permitem isolar padrões "
                      "de positivos.")
        else:
            reason = "≈ 0,5% das linhas por folha (mín. 20) evita folhas ajustadas a ruído."
        a.set("min_child_samples", mcs, reason)
        a.set("subsample", 0.8, "80% das linhas por árvore: regulariza e acelera.")
        a.set("colsample_bytree", 1.0 if p < 10 else 0.8, "Poucas variáveis: usar todas." if p < 10 else
              "80% das variáveis por árvore: mais diversidade, menos overfitting.")
        a.set("reg_lambda", 5.0 if n < 5000 else 1.0, "Regularização L2 mais forte em bases pequenas." if n < 5000 else
              "Regularização L2 ligeira.")
        a.set("reg_alpha", 0.5 if p > 100 else 0.0, "Muitas variáveis: L1 ajuda a ignorar as irrelevantes." if p > 100
              else "Sem necessidade de L1.")
        class_weight_rule()
        a.notes.append("O nº de árvores é fixo no pipeline; a afinação automática explora a combinação taxa × árvores.")
    elif mid == "xgboost":
        lr, trees = _boost_budget(n, goal)
        a.set("learning_rate", lr, f"Taxa {lr} com {trees} árvores.")
        a.set("n_estimators", trees, f"Capacidade total (taxa × árvores = {lr * trees:.0f}).")
        depth = 4 if (n < 5000 or interp == "alta") else (6 if n < 100_000 else 8)
        a.set("max_depth", depth, f"Profundidade {depth}: interações até {depth} variáveis, adequado a {_fmt(n)} linhas.")
        a.set("min_child_weight", 5.0 if n < 5000 else 1.0, "Folhas mais robustas em bases pequenas." if n < 5000 else "Valor padrão.")
        a.set("subsample", 0.8, "80% das linhas por árvore.")
        a.set("colsample_bytree", 0.8, "80% das variáveis por árvore.")
        a.set("gamma", 1.0 if n < 5000 else 0.0, "Poda adicional em bases pequenas." if n < 5000 else "Sem poda adicional.")
        a.set("reg_lambda", 5.0 if n < 5000 else 1.0, "Regularização L2.")
        if prof.task == "binary_classification" and prof.positive_rate:
            minority = min(prof.positive_rate, 1 - prof.positive_rate)
            ratio = (1 - minority) / minority
            if imb == "extremo":
                spw = round(math.sqrt(ratio), 2) if _ranking_metric(uc) else round(ratio, 2)
                why = (f"Desequilíbrio extremo (rácio negativos/positivos ≈ {ratio:.0f}). Para ordenar (métrica "
                       f"{uc.metrics.primary if uc else 'de ranking'}) a raiz do rácio ({spw}) costuma ser mais "
                       "estável que o rácio completo." if _ranking_metric(uc) else
                       f"Desequilíbrio extremo: peso dos positivos = rácio negativos/positivos ({spw}).")
            elif imb == "forte":
                spw, why = round(ratio, 2), f"Desequilíbrio forte: peso = rácio negativos/positivos ≈ {ratio:.1f}."
            else:
                spw, why = 1.0, "Desequilíbrio ligeiro/moderado: mantenha 1 e ajuste o limiar de decisão."
            a.set("scale_pos_weight", spw, why)
        else:
            a.set("scale_pos_weight", 1.0, "Só aplicável à classificação binária.")
    # ------------------------------------------------------------------ outros supervisionados
    elif mid == "knn":
        k = int(_clamp(round(math.sqrt(n) / 2), 5, 75))
        if prof.task == "binary_classification" and k % 2 == 0:
            k += 1
        a.set("n_neighbors", k, f"Regra prática k ≈ √n / 2 ({k}); ímpar evita empates em classificação binária.")
        a.set("weights", "distance", "Vizinhos mais próximos pesam mais — previsões mais finas.")
        a.set("p", 1 if p > 20 else 2, "Manhattan é mais robusta com muitas dimensões." if p > 20 else "Distância euclidiana.")
        if n > 50_000:
            a.notes.append(f"KNN com {_fmt(n)} linhas é lento no scoring — prefira modelos de árvores.")
        if p > 30:
            a.notes.append("Muitas variáveis degradam as distâncias (maldição da dimensionalidade).")
    elif mid == "svm":
        a.set("C", 1.0, "Valor de referência; explore 0,1–100 com afinação.")
        a.set("kernel", "linear" if p > 100 else "rbf", "Muitas variáveis: kernel linear." if p > 100 else
              "RBF capta fronteiras não lineares.")
        a.set("gamma", "scale", "Ajusta o alcance do kernel à variância dos dados.")
        class_weight_rule()
        if n > 20_000:
            a.notes.append(f"SVM com {_fmt(n)} linhas pode demorar muito (complexidade ~n²) — use uma amostra ou boosting.")
    elif mid == "naive_bayes":
        a.set("var_smoothing", 1e-9, "Valor padrão; raramente precisa de afinação.")
    elif mid == "mlp":
        arch = "32" if n < 5000 else ("64,32" if n < 50_000 else "128,64")
        a.set("hidden_layer_sizes", arch, f"Arquitetura proporcional ao volume de dados ({_fmt(n)} linhas).")
        a.set("alpha", 0.01 if n < 5000 else 0.001, "Regularização mais forte em bases pequenas." if n < 5000 else "Regularização ligeira.")
        a.set("learning_rate_init", 0.001, "Passo padrão do otimizador Adam.")
        a.set("max_iter", 500, "Épocas máximas; o early stopping pára antes se estabilizar.")
        a.set("early_stopping", True, "Evita overfitting.")
        if n < 5000:
            a.notes.append("Redes neuronais raramente compensam com menos de ~5 000 linhas; compare com boosting.")
    # ------------------------------------------------------------------ séries temporais
    elif mid in ("seasonal_naive", "holt_winters", "sarima", "gbm_lags"):
        season = prof.season_length or 7
        freq = prof.freq or "D"
        if mid == "seasonal_naive":
            a.set("season_length", season, f"Frequência {freq}: o ciclo sazonal dominante tem {season} períodos.")
        elif mid == "holt_winters":
            ts = prof.trend_strength
            ss = prof.seasonal_strength
            a.set("trend", "add" if (ts is None or ts > 0.3) else "none",
                  f"Força da tendência = {ts:.2f}: incluir tendência aditiva." if ts is not None and ts > 0.3 else
                  ("Tendência fraca: modelo só com nível e sazonalidade." if ts is not None else "Tendência aditiva por omissão."))
            a.set("damped_trend", True, "Amortecer a tendência evita extrapolações irrealistas no horizonte.")
            a.set("seasonal", "add" if (ss is None or ss > 0.2) else "none",
                  f"Força da sazonalidade = {ss:.2f}." if ss is not None else "Sazonalidade aditiva por omissão.")
            if prof.has_zeros:
                a.notes.append("A série tem zeros: a sazonalidade multiplicativa não é aplicável.")
            a.set("seasonal_periods", season, f"Ciclo de {season} períodos ({freq}).")
        elif mid == "sarima":
            ts, ss = prof.trend_strength or 0.5, prof.seasonal_strength or 0.5
            a.set("p", 1, "Um termo autorregressivo é um bom ponto de partida.")
            a.set("d", 1 if ts > 0.3 else 0, "Diferenciação para remover a tendência." if ts > 0.3 else "Série sem tendência relevante.")
            a.set("q", 1, "Um termo de médias móveis.")
            a.set("P", 1, "Termo autorregressivo sazonal.")
            a.set("D", 1 if ss > 0.3 else 0, "Diferenciação sazonal remove o padrão repetitivo." if ss > 0.3 else "Sazonalidade fraca.")
            a.set("Q", 1, "Termo MA sazonal.")
            s = season if season <= 52 else 0
            a.set("s", s, f"Período sazonal {s}." if s else "Sazonalidade longa (>52) torna o SARIMA impraticável — use gbm_lags.")
        else:
            lags = {"D": "1,7,14,28,364" if (prof.series_length or 0) > 800 else "1,7,14,28", "W": "1,4,52",
                    "M": "1,2,3,4,12", "H": "1,2,3,7,14,21,28"}.get(freq, "1,7,14,28")
            a.set("lags", lags, f"Lags alinhados com a frequência {freq} e o ciclo de {season} períodos"
                  + (" (inclui o ano anterior: há histórico suficiente)." if "364" in lags else "."))
            a.set("rolling_windows", {"D": "7,28", "W": "4,12", "M": "3,6,12"}.get(freq, "7,28"),
                  "Médias móveis curtas e longas captam o nível recente.")
            rows = (prof.series_length or 500) * (prof.n_series or 1)
            a.set("n_estimators", 400 if rows > 3000 else 250, f"≈ {_fmt(rows)} observações de treino.")
            a.set("learning_rate", 0.05, "Taxa moderada e estável.")
            a.set("num_leaves", 31 if rows > 5000 else 15, "Árvores mais simples com poucas observações." if rows <= 5000 else "Complexidade padrão.")
    # ------------------------------------------------------------------ clustering
    elif mid in ("kmeans", "gaussian_mixture", "agglomerative"):
        k = prof.suggested_k or (5 if uc and uc.id == "segmentacao_clientes" else 4)
        key = "n_components" if mid == "gaussian_mixture" else "n_clusters"
        a.set(key, k, f"k = {k}: sugerido pela silhueta/cotovelo e pela capacidade do negócio de operar 3–7 segmentos."
              if prof.suggested_k else f"k = {k} é um bom ponto de partida para segmentos acionáveis; o agente testa k de 2 a 10.")
        if mid == "kmeans":
            a.set("n_init", 10, "10 inicializações tornam o resultado estável.")
        elif mid == "gaussian_mixture":
            full = n > 50 * p * p
            a.set("covariance_type", "full" if full else "diag", "Dados suficientes para covariâncias completas." if full
                  else "Poucos dados para covariâncias completas: usar diagonais.")
        else:
            a.set("linkage", "ward", "Ward cria segmentos compactos e de tamanho equilibrado.")
            if n > 10_000:
                a.notes.append(f"O clustering hierárquico com {_fmt(n)} linhas é pesado (memória ~n²): o agente usa uma amostra.")
    elif mid == "dbscan":
        a.set("eps", round(prof.dbscan_eps, 3) if prof.dbscan_eps else 0.5,
              "Estimado pela curva de distâncias aos 10 vizinhos (percentil 90)." if prof.dbscan_eps else
              "Valor padrão na escala normalizada; ajuste observando a % de ruído.")
        a.set("min_samples", int(max(5, 2 * min(p, 20))), "Regra prática: 2 × nº de variáveis.")
    # ------------------------------------------------------------------ anomalias
    elif mid in ("isolation_forest", "local_outlier_factor"):
        rate = prof.expected_anomaly_rate or (uc.profile.get("expected_anomaly_rate") if uc else None) or 0.02
        a.set("contamination", round(float(rate), 4), f"≈ {100 * rate:.1f}% de casos sinalizados — alinhe com a "
              "capacidade de revisão da equipa e com a taxa histórica conhecida.")
        if mid == "isolation_forest":
            a.set("n_estimators", 300, "Score estável.")
            a.set("max_samples", "auto", "256 registos por árvore: padrão eficaz.")
            a.set("max_features", 1.0, "Todas as variáveis.")
        else:
            a.set("n_neighbors", int(_clamp(round(math.sqrt(n) / 3), 20, 50)), "Vizinhança suficientemente grande para estimar densidades.")
            if n > 50_000:
                a.notes.append("LOF com muitas linhas é lento — use uma amostra ou Isolation Forest.")
    elif mid == "robust_zscore":
        a.set("threshold", 3.5, "Referência de Iglewicz & Hoaglin para outliers com MAD.")
    elif mid == "apriori":
        n_tx = prof.n_transactions or n
        sup = 0.01 if n_tx < 10_000 else 0.005
        sup = max(sup, round(5 / max(n_tx, 1), 4))
        a.set("min_support", sup, f"Com {_fmt(n_tx)} transações, {100 * sup:.1f}% ≈ {_fmt(sup * n_tx)} talões por combinação.")
        a.set("min_confidence", 0.2, "Regras com pelo menos 20% de probabilidade condicional.")
        a.set("min_lift", 1.2, "Associação pelo menos 20% acima do acaso.")
        a.set("max_len", 2 if (prof.n_items or 0) > 500 else 3, "Regras até 3 itens (2 com catálogos muito grandes).")
    return a


# =============================================================================== API pública
def recommend(model_id: str, profile: DataProfile | dict[str, Any], use_case_id: Optional[str] = None,
              goal: Optional[str] = None) -> dict[str, Any]:
    kb = get_kb()
    model = kb.model(model_id)
    if model is None:
        raise ValueError(f"Modelo desconhecido: {model_id}")
    prof = profile if isinstance(profile, DataProfile) else DataProfile.from_dict(profile)
    uc = kb.use_case(use_case_id)
    g = _goal(goal, uc)
    advice = _rules(model, prof, uc, g)
    details = []
    params: dict[str, Any] = {}
    for hp in model.hyperparameters:
        value = advice.params.get(hp.name, hp.default)
        params[hp.name] = value
        details.append({
            "name": hp.name, "label": hp.label, "type": hp.type, "value": value, "default": hp.default,
            "changed": str(value) != str(hp.default), "reason": advice.reasons.get(hp.name, "Valor padrão da biblioteca."),
            "importance": hp.importance, "description": hp.description, "increase": hp.increase,
            "decrease": hp.decrease, "term": hp.term, "min": hp.min, "max": hp.max, "log": hp.log,
            "choices": hp.choices, "search": search_space_for(hp, value, prof),
        })
    notes = list(advice.notes)
    if uc:
        notes.insert(0, f"Especializado para o caso '{uc.name}' (métrica principal: {uc.metrics.primary}; "
                        f"interpretabilidade: {_interp(uc)}; objetivo: {g}).")
    order = {"alta": 0, "média": 1, "baixa": 2}
    details.sort(key=lambda d: order.get(d["importance"], 3))
    return {"model_id": model.id, "model_name": model.name, "goal": g, "goal_description": GOALS[g],
            "params": params, "details": details, "notes": notes, "profile": prof.to_dict(),
            "assessment": assess(model, params, prof)}


def search_space_for(hp: Any, value: Any, prof: DataProfile) -> dict[str, Any]:
    s = dict(hp.search or {})
    if not s:
        return {}
    if "choices" in s:
        return {"choices": s["choices"]}
    lo, hi = s.get("low"), s.get("high")
    if hp.name in ("num_leaves", "max_leaf_nodes") and prof.n_rows < 5000:
        hi = min(hi, 63)
    if hp.name in ("min_child_samples", "min_samples_leaf") and prof.n_rows < 5000:
        hi = min(hi, max(lo + 1, prof.n_rows // 50))
    return {"low": lo, "high": hi}


def search_space(model_id: str, profile: DataProfile | dict[str, Any], top: int = 6) -> dict[str, dict[str, Any]]:
    """Espaço de pesquisa para afinação (os hiperparâmetros mais importantes)."""
    model = get_kb().model(model_id)
    if model is None:
        return {}
    prof = profile if isinstance(profile, DataProfile) else DataProfile.from_dict(profile)
    out = {}
    for hp in sorted(model.hyperparameters, key=lambda h: {"alta": 0, "média": 1, "baixa": 2}[h.importance]):
        s = search_space_for(hp, hp.default, prof)
        if s:
            out[hp.name] = s
        if len(out) >= top:
            break
    return out


def validate(model_id: str, params: dict[str, Any], profile: DataProfile | dict[str, Any],
             use_case_id: Optional[str] = None) -> dict[str, Any]:
    kb = get_kb()
    model = kb.model(model_id)
    if model is None:
        raise ValueError(f"Modelo desconhecido: {model_id}")
    prof = profile if isinstance(profile, DataProfile) else DataProfile.from_dict(profile)
    uc = kb.use_case(use_case_id)
    issues: list[dict[str, Any]] = []
    norm: dict[str, Any] = {}

    def issue(level: str, param: Optional[str], msg: str, term: Optional[str] = None) -> None:
        issues.append({"level": level, "param": param, "message": msg, "term": term})

    for hp in model.hyperparameters:
        v = params.get(hp.name, hp.default)
        try:
            if v is None:
                norm[hp.name] = None
                continue
            if hp.type == "int":
                fv = float(v)
                if not fv.is_integer():
                    issue("warning", hp.name, f"{hp.label}: deve ser inteiro — arredondado para {round(fv)}.")
                v = int(round(fv))
            elif hp.type == "float":
                v = float(v)
            elif hp.type == "bool":
                v = v if isinstance(v, bool) else str(v).lower() in ("true", "1", "sim")
            else:
                v = str(v)
                if hp.choices and v not in [str(c) for c in hp.choices]:
                    issue("error", hp.name, f"{hp.label}: '{v}' não é válido. Opções: {', '.join(map(str, hp.choices))}.")
        except (TypeError, ValueError):
            issue("error", hp.name, f"{hp.label}: valor '{v}' inválido para o tipo {hp.type}.")
            continue
        if hp.type in ("int", "float") and v is not None:
            if hp.min is not None and v < hp.min:
                issue("error", hp.name, f"{hp.label}: {v} está abaixo do mínimo permitido ({hp.min}).", hp.term)
            if hp.max is not None and v > hp.max:
                issue("error", hp.name, f"{hp.label}: {v} está acima do máximo permitido ({hp.max}).", hp.term)
        norm[hp.name] = v

    n = prof.n_rows
    clf = prof.task in ("binary_classification", "multiclass_classification")
    g = norm.get
    mid = model.id
    if mid in ("lightgbm", "xgboost", "hist_gradient_boosting", "gbm_lags"):
        lr = g("learning_rate") or 0.1
        trees = g("n_estimators") or g("max_iter") or 100
        if lr > 0.3:
            issue("warning", "learning_rate", f"Taxa de aprendizagem {lr} é alta: treino instável e risco de overfitting. "
                  "Valores típicos: 0,01–0,1.", "learning_rate")
        if lr < 0.01 and trees < 1000:
            issue("warning", "n_estimators", f"Taxa muito baixa ({lr}) com apenas {trees} árvores: risco de underfitting. "
                  "Aumente as árvores ou a taxa.", "underfitting")
        cap = lr * trees
        if cap < 5 and mid != "hist_gradient_boosting":
            issue("warning", "n_estimators", f"Capacidade total baixa (taxa × árvores = {cap:.1f}); o modelo pode "
                  "não aprender o suficiente.", "underfitting")
        if cap > 120 and mid != "hist_gradient_boosting":
            issue("info", "n_estimators", f"Capacidade total elevada (taxa × árvores = {cap:.0f}) sem early stopping: "
                  "vigie a diferença treino vs validação.", "overfitting")
    if mid in ("lightgbm", "gbm_lags"):
        leaves = g("num_leaves") or 31
        depth = g("max_depth")
        if depth and depth > 0 and leaves > 2 ** depth:
            issue("warning", "num_leaves", f"num_leaves ({leaves}) > 2^max_depth ({2 ** depth}): as folhas extra nunca "
                  "serão usadas. Reduza o num_leaves ou aumente a profundidade.", "num_leaves")
        if leaves > max(n / 20, 15) and mid == "lightgbm":
            issue("warning", "num_leaves", f"{leaves} folhas para {_fmt(n)} linhas é demasiado complexo: risco de "
                  "overfitting.", "overfitting")
        mcs = g("min_child_samples")
        if mcs is not None and mcs < 5:
            issue("warning", "min_child_samples", "Menos de 5 registos por folha: folhas ajustadas a ruído.", "min_samples_leaf")
    if mid == "xgboost":
        depth = g("max_depth") or 6
        if depth >= 10 and n < 20_000:
            issue("warning", "max_depth", f"Profundidade {depth} com {_fmt(n)} linhas: risco elevado de overfitting.", "max_depth")
        spw = g("scale_pos_weight") or 1.0
        if prof.task == "binary_classification" and prof.positive_rate:
            minority = min(prof.positive_rate, 1 - prof.positive_rate)
            ratio = (1 - minority) / minority
            if prof.imbalance in ("forte", "extremo") and spw == 1.0:
                issue("info", "scale_pos_weight", f"Classes desequilibradas (rácio ≈ {ratio:.0f}): considere "
                      f"scale_pos_weight entre {math.sqrt(ratio):.1f} e {ratio:.0f}.", "scale_pos_weight")
            if spw > 2 * ratio:
                issue("warning", "scale_pos_weight", f"scale_pos_weight ({spw}) é mais do dobro do rácio "
                      f"negativos/positivos ({ratio:.1f}): excesso de falsos positivos.", "scale_pos_weight")
    if mid in ("random_forest", "extra_trees"):
        if (g("n_estimators") or 100) < 100:
            issue("warning", "n_estimators", "Menos de 100 árvores: previsões e importâncias instáveis.", "n_estimators")
        if (g("max_depth") in (0, None)) and (g("min_samples_leaf") or 1) == 1 and n < 2000:
            issue("warning", "min_samples_leaf", "Árvores sem limite e folhas de 1 registo numa base pequena: "
                  "risco de overfitting. Aumente o mínimo por folha (3–10).", "overfitting")
        if str(g("max_features")) == "1.0" and mid == "random_forest":
            issue("info", "max_features", "Com 100% das variáveis por divisão o Random Forest perde diversidade "
                  "(equivale a bagging de árvores).", "max_features")
    if mid == "decision_tree":
        if (g("max_depth") or 0) > 12:
            issue("warning", "max_depth", "Árvore muito profunda: regras ilegíveis e overfitting.", "max_depth")
        if (g("min_samples_leaf") or 1) < 5:
            issue("warning", "min_samples_leaf", "Folhas com menos de 5 registos geram regras frágeis.", "min_samples_leaf")
    if mid == "logistic_regression":
        c = g("C") or 1.0
        if c > 100:
            issue("info", "C", "C muito alto: praticamente sem regularização.", "regularizacao")
        if c < 0.001:
            issue("warning", "C", "C muito baixo: coeficientes quase nulos — risco de underfitting.", "underfitting")
        if g("class_weight") == "balanced" and _regulated(uc):
            issue("warning", "class_weight", "Pesos de classe descalibram probabilidades — problemático quando a "
                  "probabilidade é usada como valor (ex.: PD). Prefira ajustar o limiar.", "calibracao")
    if mid == "knn":
        k = g("n_neighbors") or 5
        if prof.task == "binary_classification" and k % 2 == 0:
            issue("info", "n_neighbors", "k par pode gerar empates na votação; prefira um valor ímpar.")
        if k > n / 10:
            issue("warning", "n_neighbors", "k demasiado grande face à base: previsões excessivamente suaves.", "underfitting")
        if k < 3:
            issue("warning", "n_neighbors", "k < 3 é muito sensível a ruído.", "overfitting")
    if mid == "svm" and n > 20_000:
        issue("warning", None, f"SVM com {_fmt(n)} linhas: treino muito lento.", "svm_termo")
    if mid == "mlp" and n < 5000:
        issue("warning", None, "Rede neuronal com poucos dados: alto risco de overfitting.", "rede_neuronal")
    if clf and "class_weight" in norm and norm.get("class_weight") in ("none", None) and prof.imbalance in ("forte", "extremo") and mid != "xgboost":
        issue("info", "class_weight", f"Desequilíbrio {prof.imbalance}: 'balanced' pode aumentar o recall.", "class_weight")
    if mid in ("kmeans", "gaussian_mixture", "agglomerative"):
        k = g("n_clusters") or g("n_components") or 5
        if k > 8:
            issue("warning", "n_clusters" if "n_clusters" in norm else "n_components",
                  f"{k} segmentos é difícil de operacionalizar pelo negócio (ideal 3–7).", "clustering")
        if prof.suggested_k and abs(k - prof.suggested_k) >= 3:
            issue("info", None, f"A análise de silhueta sugere k = {prof.suggested_k}.", "silhueta")
    if mid == "dbscan":
        eps = g("eps") or 0.5
        if eps > 3:
            issue("warning", "eps", "eps muito alto: tudo tende a cair num único cluster.")
        if eps < 0.1:
            issue("warning", "eps", "eps muito baixo: quase todos os pontos serão ruído.")
    if mid in ("isolation_forest", "local_outlier_factor"):
        c = g("contamination") or 0.02
        exp = prof.expected_anomaly_rate or (uc.profile.get("expected_anomaly_rate") if uc else None)
        if exp and c > 3 * exp:
            issue("warning", "contamination", f"Contaminação ({100 * c:.1f}%) muito acima da taxa esperada "
                  f"({100 * exp:.1f}%): muitos falsos alarmes.", "contaminacao")
        if c > 0.1:
            issue("warning", "contamination", f"Sinalizar {100 * c:.0f}% dos registos sobrecarrega a revisão humana.", "contaminacao")
    if mid == "holt_winters":
        sp = g("seasonal_periods")
        if prof.season_length and sp and sp != prof.season_length:
            issue("warning", "seasonal_periods", f"Período sazonal {sp} difere do detetado nos dados ({prof.season_length}).", "sazonalidade")
        if g("seasonal") == "mul" and prof.has_zeros:
            issue("warning", "seasonal", "Sazonalidade multiplicativa com zeros na série não é suportada (será usada aditiva).")
    if mid == "sarima":
        if (g("d") or 0) + (g("D") or 0) > 2:
            issue("warning", "d", "d + D > 2: sobre-diferenciação degrada a previsão.", "estacionariedade")
        if (g("s") or 0) > 52:
            issue("warning", "s", "Sazonalidade longa torna o SARIMA muito lento.")
        if (g("p") or 0) + (g("q") or 0) > 4:
            issue("warning", "p", "Ordens altas aumentam o risco de overfitting e instabilidade.", "overfitting")
    if mid == "gbm_lags":
        lags = [int(x) for x in str(g("lags") or "1").split(",") if x.strip()]
        if prof.series_length and max(lags) > prof.series_length / 3:
            issue("warning", "lags", f"O maior lag ({max(lags)}) exige muito histórico face ao comprimento da série "
                  f"({prof.series_length}).", "lag")
        if prof.season_length and prof.season_length not in lags:
            issue("info", "lags", f"Inclua o lag {prof.season_length} (ciclo sazonal) para captar a sazonalidade.", "sazonalidade")
    if mid == "apriori":
        n_tx = prof.n_transactions or n
        sup = g("min_support") or 0.01
        if sup * n_tx < 5:
            issue("warning", "min_support", "Suporte mínimo corresponde a menos de 5 transações: regras ao acaso.", "suporte")
        if sup > 0.2:
            issue("info", "min_support", "Suporte alto: poucas regras (só produtos muito populares).", "suporte")
        if (g("min_confidence") or 0.2) < 0.05:
            issue("warning", "min_confidence", "Confiança muito baixa gera regras irrelevantes.", "confianca")

    assessment = assess(model, norm, prof)
    errors = [i for i in issues if i["level"] == "error"]
    return {"model_id": model.id, "valid": not errors, "issues": issues, "params": norm, "assessment": assessment}


def assess(model: ModelSpec, params: dict[str, Any], prof: DataProfile) -> dict[str, Any]:
    """Indicador heurístico de complexidade e risco de overfitting/underfitting (0–100)."""
    n = max(prof.n_rows, 10)
    g = params.get
    fam = model.family
    cap = 0.5
    try:
        if model.id in ("lightgbm", "gbm_lags"):
            leaves = float(g("num_leaves") or 31)
            depth = float(g("max_depth") or -1)
            eff_leaves = min(leaves, 2 ** depth) if depth > 0 else leaves
            total = float(g("learning_rate") or 0.1) * float(g("n_estimators") or 100)
            cap = (math.log2(max(eff_leaves, 2)) / 8) * min(total / 25, 1.6) * (1 - 0.35 * min((g("min_child_samples") or 20) / 200, 1))
            cap *= 1 - 0.15 * min(float(g("reg_lambda") or 0) / 10, 1)
        elif model.id == "xgboost":
            total = float(g("learning_rate") or 0.1) * float(g("n_estimators") or 100)
            cap = (float(g("max_depth") or 6) / 10) * min(total / 25, 1.6) * (1 - 0.3 * min(float(g("min_child_weight") or 1) / 20, 1))
        elif model.id == "hist_gradient_boosting":
            cap = (math.log2(max(float(g("max_leaf_nodes") or 31), 2)) / 8) * (0.7 if str(g("early_stopping")) != "false" else 1.1)
        elif fam == "tree_ensemble":
            depth = g("max_depth") or 0
            cap = (1.0 if depth in (0, None) else min(float(depth) / 20, 1)) * (1 - 0.5 * min(float(g("min_samples_leaf") or 1) / 20, 1)) * 0.8
        elif model.id == "decision_tree":
            cap = min(float(g("max_depth") or 5) / 12, 1) * (1 - 0.5 * min(float(g("min_samples_leaf") or 1) / 50, 1))
        elif model.id == "logistic_regression":
            cap = _clamp((math.log10(max(float(g("C") or 1), 1e-4)) + 4) / 6, 0, 1) * 0.6
        elif model.id in ("ridge", "lasso", "elastic_net"):
            cap = _clamp(1 - (math.log10(max(float(g("alpha") or 1), 1e-5)) + 5) / 7, 0, 1) * 0.5
        elif model.id == "linear_regression":
            cap = 0.35
        elif model.id == "knn":
            cap = _clamp(1 - math.log10(max(float(g("n_neighbors") or 5), 1)) / 2.2, 0, 1)
        elif model.id == "svm":
            cap = _clamp((math.log10(max(float(g("C") or 1), 1e-3)) + 3) / 6, 0, 1)
        elif model.id == "mlp":
            units = sum(int(x) for x in str(g("hidden_layer_sizes") or "64").split(",") if x.strip())
            cap = _clamp(math.log2(units + 1) / 9, 0, 1) * (1 - 0.4 * min(math.log10(float(g("alpha") or 1e-4) * 1e5) / 5, 1))
        elif fam == "clustering":
            k = float(g("n_clusters") or g("n_components") or 5)
            cap = _clamp(k / 12, 0, 1)
        else:
            cap = 0.4
    except (TypeError, ValueError):
        cap = 0.5
    cap = _clamp(cap, 0.0, 1.0)
    support = _clamp((math.log10(n) - 2.5) / 3, 0.05, 1.0)  # 300 linhas → ~0; 300k → 1
    overfit = _clamp(100 * cap * (1.6 - support), 0, 100)
    underfit = _clamp(100 * (1 - cap) * (0.4 + 0.6 * support), 0, 100)

    def level(v: float) -> str:
        return "baixo" if v < 35 else ("médio" if v < 65 else "alto")

    cost_factor = {"boosting": 0.5, "tree_ensemble": 0.6, "kernel": 0.9, "instance": 0.7, "neural": 0.8}.get(fam, 0.2)
    trees = float(g("n_estimators") or g("max_iter") or 100) if fam in ("boosting", "tree_ensemble") else 100
    cost = _clamp(cost_factor * (math.log10(n) / 6) * (0.5 + min(trees / 1000, 1)) * 100, 0, 100)
    return {"complexity": round(100 * cap), "overfit_risk": round(overfit), "overfit_level": level(overfit),
            "underfit_risk": round(underfit), "underfit_level": level(underfit), "training_cost": round(cost),
            "training_cost_level": level(cost),
            "explanation": "Indicador heurístico: combina a capacidade do modelo (hiperparâmetros) com o volume de "
                           "dados. Confirme sempre com a comparação treino vs validação."}


__all__ = ["DataProfile", "GOALS", "assess", "imbalance_level", "recommend", "search_space", "validate"]
