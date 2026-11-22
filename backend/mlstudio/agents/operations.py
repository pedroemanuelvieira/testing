"""Agentes de Governança, Implementação (Power BI), Monitorização, Relatórios e Guia."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional

import numpy as np
import pandas as pd

from ..connectors import ConnectorError
from ..core import agent as B
from ..core.agent import Agent, AgentCard, AgentError, AgentResult, now_iso
from ..core.context import AgentContext
from ..ml import drift as D
from ..ml import timeseries as ts
from ..ml.explain import local_contributions, reasons_text
from ..ml.factory import predict_scores
from ..ml.semantic import humanize
from .common import num, pct, score_label, sensitive_columns
from .evaluation import champion_meta
from .profiling import cramers_v, single_feature_power

PII_NAMES = re.compile(r"(^nome|_nome$|apelido|e-?mail|telefone|telemovel|phone|^nif$|_nif$|contribuinte|iban|morada|"
                       r"endereco|codigo_postal|cod_postal|data_nascimento|nascimento|passaporte|cartao_cidadao|^cc$|"
                       r"num_cc|ip_address|^ip$)", re.I)
EMAIL = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.]+$")
PHONE = re.compile(r"^(\+351)?\s?(9[1236]\d{7}|2\d{8})$")
IBAN = re.compile(r"^PT50\d{21}$", re.I)
POSTAL = re.compile(r"^\d{4}-\d{3}$")

AI_ACT = {
    "alto": ("Sistema de alto risco (AI Act, Anexo III)",
             "Gestão de riscos, governação e qualidade de dados, documentação técnica, registo de eventos (logs), "
             "transparência para utilizadores, supervisão humana efetiva, exatidão/robustez/cibersegurança e "
             "avaliação de conformidade antes da entrada em produção."),
    "limitado": ("Risco limitado",
                 "Obrigações de transparência e boas práticas de documentação, monitorização e supervisão humana."),
    "mínimo": ("Risco mínimo", "Sem obrigações específicas do AI Act; recomenda-se documentação (model card) e "
                               "monitorização como boa prática."),
}


def valid_nif(value: str) -> bool:
    s = re.sub(r"\D", "", str(value))
    if len(s) != 9 or s[0] not in "1235689":
        return False
    total = sum(int(s[i]) * (9 - i) for i in range(8))
    check = 11 - total % 11
    return (0 if check >= 10 else check) == int(s[8])


def detect_pii(df: pd.DataFrame) -> list[dict[str, Any]]:
    out = []
    for c in df.columns:
        reasons = []
        if PII_NAMES.search(c):
            reasons.append("nome da coluna")
        s = df[c].dropna().astype(str).head(300)
        if len(s):
            for label, test in (("emails", lambda v: bool(EMAIL.match(v))), ("telefones", lambda v: bool(PHONE.match(v.replace(" ", "")))),
                                ("IBAN", lambda v: bool(IBAN.match(v.replace(" ", "")))),
                                ("códigos postais", lambda v: bool(POSTAL.match(v))), ("NIF válidos", valid_nif)):
                rate = s.map(test).mean()
                if rate > 0.6:
                    reasons.append(f"{pct(rate)} dos valores parecem {label}")
        if reasons:
            out.append({"coluna": c, "deteccao": "; ".join(reasons)})
    return out


def group_series(s: pd.Series) -> pd.Series:
    """Agrupa uma variável em grupos legíveis (idade em faixas, numéricas em quartis); nulos → 'em falta'."""
    if pd.api.types.is_numeric_dtype(s) and s.nunique() > 8:
        if "idade" in str(s.name).lower():
            out = pd.cut(s, [0, 29, 44, 59, 200], labels=["< 30", "30–44", "45–59", "60+"]).astype(object)
        else:
            out = pd.qcut(s, 4, duplicates="drop").astype(object)
    else:
        out = s.astype(object)
    return out.where(pd.notna(out), "em falta").astype(str)


class GovernanceAgent(Agent):
    card = AgentCard(
        id="governance", name="Agente de Governança & Ética", component="Governança, RGPD e AI Act",
        role="Responsável de ética e conformidade", icon="scale", step="governanca",
        description="Deteta dados pessoais (incluindo NIF com validação de dígito de controlo, IBAN, emails, "
                    "telefones), identifica atributos sensíveis e variáveis proxy, mede a equidade das decisões "
                    "por grupo (paridade, impacto desigual, igualdade de oportunidade), indica o nível de risco no "
                    "AI Act e gera a ficha do modelo (model card).",
        capabilities=["Deteção de PII (RGPD)", "Análise de equidade por grupo", "Deteção de proxies",
                      "Nível de risco AI Act", "Model card automático"],
        inputs=["Dados", "Modelo campeão", "Caso de uso"], outputs=["Relatório de PII", "Equidade", "Model card"],
    )

    def run(self, ctx: AgentContext, result: AgentResult, **_: Any) -> None:
        p, uc = ctx.project, ctx.use_case
        df = ctx.data()
        pii = detect_pii(df)
        used_feats = set()
        meta = None
        try:
            meta = champion_meta(ctx)
            used_feats = set(meta.get("features", []))
        except AgentError:
            pass
        for r in pii:
            r["usada_no_modelo"] = "sim" if r["coluna"] in used_feats else "não"
        result.blocks.append(B.table("Dados pessoais detetados (RGPD)", pii or [{"coluna": "—", "deteccao": "Nenhum dado pessoal direto detetado"}],
                                     [{"key": "coluna", "label": "Coluna"}, {"key": "deteccao", "label": "Deteção"},
                                      {"key": "usada_no_modelo", "label": "Usada no modelo"}],
                                     terms=["dados_pessoais", "rgpd", "pseudonimizacao"]))
        for r in pii:
            if r.get("usada_no_modelo") == "sim":
                result.critical(f"Dado pessoal usado como variável: {r['coluna']}", "Remova-o ou pseudonimize-o — não "
                                "deve ser necessário para prever.", ["dados_pessoais"])
        sens = sensitive_columns(ctx, df)
        risk = uc.ai_act_risk if uc else "mínimo"
        title, obligations = AI_ACT.get(risk, AI_ACT["mínimo"])
        result.blocks.append(B.callout("critical" if risk == "alto" else "warning" if risk == "limitado" else "info",
                                       f"AI Act — {title}", obligations, ["ai_act", "human_in_the_loop"]))
        used_sens = [c for c in sens if c in used_feats]
        if used_sens:
            msg = ", ".join(used_sens)
            (result.critical if risk == "alto" else result.warn)(
                "Atributos sensíveis usados como variáveis", f"{msg}. Em sistemas de alto risco evite-os e audite a equidade.",
                ["atributo_sensivel", "fairness"])
        # proxies
        proxies = []
        if meta and meta.get("kind") == "supervised":
            for s in sens:
                for f in [x for x in meta["features"] if x != s and x in df.columns][:40]:
                    try:
                        keep = df[s].notna() & ~df[s].astype(str).str.upper().isin(["N/A", "NA", "NAN", "", "EM FALTA"])
                        tgt = df.loc[keep, s]
                        if tgt.nunique() < 2:
                            continue
                        if pd.api.types.is_numeric_dtype(tgt) and tgt.nunique() > 8:
                            if pd.api.types.is_numeric_dtype(df[f]):
                                v = abs(df.loc[keep, [s, f]].astype(float).corr(method="spearman").iloc[0, 1])
                            else:
                                v = single_feature_power(df.loc[keep, f].astype(str), tgt.astype(float), "regression")
                        else:
                            fx = df.loc[keep, f]
                            v = cramers_v(group_series(fx) if pd.api.types.is_numeric_dtype(fx) else fx, tgt)
                    except Exception:  # noqa: BLE001
                        continue
                    if v and v > 0.5:
                        proxies.append({"atributo_sensivel": s, "variavel": f, "associacao": float(v)})
        if proxies:
            result.blocks.append(B.table("Possíveis variáveis proxy", sorted(proxies, key=lambda r: -r["associacao"])[:15],
                                         [{"key": "atributo_sensivel", "label": "Atributo sensível"}, {"key": "variavel", "label": "Variável"},
                                          {"key": "associacao", "label": "Associação", "fmt": "num"}],
                                         terms=["proxy_discriminacao"]))
            result.warn("Variáveis proxy de atributos sensíveis", "Podem reproduzir discriminação mesmo sem usar o "
                        "atributo diretamente.", ["proxy_discriminacao"])
        # equidade
        fairness_rows = []
        if meta and meta.get("kind") == "supervised":
            hold = ctx.registry.holdout(meta["id"])
            task = meta["problem_type"]
            for s in [c for c in sens if c in hold.columns]:
                g = group_series(hold[s])
                if task == "binary_classification":
                    thr = meta.get("threshold") or 0.5
                    pred = (hold["__p__"] >= thr).astype(int)
                    y = hold["__y__"].astype(int)
                    for val in sorted(g.unique()):
                        m = (g == val).values
                        if m.sum() < 30:
                            continue
                        pos = y[m] == 1
                        fairness_rows.append({"atributo": s, "grupo": val, "n": int(m.sum()), "taxa_decisao_positiva": float(pred[m].mean()),
                                              "recall": float(pred[m][pos].mean()) if pos.sum() else None,
                                              "fpr": float(pred[m][~pos].mean()) if (~pos).sum() else None,
                                              "taxa_real": float(y[m].mean())})
                elif task == "regression":
                    for val in sorted(g.unique()):
                        m = (g == val).values
                        if m.sum() < 30:
                            continue
                        fairness_rows.append({"atributo": s, "grupo": val, "n": int(m.sum()),
                                              "media_prevista": float(hold["__pred__"][m].mean()),
                                              "media_real": float(hold["__y__"][m].mean()),
                                              "mae": float(np.mean(np.abs(hold["__pred__"][m] - hold["__y__"][m])))})
            if fairness_rows:
                group_cols = [{"key": "atributo", "label": "Atributo"}, {"key": "grupo", "label": "Grupo"}, {"key": "n", "label": "Casos", "fmt": "int"}]
                if "taxa_decisao_positiva" in fairness_rows[0]:
                    group_cols += [{"key": "taxa_decisao_positiva", "label": "Taxa de decisão positiva", "fmt": "pct"},
                                   {"key": "recall", "label": "Recall (TPR)", "fmt": "pct"}, {"key": "fpr", "label": "Taxa de falsos positivos", "fmt": "pct"},
                                   {"key": "taxa_real", "label": "Taxa real", "fmt": "pct"}]
                else:
                    group_cols += [{"key": "media_prevista", "label": "Média prevista", "fmt": "num"},
                                   {"key": "media_real", "label": "Média real", "fmt": "num"}, {"key": "mae", "label": "MAE", "fmt": "num"}]
                result.blocks.append(B.table("Métricas por grupo", fairness_rows, group_cols,
                                             terms=["fairness", "paridade_demografica", "igualdade_oportunidade"]))
                fr = pd.DataFrame(fairness_rows)
                summary_rows = []
                for s, gdf in fr.groupby("atributo"):
                    if "taxa_decisao_positiva" in gdf:
                        rates = gdf["taxa_decisao_positiva"]
                        di = float(rates.min() / rates.max()) if rates.max() > 0 else 1.0
                        dp = float(rates.max() - rates.min())
                        eo = float(gdf["recall"].max() - gdf["recall"].min()) if gdf["recall"].notna().any() else None
                        summary_rows.append({"atributo": s, "impacto_desigual": di, "dif_paridade": dp, "dif_igualdade_oportunidade": eo})
                        if di < 0.8:
                            result.warn(f"Impacto desigual em '{s}'", f"Rácio {num(di)} < 0,8 (regra dos 4/5). Note que as taxas "
                                        "reais também podem diferir — analise as causas antes de corrigir.", ["impacto_desigual"])
                        else:
                            result.success(f"Sem impacto desigual relevante em '{s}'", f"Rácio {num(di)}.", ["impacto_desigual"])
                if summary_rows:
                    result.blocks.append(B.table("Resumo de equidade", summary_rows, [
                        {"key": "atributo", "label": "Atributo"}, {"key": "impacto_desigual", "label": "Impacto desigual (≥ 0,8)", "fmt": "num"},
                        {"key": "dif_paridade", "label": "Dif. paridade demográfica", "fmt": "pct"},
                        {"key": "dif_igualdade_oportunidade", "label": "Dif. igualdade de oportunidade", "fmt": "pct"}],
                        terms=["impacto_desigual", "paridade_demografica", "igualdade_oportunidade"]))
        elif not sens:
            result.info("Sem atributos sensíveis identificados", "Não há colunas como género, idade ou nacionalidade nos dados.")
        # model card
        card_md = self.model_card(ctx, meta, pii, sens, fairness_rows, risk)
        if meta:
            ctx.registry.update(meta["id"], model_card=card_md, governance={"pii": pii, "sensitive": sens, "ai_act_risk": risk,
                                                                          "reviewed_at": now_iso()})
        folder = ctx.settings.exports_dir / p.id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "model_card.md").write_text(card_md, encoding="utf-8")
        result.blocks.append(B.markdown(card_md, "Ficha do modelo (model card)"))
        result.blocks.append(B.download("Documentação", [{"label": "model_card.md", "path": f"{p.id}/model_card.md"}]))
        if risk == "alto":
            result.recommendations.append("Garanta supervisão humana: o modelo prioriza, uma pessoa decide.")
            result.recommendations.append("Envolva o DPO e a área de Compliance antes da implementação.")
        result.summary = (f"Risco AI Act: {risk}. {len(pii)} coluna(s) com dados pessoais; {len(sens)} atributo(s) sensível(eis)"
                          + (f"; {len(proxies)} possível(eis) proxy." if proxies else "."))
        result.outputs = {"pii": pii, "sensitive": sens, "ai_act_risk": risk, "fairness": fairness_rows, "proxies": proxies}
        result.terms = ["rgpd", "ai_act", "fairness", "model_card", "dados_pessoais"]
        result.next_step = "implementacao"

    def model_card(self, ctx: AgentContext, meta: Optional[dict], pii: list, sens: list, fairness: list, risk: str) -> str:
        p, uc = ctx.project, ctx.use_case
        lines = [f"# Ficha do modelo — {p.name}", "",
                 f"**Gerada em:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
                 f"**Caso de uso:** {uc.name if uc else 'personalizado'}  ",
                 f"**Tipo de problema:** {ctx.problem.name}  ",
                 f"**Nível de risco (AI Act):** {risk}", "", "## Objetivo e uso pretendido",
                 (uc.business_question if uc else p.description or "—"), "",
                 f"**Decisão suportada:** {uc.decision if uc else '—'}", "", "## Dados",
                 f"- Fonte: {p.data_info.get('connector', '—')} — {p.source.table if p.source else '—'}",
                 f"- Linhas: {p.data_info.get('rows', '—')}; extração: {p.data_info.get('loaded_at', '—')}",
                 f"- Alvo: `{p.target or '—'}`", f"- Colunas excluídas: {', '.join(p.excluded_columns) or '—'}", ""]
        if meta:
            lines += ["## Modelo", f"- Algoritmo: **{meta.get('model_name')}** (versão `{meta['id']}`)",
                      f"- Estado: {meta.get('stage')}", f"- Divisão: {meta.get('split', '—')}",
                      f"- Hiperparâmetros: `{meta.get('params')}`", ""]
            mt = meta.get("metrics_test", {})
            base = meta.get("baseline_metrics", {})
            if mt:
                lines += ["## Desempenho (conjunto de teste)", "| Métrica | Modelo | Baseline |", "|---|---|---|"]
                for k, v in list(mt.items())[:10]:
                    if isinstance(v, (int, float)):
                        b = base.get(k)
                        lines.append(f"| {k} | {v:.4f} | {b:.4f} |" if isinstance(b, (int, float)) else f"| {k} | {v:.4f} | — |")
                lines.append("")
            if meta.get("threshold") is not None:
                lines += [f"**Limiar de decisão:** {num(meta['threshold'])} — {meta.get('threshold_reason', '')}", ""]
        lines += ["## Dados pessoais e atributos sensíveis",
                  f"- Dados pessoais detetados: {', '.join(r['coluna'] for r in pii) or 'nenhum'}",
                  f"- Atributos sensíveis: {', '.join(sens) or 'nenhum'}", ""]
        if fairness:
            lines += ["## Equidade", "Ver tabela de métricas por grupo na plataforma. Critério: impacto desigual ≥ 0,8.", ""]
        lines += ["## Limitações e riscos"] + [f"- {x}" for x in (uc.pitfalls if uc else [])] + [
            "- O modelo reflete padrões históricos e pode degradar-se com mudanças de contexto (monitorizar drift).",
            "- Importância de variáveis não implica causalidade.", "",
            "## Supervisão humana",
            "As previsões apoiam a decisão; a decisão final é tomada por uma pessoa responsável." if risk != "mínimo"
            else "Recomenda-se revisão periódica dos resultados pelo dono de negócio.", ""]
        if meta and meta.get("libraries"):
            lines += ["## Ambiente", ", ".join(f"{k} {v}" for k, v in meta["libraries"].items())]
        return "\n".join(lines)


# =============================================================================== IMPLEMENTAÇÃO
def _slug(text: str) -> str:
    import unicodedata

    t = unicodedata.normalize("NFKD", text)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^\w]+", "_", t).strip("_")[:40] or "previsoes"


def score_frame(ctx: AgentContext, meta: dict, df: pd.DataFrame, reasons: bool = True,
                max_reason_rows: int = 20_000) -> pd.DataFrame:
    """Aplica um modelo registado a um DataFrame com as colunas originais."""
    kind = meta.get("kind")
    version = meta["id"]
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    ids = [c for c in meta.get("id_columns", []) if c in df.columns]
    out = df[ids].copy() if ids else pd.DataFrame(index=df.index)
    if kind == "supervised":
        pipe = ctx.registry.load(version)
        feats = meta["features"]
        missing = [f for f in feats if f not in df.columns]
        if missing:
            raise AgentError(f"Faltam colunas para o scoring: {', '.join(missing[:8])}")
        X = df[feats]
        task = meta["problem_type"]
        if task == "binary_classification":
            p = predict_scores(pipe, X, task)
            thr = meta.get("threshold") or 0.5
            out["probabilidade"] = np.round(p, 4)
            out["banda_risco"] = np.where(p >= thr, "Alto", np.where(p >= 0.6 * thr, "Médio", "Baixo"))
            out["decisao"] = np.where(p >= thr, "Agir", "Monitorizar")
            label = score_label(ctx)
            target_score = p
        elif task == "multiclass_classification":
            proba = pipe.predict_proba(X)
            classes = meta["classes"]
            out["classe_prevista"] = [classes[i] for i in np.argmax(proba, axis=1)]
            out["probabilidade"] = np.round(np.max(proba, axis=1), 4)
            label, target_score = "probabilidade", np.max(proba, axis=1)
        else:
            pred = pipe.predict(X)
            out["valor_previsto"] = np.round(pred, 4)
            out["decil"] = pd.qcut(pd.Series(pred, index=df.index).rank(method="first"), 10, labels=False) + 1
            label, target_score = "valor", pred
        if reasons:
            order = np.argsort(-np.asarray(target_score))[:max_reason_rows]
            rows = X.iloc[order]
            try:  # referência = conjunto de teste do treino (funciona mesmo com 1 linha a pontuar)
                hold = ctx.registry.holdout(version)
                bg = hold[[f for f in feats if f in hold.columns]].sample(min(800, len(hold)), random_state=1)
            except KeyError:
                bg = X.sample(min(800, len(X)), random_state=1)
            pf = (lambda d: predict_scores(pipe, d, task)) if task != "multiclass_classification" else (lambda d: np.max(pipe.predict_proba(d), axis=1))
            contribs = local_contributions(pf, rows, bg, top_k=3)
            texts = pd.Series("", index=df.index, dtype=object)
            texts.iloc[order] = [reasons_text(c, label) for c in contribs]
            out["principais_motivos"] = texts.values
    elif kind == "clustering":
        assigner = ctx.registry.load(version)
        labels = assigner.predict(df)
        names = meta.get("segment_names", {})
        out["segmento"] = labels
        out["nome_segmento"] = [names.get(str(l), str(l)) for l in labels]
        dist = assigner.distance(df)
        if dist is not None:
            out["distancia_centro"] = np.round(dist, 4)
    elif kind == "anomaly":
        det = ctx.registry.load(version)
        scores = det.score(df)
        out["score_anomalia"] = np.round(scores, 5)
        out["e_anomalia"] = scores >= det.threshold_
        flagged = np.where(out["e_anomalia"].values)[0][:5000]
        mot = pd.Series("", index=df.index, dtype=object)
        if len(flagged):
            rs = det.reasons(df.iloc[flagged])
            mot.iloc[flagged] = ["; ".join(f"{humanize(x['variavel'])} (z={x['z']:+.1f})" for x in r) for r in rs]
        out["motivos"] = mot.values
    else:
        raise AgentError(f"Scoring não aplicável a modelos do tipo '{kind}'.")
    out["versao_modelo"] = version
    out["data_scoring"] = stamp
    return out.reset_index(drop=True)


class DeploymentAgent(Agent):
    card = AgentCard(
        id="deployment", name="Agente de Implementação (Power BI)", component="Implementação / MLOps",
        role="Engenheiro de MLOps BI", icon="rocket", step="implementacao",
        description="Promove o modelo a produção, extrai a população atual do Power BI, gera previsões com bandas "
                    "de risco e motivos, publica a tabela no Power BI (através do conector) ou em ficheiros, e "
                    "entrega as medidas DAX, os visuais recomendados e o exemplo de chamada à API.",
        capabilities=["Promoção champion → produção", "Scoring em lote com motivos", "Escrita no Power BI",
                      "Exportação CSV/Excel/Parquet", "Medidas DAX e visuais", "Endpoint REST"],
        inputs=["Modelo", "Fonte de dados atual"], outputs=["Tabela de previsões", "Medidas DAX", "Ficheiros"],
        params=[{"name": "publish", "label": "Publicar", "type": "choice", "choices": ["export", "powerbi", "both"]},
                {"name": "promote", "label": "Promover a produção", "type": "bool"}],
    )

    def run(self, ctx: AgentContext, result: AgentResult, version_id: Optional[str] = None, publish: str = "both",
            promote: bool = True, fresh: bool = True, **_: Any) -> None:
        p, uc = ctx.project, ctx.use_case
        meta = champion_meta(ctx, version_id or p.production_version_id)
        if promote and meta.get("stage") != "produção":
            meta = ctx.registry.promote(meta["id"])
            ctx.save_project(production_version_id=meta["id"])
            result.success("Modelo promovido a produção", f"{meta['model_name']} ({meta['id']}).", ["champion_challenger"])
        kind = meta.get("kind")
        ctx.progress(0.1, "A obter a população atual…")
        df, origin = self._current_data(ctx, fresh)
        ctx.progress(0.3, "A gerar previsões…")
        if kind == "forecast":
            out = self._forecast(ctx, meta, df)
        elif kind == "association":
            out = ctx.registry.artifact(meta["id"], "rules")
            out["versao_modelo"] = meta["id"]
        else:
            out = score_frame(ctx, meta, df)
        table = (uc.powerbi_output.table if uc and uc.powerbi_output else f"Previsoes_{_slug(p.name)}")
        ctx.progress(0.75, "A publicar resultados…")
        files = []
        if publish in ("export", "both"):
            folder = ctx.settings.exports_dir / p.id
            folder.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base = f"{table}_{stamp}"
            out.to_csv(folder / f"{base}.csv", index=False, sep=";", decimal=",", encoding="utf-8-sig")
            out.to_parquet(folder / f"{base}.parquet", index=False)
            files += [{"label": f"{base}.csv (Excel PT: ; e ,)", "path": f"{p.id}/{base}.csv"},
                      {"label": f"{base}.parquet", "path": f"{p.id}/{base}.parquet"}]
            if len(out) <= 100_000:
                out.to_excel(folder / f"{base}.xlsx", index=False)
                files.append({"label": f"{base}.xlsx", "path": f"{p.id}/{base}.xlsx"})
        pbi = None
        if publish in ("powerbi", "both") and p.source:
            try:
                conn = ctx.hub.get(p.source.connector_id)
                if "write" in conn.capabilities:
                    pbi = conn.write_table(p.source.workspace_id, "Resultados ML", table, out, mode="replace")
                    result.success("Tabela publicada no Power BI", pbi.get("message", ""), ["push_dataset"])
                else:
                    result.info("Conector sem escrita", f"O conector '{conn.name}' não escreve no Power BI — use os ficheiros exportados "
                                "num dataflow/lakehouse.", ["push_dataset"])
            except ConnectorError as exc:
                result.warn("Falha a publicar no Power BI", str(exc))
        ctx.registry.update(meta["id"], last_scoring={"at": now_iso(), "rows": len(out), "table": table, "origin": origin,
                                                      "published": bool(pbi), "files": files})
        result.blocks.append(B.kpis([
            B.kpi("Registos pontuados", len(out), "int", origin, "scoring_batch"),
            B.kpi("Tabela", table, "text", "Modelo semântico 'Resultados ML'" if pbi else "Ficheiros exportados", "push_dataset"),
            B.kpi("Versão", meta["id"], "text", meta.get("stage", ""), "versionamento"),
            *([B.kpi("Casos de risco alto", int((out["banda_risco"] == "Alto").sum()), "int",
                     pct((out["banda_risco"] == "Alto").mean()), "limiar_decisao")] if "banda_risco" in out else []),
        ], "Implementação"))
        if "banda_risco" in out:
            vc = out["banda_risco"].value_counts().reindex(["Alto", "Médio", "Baixo"]).fillna(0)
            result.blocks.append(B.chart("bar", "Distribuição por banda de risco", [{"banda": k, "n": int(v)} for k, v in vc.items()],
                                         x="banda", y="n"))
        result.blocks.append(B.table(f"Pré-visualização — {table}", out.head(25)))
        if files:
            result.blocks.append(B.download("Ficheiros para o Power BI", files))
        measures = list(uc.powerbi_output.measures) if uc and uc.powerbi_output else []
        dax_text = "\n\n".join(f"-- {m.name}\n{m.dax}" for m in measures)
        dax_text += (f"\n\n-- Registos pontuados\nRegistos Pontuados = COUNTROWS({table})"
                     f"\n\n-- Última atualização do modelo\nÚltimo Scoring = MAX({table}[data_scoring])")
        result.blocks.append(B.code("dax", dax_text.strip(), "Medidas DAX sugeridas",
                                    f"Relacione {table} com a dimensão pelo identificador ({', '.join(meta.get('id_columns', [])) or 'chave'})."))
        if uc and uc.powerbi_output:
            result.blocks.append(B.markdown("\n".join(f"- {v}" for v in uc.powerbi_output.visuals), "Visuais recomendados no relatório"))
        if kind == "supervised":
            feats = meta["features"][:6]
            example = {f: (None if f not in df.columns else df[f].iloc[0]) for f in feats}
            snippet = ("import requests\n\nresp = requests.post(\n"
                       f"    \"http://<servidor>/api/models/{meta['id']}/predict\",\n"
                       f"    json={{\"rows\": [{B.jsonable(example)} ]}},  # inclua todas as colunas do modelo\n"
                       "    timeout=30,\n)\nprint(resp.json())")
            result.blocks.append(B.code("python", snippet, "Scoring online (API REST)", "Para decisões em tempo real (ex.: fraude)."))
        result.recommendations += [
            "Agende o scoring com a mesma periodicidade da atualização do modelo semântico.",
            "Acompanhe as previsões com o Agente de Monitorização (drift e desempenho real).",
        ]
        result.summary = f"{len(out):,} registos pontuados com {meta['model_name']} e publicados como '{table}'.".replace(",", " ")
        result.outputs = {"table": table, "rows": len(out), "files": files, "powerbi": pbi, "version_id": meta["id"]}
        result.terms = ["scoring_batch", "push_dataset", "medida_dax", "registo_modelos"]
        result.next_step = "monitorizacao"

    def _current_data(self, ctx: AgentContext, fresh: bool) -> tuple[pd.DataFrame, str]:
        p = ctx.project
        if fresh and p.source and p.source.table:
            try:
                conn = ctx.hub.get(p.source.connector_id)
                df = conn.read_table(p.source.workspace_id, p.source.dataset_id, p.source.table, columns=p.source.columns)
                return df, f"extraído agora de {conn.name}"
            except (ConnectorError, AgentError):
                pass
        return ctx.data(), "snapshot do projeto"

    def _forecast(self, ctx: AgentContext, meta: dict, df: pd.DataFrame) -> pd.DataFrame:
        long, info = ts.prepare_series(df, meta["time_column"], meta.get("value_column"), meta.get("aggregation", "sum"),
                                       meta.get("series_columns"), meta.get("freq"))
        fc = ts.forecast(meta["model_id"], meta["params"], long, int(meta["horizon"]), info["freq"], info["season"])
        try:
            lo, hi = ts.intervals(ctx.registry.artifact(meta["id"], "backtest"), meta["model_id"], int(meta["horizon"]))
        except KeyError:
            lo = hi = np.zeros(int(meta["horizon"]))
        fc["passo"] = fc.groupby("serie").cumcount() + 1
        fc["limite_inferior"] = (fc["yhat"] * (1 + lo[fc["passo"] - 1])).clip(lower=0)
        fc["limite_superior"] = fc["yhat"] * (1 + hi[fc["passo"] - 1])
        out = fc.rename(columns={"ds": "data", "yhat": "previsao"})[["serie", "data", "previsao", "limite_inferior", "limite_superior"]]
        out["modelo"] = meta["model_name"]
        out["versao_modelo"] = meta["id"]
        out["data_scoring"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        return out


# =============================================================================== MONITORIZAÇÃO
class MonitoringAgent(Agent):
    card = AgentCard(
        id="monitoring", name="Agente de Monitorização", component="Monitorização e re-treino",
        role="Guardião do modelo em produção", icon="activity", step="monitorizacao",
        description="Compara os dados atuais com os de treino (PSI, KS, qui-quadrado), mede o drift das previsões "
                    "e, quando o resultado real já é conhecido, o desempenho atual. Classifica o estado "
                    "(estável/atenção/crítico) e recomenda re-treino. Permite simular drift para formação.",
        capabilities=["PSI por variável", "Testes KS / χ²", "Drift das previsões", "Desempenho real",
                      "Histórico e recomendação de re-treino", "Simulação de drift"],
        inputs=["Modelo em produção", "Dados atuais"], outputs=["Relatório de drift", "Estado do modelo"],
        params=[{"name": "simulate_drift", "label": "Simular drift (formação)", "type": "bool"}],
    )

    def run(self, ctx: AgentContext, result: AgentResult, version_id: Optional[str] = None, simulate_drift: bool = False,
            fresh: bool = True, **_: Any) -> None:
        p = ctx.project
        meta = champion_meta(ctx, version_id or p.production_version_id)
        df, origin = DeploymentAgent()._current_data(ctx, fresh)
        if meta.get("kind") == "forecast":
            return self._forecast(ctx, result, meta, df)
        ref = meta.get("reference_stats")
        feats = meta.get("features", [])
        if not ref:
            sample_src = ctx.data()
            ref = D.reference_stats(sample_src, [f for f in feats if f in sample_src.columns])
        if simulate_drift:
            df = self._simulate(df, feats)
            origin += " + drift simulado"
            result.info("Drift simulado", "Foram deslocadas 3 variáveis numéricas e alterada uma distribuição categórica "
                        "para demonstração.", ["drift_dados"])
        comp = D.compare(ref, df)
        max_psi = float(comp["psi"].max()) if len(comp) else 0.0
        n_sig = int((comp["psi"] > 0.25).sum())
        n_mod = int(((comp["psi"] > 0.1) & (comp["psi"] <= 0.25)).sum())
        perf_now, perf_ref, pred_psi = None, None, None
        if meta.get("kind") == "supervised":
            pipe = ctx.registry.load(meta["id"])
            task = meta["problem_type"]
            X = df[[f for f in feats if f in df.columns]]
            if len(X.columns) == len(feats):
                scores = predict_scores(pipe, X, task) if task != "multiclass_classification" else None
                sr = meta.get("score_ref")
                if scores is not None and sr:
                    pred_psi = D.psi(np.array(sr["props"]), D.score_distribution(scores, np.array(sr["edges"])))
                tgt = meta.get("target")
                if tgt in df.columns and scores is not None:
                    y = df[tgt]
                    if task == "binary_classification":
                        yb = (y.astype(str) == str(meta.get("positive_class"))).astype(int)
                        if yb.nunique() == 2:
                            from sklearn.metrics import roc_auc_score

                            perf_now = float(roc_auc_score(yb, scores))
                            perf_ref = meta.get("metrics_test", {}).get("roc_auc")
                    elif task == "regression":
                        perf_now = float(np.mean(np.abs(pd.to_numeric(y, errors="coerce") - scores)))
                        perf_ref = meta.get("metrics_test", {}).get("mae")
        degraded = False
        if perf_now is not None and perf_ref:
            if meta["problem_type"] == "binary_classification":
                degraded = perf_now < perf_ref - 0.03
            else:
                degraded = perf_now > perf_ref * 1.10
        status = "crítico" if (n_sig >= 2 or degraded or (pred_psi or 0) > 0.25) else (
            "atenção" if (n_sig or n_mod or (pred_psi or 0) > 0.1) else "estável")
        history = list(meta.get("monitoring", []))
        history.append({"data": now_iso(), "estado": status, "max_psi": max_psi, "psi_previsoes": pred_psi,
                        "desempenho": perf_now, "origem": origin})
        ctx.registry.update(meta["id"], monitoring=history[-50:])
        result.blocks.append(B.kpis([
            B.kpi("Estado", status, "status", origin, "monitorizacao_termo",
                  {"estável": "ok", "atenção": "warning", "crítico": "critical"}[status]),
            B.kpi("PSI máximo", max_psi, "num", "< 0,1 estável · > 0,25 significativo", "psi"),
            B.kpi("Variáveis com drift significativo", n_sig, "int", f"{n_mod} moderado", "drift_dados"),
            B.kpi("PSI das previsões", pred_psi, "num", "", "psi"),
            *([B.kpi("Desempenho atual", perf_now, "num", f"no treino: {num(perf_ref or np.nan, 3)}", "concept_drift")]
              if perf_now is not None else []),
        ], "Saúde do modelo"))
        result.blocks.append(B.chart("bar", "PSI por variável", comp.head(20)[["variavel", "psi"]].fillna(0), x="variavel", y="psi",
                                     horizontal=True, thresholds=[0.1, 0.25], terms=["psi"]))
        result.blocks.append(B.table("Detalhe do drift", comp, [
            {"key": "variavel", "label": "Variável"}, {"key": "tipo", "label": "Tipo"}, {"key": "psi", "label": "PSI", "fmt": "num"},
            {"key": "nivel", "label": "Nível", "fmt": "badge"}, {"key": "teste", "label": "Teste"},
            {"key": "p_value", "label": "p-value", "fmt": "num"}, {"key": "detalhe", "label": "Detalhe"}],
            terms=["psi", "teste_ks", "qui_quadrado"]))
        top = comp.dropna(subset=["psi"]).head(1)
        if len(top) and top.iloc[0]["variavel"] in ref and ref[top.iloc[0]["variavel"]]["kind"] == "numeric":
            v = top.iloc[0]["variavel"]
            r = ref[v]
            edges = np.array(r["edges"])
            cur = D.score_distribution(pd.to_numeric(df[v], errors="coerce").dropna().values, edges)
            result.blocks.append(B.chart("bar", f"Distribuição de {humanize(v)}: treino vs atual",
                                         [{"intervalo": f"{edges[i]:.3g}–{edges[i + 1]:.3g}", "treino": r["props"][i], "atual": float(cur[i])}
                                          for i in range(len(r["props"]))], x="intervalo", y=["treino", "atual"], fmt="pct"))
        if len(history) > 1:
            result.blocks.append(B.chart("line", "Histórico de monitorização", [{"execucao": i + 1, "max_psi": h["max_psi"]}
                                                                                for i, h in enumerate(history)],
                                         x="execucao", y="max_psi", thresholds=[0.1, 0.25]))
        if status == "crítico":
            result.critical("Re-treino recomendado", "Drift significativo ou degradação de desempenho. Re-treine e compare "
                            "champion vs challenger.", ["retreino", "champion_challenger"])
        elif status == "atenção":
            result.warn("Vigiar de perto", "Há alterações moderadas nas distribuições.", ["drift_dados"])
        else:
            result.success("Modelo estável", "As distribuições mantêm-se próximas das do treino.")
        result.summary = f"Estado: {status}. PSI máximo {num(max_psi)}; {n_sig} variável(eis) com drift significativo."
        result.outputs = {"status": status, "max_psi": max_psi, "prediction_psi": pred_psi, "performance": perf_now}
        result.terms = ["drift_dados", "psi", "concept_drift", "retreino"]
        result.next_step = None

    @staticmethod
    def _simulate(df: pd.DataFrame, feats: list[str]) -> pd.DataFrame:
        rng = np.random.default_rng(7)
        out = df.copy()
        nums = [f for f in feats if f in out.columns and pd.api.types.is_numeric_dtype(out[f]) and out[f].nunique() > 10][:3]
        for f in nums:
            out[f] = out[f] + 0.6 * out[f].std() + rng.normal(0, 0.1 * out[f].std(), len(out))
        cats = [f for f in feats if f in out.columns and not pd.api.types.is_numeric_dtype(out[f])][:1]
        for f in cats:
            top = out[f].value_counts().index
            if len(top) > 1:
                mask = rng.random(len(out)) < 0.35
                out.loc[mask, f] = top[-1]
        return out

    def _forecast(self, ctx: AgentContext, result: AgentResult, meta: dict, df: pd.DataFrame) -> None:
        long, _ = ts.prepare_series(df, meta["time_column"], meta.get("value_column"), meta.get("aggregation", "sum"),
                                    meta.get("series_columns"), meta.get("freq"))
        fc = ctx.registry.artifact(meta["id"], "forecast").rename(columns={"data": "ds"})
        merged = long.merge(fc, on=["serie", "ds"], how="inner")
        if merged.empty:
            result.info("Ainda sem valores reais para o período previsto",
                        "Volte a executar quando o modelo semântico tiver dados do horizonte de previsão.", ["horizonte_previsao"])
            result.summary = "A aguardar dados reais do horizonte de previsão."
            result.outputs = {"status": "a aguardar"}
            return
        w = float(np.sum(np.abs(merged["y"] - merged["previsao"])) / max(np.sum(np.abs(merged["y"])), 1e-9))
        ref = meta.get("metrics_test", {}).get("wape")
        status = "crítico" if ref and w > ref * 1.5 else ("atenção" if ref and w > ref * 1.15 else "estável")
        result.blocks.append(B.kpis([B.kpi("WAPE realizado", w, "pct", f"backtesting: {pct(ref or 0)}", "wape"),
                                     B.kpi("Estado", status, "status")]))
        result.summary = f"WAPE realizado {pct(w)} ({status})."
        result.outputs = {"status": status, "wape": w}


# =============================================================================== RELATÓRIOS
class ReportingAgent(Agent):
    card = AgentCard(
        id="reporting", name="Agente de Relatórios", component="Comunicação de resultados",
        role="Storyteller de dados", icon="file-text", step=None,
        description="Compila o projeto num relatório executivo (Markdown e HTML) com o problema, os dados, a "
                    "qualidade, o modelo, o desempenho em linguagem de negócio, os drivers, os riscos e os próximos "
                    "passos — pronto a partilhar com stakeholders.",
        capabilities=["Resumo executivo", "Relatório HTML/Markdown", "Próximos passos"],
        inputs=["Resultados dos agentes"], outputs=["Relatório"], requires_data=False,
    )

    def run(self, ctx: AgentContext, result: AgentResult, **_: Any) -> None:
        p, uc = ctx.project, ctx.use_case
        sections = [f"# {p.name}", "", f"_Relatório gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')}_", ""]
        sections += ["## Resumo executivo"]
        order = ["framing", "connector", "profiler", "quality", "features", "selection", "advisor", "training", "forecasting",
                 "segmentation", "anomaly", "association", "evaluation", "explainability", "governance", "deployment", "monitoring"]
        for aid in order:
            run = ctx.latest(aid)
            if run and run.get("summary"):
                sections.append(f"- **{run['title']}:** {run['summary']}")
        sections += ["", "## Problema de negócio"]
        if uc:
            sections += [f"- **Pergunta:** {uc.business_question}", f"- **Decisão:** {uc.decision}",
                         f"- **Métrica de negócio:** {uc.metrics.business}"]
        meta = ctx.champion()
        if meta:
            sections += ["", "## Modelo", f"- **Algoritmo:** {meta['model_name']} (`{meta['id']}`, estado: {meta.get('stage')})"]
            mt = meta.get("metrics_test", {})
            if mt:
                sections.append("- **Desempenho (teste):** " + ", ".join(f"{k} = {v:.3f}" for k, v in list(mt.items())[:6]
                                                                       if isinstance(v, (int, float))))
        for aid, title in (("explainability", "Principais fatores"), ("quality", "Qualidade e riscos de dados"),
                           ("governance", "Governança")):
            run = ctx.latest(aid)
            if run:
                sections += ["", f"## {title}"] + [f"- {i['title']}: {i['detail']}" for i in run.get("insights", [])[:6]]
        sections += ["", "## Próximos passos"]
        steps = GuideAgent.pending_steps(ctx)
        sections += [f"{i + 1}. {ctx.kb.step(s).title}" for i, s in enumerate(steps[:5])] or ["- Projeto completo — monitorizar regularmente."]
        md = "\n".join(sections)
        folder = ctx.settings.exports_dir / p.id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "relatorio.md").write_text(md, encoding="utf-8")
        html = self.to_html(md, p.name)
        (folder / "relatorio.html").write_text(html, encoding="utf-8")
        result.blocks.append(B.markdown(md))
        result.blocks.append(B.download("Relatório", [{"label": "relatorio.html", "path": f"{p.id}/relatorio.html"},
                                                      {"label": "relatorio.md", "path": f"{p.id}/relatorio.md"}]))
        result.summary = "Relatório executivo gerado (HTML e Markdown)."
        result.outputs = {"markdown": md}

    @staticmethod
    def to_html(md: str, title: str) -> str:
        import html as h

        def inline(text: str) -> str:
            esc = h.escape(text)
            esc = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc)
            esc = re.sub(r"`(.+?)`", r"<code>\1</code>", esc)
            return re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"<em>\1</em>", esc)

        body: list[str] = []
        in_list: Optional[str] = None
        for line in md.splitlines():
            item = re.match(r"^(- |\d+\. )(.*)$", line)
            tag = ("ol" if line[:1].isdigit() else "ul") if item else None
            if in_list and tag != in_list:
                body.append(f"</{in_list}>")
                in_list = None
            if item:
                if in_list is None:
                    body.append(f"<{tag}>")
                    in_list = tag
                body.append(f"<li>{inline(item.group(2))}</li>")
            elif line.startswith("## "):
                body.append(f"<h2>{inline(line[3:])}</h2>")
            elif line.startswith("# "):
                body.append(f"<h1>{inline(line[2:])}</h1>")
            elif line.strip():
                body.append(f"<p>{inline(line)}</p>")
        if in_list:
            body.append(f"</{in_list}>")
        css = ("body{font-family:Segoe UI,Arial,sans-serif;max-width:860px;margin:40px auto;padding:0 16px;color:#1f2937;line-height:1.55}"
               "h1{color:#1e3a8a}h2{color:#1e40af;border-bottom:1px solid #e5e7eb;padding-bottom:4px;margin-top:28px}"
               "code{background:#f3f4f6;padding:1px 4px;border-radius:4px}")
        return f"<!doctype html><html lang='pt'><head><meta charset='utf-8'><title>{h.escape(title)}</title><style>{css}</style></head><body>{''.join(body)}</body></html>"


# =============================================================================== GUIA
FLOWS = {
    "binary_classification": ["enquadramento", "dados", "perfil", "qualidade", "features", "modelos", "parametros", "treino",
                              "avaliacao", "explicabilidade", "governanca", "implementacao", "monitorizacao"],
    "forecasting": ["enquadramento", "dados", "perfil", "qualidade", "modelos", "parametros", "treino", "avaliacao",
                    "explicabilidade", "implementacao", "monitorizacao"],
    "clustering": ["enquadramento", "dados", "perfil", "qualidade", "modelos", "parametros", "treino", "avaliacao",
                   "explicabilidade", "governanca", "implementacao", "monitorizacao"],
    "anomaly_detection": ["enquadramento", "dados", "perfil", "qualidade", "modelos", "parametros", "treino", "avaliacao",
                          "explicabilidade", "governanca", "implementacao", "monitorizacao"],
    "association_rules": ["enquadramento", "dados", "perfil", "modelos", "parametros", "treino", "avaliacao", "implementacao"],
}
FLOWS["multiclass_classification"] = FLOWS["binary_classification"]
FLOWS["regression"] = FLOWS["binary_classification"]


class GuideAgent(Agent):
    card = AgentCard(
        id="guide", name="Agente Guia (Glossário & Percurso)", component="Orientação e formação",
        role="Mentor", icon="map", step=None,
        description="Acompanha o percurso do projeto: indica o próximo passo, explica porquê e como fazê-lo, "
                    "mostra a checklist e os erros comuns, e liga cada conceito ao glossário.",
        capabilities=["Próximo passo recomendado", "Checklist por passo", "Glossário contextual", "Progresso do projeto"],
        inputs=["Estado do projeto"], outputs=["Próximo passo", "Explicação"], requires_data=False,
    )

    @staticmethod
    def pending_steps(ctx: AgentContext) -> list[str]:
        flow = FLOWS.get(ctx.project.problem_type, FLOWS["binary_classification"])
        return [s for s in flow if ctx.project.step_status(s) not in ("done", "warning", "skipped")]

    def run(self, ctx: AgentContext, result: AgentResult, step_id: Optional[str] = None, **_: Any) -> None:
        kb = ctx.kb
        flow = FLOWS.get(ctx.project.problem_type, FLOWS["binary_classification"])
        pending = self.pending_steps(ctx)
        sid = step_id or (pending[0] if pending else flow[-1])
        step = kb.step(sid)
        done = len(flow) - len(pending)
        result.blocks.append(B.kpis([B.kpi("Progresso", done / len(flow), "pct", f"{done} de {len(flow)} passos"),
                                     B.kpi("Próximo passo", f"{step.order}. {step.title}", "text")]))
        md = [f"### {step.order}. {step.title}", "", f"**Objetivo:** {step.objective}", "", f"**Porque importa:** {step.why}", "",
              "**Como fazer:**"] + [f"{i + 1}. {h}" for i, h in enumerate(step.how)] + ["", "**Checklist:**"] + \
             [f"- [ ] {c}" for c in step.checklist] + ["", "**Erros comuns:**"] + [f"- {m}" for m in step.mistakes]
        result.blocks.append(B.markdown("\n".join(md)))
        terms = [kb.term(t) for t in step.terms if kb.term(t)]
        result.blocks.append(B.table("Conceitos deste passo", [{"termo": t.term, "id": t.id, "definicao": t.short} for t in terms],
                                     [{"key": "id", "label": "Termo", "fmt": "term"}, {"key": "definicao", "label": "Definição"}]))
        agent_name = next((a.card.name for a in _registry_cards() if a.card.id == step.agent), step.agent)
        result.summary = f"Próximo passo: {step.order}. {step.title} — executado pelo {agent_name}."
        result.outputs = {"next_step": sid, "progress": done / len(flow), "pending": pending}
        result.terms = step.terms
        result.next_step = sid


def _registry_cards() -> list[Agent]:
    from . import AGENTS

    return list(AGENTS.values())
