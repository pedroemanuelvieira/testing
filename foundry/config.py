"""Caminhos e leitura da arquitetura declarativa do escritório (escritorio/*.json)."""
from __future__ import annotations
import json
import os
from pathlib import Path

RAIZ = Path(os.environ.get("FOUNDRY_RAIZ") or Path(__file__).resolve().parent.parent)
ESCRITORIO = RAIZ / "escritorio"
UI = Path(__file__).resolve().parent / "ui"
PASTAS = ("inbox/pedidos", "inbox/dados", "inbox/modelos", "inbox/refresh", "inbox/reunioes", "out", "done")
ESTADOS_REGISTO = ("documentado", "configurado", "instalado", "verificado", "producao")
FASES = ("ingestao", "transformacao", "ml", "producao")
ESTADOS_TAREFA = ("pendente", "em_curso", "bloqueada", "concluida", "arquivada")


def caminho_bd() -> Path:
    return Path(os.environ.get("FOUNDRY_BD") or RAIZ / "dojo_storage.db")


def _ler(nome: str) -> dict:
    with open(ESCRITORIO / nome, encoding="utf-8") as f:
        return json.load(f)


def equipa() -> dict:
    return _ler("equipa.json")


def rotinas() -> list[dict]:
    return _ler("rotinas.json")["rotinas"]


def agente(agente_id: str) -> dict | None:
    return next((a for a in equipa()["agentes"] if a["id"] == agente_id), None)


def rotina(rotina_id: str) -> dict | None:
    return next((r for r in rotinas() if r["id"] == rotina_id), None)


def validar() -> list[str]:
    """Verifica a coerência entre equipa.json, rotinas.json, agentes e skills. Devolve a lista de erros."""
    from . import cron
    erros: list[str] = []
    eq = equipa()
    ids = [a["id"] for a in eq["agentes"]]
    if len(ids) != len(set(ids)):
        erros.append("equipa.json: ids de agente repetidos")
    skills_dir = RAIZ / ".claude" / "skills"
    for a in eq["agentes"]:
        if a["estado"] not in ESTADOS_REGISTO:
            erros.append(f"{a['id']}: estado desconhecido «{a['estado']}»")
        if a.get("tipo") != "orquestrador" and not (RAIZ / ".claude" / "agents" / f"{a['id']}.md").exists():
            erros.append(f"{a['id']}: falta .claude/agents/{a['id']}.md")
        for s in a.get("skills", []):
            if not (skills_dir / s / "SKILL.md").exists():
                erros.append(f"{a['id']}: skill «{s}» sem .claude/skills/{s}/SKILL.md")
    for p in eq.get("projetos_ml", []):
        if not (skills_dir / p["skill"] / "SKILL.md").exists():
            erros.append(f"projeto {p['numero']}: skill «{p['skill']}» em falta")
    vistos = set()
    for r in rotinas():
        if r["id"] in vistos:
            erros.append(f"rotina repetida: {r['id']}")
        vistos.add(r["id"])
        if r["agente"] not in ids:
            erros.append(f"rotina {r['id']}: agente desconhecido «{r['agente']}»")
        if r.get("cron"):
            try:
                cron.analisar(r["cron"])
            except ValueError as e:
                erros.append(f"rotina {r['id']}: cron inválido ({e})")
    return erros
