"""Deriva e anomalias.

  python -m foundry drift psi <referencia.csv> <atual.csv> [--colunas a,b] [--out pasta]
      Population Stability Index por coluna (numéricas em decis da referência; categóricas por categoria).
      Leitura habitual: < 0,10 estável · 0,10 a 0,25 a vigiar · > 0,25 deriva relevante.
  python -m foundry drift anomalias <serie.csv> --data COL --valor COL [--grupo COL] [--ultimos 4] [--limiar 3.5] [--out pasta]
      z robusto (mediana/MAD) do desvio face ao nível local (8 observações anteriores), por grupo.
      Precisa de 16 ou mais pontos por série; assinala os últimos pontos fora do limiar.
"""
from __future__ import annotations
import argparse
import math
import statistics
from collections import Counter, defaultdict
from . import comum

_EPS = 1e-4


def _psi(ref: list[float], atu: list[float]) -> float:
    return sum((a - r) * math.log(a / r) for r, a in ((max(r, _EPS), max(a, _EPS)) for r, a in zip(ref, atu)))


def _nivel(v: float) -> str:
    return "estavel" if v < 0.10 else ("vigiar" if v <= 0.25 else "deriva")


def psi(ref_csv: str, atu_csv: str, colunas: list[str] | None = None) -> dict:
    c1, l1, o1 = comum.ler_csv(ref_csv)
    c2, l2, o2 = comum.ler_csv(atu_csv)
    comuns = [c for c in c1 if c in c2 and (not colunas or c in colunas)]
    avisos = []
    so_ref = [c for c in c1 if c not in c2]
    so_atu = [c for c in c2 if c not in c1]
    if so_ref or so_atu:
        avisos.append(f"esquema diferente: só na referência {so_ref or '—'}; só no atual {so_atu or '—'}")
    if len(l1) < 50 or len(l2) < 50:
        avisos.append("menos de 50 linhas numa das amostras: PSI pouco fiável")
    res = []
    for c in comuns:
        v1 = [l[c] for l in l1 if not comum.vazio(l.get(c))]
        v2 = [l[c] for l in l2 if not comum.vazio(l.get(c))]
        if not v1 or not v2:
            continue
        n1 = [x for x in (comum.num(v, o1["decimal"]) for v in v1) if x is not None]
        n2 = [x for x in (comum.num(v, o2["decimal"]) for v in v2) if x is not None]
        if len(n1) >= 0.95 * len(v1) and len(n2) >= 0.95 * len(v2) and len(set(n1)) > 10:
            s = sorted(n1)
            cortes = sorted({s[int(len(s) * q / 10)] for q in range(1, 10)})
            def partes(xs):
                cont = [0] * (len(cortes) + 1)
                for x in xs:
                    cont[sum(x > k for k in cortes)] += 1
                return [k / len(xs) for k in cont]
            valor, tipo = _psi(partes(n1), partes(n2)), "numerica"
            extra = {"media_ref": round(sum(n1) / len(n1), 4), "media_atual": round(sum(n2) / len(n2), 4)}
        else:
            k1, k2 = Counter(v1), Counter(v2)
            cats = sorted(set(k1) | set(k2))
            if len(cats) > 200:
                continue   # identificadores e texto livre não se comparam por PSI
            valor, tipo = _psi([k1[k] / len(v1) for k in cats], [k2[k] / len(v2) for k in cats]), "categorica"
            extra = {"categorias_novas": [k for k in cats if k not in k1][:10], "categorias_desaparecidas": [k for k in cats if k not in k2][:10]}
        res.append({"coluna": c, "tipo": tipo, "psi": round(valor, 4), "nivel": _nivel(valor),
                    "nulos_ref_pct": round(100 * (len(l1) - len(v1)) / len(l1), 2), "nulos_atual_pct": round(100 * (len(l2) - len(v2)) / len(l2), 2), **extra})
    res.sort(key=lambda r: -r["psi"])
    deriva = [r["coluna"] for r in res if r["nivel"] == "deriva"]
    vigiar = [r["coluna"] for r in res if r["nivel"] == "vigiar"]
    if deriva:
        avisos.append("deriva relevante em: " + ", ".join(deriva))
    return {"referencia": ref_csv, "atual": atu_csv, "linhas_ref": len(l1), "linhas_atual": len(l2), "colunas_avaliadas": len(res),
            "em_deriva": len(deriva), "a_vigiar": len(vigiar), "estado": "avisos" if avisos else "ok", "avisos": avisos, "colunas": res}


