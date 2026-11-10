"""Executor: invoca um funcionário através do Claude Code CLI (`claude -p`) e regista o resultado.

Usa a subscrição Claude de quem corre o motor (sem chaves de API). O modo «simulado» serve para
demonstrações e testes; nunca é escolhido em silêncio: sem o CLI instalado a execução fica «falhou».
"""
from __future__ import annotations
import glob
import json
import os
import re
import shutil
import subprocess
import time
from . import config, db

RODAPE = (
    "\n\nTermina a resposta com exatamente estas duas linhas, sem mais nada depois:\n"
    "ESTADO: ok | avisos | falhou\n"
    "RESUMO: <uma linha com o resultado, sem dados pessoais>"
)
_RE_ESTADO = re.compile(r"^\s*\**ESTADO\**\s*:\s*\**\s*(ok|avisos|falhou)\b", re.I | re.M)
_RE_RESUMO = re.compile(r"^\s*\**RESUMO\**\s*:\s*(.+)$", re.I | re.M)


def modo() -> str:
    return "simulado" if os.environ.get("FOUNDRY_MOTOR", "").lower() in ("simulado", "mock") else "claude"


def claude_cli() -> str | None:
    return os.environ.get("FOUNDRY_CLAUDE") or shutil.which("claude")


def entradas_em_falta(rot: dict) -> str | None:
    """Pré-condição barata: se a rotina exige ficheiros e não há nenhum, não se gasta uma execução."""
    padroes = rot.get("requer") or []
    if not padroes:
        return None
    for p in padroes:
        if any(os.path.isfile(f) and not f.endswith(".gitkeep") for f in glob.glob(str(config.RAIZ / p), recursive=True)):
            return None
    return "sem entradas em " + ", ".join(padroes)


def montar_prompt(ag: dict, rot: dict | None, pedido: str | None, origem: str) -> str:
    cabecalho = f"[Escritório {config.equipa()['escritorio']} · execução {origem}"
    cabecalho += f" · rotina {rot['id']}]" if rot else " · pedido direto]"
    corpo = rot["prompt"] if rot else ""
    if pedido:
        corpo = (corpo + "\n\nPedido adicional: " if corpo else "") + pedido.strip()
    return f"{cabecalho}\n{corpo}{RODAPE}"


def interpretar(texto: str, erro: bool) -> tuple[str, str]:
    estados = _RE_ESTADO.findall(texto or "")
    resumos = _RE_RESUMO.findall(texto or "")
    estado = estados[-1].lower() if estados else ("falhou" if erro else "avisos")
    if erro:
        estado = "falhou"
    resumo = resumos[-1].strip() if resumos else ("" if estados else "Resposta sem linha de ESTADO: rever a saída")
    if not resumo:
        linhas = [l.strip() for l in (texto or "").splitlines() if l.strip() and not _RE_ESTADO.match(l)]
        resumo = linhas[-1] if linhas else "sem resumo"
    return estado, resumo[:300]


def _simular(ag: dict, rot: dict | None, pedido: str | None) -> dict:
    time.sleep(float(os.environ.get("FOUNDRY_SIMULADO_ATRASO", "0.3")))
    alvo = rot["id"] if rot else (pedido or "pedido direto")
    return {"texto": f"[SIMULAÇÃO · nenhum modelo foi invocado]\n{ag['nome']} receberia: {alvo}\n\n"
                     f"ESTADO: ok\nRESUMO: simulação de «{alvo}» (sem execução real)",
            "erro": False, "custo": None, "turnos": None}


def _chamar_claude(ag: dict, prompt: str, limite_s: int) -> dict:
    cli = claude_cli()
    if not cli:
        return {"texto": "Claude Code CLI não encontrado no PATH. Instala-o (https://claude.com/claude-code), "
                         "faz `claude` uma vez para iniciar sessão e volta a tentar.\n\nESTADO: falhou\n"
                         "RESUMO: Claude Code CLI não instalado nesta máquina", "erro": True, "custo": None, "turnos": None}
    cmd = [cli, "-p", prompt, "--output-format", "json"]
    if ag.get("tipo") != "orquestrador":
        cmd += ["--agent", ag["id"]]
    cmd += os.environ.get("FOUNDRY_CLAUDE_ARGS", "").split()
    try:
        p = subprocess.run(cmd, cwd=config.RAIZ, capture_output=True, text=True, timeout=limite_s,
                           encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return {"texto": f"Tempo limite de {limite_s}s excedido.\n\nESTADO: falhou\nRESUMO: tempo limite excedido",
                "erro": True, "custo": None, "turnos": None}
    except OSError as e:
        return {"texto": f"Não foi possível lançar o Claude Code CLI: {e}\n\nESTADO: falhou\nRESUMO: erro ao lançar o CLI",
                "erro": True, "custo": None, "turnos": None}
    bruto = (p.stdout or "").strip()
    try:
        d = json.loads(bruto)
        if isinstance(d, list):   # alguns formatos devolvem a lista de mensagens: o resultado é a última
            d = next((x for x in reversed(d) if isinstance(x, dict) and x.get("type") == "result"), {})
        texto = d.get("result") or ""
        erro = bool(d.get("is_error")) or p.returncode != 0
        if erro and not texto:
            texto = (p.stderr or bruto)[-2000:]
        return {"texto": texto, "erro": erro, "custo": d.get("total_cost_usd"), "turnos": d.get("num_turns")}
    except (json.JSONDecodeError, AttributeError):
        texto = bruto or (p.stderr or "").strip()[-2000:] or "O CLI terminou sem resposta."
        return {"texto": texto, "erro": p.returncode != 0, "custo": None, "turnos": None}


def executar(agente_id: str, rotina_id: str | None = None, pedido: str | None = None, origem: str = "manual",
             eid: int | None = None) -> dict:
    """Corre uma rotina ou um pedido direto e devolve a execução registada."""
    rot = config.rotina(rotina_id) if rotina_id else None
    if rotina_id and not rot:
        raise ValueError(f"rotina desconhecida: {rotina_id}")
    ag = config.agente(rot["agente"] if rot else agente_id)
    if not ag:
        raise ValueError(f"agente desconhecido: {agente_id}")
    if not rot and not (pedido or "").strip():
        raise ValueError("indica uma rotina ou escreve um pedido")
    if eid is None:
        eid = db.execucao_abrir(ag["id"], origem, rot["id"] if rot else None, pedido)
    t0 = time.time()
    falta = entradas_em_falta(rot) if rot and not pedido else None
    if falta:
        db.execucao_fechar(eid, "ignorada", falta, "", 0)
        return db.execucao(eid)
    prompt = montar_prompt(ag, rot, pedido, origem)
    limite = int((rot or {}).get("limite_s") or os.environ.get("FOUNDRY_LIMITE_S", "900"))
    r = _simular(ag, rot, pedido) if modo() == "simulado" else _chamar_claude(ag, prompt, limite)
    estado, resumo = interpretar(r["texto"], r["erro"])
    db.execucao_fechar(eid, estado, resumo, r["texto"], time.time() - t0, r["custo"], r["turnos"])
    nivel = {"ok": "ok", "avisos": "aviso", "falhou": "erro"}[estado]
    db.evento(rot["nome"] if rot else "Pedido direto", ag["id"], nivel, resumo)
    return db.execucao(eid)
