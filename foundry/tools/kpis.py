"""Período atual contra o anterior, com os maiores contributos por dimensão.

Uso: python -m foundry kpis <ficheiro.csv> --data COL --valor COL[,COL2] [--dim COL[,COL2]] [--periodo semana|mes] [--ate AAAA-MM-DD] [--out pasta]

Compara o último período COMPLETO com o anterior e com o homólogo (mesma semana/mês do ano anterior, se existir).
Períodos abertos não entram. As percentagens sobre base zero ficam por calcular (—), nunca infinitas.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import date, timedelta
from . import comum


def _chave(d: date, periodo: str) -> date:
    return d - timedelta(days=d.weekday()) if periodo == "semana" else d.replace(day=1)


def _seguinte(p: date, periodo: str) -> date:
    return p + timedelta(days=7) if periodo == "semana" else (p.replace(day=28) + timedelta(days=4)).replace(day=1)


def _anterior(p: date, periodo: str) -> date:
    return p - timedelta(days=7) if periodo == "semana" else (p - timedelta(days=1)).replace(day=1)


def _homologo(p: date, periodo: str) -> date:
    return p - timedelta(days=364) if periodo == "semana" else p.replace(year=p.year - 1)


def _var(atual: float, base: float | None) -> dict:
    if base is None:
        return {"base": None, "abs": None, "pct": None}
    return {"base": round(base, 2), "abs": round(atual - base, 2), "pct": round(100 * (atual - base) / base, 1) if base else None}


def comparar(caminho: str, col_data: str, valores: list[str], dims: list[str], periodo: str = "semana", ate: date | None = None) -> dict:
    cols, linhas, o = comum.ler_csv(caminho)
    for c in [col_data, *valores, *dims]:
        if c not in cols:
            raise ValueError(f"coluna inexistente: {c}")
    tot: dict = defaultdict(lambda: defaultdict(float))
    por_dim: dict = {d: defaultdict(lambda: defaultdict(float)) for d in dims}
    datas, ilegiveis = [], 0
    for l in linhas:
        d = comum.data(l.get(col_data))
        if not d:
            ilegiveis += 1
            continue
        datas.append(d)
        p = _chave(d, periodo)
        for v in valores:
            x = comum.num(l.get(v), o["decimal"])
            if x is None:
                continue
            tot[v][p] += x
            for dim in dims:
                por_dim[dim][(v, l.get(dim) or "(vazio)")][p] += x
    if not datas:
        raise ValueError("nenhuma data legível")
    limite = ate or max(datas)
    ultimo = _chave(limite, periodo)
    agregado = all(d == _chave(d, periodo) for d in datas)   # dados já ao grão do período: o último está completo
    if not agregado and _seguinte(ultimo, periodo) - timedelta(days=1) > limite:   # período ainda aberto
        ultimo = _anterior(ultimo, periodo)
    ant, hom = _anterior(ultimo, periodo), _homologo(ultimo, periodo)
    avisos = []
    if ilegiveis:
        avisos.append(f"{ilegiveis} linha(s) com data ilegível ignorada(s)")
    metricas = []
    for v in valores:
        if ultimo not in tot[v]:
            raise ValueError(f"sem dados de «{v}» no período {ultimo.isoformat()}")
        atual = tot[v][ultimo]
        m = {"metrica": v, "atual": round(atual, 2), "vs_anterior": _var(atual, tot[v].get(ant)), "vs_homologo": _var(atual, tot[v].get(hom))}
        historico = [tot[v][p] for p in sorted(tot[v]) if p <= ultimo]
        z = comum.z_robusto(historico)
        m["z_robusto"] = round(z[-1], 2) if z and z[-1] is not None else None
        if m["z_robusto"] is not None and abs(m["z_robusto"]) > 3.5:
            avisos.append(f"{v}: período fora do habitual (z={m['z_robusto']}): verificar os dados antes de explicar")
        m["contributos"] = {}
        for dim in dims:
            difs = [{"valor": k[1], "atual": round(s.get(ultimo, 0), 2), "anterior": round(s.get(ant, 0), 2),
                     "contributo": round(s.get(ultimo, 0) - s.get(ant, 0), 2)} for k, s in por_dim[dim].items() if k[0] == v]
            difs.sort(key=lambda x: -abs(x["contributo"]))
            m["contributos"][dim] = difs[:5]
        metricas.append(m)
    return {"ficheiro": caminho, "periodo": periodo, "atual": ultimo.isoformat(), "anterior": ant.isoformat(), "homologo": hom.isoformat(),
            "dados_ate": max(datas).isoformat(), "estado": "avisos" if avisos else "ok", "avisos": avisos, "metricas": metricas}


def _markdown(r: dict) -> str:
    p = lambda x: "—" if x is None else f"{x:+.1f}%".replace(".", ",")
    l = [f"# KPIs · {r['periodo']} de {r['atual']}", "", f"Comparado com {r['anterior']} (anterior) e {r['homologo']} (homólogo). Dados até {r['dados_ate']}.", ""]
    l += [f"- {a}" for a in r["avisos"]] + [""] if r["avisos"] else []
    l += ["| Métrica | Atual | Anterior | Var. | Homólogo | Var. |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for m in r["metricas"]:
        a, h = m["vs_anterior"], m["vs_homologo"]
        l.append(f"| {m['metrica']} | {comum.fmt(m['atual'])} | {comum.fmt(a['base'])} | {p(a['pct'])} | {comum.fmt(h['base'])} | {p(h['pct'])} |")
    for m in r["metricas"]:
        for dim, difs in m["contributos"].items():
            l += ["", f"## {m['metrica']} · maiores contributos por {dim}", "", f"| {dim} | Atual | Anterior | Contributo |", "| --- | ---: | ---: | ---: |"]
            l += [f"| {d['valor']} | {comum.fmt(d['atual'])} | {comum.fmt(d['anterior'])} | {comum.fmt(d['contributo'])} |" for d in difs]
    return "\n".join(l) + "\n"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="python -m foundry kpis", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ficheiro"); ap.add_argument("--data", required=True); ap.add_argument("--valor", required=True)
    ap.add_argument("--dim", default=""); ap.add_argument("--periodo", choices=("semana", "mes"), default="semana"); ap.add_argument("--ate"); ap.add_argument("--out")
    a = ap.parse_args(argv)
    try:
        ate = comum.data(a.ate) if a.ate else None
        if a.ate and not ate:
            raise ValueError("--ate: usar AAAA-MM-DD")
        r = comparar(a.ficheiro, a.data, a.valor.split(","), [d for d in a.dim.split(",") if d], a.periodo, ate)
    except (ValueError, OSError) as e:
        print(f"Erro de dados: {e}")
        return 2
    comum.emitir(r, a.out, "kpis", _markdown(r))
    return 0
