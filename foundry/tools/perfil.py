"""Perfil de qualidade de um CSV: nulos, duplicados, tipos, chave, frescura e valores extremos.

Uso: python -m foundry perfil <ficheiro.csv> [--chave col1,col2] [--data coluna] [--max-dias 2] [--out pasta]
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import date
from . import comum


def perfilar(caminho: str, chave: list[str] | None = None, col_data: str | None = None, max_dias: int | None = None,
             sep: str | None = None, encoding: str | None = None, hoje: date | None = None) -> dict:
    colunas, linhas, opcoes = comum.ler_csv(caminho, sep, encoding)
    dec = opcoes["decimal"]
    n = len(linhas)
    avisos: list[str] = []
    cols = []
    for c in colunas:
        valores = [l.get(c, "") for l in linhas]
        preenchidos = [v for v in valores if not comum.vazio(v)]
        nums = [x for x in (comum.num(v, dec) for v in preenchidos) if x is not None]
        datas = [d for d in (comum.data(v) for v in preenchidos) if d is not None]
        if preenchidos and len(datas) >= 0.95 * len(preenchidos) and not (len(nums) == len(preenchidos) and all(len(v) < 8 for v in preenchidos)):
            tipo = "data"
        elif preenchidos and len(nums) >= 0.95 * len(preenchidos):
            tipo = "inteiro" if all(float(x).is_integer() for x in nums) else "decimal"
        else:
            tipo = "texto"
        info = {"coluna": c, "tipo": tipo, "nulos": n - len(preenchidos), "nulos_pct": round(100 * (n - len(preenchidos)) / n, 2) if n else 0,
                "distintos": len(set(preenchidos))}
        if tipo in ("inteiro", "decimal") and nums:
            z = comum.z_robusto(nums)
            info.update(minimo=min(nums), maximo=max(nums), media=round(sum(nums) / len(nums), 4),
                        negativos=sum(x < 0 for x in nums), extremos=sum(1 for v in z if v is not None and abs(v) > 3.5),
                        nao_numericos=len(preenchidos) - len(nums))
            if info["nao_numericos"]:
                avisos.append(f"{c}: {info['nao_numericos']} valor(es) não numérico(s) numa coluna numérica")
        elif tipo == "data" and datas:
            info.update(minimo=min(datas).isoformat(), maximo=max(datas).isoformat(), invalidas=len(preenchidos) - len(datas))
            if info["invalidas"]:
                avisos.append(f"{c}: {info['invalidas']} data(s) ilegível(eis)")
        else:
            info["mais_frequentes"] = [{"valor": v[:40], "n": k} for v, k in Counter(preenchidos).most_common(3)]
            sujos = sum(1 for v in valores if v != v.strip())
            variantes = len({v.lower() for v in preenchidos}) < info["distintos"]
            if variantes:
                avisos.append(f"{c}: o mesmo valor aparece com maiúsculas/minúsculas diferentes")
            info["espacos_a_volta"] = sujos
        if info["nulos_pct"] >= 20:
            avisos.append(f"{c}: {info['nulos_pct']}% de nulos")
        cols.append(info)

    duplicadas = n - len({tuple(l.get(c, "") for c in colunas) for l in linhas})
    if duplicadas:
        avisos.append(f"{duplicadas} linha(s) exatamente duplicada(s): confirmar com o dono dos dados antes de remover")
    res = {"ficheiro": caminho, "linhas": n, "colunas": len(colunas), "duplicadas": duplicadas, "opcoes": opcoes}
    if n == 0:
        avisos.append("ficheiro sem linhas de dados")
    if chave:
        em_falta = [c for c in chave if c not in colunas]
        if em_falta:
            raise ValueError(f"coluna(s) de chave inexistente(s): {', '.join(em_falta)}")
        cont = Counter(tuple(l.get(c, "") for c in chave) for l in linhas)
        rep = sum(k - 1 for k in cont.values() if k > 1)
        nulas = sum(1 for l in linhas if any(comum.vazio(l.get(c)) for c in chave))
        res["chave"] = {"colunas": chave, "repetidas": rep, "com_nulos": nulas, "unica": rep == 0 and nulas == 0}
        if rep or nulas:
            avisos.append(f"chave {'+'.join(chave)} não é única: {rep} repetição(ões), {nulas} linha(s) com nulos")
    if col_data:
        if col_data not in colunas:
            raise ValueError(f"coluna de data inexistente: {col_data}")
        ds = [d for d in (comum.data(l.get(col_data)) for l in linhas) if d]
        if ds:
            atraso = ((hoje or date.today()) - max(ds)).days
            res["frescura"] = {"coluna": col_data, "ultima_data": max(ds).isoformat(), "dias_de_atraso": atraso}
            if max_dias is not None and atraso > max_dias:
                avisos.append(f"dados desatualizados: última data {max(ds).isoformat()} ({atraso} dias; limite {max_dias})")
            em_falta = _dias_em_falta(ds)
            if em_falta:
                res["frescura"]["buracos"] = em_falta[:10]
                avisos.append(f"{len(em_falta)} intervalo(s) sem datas na série (ver frescura.buracos)")
        else:
            avisos.append(f"{col_data}: nenhuma data legível")
    res.update(estado="avisos" if avisos else "ok", avisos=avisos, detalhe_colunas=cols)
    return res


def _dias_em_falta(ds: list[date]) -> list[str]:
    """Buracos maiores do que 3× o passo habitual da série (diária, semanal, mensal…)."""
    u = sorted(set(ds))
    if len(u) < 6:
        return []
    passos = sorted((b - a).days for a, b in zip(u, u[1:]))
    habitual = passos[len(passos) // 2]
    return [f"{a.isoformat()} → {b.isoformat()}" for a, b in zip(u, u[1:]) if (b - a).days > 3 * max(habitual, 1)]


def _markdown(r: dict) -> str:
    l = [f"# Qualidade de dados · {r['ficheiro']}", "",
         f"**Estado:** {r['estado']} · {r['linhas']} linhas · {r['colunas']} colunas · {r['duplicadas']} duplicadas", ""]
    if r["avisos"]:
        l += ["## Avisos"] + [f"- {a}" for a in r["avisos"]] + [""]
    if "frescura" in r:
        l += [f"**Frescura:** última data {r['frescura']['ultima_data']} ({r['frescura']['dias_de_atraso']} dias)", ""]
    l += ["## Colunas", "", "| Coluna | Tipo | Nulos % | Distintos | Mínimo | Máximo | Extremos |", "| --- | --- | ---: | ---: | --- | --- | ---: |"]
    for c in r["detalhe_colunas"]:
        l.append(f"| {c['coluna']} | {c['tipo']} | {c['nulos_pct']} | {c['distintos']} | {c.get('minimo', '')} | {c.get('maximo', '')} | {c.get('extremos', '')} |")
    return "\n".join(l) + "\n"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="python -m foundry perfil", description=__doc__)
    ap.add_argument("ficheiro"); ap.add_argument("--chave"); ap.add_argument("--data"); ap.add_argument("--max-dias", type=int)
    ap.add_argument("--sep"); ap.add_argument("--encoding"); ap.add_argument("--out")
    a = ap.parse_args(argv)
    try:
        r = perfilar(a.ficheiro, a.chave.split(",") if a.chave else None, a.data, a.max_dias, a.sep, a.encoding)
    except (ValueError, OSError) as e:
        print(f"Erro de dados: {e}")
        return 2
    comum.emitir(r, a.out, "qualidade", _markdown(r))
    return 0
