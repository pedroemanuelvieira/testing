"""Fronteira de dados: procura dados sensíveis em ficheiros antes de os partilhar ou versionar.

Uso: python -m foundry fronteira [caminhos…] [--staged] [--out pasta]
  sem argumentos  verifica cerebro/, escritorio/ e .claude/ (o que a equipa partilha por git)
  --staged        verifica os ficheiros preparados para commit (usado pelo gancho pre-commit)

É um detetor heurístico: pode falhar ou dar falsos positivos e NÃO certifica anonimização.
Os valores encontrados nunca são repetidos por inteiro. Código de saída 1 se houver achados.
"""
from __future__ import annotations
import argparse
import re
import subprocess
from pathlib import Path
from . import comum
from .. import config

_PADROES = [
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]{2,}\b")),
    ("iban", re.compile(r"\b[A-Z]{2}\d{2}(?: ?\d{4}){4,7}(?: ?\d{1,3})?\b")),
    ("telefone", re.compile(r"(?<![\w.])(?:\+351 ?)?(?:9[1236]\d|2\d{2}) ?\d{3} ?\d{3}(?![\w.])")),
    ("credencial", re.compile(r"(?i)\b(?:password|passwd|pwd|secret|api[_-]?key|token|client[_-]?secret)\b\s*[=:]\s*['\"]?[^\s'\"<>{}]{6,}")),
    ("chave", re.compile(r"\b(?:sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16}|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,})")),
    ("ligacao", re.compile(r"(?i)\b(?:Server|Data Source)\s*=\s*[^;]+;[^\n]*(?:Password|Pwd)\s*=")),
]
_NIF = re.compile(r"(?<![\d.,/-])[1235689]\d{8}(?![\d.,/-])")
_PERMITIDOS = re.compile(r"(?i)@(?:example\.(?:com|org)|exemplo\.pt|anthropic\.com)\b|noreply@|<[A-Z_]+>")
_IGNORAR_DIR = {".git", "__pycache__", "node_modules", ".venv", "venv", "motor_ml", "exemplos", "testes"}
_BINARIOS = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".db", ".pbix", ".pbit", ".xlsx", ".ttf", ".woff", ".woff2"}


def _nif_valido(s: str) -> bool:
    soma = sum(int(d) * p for d, p in zip(s[:8], range(9, 1, -1)))
    resto = soma % 11
    return int(s[8]) == (0 if resto < 2 else 11 - resto)


def _mascarar(v: str) -> str:
    v = v.strip()
    return v[:2] + "…" + v[-2:] if len(v) > 6 else "…"


def verificar_texto(texto: str) -> list[dict]:
    achados = []
    for n, linha in enumerate(texto.splitlines(), 1):
        if len(linha) > 4000:
            continue
        for tipo, rx in _PADROES:
            for m in rx.finditer(linha):
                if tipo == "email" and _PERMITIDOS.search(m.group(0)):
                    continue
                if tipo == "credencial" and re.search(r"(?i)[=:]\s*['\"]?(?:<|\$\{|\*{3}|x{4}|exemplo|example|changeme|os\.environ)", m.group(0)):
                    continue
                achados.append({"linha": n, "tipo": tipo, "amostra": _mascarar(m.group(0).split("=")[-1].split(":")[-1] if tipo == "credencial" else m.group(0))})
        for m in _NIF.finditer(linha):
            if _nif_valido(m.group(0)):
                achados.append({"linha": n, "tipo": "nif", "amostra": _mascarar(m.group(0))})
    return achados


def _ficheiros(caminhos: list[str]) -> list[Path]:
    saida = []
    for c in caminhos:
        p = Path(c) if Path(c).is_absolute() else config.RAIZ / c
        if p.is_file():
            saida.append(p)
        elif p.is_dir():
            saida += [f for f in sorted(p.rglob("*")) if f.is_file() and not (set(f.relative_to(p).parts[:-1]) & _IGNORAR_DIR)]
    return [f for f in saida if f.suffix.lower() not in _BINARIOS and f.stat().st_size <= 2_000_000]


def verificar(caminhos: list[str]) -> dict:
    achados = []
    fs = _ficheiros(caminhos)
    for f in fs:
        try:
            texto = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for a in verificar_texto(texto):
            achados.append({"ficheiro": str(f.relative_to(config.RAIZ)) if config.RAIZ in f.parents else str(f), **a})
    por_tipo: dict[str, int] = {}
    for a in achados:
        por_tipo[a["tipo"]] = por_tipo.get(a["tipo"], 0) + 1
    avisos = [f"{a['ficheiro']}:{a['linha']} · {a['tipo']} ({a['amostra']})" for a in achados[:20]]
    return {"ficheiros_verificados": len(fs), "achados": len(achados), "por_tipo": por_tipo, "estado": "avisos" if achados else "ok",
            "avisos": avisos, "detalhe": achados, "nota": "detetor heurístico: não certifica anonimização"}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="python -m foundry fronteira", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("caminhos", nargs="*"); ap.add_argument("--staged", action="store_true"); ap.add_argument("--out")
    a = ap.parse_args(argv)
    caminhos = a.caminhos
    if a.staged:
        p = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"], cwd=config.RAIZ, capture_output=True, text=True)
        caminhos = [l for l in p.stdout.splitlines() if l.strip() and not (set(Path(l).parts) & _IGNORAR_DIR)]
        if not caminhos:
            return 0
    elif not caminhos:
        caminhos = ["cerebro", "escritorio", ".claude", "README.md", "CLAUDE.md"]
    r = verificar(caminhos)
    comum.emitir(r, a.out, "fronteira")
    if r["achados"] and a.staged:
        print("\nCommit bloqueado pela fronteira de dados. Substitui os valores por placeholders (ex.: <CLIENTE_EXEMPLO>) "
              "ou, se forem falsos positivos, confirma com `git commit --no-verify`.")
    return 1 if r["achados"] else 0
