"""Armazenamento local em SQLite (dojo_storage.db): execuções, tarefas, eventos e metadados.

A base é local a cada máquina e nunca é versionada. O que a equipa partilha vive em git
(escritorio/, cerebro/, .claude/). Nada é apagado: tarefas fechadas passam a «arquivada».
"""
from __future__ import annotations
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timedelta
from . import config

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS execucoes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, rotina TEXT, agente TEXT NOT NULL, origem TEXT NOT NULL,
  pedido TEXT, inicio TEXT NOT NULL, fim TEXT, estado TEXT NOT NULL, resumo TEXT, saida TEXT,
  duracao_s REAL, custo_usd REAL, turnos INTEGER);
CREATE INDEX IF NOT EXISTS ix_exec_inicio ON execucoes(inicio);
CREATE TABLE IF NOT EXISTS tarefas (
  id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT NOT NULL, agente TEXT, fase TEXT NOT NULL DEFAULT 'ingestao',
  estado TEXT NOT NULL DEFAULT 'pendente', foco INTEGER NOT NULL DEFAULT 0, prazo TEXT, notas TEXT,
  origem TEXT, criado TEXT NOT NULL, atualizado TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS eventos (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, agente TEXT, nivel TEXT NOT NULL DEFAULT 'info',
  titulo TEXT NOT NULL, detalhe TEXT);
CREATE TABLE IF NOT EXISTS meta (chave TEXT PRIMARY KEY, valor TEXT);
"""
_trinco = threading.Lock()


def agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def ligar() -> sqlite3.Connection:
    con = sqlite3.connect(config.caminho_bd(), timeout=30)
    con.row_factory = sqlite3.Row
    con.executescript(_ESQUEMA)
    return con


def _exec(sql: str, args=()) -> int:
    with _trinco, closing(ligar()) as con, con:
        return con.execute(sql, args).lastrowid


def _ler(sql: str, args=()) -> list[dict]:
    with closing(ligar()) as con:
        return [dict(r) for r in con.execute(sql, args)]


# ---------------------------------------------------------------- execuções
def execucao_abrir(agente: str, origem: str, rotina: str | None, pedido: str | None) -> int:
    return _exec("INSERT INTO execucoes(rotina,agente,origem,pedido,inicio,estado) VALUES(?,?,?,?,?,'em_curso')",
                 (rotina, agente, origem, pedido, agora()))


def execucao_fechar(eid: int, estado: str, resumo: str, saida: str, duracao_s: float,
                    custo_usd: float | None = None, turnos: int | None = None) -> None:
    _exec("UPDATE execucoes SET fim=?,estado=?,resumo=?,saida=?,duracao_s=?,custo_usd=?,turnos=? WHERE id=?",
          (agora(), estado, resumo, saida, round(duracao_s, 1), custo_usd, turnos, eid))


def execucao(eid: int) -> dict | None:
    r = _ler("SELECT * FROM execucoes WHERE id=?", (eid,))
    return r[0] if r else None


def execucoes(limite: int = 40) -> list[dict]:
    return _ler("SELECT id,rotina,agente,origem,pedido,inicio,fim,estado,resumo,duracao_s,custo_usd,turnos "
                "FROM execucoes ORDER BY id DESC LIMIT ?", (limite,))


def ultima_por_rotina() -> dict[str, dict]:
    linhas = _ler("SELECT e.id,e.rotina,e.inicio,e.fim,e.estado,e.resumo FROM execucoes e JOIN "
                  "(SELECT rotina, MAX(id) mid FROM execucoes WHERE rotina IS NOT NULL GROUP BY rotina) u ON u.mid=e.id")
    return {l["rotina"]: l for l in linhas}


def ultima_por_agente() -> dict[str, dict]:
    linhas = _ler("SELECT e.id,e.agente,e.inicio,e.estado,e.resumo FROM execucoes e JOIN "
                  "(SELECT agente, MAX(id) mid FROM execucoes GROUP BY agente) u ON u.mid=e.id")
    return {l["agente"]: l for l in linhas}


def fechar_orfas() -> int:
    """Execuções que ficaram «em_curso» de um arranque anterior passam a «falhou» (o motor foi interrompido)."""
    orfas = _ler("SELECT id FROM execucoes WHERE estado='em_curso'")
    for o in orfas:
        _exec("UPDATE execucoes SET estado='falhou', fim=?, resumo='Motor interrompido antes de terminar' WHERE id=?",
              (agora(), o["id"]))
    return len(orfas)


def telemetria(dias: int = 7) -> dict:
    desde = (datetime.now() - timedelta(days=dias)).isoformat(timespec="seconds")
    hoje = datetime.now().strftime("%Y-%m-%d")
    tot = _ler("SELECT estado, COUNT(*) n, COALESCE(SUM(duracao_s),0) dur, COALESCE(SUM(custo_usd),0) custo "
               "FROM execucoes WHERE inicio>=? AND estado NOT IN ('em_curso','ignorada') GROUP BY estado", (desde,))
    por_estado = {t["estado"]: t["n"] for t in tot}
    n = sum(por_estado.values())
    boas = por_estado.get("ok", 0) + por_estado.get("avisos", 0)
    return {
        "dias": dias,
        "execucoes": n,
        "por_estado": por_estado,
        "taxa_sucesso": round(100 * boas / n, 1) if n else None,
        "duracao_media_s": round(sum(t["dur"] for t in tot) / n, 1) if n else None,
        "custo_usd": round(sum(t["custo"] for t in tot), 4),
        "hoje": _ler("SELECT COUNT(*) n FROM execucoes WHERE substr(inicio,1,10)=? AND estado!='ignorada'", (hoje,))[0]["n"],
        "falhas_hoje": _ler("SELECT COUNT(*) n FROM execucoes WHERE substr(inicio,1,10)=? AND estado='falhou'", (hoje,))[0]["n"],
        "por_dia": _ler("SELECT substr(inicio,1,10) dia, SUM(estado IN ('ok','avisos')) boas, SUM(estado='falhou') falhas "
                        "FROM execucoes WHERE inicio>=? AND estado NOT IN ('em_curso','ignorada') GROUP BY dia ORDER BY dia", (desde,)),
        "por_agente": _ler("SELECT agente, COUNT(*) n, SUM(estado IN ('ok','avisos')) boas, SUM(estado='falhou') falhas, "
                           "ROUND(AVG(duracao_s),1) dur FROM execucoes WHERE inicio>=? AND estado NOT IN ('em_curso','ignorada') "
                           "GROUP BY agente ORDER BY n DESC", (desde,)),
    }


# ---------------------------------------------------------------- tarefas
def tarefa_criar(titulo: str, agente: str | None = None, fase: str = "ingestao", estado: str = "pendente",
                 prazo: str | None = None, notas: str | None = None, origem: str | None = None) -> int:
    if fase not in config.FASES:
        raise ValueError(f"fase: uma de {config.FASES}")
    if estado not in config.ESTADOS_TAREFA:
        raise ValueError(f"estado: um de {config.ESTADOS_TAREFA}")
    t = agora()
    return _exec("INSERT INTO tarefas(titulo,agente,fase,estado,prazo,notas,origem,criado,atualizado) VALUES(?,?,?,?,?,?,?,?,?)",
                 (titulo.strip(), agente, fase, estado, prazo, notas, origem, t, t))


def tarefa_atualizar(tid: int, **campos) -> None:
    permitidos = {"titulo", "agente", "fase", "estado", "foco", "prazo", "notas"}
    campos = {k: v for k, v in campos.items() if k in permitidos and v is not None}
    if "fase" in campos and campos["fase"] not in config.FASES:
        raise ValueError(f"fase: uma de {config.FASES}")
    if "estado" in campos and campos["estado"] not in config.ESTADOS_TAREFA:
        raise ValueError(f"estado: um de {config.ESTADOS_TAREFA}")
    if campos.get("foco"):
        em_foco = _ler("SELECT COUNT(*) n FROM tarefas WHERE foco=1 AND estado NOT IN ('concluida','arquivada') AND id!=?", (tid,))[0]["n"]
        if em_foco >= 3:
            raise ValueError("já há 3 tarefas em foco: retira uma primeiro")
    if not campos:
        return
    sets = ", ".join(f"{k}=?" for k in campos) + ", atualizado=?"
    _exec(f"UPDATE tarefas SET {sets} WHERE id=?", (*campos.values(), agora(), tid))


def tarefas(incluir_arquivadas: bool = False) -> list[dict]:
    onde = "" if incluir_arquivadas else "WHERE estado!='arquivada'"
    return _ler(f"SELECT * FROM tarefas {onde} ORDER BY foco DESC, CASE estado WHEN 'bloqueada' THEN 0 WHEN 'em_curso' THEN 1 "
                "WHEN 'pendente' THEN 2 ELSE 3 END, COALESCE(prazo,'9999'), id")


# ---------------------------------------------------------------- eventos e meta
def evento(titulo: str, agente: str | None = None, nivel: str = "info", detalhe: str | None = None) -> int:
    if nivel not in ("info", "ok", "aviso", "erro"):
        nivel = "info"
    return _exec("INSERT INTO eventos(ts,agente,nivel,titulo,detalhe) VALUES(?,?,?,?,?)", (agora(), agente, nivel, titulo, detalhe))


def eventos(limite: int = 60) -> list[dict]:
    return _ler("SELECT * FROM eventos ORDER BY id DESC LIMIT ?", (limite,))


def meta_ler(chave: str, omissao: str | None = None) -> str | None:
    r = _ler("SELECT valor FROM meta WHERE chave=?", (chave,))
    return r[0]["valor"] if r else omissao


def meta_gravar(chave: str, valor: str) -> None:
    _exec("INSERT INTO meta(chave,valor) VALUES(?,?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor", (chave, valor))
