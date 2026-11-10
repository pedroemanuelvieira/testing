"""CLI unica das skills bi_ml (v0.4): `python -m bi_ml.cli <comando> --data DIR --out DIR`.

Comandos: check, lifecycle, churn, forecast, stockout, variance, basket, cohorts, roi-series, all.
Entradas em DIR (CSV): sales.csv (obrigatorio), stock.csv, invest.csv, budget_plan.csv, forecast_plan.csv.
Todos os comandos passam pela camada prepare (devolucoes, balcao, ids, duplicados) e gravam
qualidade_dados.json: nenhum resultado sem o relatorio dos dados que o originaram.
"""
from __future__ import annotations
import argparse, json, os, sys, warnings
import numpy as np
import pandas as pd
from . import contract, prepare, customers, demand, planning, basket_roi as br, stock_and_variance as sv, abc_xyz
from .contract import ContractError, DataQualityWarning


ID_COLS = {c: str for c in ("product_id", "customer_id", "order_id", "campaign_id")}   # preserva zeros a esquerda
REVENUE_BASES = ("sem_imposto", "com_imposto")
MONETARY_CMDS = ("stockout", "roi-series", "lifecycle", "churn", "variance", "abc-xyz", "cohorts")


def semantica_fiscal_avisos(cmd, fiscal, has_cost):
    """v0.9 (Grok, IVA): avisos quando um comando monetario corre sem base fiscal declarada.
    Forecast e basket usam quantidades; ABC e coortes tambem apresentam receitas."""
    if cmd not in MONETARY_CMDS:
        return []
    av = []
    if fiscal.get("revenue_basis") is None:
        av.append("base fiscal da receita NAO declarada (csv_options.revenue_basis = sem_imposto|com_imposto): "
                  "valores monetarios sao os do extrato; margens e ROI so sao validos se receita, custo e gasto "
                  "estiverem na MESMA base. O pacote nao infere nem desconta taxas.")
    elif fiscal["revenue_basis"] == "com_imposto" and (has_cost or cmd == "roi-series"):
        av.append("receita COM imposto: comparar com custo/gasto na mesma base, ou converter no ERP linha a linha "
                  "(taxas mistas e isencoes impedem dividir por um fator unico).")
    if fiscal.get("currency") is None:
        av.append("moeda nao declarada (csv_options.currency): nao misturar extratos de moedas diferentes.")
    return av


def load(data_dir):
    p = lambda n: os.path.join(data_dir, n)
    if not os.path.exists(p("sales.csv")):
        raise ContractError(f"falta {p('sales.csv')}")
    config_path = p("csv_options.json")
    opts = json.load(open(config_path)) if os.path.exists(config_path) else {}
    if set(opts) - {"sep", "decimal", "encoding", "date_format", "exclude_products", "revenue_basis", "currency"}:
        raise ContractError("csv_options: opcao desconhecida")
    # v0.9 (Grok, IVA): semantica fiscal DECLARADA, nunca inferida (taxas mistas/isencoes impedem um fator unico)
    basis = opts.pop("revenue_basis", None); currency = opts.pop("currency", None)
    if basis is not None and basis not in REVENUE_BASES:
        raise ContractError(f"csv_options.revenue_basis: um de {REVENUE_BASES}")
    if currency is not None and not (isinstance(currency, str) and len(currency) == 3 and currency.isalpha()):
        raise ContractError("csv_options.currency: codigo ISO de 3 letras (ex. EUR)")
    exclude = opts.pop("exclude_products", None)   # v0.7: ids de linhas nao-produto (portes, embalagem)
    if exclude is not None and not (isinstance(exclude, list) and all(isinstance(x, (str, int)) for x in exclude)):
        raise ContractError("csv_options.exclude_products: tem de ser uma lista de ids")
    raw = prepare.read_erp_csv(p("sales.csv"), **opts)
    sales, rets, rel_s = prepare.prepare_sales(raw, exclude_products=exclude)
    stock = rel_k = None
    if os.path.exists(p("stock.csv")):
        stock, rel_k = prepare.prepare_stock(prepare.read_erp_csv(p("stock.csv"), **opts))
    return sales, rets, stock, {"vendas": rel_s, "stock": rel_k,
                                "semantica_fiscal": {"revenue_basis": basis, "currency": currency}}


def _w(df, out, name, index=False):
    os.makedirs(out, exist_ok=True)
    df.to_csv(os.path.join(out, name), index=index)


