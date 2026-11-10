"""Expressões cron de 5 campos (minuto hora dia-do-mês mês dia-da-semana), na hora local da máquina.

Suporta `*`, listas `a,b`, intervalos `a-b` e passos `*/n` ou `a-b/n`. Dia da semana: 0 ou 7 = domingo.
Como no cron clássico, se dia-do-mês e dia-da-semana estiverem ambos restringidos, basta um deles coincidir.
"""
from __future__ import annotations
from datetime import datetime, timedelta

_LIMITES = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))
_DIAS = ("dom", "seg", "ter", "qua", "qui", "sex", "sáb")


def _campo(texto: str, lo: int, hi: int) -> set[int]:
    valores: set[int] = set()
    for parte in texto.split(","):
        passo = 1
        if "/" in parte:
            parte, p = parte.split("/", 1)
            passo = int(p)
            if passo < 1:
                raise ValueError("passo tem de ser >= 1")
        if parte == "*":
            a, b = lo, hi
        elif "-" in parte:
            a, b = (int(x) for x in parte.split("-", 1))
        else:
            a = b = int(parte)
        if a < lo or b > hi or a > b:
            raise ValueError(f"valor fora de {lo}-{hi}: «{texto}»")
        valores.update(range(a, b + 1, passo))
    return valores


def analisar(expr: str) -> tuple[set[int], set[int], set[int], set[int], set[int], bool, bool]:
    campos = expr.split()
    if len(campos) != 5:
        raise ValueError("são precisos 5 campos")
    m, h, dm, me, ds = (_campo(c, lo, hi) for c, (lo, hi) in zip(campos, _LIMITES))
    ds = {0 if d == 7 else d for d in ds}
    return m, h, dm, me, ds, campos[2] != "*", campos[4] != "*"


def _dia_coincide(p, dt: datetime) -> bool:
    _, _, dm, me, ds, dm_restrito, ds_restrito = p
    if dt.month not in me:
        return False
    no_dm = dt.day in dm
    no_ds = (dt.weekday() + 1) % 7 in ds
    if dm_restrito and ds_restrito:
        return no_dm or no_ds
    return no_dm and no_ds


def coincide(expr: str, dt: datetime) -> bool:
    p = analisar(expr)
    return dt.minute in p[0] and dt.hour in p[1] and _dia_coincide(p, dt)


def proxima(expr: str, depois: datetime) -> datetime | None:
    """Primeira execução estritamente depois de `depois` (procura até 2 anos)."""
    p = analisar(expr)
    dia = depois.replace(second=0, microsecond=0)
    for _ in range(732):
        if _dia_coincide(p, dia):
            for h in sorted(p[1]):
                for m in sorted(p[0]):
                    cand = dia.replace(hour=h, minute=m)
                    if cand > depois:
                        return cand
        dia = (dia + timedelta(days=1)).replace(hour=0, minute=0)
    return None


def anterior(expr: str, ate: datetime, janela_h: int = 24) -> datetime | None:
    """Última execução prevista em [ate - janela, ate]."""
    cand = proxima(expr, ate - timedelta(hours=janela_h))
    ultimo = None
    while cand and cand <= ate:
        ultimo = cand
        cand = proxima(expr, cand)
    return ultimo


def descrever(expr: str) -> str:
    """Leitura humana curta, em português, para a interface."""
    try:
        m, h, dm, me, ds, dm_r, ds_r = analisar(expr)
    except ValueError:
        return expr
    horas = ", ".join(f"{hh:02d}:{mm:02d}" for hh in sorted(h) for mm in sorted(m)) if len(h) * len(m) <= 6 else f"{len(h) * len(m)}×/dia"
    if dm_r and not ds_r:
        quando = "dia " + ", ".join(str(d) for d in sorted(dm)) + " de cada mês"
    elif ds_r and not dm_r:
        if ds == {1, 2, 3, 4, 5}:
            quando = "dias úteis"
        else:
            quando = ", ".join(_DIAS[d] for d in sorted(ds))
    elif not dm_r and not ds_r:
        quando = "todos os dias"
    else:
        quando = "dias " + ",".join(str(d) for d in sorted(dm)) + " ou " + ",".join(_DIAS[d] for d in sorted(ds))
    return f"{quando} · {horas}"