def anomalias(csv_path: str, col_data: str, col_valor: str, col_grupo: str | None = None, ultimos: int = 4, limiar: float = 3.5) -> dict:
    cols, linhas, o = comum.ler_csv(csv_path)
    for c in (col_data, col_valor, col_grupo):
        if c and c not in cols:
            raise ValueError(f"coluna inexistente: {c}")
    series: dict[str, dict] = defaultdict(lambda: defaultdict(float))
    for l in linhas:
        d, v = comum.data(l.get(col_data)), comum.num(l.get(col_valor), o["decimal"])
        if d and v is not None:
            series[l.get(col_grupo, "") if col_grupo else "total"][d] += v
    achados, sem_base = [], []
    for g, s in sorted(series.items()):
        datas = sorted(s)
        vals = [s[d] for d in datas]
        if len(vals) < 16:
            sem_base.append(g)
            continue
        # resíduo face ao nível local (mediana das 8 observações anteriores): aguenta tendência e sazonalidade lenta
        niveis = [statistics.median(vals[i - 8:i]) for i in range(8, len(vals))]
        z = comum.z_robusto([v - n for v, n in zip(vals[8:], niveis)])
        if z[0] is None:
            sem_base.append(g)
            continue
        for d, v, n, zi in list(zip(datas[8:], vals[8:], niveis, z))[-ultimos:]:
            if abs(zi) > limiar:
                achados.append({"grupo": g, "data": d.isoformat(), "valor": round(v, 2), "nivel_habitual": round(n, 2),
                                "desvio_pct": round(100 * (v - n) / n, 1) if n else None, "z": round(zi, 2), "sentido": "acima" if zi > 0 else "abaixo"})
    achados.sort(key=lambda a: -abs(a["z"]))
    avisos = [f"{a['grupo']} em {a['data']}: {a['desvio_pct']}% face ao nível habitual (z={a['z']})" for a in achados[:8]]
    if sem_base:
        avisos.append(f"{len(sem_base)} série(s) com menos de 16 pontos ou constantes: não avaliadas")
    return {"ficheiro": csv_path, "series": len(series), "anomalias": len(achados), "limiar_z": limiar, "ultimos_pontos": ultimos,
            "estado": "avisos" if achados else "ok", "avisos": avisos, "achados": achados, "nao_avaliadas": sem_base}


def _md_psi(r: dict) -> str:
    l = [f"# Deriva (PSI) · {r['atual']} contra {r['referencia']}", "", f"**Estado:** {r['estado']} · {r['em_deriva']} em deriva · {r['a_vigiar']} a vigiar", ""]
    l += [f"- {a}" for a in r["avisos"]] + ["", "| Coluna | Tipo | PSI | Nível |", "| --- | --- | ---: | --- |"]
    l += [f"| {c['coluna']} | {c['tipo']} | {c['psi']} | {c['nivel']} |" for c in r["colunas"]]
    return "\n".join(l) + "\n\nPSI mede mudança de distribuição, não a sua causa: confirmar primeiro se é erro de dados.\n"


def _md_anom(r: dict) -> str:
    l = [f"# Anomalias · {r['ficheiro']}", "", f"**Estado:** {r['estado']} · {r['anomalias']} ponto(s) fora de |z| > {r['limiar_z']} nos últimos {r['ultimos_pontos']}", "",
         "| Grupo | Data | Valor | Nível habitual | Desvio % | z |", "| --- | --- | ---: | ---: | ---: | ---: |"]
    l += [f"| {a['grupo']} | {a['data']} | {a['valor']} | {a['nivel_habitual']} | {a['desvio_pct']} | {a['z']} |" for a in r["achados"]]
    return "\n".join(l) + "\n\nUma anomalia pede primeiro verificação dos dados e só depois explicação de negócio.\n"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="python -m foundry drift", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("psi"); p.add_argument("referencia"); p.add_argument("atual"); p.add_argument("--colunas"); p.add_argument("--out")
    n = sub.add_parser("anomalias"); n.add_argument("serie"); n.add_argument("--data", required=True); n.add_argument("--valor", required=True)
    n.add_argument("--grupo"); n.add_argument("--ultimos", type=int, default=4); n.add_argument("--limiar", type=float, default=3.5); n.add_argument("--out")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "psi":
            r = psi(a.referencia, a.atual, a.colunas.split(",") if a.colunas else None)
            comum.emitir(r, a.out, "deriva", _md_psi(r))
        else:
            r = anomalias(a.serie, a.data, a.valor, a.grupo, a.ultimos, a.limiar)
            comum.emitir(r, a.out, "anomalias", _md_anom(r))
    except (ValueError, OSError) as e:
        print(f"Erro de dados: {e}")
        return 2
    return 0