def run(cmd, data, out, **kw):
    """Executa um comando; devolve dict resumo. Avisos de qualidade sao capturados e gravados."""
    os.makedirs(out, exist_ok=True)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        sales, rets, stock, qual = load(data)
        res = _dispatch(cmd, data, out, sales, stock, **kw)
    fiscal = semantica_fiscal_avisos(cmd if cmd != "all" else "stockout", qual["semantica_fiscal"], "cost" in sales.columns)
    qual["avisos"] = sorted({f"{w.category.__name__}: {w.message}" for w in caught} | {f"SemanticaFiscal: {a}" for a in fiscal})
    json.dump(qual, open(os.path.join(out, "qualidade_dados.json"), "w"), indent=2, default=str, ensure_ascii=False)
    res["qualidade_dados"] = {"avisos": len(qual["avisos"]), "devolucoes_valor": qual["vendas"].get("devolucoes_valor", 0),
                            "ajustes_valor_liquido": qual["vendas"].get("ajustes_valor_liquido", 0),
                            "receita_liquida": qual["vendas"].get("receita_liquida"),
                            "semantica_fiscal": qual["semantica_fiscal"], "avisos_fiscais": fiscal}
    json.dump(res, open(os.path.join(out, f"relatorio_{cmd}.json"), "w"), indent=2, default=str, ensure_ascii=False)
    return res


