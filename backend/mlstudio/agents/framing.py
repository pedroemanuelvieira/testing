"""Agente de Enquadramento de Negócio e Agente de Dados Power BI."""
from __future__ import annotations

import re
from typing import Any, Optional

import pandas as pd

from ..connectors import ConnectorError, Filter
from ..connectors import dax as daxmod
from ..core import agent as B
from ..core.agent import Agent, AgentCard, AgentError, AgentResult
from ..core.context import AgentContext
from ..core.project import DataSource
from ..ml.semantic import infer_roles
from .common import SUPERVISED, pct

TARGET_HINTS = re.compile(r"(churn|abandono|saiu|saida|converteu|respondeu|fraude|incumprimento|default|atras|"
                          r"falha|rutura|target|alvo|label|flag|aderiu|resultado|categoria_nps|classe)", re.I)


def apply_use_case_defaults(ctx: AgentContext, df: Optional[pd.DataFrame] = None, force: bool = False) -> list[str]:
    """Preenche a configuração do projeto a partir do caso de uso (alvo, IDs, exclusões...)."""
    p, uc = ctx.project, ctx.use_case
    changes: list[str] = []
    if uc is None:
        return changes
    demo = uc.demo or {}
    cols = set(df.columns) if df is not None else None

    def ok(col: Optional[str]) -> bool:
        return bool(col) and (cols is None or col in cols)

    if (force or not p.target) and ok(uc.target.column):
        p.target = uc.target.column
        changes.append(f"alvo = {p.target}")
    if p.positive_class is None and uc.target.positive_class is not None:
        p.positive_class = uc.target.positive_class
    for attr, key in (("id_columns", "id_columns"), ("series_columns", "series_columns"), ("features", "features")):
        vals = [c for c in demo.get(key, []) or [] if ok(c)]
        if vals and (force or not getattr(p, attr)):
            setattr(p, attr, vals)
            changes.append(f"{attr} = {', '.join(vals)}")
    excl = [c for c in demo.get("exclude", []) or [] if ok(c)]
    new_ex = [c for c in excl if c not in p.excluded_columns]
    if new_ex:
        p.excluded_columns = p.excluded_columns + new_ex
        changes.append(f"excluídas = {', '.join(new_ex)}")
    for attr, key in (("time_column", "time_column"), ("value_column", "value_column"),
                      ("transaction_column", "transaction_column"), ("item_column", "item_column"),
                      ("label_column", "label_column")):
        val = demo.get(key)
        if ok(val) and (force or not getattr(p, attr)):
            setattr(p, attr, val)
            changes.append(f"{attr} = {val}")
    if demo.get("aggregation") and (force or p.aggregation == "sum"):
        p.aggregation = demo["aggregation"]
    if demo.get("freq") and (force or not p.freq):
        p.freq = demo["freq"]
    if demo.get("horizon") and (force or not p.horizon):
        p.horizon = int(demo["horizon"])
    if uc.business_costs and not p.business_costs:
        p.business_costs = {"cost_fp": uc.business_costs.cost_fp, "cost_fn": uc.business_costs.cost_fn,
                            "benefit_tp": uc.business_costs.benefit_tp}
        changes.append("custos de negócio do caso de uso")
    if uc.profile.get("goal") and p.goal == "equilibrado":
        p.goal = uc.profile["goal"]
    return changes


