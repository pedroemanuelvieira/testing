"""Monitor de refreshes e pipelines a partir de um registo exportado (CSV).

Uso: python -m foundry refresh <registo.csv> [--horas 24] [--max-atraso-h 26] [--agora AAAA-MM-DDTHH:MM] [--out pasta]

Colunas esperadas (nomes flexíveis): objeto (dataset|pipeline|nome|objeto), inicio, fim, estado, erro (opcional).
Reporta falhas na janela, objetos sem sucesso recente, durações anómalas (> 2× a mediana do próprio objeto)
e falhas repetidas. Não lê serviços externos: trabalha sobre o que foi exportado para inbox/refresh/.
"""
from __future__ import annotations
import argparse
import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from . import comum

_SIN = {"objeto": ("objeto", "dataset", "pipeline", "nome", "name", "modelo", "job"), "inicio": ("inicio", "início", "start", "starttime", "start_time"),
        "fim": ("fim", "end", "endtime", "end_time"), "estado": ("estado", "status", "resultado"), "erro": ("erro", "error", "mensagem", "message")}
_OK = {"ok", "sucesso", "success", "succeeded", "completed", "concluido", "concluído"}
_FALHA = {"falhou", "erro", "failed", "failure", "error", "cancelled", "cancelado", "timeout"}


def analisar(caminho: str, horas: int = 24, max_atraso_h: int = 26, agora: datetime | None = None) -> dict:
    cols, linhas, _ = comum.ler_csv(caminho)
    mapa = {k: next((c for c in cols if c.lower().replace(" ", "_") in v), None) for k, v in _SIN.items()}
    em_falta = [k for k in ("objeto", "inicio", "estado") if not mapa[k]]
    if em_falta:
        raise ValueError(f"colunas em falta: {', '.join(em_falta)} (encontradas: {', '.join(cols)})")
    corridas, ilegiveis = defaultdict(list), 0
    for l in linhas:
        ini = comum.momento(l.get(mapa["inicio"]))
        if not ini:
            ilegiveis += 1
            continue
        fim = comum.momento(l.get(mapa["fim"])) if mapa["fim"] else None
        est = (l.get(mapa["estado"]) or "").strip().lower()
        corridas[l.get(mapa["objeto"]) or "(sem nome)"].append({
            "inicio": ini, "fim": fim, "ok": est in _OK, "falha": est in _FALHA, "estado": est,
            "erro": (l.get(mapa["erro"]) or "")[:200] if mapa["erro"] else "",
            "dur": (fim - ini).total_seconds() / 60 if fim and fim >= ini else None})
    if not corridas:
        raise ValueError("nenhuma execução legível no registo")
    agora = agora or max(c["inicio"] for cs in corridas.values() for c in cs)
    desde = agora - timedelta(hours=horas)
    falhas, atrasados, lentos, repetidas = [], [], [], []
    tot = boas = 0
    for obj, cs in sorted(corridas.items()):
        cs.sort(key=lambda c: c["inicio"])
        na_janela = [c for c in cs if desde <= c["inicio"] <= agora]
        tot += len(na_janela)
        boas += sum(c["ok"] for c in na_janela)
        for c in na_janela:
            if c["falha"]:
                falhas.append({"objeto": obj, "inicio": c["inicio"].isoformat(timespec="minutes"), "erro": c["erro"] or "(sem mensagem)"})
        ultimo_ok = max((c["inicio"] for c in cs if c["ok"] and c["inicio"] <= agora), default=None)
        if ultimo_ok is None or (agora - ultimo_ok).total_seconds() / 3600 > max_atraso_h:
            atrasados.append({"objeto": obj, "ultimo_sucesso": ultimo_ok.isoformat(timespec="minutes") if ultimo_ok else None,
                              "horas": round((agora - ultimo_ok).total_seconds() / 3600, 1) if ultimo_ok else None})
        durs = [c["dur"] for c in cs if c["ok"] and c["dur"] is not None and c["inicio"] < desde]
        if len(durs) >= 5:
            med = statistics.median(durs)
            for c in na_janela:
                if c["ok"] and c["dur"] is not None and med > 0 and c["dur"] > 2 * med and c["dur"] - med > 2:
                    lentos.append({"objeto": obj, "inicio": c["inicio"].isoformat(timespec="minutes"), "minutos": round(c["dur"], 1), "mediana": round(med, 1)})
        ultimas = [c for c in cs if c["inicio"] <= agora][-3:]
        if len(ultimas) == 3 and all(c["falha"] for c in ultimas):
            repetidas.append(obj)
    avisos = []
    if falhas:
        avisos.append(f"{len(falhas)} falha(s) nas últimas {horas} h em {len({f['objeto'] for f in falhas})} objeto(s)")
    if repetidas:
        avisos.append("3 falhas seguidas: " + ", ".join(repetidas))
    if atrasados:
        avisos.append(f"{len(atrasados)} objeto(s) sem sucesso há mais de {max_atraso_h} h")
    if lentos:
        avisos.append(f"{len(lentos)} execução(ões) com mais do dobro da duração habitual")
    if ilegiveis:
        avisos.append(f"{ilegiveis} linha(s) com início ilegível ignorada(s)")
    estado = "falhou" if repetidas else ("avisos" if avisos else "ok")
    return {"ficheiro": caminho, "avaliado_em": agora.isoformat(timespec="minutes"), "janela_h": horas, "objetos": len(corridas),
            "execucoes_janela": tot, "taxa_sucesso": round(100 * boas / tot, 1) if tot else None, "estado": estado, "avisos": avisos,
            "falhas": falhas, "falhas_repetidas": repetidas, "atrasados": atrasados, "lentos": lentos}


def _markdown(r: dict) -> str:
    l = [f"# Refreshes e pipelines · {r['avaliado_em']}", "",
         f"**Estado:** {r['estado']} · {r['objetos']} objetos · {r['execucoes_janela']} execuções em {r['janela_h']} h · sucesso {r['taxa_sucesso']}%", ""]
    l += [f"- {a}" for a in r["avisos"]]
    if r["falhas"]:
        l += ["", "## Falhas", "", "| Objeto | Início | Erro |", "| --- | --- | --- |"] + [f"| {f['objeto']} | {f['inicio']} | {f['erro']} |" for f in r["falhas"]]
    if r["atrasados"]:
        l += ["", "## Sem sucesso recente", "", "| Objeto | Último sucesso | Horas |", "| --- | --- | ---: |"]
        l += [f"| {a['objeto']} | {a['ultimo_sucesso'] or 'nunca'} | {a['horas'] if a['horas'] is not None else '—'} |" for a in r["atrasados"]]
    if r["lentos"]:
        l += ["", "## Mais lentos do que o habitual", "", "| Objeto | Início | Minutos | Mediana |", "| --- | --- | ---: | ---: |"]
        l += [f"| {s['objeto']} | {s['inicio']} | {s['minutos']} | {s['mediana']} |" for s in r["lentos"]]
    return "\n".join(l) + "\n"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="python -m foundry refresh", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("registo"); ap.add_argument("--horas", type=int, default=24); ap.add_argument("--max-atraso-h", type=int, default=26)
    ap.add_argument("--agora"); ap.add_argument("--out")
    a = ap.parse_args(argv)
    try:
        agora = datetime.fromisoformat(a.agora) if a.agora else None
        r = analisar(a.registo, a.horas, a.max_atraso_h, agora)
    except (ValueError, OSError) as e:
        print(f"Erro de dados: {e}")
        return 2
    comum.emitir(r, a.out, "refresh", _markdown(r))
    return 0