def _dispatch(cmd, data, out, sales, stock, **kw):
    r = {}
    if cmd == "check":
        r["linhas_vendas"] = int(len(sales)); r["periodo"] = [str(sales.date.min().date()), str(sales.date.max().date())]
        r["produtos"] = int(sales.product_id.nunique())
        if stock is not None:
            r["cobertura_stock"] = contract.check_id_overlap(sales, stock, allow_partial=True)
    elif cmd == "lifecycle":
        lc = customers.lifecycle(sales); _w(lc, out, "lifecycle.csv", True); r["estagios"] = lc["stage"].value_counts().to_dict()
    elif cmd == "churn":
        sc, met, _ = customers.churn_model(sales)
        sc["clv_12m_heuristica"] = customers.clv_12m(sales, sc); sc["risco_x_valor"] = sc["p_churn"] * sc["clv_12m_heuristica"]
        _w(sc, out, "churn_scores.csv", True); r["metricas"] = met
    elif cmd == "forecast":
        fc = demand.forecast_all(sales, stock, h=kw.get("h", 8), selection_policy=kw.get("selection_policy", "baseline")); _w(fc, out, "forecast.csv")
        om = pd.DataFrame(sorted(fc.attrs.get("omitidos", {}).items()), columns=["product_id", "motivo"])
        _w(om, out, "forecast_omitidos.csv"); r["produtos_previstos"] = int(fc.product_id.nunique()) if len(fc) else 0
        r["produtos_omitidos"] = int(len(om))
        if len(fc):
            g = fc.groupby("product_id").first()
            r["wape_holdout_mediano"] = float(g.wape_holdout.median()); r["wape_holdout_media_13s_mediano"] = float(g.wape_holdout_media_13s.median())
    elif cmd == "stockout":
        if stock is None:
            raise ContractError("stockout: falta stock.csv")
        ev, summ = sv.lost_sales(sales, stock, allow_partial=kw.get("allow_partial", False))
        _w(ev, out, "rupturas_eventos.csv"); _w(summ, out, "rupturas_resumo.csv", True)
        r["receita_perdida_total"] = float(summ.receita_perdida.sum()) if len(summ) else 0.0
        r["possivel_descontinuado"] = sorted(summ.index[summ.possivel_descontinuado].tolist()) if len(summ) else []
    elif cmd == "variance":
        last = sales.date.max(); days = kw.get("days", 90)
        cur = sales[sales.date > last - pd.Timedelta(days=days)]
        ref = sales[(sales.date <= last - pd.Timedelta(days=days)) & (sales.date > last - pd.Timedelta(days=2 * days))]
        _w(sv.pvm(cur, ref, days_cur=days, days_ref=days), out, "pvm.csv", True)
        _w(sv.anomalies(sales), out, "anomalias.csv")
        for kind in ("budget", "forecast"):
            pth = os.path.join(data, kind + "_plan.csv")
            if os.path.exists(pth):
                _w(planning.plan_variance(sales, pd.read_csv(pth, dtype=ID_COLS), last, kind=kind), out, f"{kind}_variance.csv")
        r["periodo_atual"] = [str((last - pd.Timedelta(days=days - 1)).date()), str(last.date())]
    elif cmd == "abc-xyz":
        if not kw.get("start") or not kw.get("end"):
            raise ContractError("abc-xyz: --start e --end obrigatorios (janela completa)")
        _w(abc_xyz.classify(sales, kw["start"], kw["end"]), out, "abc_xyz.csv")
    elif cmd == "basket":
        bp = br.basket_pairs(sales, min_lift=kw.get("min_lift"), min_incremental_orders=kw.get("min_incremental_orders"))
        _w(bp, out, "basket_pares.csv"); r["pares_significativos"] = int(bp["significativo"].sum()) if len(bp) else 0
        r["pares_elegiveis"] = int(bp["elegivel"].sum()) if len(bp) else 0
        r["limiar_material"] = {"min_lift": kw.get("min_lift"), "min_incremental_orders": kw.get("min_incremental_orders")}
    elif cmd == "cohorts":
        _w(planning.cohort_retention(sales, sales.date.max()), out, "cohort_retention.csv")
    elif cmd == "roi-series":
        if not kw.get("series") or kw.get("spend") is None or kw.get("margin_rate") is None or not kw.get("intervention_date"):
            raise ContractError("roi-series: --series, --intervention-date, --spend e --margin-rate obrigatorios")
        s = pd.read_csv(kw["series"])
        dates = prepare.parse_dates(s["date"])
        t0 = pd.Timestamp(kw["intervention_date"])
        if not (dates.min() < t0 <= dates.max()):
            raise ContractError("roi-series: intervention_date fora do intervalo da serie")
        if dates.isna().any() or dates.duplicated().any() or not dates.is_monotonic_increasing or dates.diff().dropna().nunique() != 1:
            raise ContractError("roi-series: datas unicas, ordenadas e regularmente espacadas obrigatorias")
        k = int((dates < pd.Timestamp(kw["intervention_date"])).sum())
        ctrl = [c for c in s.columns if c.startswith("control")]
        hold = [c for c in s.columns if c.startswith("holdout")]
        if kw.get("desenho"):
            if not hold:
                raise ContractError("roi-series: --desenho exige colunas holdout_1..holdout_M (unidades reservadas ANTES da "
                                    "campanha, nao expostas); declarar o desenho sem os dados do holdout nao e aceite")
            cols, is_hold = hold, True
        else:
            if hold:
                raise ContractError("roi-series: colunas holdout_* exigem --desenho (aleatorizado|holdout_*)")
            if not ctrl:
                raise ContractError("roi-series: precisa de colunas control_1..control_K")
            cols, is_hold = ctrl, False
        res = planning.controlled_incremental_ci(s["outcome"].to_numpy(float), s[cols].to_numpy(float), k, holdout=is_hold)
        d = planning.roi_decision(res, kw["spend"], kw["margin_rate"], desenho=kw.get("desenho"))
        r = {k_: v for k_, v in res.items() if k_ != "counterfactual"}; r.update(d)
    elif cmd == "all":
        for c in ("check", "lifecycle", "churn", "forecast", "stockout", "variance", "basket", "cohorts"):
            if c == "stockout" and stock is None:
                continue
            try:
                r[c] = _dispatch(c, data, out, sales, stock, **kw)
            except Exception as e:           # um modulo a falhar nao esconde os outros nem o motivo
                r[c] = {"erro": f"{type(e).__name__}: {e}"}
        ip = os.path.join(data, "invest.csv")
        if os.path.exists(ip) and kw.get("roi_legado"):   # v0.6 (Grok): legado enviesado so a pedido explicito
            leg = br.campaign_roi(sales, contract.validate(pd.read_csv(ip, dtype=ID_COLS), contract.INVEST, "invest"))
            leg["aviso"] = "metodo legado (v0.1): vies medido +10% a +27%; preferir roi-series com IC e diagnosticos"
            _w(leg, out, "roi_campanhas_legado.csv")
    else:
        raise ContractError(f"comando desconhecido: {cmd}")
    return r


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bi_ml.cli")
    ap.add_argument("cmd", choices=["check", "lifecycle", "churn", "forecast", "stockout", "variance", "basket",
                                    "cohorts", "roi-series", "abc-xyz", "all"])
    ap.add_argument("--data", required=True); ap.add_argument("--out", default="saida")
    ap.add_argument("--selection-policy", choices=list(demand.POLICIES), default="baseline",
                    help="baseline (defeito): media 13 semanas; guarded: troca so com ganho >=15%% e vitoria em >=2/3 das dobras; adaptive: experimental")
    ap.add_argument("--horizon", type=int, dest="h", default=8); ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--allow-partial-stock", action="store_true", dest="allow_partial")
    ap.add_argument("--start"); ap.add_argument("--end")
    ap.add_argument("--series"); ap.add_argument("--intervention-date"); ap.add_argument("--spend", type=float)
    ap.add_argument("--margin-rate", type=float, dest="margin_rate")
    ap.add_argument("--min-lift", type=float, dest="min_lift",
                    help="(basket) lift minimo de NEGOCIO; sem qualquer limiar de negocio, elegivel=False e material=NA")
    ap.add_argument("--min-incremental-orders", type=float, dest="min_incremental_orders",
                    help="(basket) encomendas associadas incrementais minimas N x leverage (definir a partir de margem e custo da acao)")
    ap.add_argument("--desenho", choices=list(planning.DESENHOS_CAUSAIS),
                    help="declara desenho com holdout reservado ANTES da campanha; exige colunas holdout_* na serie; sem isto a decisao ROI nao e causal")
    ap.add_argument("--roi-legado", action="store_true", dest="roi_legado",
                    help="(all) corre tambem o ROI legado v0.1, enviesado; desligado por omissao")
    a = ap.parse_args(argv)
    kw = {k: v for k, v in vars(a).items() if k not in ("cmd", "data", "out") and v is not None and v is not False}
    try:
        res = run(a.cmd, a.data, a.out, **kw)
    except ContractError as e:
        print(f"ERRO DE DADOS: {e}", file=sys.stderr); return 2
    print(json.dumps(res, indent=2, default=str, ensure_ascii=False)); return 0


if __name__ == "__main__":
    sys.exit(main())