class FramingAgent(Agent):
    card = AgentCard(
        id="framing", name="Agente de Enquadramento de Negócio", component="Enquadramento",
        role="Analista de negócio", icon="compass", step="enquadramento",
        description="Traduz a necessidade de negócio numa pergunta de ML: tipo de problema, alvo, decisão, KPI, "
                    "custos de erro e baseline. Aceita perguntas em texto livre e sugere o caso de uso mais próximo.",
        capabilities=["Classificar perguntas de negócio em casos de uso", "Sugerir alvo, coluna temporal e IDs",
                      "Construir a ficha do problema", "Definir baseline e custos de negócio"],
        inputs=["Pergunta de negócio (opcional)", "Caso de uso", "Dados (opcional)"],
        outputs=["Ficha do problema", "Tipo de problema", "Alvo sugerido", "Custos de negócio"],
        params=[{"name": "question", "label": "Pergunta de negócio", "type": "text"},
                {"name": "use_case_id", "label": "Caso de uso", "type": "use_case"}],
        requires_data=False,
    )

    def run(self, ctx: AgentContext, result: AgentResult, question: str = "", use_case_id: Optional[str] = None,
            apply: bool = True, **_: Any) -> None:
        p, kb = ctx.project, ctx.kb
        suggestions = []
        if question:
            hits = kb.search(question, kinds=["use_case"], k=5)
            for h in hits:
                uc = kb.use_case(h["id"])
                suggestions.append({"caso": uc.name, "id": uc.id, "area": kb.area(uc.area).name,
                                    "tipo": kb.problem_type(uc.problem_type).name, "relevancia": h["score"]})
            if suggestions:
                result.blocks.append(B.table("Casos de uso mais próximos da pergunta", suggestions,
                                             [{"key": "caso", "label": "Caso de uso"}, {"key": "area", "label": "Área"},
                                              {"key": "tipo", "label": "Tipo de problema"},
                                              {"key": "relevancia", "label": "Relevância", "fmt": "num"}]))
                if not use_case_id and not p.use_case_id:
                    use_case_id = suggestions[0]["id"]
        if use_case_id and use_case_id != p.use_case_id:
            uc = kb.use_case(use_case_id)
            if uc is None:
                raise AgentError(f"Caso de uso inexistente: {use_case_id}")
            p.use_case_id, p.problem_type = uc.id, uc.problem_type
            p.area_id = p.area_id or uc.area
        uc = ctx.use_case
        pt = ctx.problem
        df = ctx.data(required=False)
        changes = apply_use_case_defaults(ctx, df) if apply else []

        # sugestões a partir dos dados
        if df is not None:
            roles = infer_roles(df, target=p.target, id_columns=p.id_columns)
            if p.problem_type in SUPERVISED and (not p.target or p.target not in df.columns):
                cands = [c for c in df.columns if TARGET_HINTS.search(c)]
                if p.problem_type == "binary_classification":
                    cands = [c for c in cands if df[c].nunique() == 2] or [c for c in df.columns if df[c].nunique() == 2]
                if cands:
                    p.target = cands[0]
                    changes.append(f"alvo sugerido = {p.target}")
                    result.info("Alvo sugerido pelos nomes das colunas", f"Candidatos: {', '.join(cands[:5])}.", ["target"])
            ids = [c for c, r in roles.items() if r == "id" and c not in p.id_columns]
            if ids and not p.id_columns:
                p.id_columns = ids[:3]
                changes.append(f"IDs = {', '.join(p.id_columns)}")
            dates = [c for c, r in roles.items() if r == "datetime"]
            if p.problem_type == "forecasting" and not p.time_column and dates:
                p.time_column = dates[0]
                changes.append(f"coluna temporal = {p.time_column}")
            p.column_roles = roles
        if apply:
            ctx.save_project()

        # ficha do problema
        area = kb.area(p.area_id) if p.area_id else None
        rows = [
            {"campo": "Área de negócio", "valor": area.name if area else "—"},
            {"campo": "Caso de uso", "valor": uc.name if uc else "Personalizado"},
            {"campo": "Tipo de problema", "valor": f"{pt.name} — {pt.short}"},
            {"campo": "Pergunta de negócio", "valor": uc.business_question if uc else (question or "—")},
            {"campo": "Decisão suportada", "valor": uc.decision if uc else "—"},
            {"campo": "Unidade de análise", "valor": uc.unit if uc else "—"},
            {"campo": "Alvo", "valor": (f"{p.target} — {uc.target.definition}" if uc and p.target else (p.target or "—"))},
            {"campo": "Horizonte", "valor": (uc.horizon if uc else "") or (f"{p.horizon} períodos" if p.horizon else "—")},
            {"campo": "Métrica principal", "valor": (uc.metrics.primary if uc else pt.primary_metric)},
            {"campo": "Métrica de negócio", "valor": uc.metrics.business if uc else "—"},
            {"campo": "Nível de risco (AI Act)", "valor": uc.ai_act_risk if uc else "a avaliar"},
        ]
        result.blocks.append(B.table("Ficha do problema", rows, [{"key": "campo", "label": "Campo"},
                                                                 {"key": "valor", "label": "Definição"}],
                                     terms=["target", "kpi", "horizonte_previsao"]))
        if p.business_costs:
            c = p.business_costs
            result.blocks.append(B.kpis([
                B.kpi("Custo de um falso positivo", c.get("cost_fp"), "money", "Agir sobre quem não precisava", "falso_positivo"),
                B.kpi("Custo de um falso negativo", c.get("cost_fn"), "money", "Não agir sobre um caso real", "falso_positivo"),
                B.kpi("Benefício de um verdadeiro positivo", c.get("benefit_tp"), "money", "Valor salvo/ganho", "matriz_custo_beneficio"),
            ], "Matriz de custo-benefício"))
            if uc and uc.business_costs and uc.business_costs.note:
                result.blocks.append(B.callout("info", "Pressupostos dos custos", uc.business_costs.note,
                                               ["matriz_custo_beneficio"]))
        # baseline
        if df is not None and p.target in (df.columns if df is not None else []):
            y = df[p.target].dropna()
            if p.problem_type == "binary_classification":
                pos = p.positive_class if p.positive_class is not None else y.value_counts().index[-1]
                rate = float((y.astype(str) == str(pos)).mean())
                result.blocks.append(B.kpis([
                    B.kpi("Taxa de positivos", rate, "pct", f"classe positiva = {pos}", "desequilibrio_classes"),
                    B.kpi("Accuracy de prever sempre 'não'", 1 - rate, "pct", "Baseline enganadora", "accuracy"),
                    B.kpi("AUC de um modelo aleatório", 0.5, "num", "Baseline de ordenação", "auc_roc"),
                ], "Baseline"))
                if rate < 0.1:
                    result.warn("Classe positiva rara", f"Apenas {pct(rate)} de positivos: use PR-AUC/recall e trate o "
                                "desequilíbrio.", ["desequilibrio_classes", "pr_auc"])
            elif p.problem_type == "regression":
                yv = pd.to_numeric(y, errors="coerce").dropna()
                mae_base = float((yv - yv.mean()).abs().mean())
                result.blocks.append(B.kpis([
                    B.kpi("Média do alvo", float(yv.mean()), "num", "", "media_mediana"),
                    B.kpi("MAE de prever sempre a média", mae_base, "num", "Baseline a bater", "baseline"),
                    B.kpi("Assimetria do alvo", float(yv.skew()), "num", ">1 = cauda longa", "assimetria"),
                ], "Baseline"))
        if uc:
            for pit in uc.pitfalls[:3]:
                result.info("Armadilha típica deste caso", pit, ["data_leakage"] if "leak" in pit.lower() else [])
        if changes:
            result.success("Configuração do projeto atualizada", "; ".join(changes))
        result.summary = (f"Problema enquadrado como **{pt.name}**"
                          + (f" (caso de uso: {uc.name})" if uc else "") + (f", alvo `{p.target}`." if p.target else "."))
        result.outputs = {"use_case_id": p.use_case_id, "problem_type": p.problem_type, "target": p.target,
                          "suggestions": suggestions, "changes": changes}
        result.terms = pt.terms
        result.next_step = "dados" if df is None else "perfil"


class ConnectorAgent(Agent):
    card = AgentCard(
        id="connector", name="Agente de Dados Power BI", component="Ingestão de dados",
        role="Engenheiro de dados BI", icon="database", step="dados",
        description="Explora o Power BI Service (workspaces, modelos semânticos, tabelas), recomenda as tabelas "
                    "mais relevantes para o caso de uso, gera a consulta DAX e cria o snapshot de dados do projeto.",
        capabilities=["Navegar workspaces/modelos semânticos", "Ranking de tabelas por relevância", "Gerar DAX",
                      "Carregar snapshot reprodutível", "Inferir tipos de colunas"],
        inputs=["Conector", "Workspace", "Modelo semântico", "Tabela ou consulta DAX"],
        outputs=["Snapshot de dados", "Consulta DAX", "Tipos de colunas"],
        params=[{"name": "action", "label": "Ação", "type": "choice", "choices": ["load", "explore"]},
                {"name": "top", "label": "Máx. linhas", "type": "int"}],
        requires_data=False,
    )

    def run(self, ctx: AgentContext, result: AgentResult, action: Optional[str] = None,
            source: Optional[dict[str, Any]] = None, **_: Any) -> None:
        p = ctx.project
        if source:
            p.source = DataSource(**source)
        if action is None:
            action = "load" if p.source and (p.source.table or p.source.query) else "explore"
        if action == "explore":
            self._explore(ctx, result)
        else:
            self._load(ctx, result)

    def _explore(self, ctx: AgentContext, result: AgentResult) -> None:
        p, uc = ctx.project, ctx.use_case
        cid = p.source.connector_id if p.source else ctx.hub.default_id()
        conn = ctx.hub.get(cid)
        keywords = set()
        if uc:
            keywords |= {w for f in uc.typical_features for w in re.findall(r"\w{4,}", f.lower())}
            if uc.target.column:
                keywords.add(uc.target.column.lower())
        rows = []
        for ws in conn.list_workspaces():
            for ds in conn.list_datasets(ws.id):
                try:
                    tables = conn.list_tables(ws.id, ds.id)
                except ConnectorError:
                    continue
                for t in tables:
                    cols = [c.name.lower() for c in t.columns]
                    score = sum(any(k in c for c in cols) for k in keywords)
                    if uc and uc.demo.get("table") == t.name:
                        score += 10
                    if uc and uc.target.column and uc.target.column in cols:
                        score += 5
                    rows.append({"workspace": ws.name, "workspace_id": ws.id, "dataset": ds.name, "dataset_id": ds.id,
                                 "tabela": t.name, "linhas": t.row_count, "colunas": len(t.columns), "relevancia": score})
        rows.sort(key=lambda r: -r["relevancia"])
        result.blocks.append(B.table("Tabelas disponíveis (ordenadas por relevância para o caso)", rows[:30],
                                     [{"key": "tabela", "label": "Tabela"}, {"key": "dataset", "label": "Modelo semântico"},
                                      {"key": "workspace", "label": "Workspace"}, {"key": "linhas", "label": "Linhas", "fmt": "int"},
                                      {"key": "colunas", "label": "Colunas", "fmt": "int"},
                                      {"key": "relevancia", "label": "Relevância", "fmt": "int"}],
                                     terms=["modelo_semantico", "workspace_pbi"]))
        if rows and not p.source:
            best = rows[0]
            p.source = DataSource(connector_id=cid, workspace_id=best["workspace_id"], dataset_id=best["dataset_id"],
                                  table=best["tabela"])
            ctx.save_project()
            result.success("Fonte sugerida", f"{best['tabela']} em {best['dataset']} ({best['workspace']}). Execute "
                           "novamente para carregar.")
        result.summary = f"{len(rows)} tabelas encontradas no conector '{conn.name}'."
        result.outputs = {"tables": rows[:30]}
        result.next_step = "dados"

    def _load(self, ctx: AgentContext, result: AgentResult) -> None:
        p = ctx.project
        src = p.source
        if src is None:
            raise AgentError("Indique a fonte de dados (conector, workspace, modelo semântico e tabela).")
        conn = ctx.hub.get(src.connector_id)
        ctx.progress(0.1, f"A extrair dados de {conn.name}…")
        filters = [Filter.parse(f) for f in src.filters]
        if src.query:
            query = src.query
            df = conn.execute_dax(src.workspace_id, src.dataset_id, query, max_rows=src.top)
        else:
            query = daxmod.build_table_query(src.table, columns=src.columns, top=src.top, filters=filters)
            df = conn.read_table(src.workspace_id, src.dataset_id, src.table, columns=src.columns, top=src.top,
                                 filters=filters)
        if df.empty:
            raise AgentError("A consulta não devolveu linhas.")
        ctx.progress(0.6, "A guardar snapshot e a inferir tipos…")
        info = ctx.store.save_data(p.id, df)
        ctx.cache.pop("data", None)
        p.data_info = info | {"query": query, "connector": conn.name}
        changes = apply_use_case_defaults(ctx, df)
        roles = infer_roles(df, target=p.target, id_columns=p.id_columns)
        p.column_roles = roles
        ctx.save_project()
        role_names = {"numeric": "numérica", "boolean": "binária", "categorical": "categórica", "datetime": "data",
                      "id": "identificador", "text": "texto", "constant": "constante", "target": "alvo"}
        counts = pd.Series([role_names[r] for r in roles.values()]).value_counts()
        dates = [c for c, r in roles.items() if r == "datetime"]
        period = ""
        if dates:
            d = pd.to_datetime(df[dates[0]], errors="coerce")
            period = f"{d.min().date()} → {d.max().date()}"
        result.blocks.append(B.kpis([
            B.kpi("Linhas", len(df), "int", "", "observacao"),
            B.kpi("Colunas", df.shape[1], "int", ", ".join(f"{v} {k}" for k, v in counts.items())),
            B.kpi("Período", period or "—", "text", dates[0] if dates else "sem colunas de data", "janela_observacao"),
            B.kpi("Tamanho do snapshot", info["size_mb"], "num", "MB (Parquet)", "snapshot"),
        ], "Snapshot carregado"))
        result.blocks.append(B.code("dax", query, "Consulta DAX utilizada",
                                    "Pode copiá-la para o DAX Studio ou Power BI Desktop."))
        result.blocks.append(B.table("Colunas e tipos inferidos", [
            {"coluna": c, "tipo": role_names[r], "dtype": str(df[c].dtype), "nulos": float(df[c].isna().mean()),
             "distintos": int(df[c].nunique())} for c, r in roles.items()],
            [{"key": "coluna", "label": "Coluna"}, {"key": "tipo", "label": "Papel"}, {"key": "dtype", "label": "Tipo técnico"},
             {"key": "nulos", "label": "% nulos", "fmt": "pct"}, {"key": "distintos", "label": "Distintos", "fmt": "int"}]))
        result.blocks.append(B.table("Pré-visualização (20 primeiras linhas)", df.head(20)))
        if changes:
            result.success("Configuração aplicada a partir do caso de uso", "; ".join(changes))
        if len(df) < 500:
            result.warn("Poucos dados", f"Apenas {len(df)} linhas — os modelos podem ser instáveis.", ["overfitting"])
        result.summary = f"Snapshot de {len(df):,} linhas × {df.shape[1]} colunas carregado de '{conn.name}'.".replace(",", " ")
        result.outputs = {"rows": len(df), "columns": df.shape[1], "roles": roles, "query": query}
        result.terms = ["snapshot", "dax", "evaluate_dax", "granularidade"]
        result.next_step = "perfil"
