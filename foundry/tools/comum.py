"""Leitura tolerante de CSV (ERP português incluído) e estatística robusta, só com a biblioteca-padrão."""
from __future__ import annotations
import csv
import json
import statistics
from datetime import date, datetime
from pathlib import Path

_FORMATOS_DATA = ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y", "%d-%m-%Y",
                  "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%Y/%m/%d", "%Y%m%d")
VAZIOS = {"", "null", "none", "nan", "n/a", "na", "#n/d", "-"}


def ler_csv(caminho: str, sep: str | None = None, encoding: str | None = None) -> tuple[list[str], list[dict], dict]:
    """Devolve (colunas, linhas, opções detetadas). Separador e codificação são detetados quando não indicados."""
    bruto = Path(caminho).read_bytes()
    texto = None
    for enc in ([encoding] if encoding else ["utf-8-sig", "cp1252"]):
        try:
            texto = bruto.decode(enc)
            encoding = enc
            break
        except UnicodeDecodeError:
            continue
    if texto is None:
        raise ValueError(f"não foi possível ler {caminho}: indica --encoding")
    if not sep:
        primeira = texto.split("\n", 1)[0]
        sep = max((";", ",", "\t", "|"), key=primeira.count)
    leitor = csv.DictReader(texto.splitlines(), delimiter=sep)
    colunas = [c.strip() for c in (leitor.fieldnames or [])]
    if not colunas:
        raise ValueError(f"{caminho}: ficheiro vazio ou sem cabeçalho")
    linhas = [{(k or "").strip(): (v or "").strip() for k, v in l.items() if k is not None} for l in leitor]
    return colunas, linhas, {"sep": sep, "encoding": encoding, "decimal": "," if sep == ";" else "."}


def vazio(v) -> bool:
    return v is None or str(v).strip().lower() in VAZIOS


def num(v, decimal: str = ".") -> float | None:
    if vazio(v):
        return None
    s = str(v).strip().replace(" ", "").replace(" ", "").rstrip("%€")
    if decimal == ",":
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "") if s.count(",") and "." in s else s
    try:
        x = float(s)
        return x if x == x and abs(x) != float("inf") else None
    except ValueError:
        return None


def data(v) -> date | None:
    if vazio(v):
        return None
    s = str(v).strip()[:19]
    for f in _FORMATOS_DATA:
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            continue
    return None


def momento(v) -> datetime | None:
    if vazio(v):
        return None
    s = str(v).strip()[:19]
    for f in _FORMATOS_DATA:
        try:
            return datetime.strptime(s, f)
        except ValueError:
            continue
    return None


def z_robusto(valores: list[float]) -> list[float | None]:
    """z = 0,6745 × (x − mediana) / MAD. Com MAD nulo (série constante) devolve None: não se afirma anomalia."""
    if len(valores) < 5:
        return [None] * len(valores)
    med = statistics.median(valores)
    mad = statistics.median(abs(x - med) for x in valores)
    if mad == 0:
        return [None] * len(valores)
    return [0.6745 * (x - med) / mad for x in valores]


def emitir(resultado: dict, out: str | None, nome: str, markdown: str | None = None) -> None:
    """Grava <out>/<nome>.json (+ .md) e imprime uma linha JSON curta com o essencial."""
    ficheiros = []
    if out:
        pasta = Path(out)
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / f"{nome}.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        ficheiros.append(str(pasta / f"{nome}.json"))
        if markdown:
            (pasta / f"{nome}.md").write_text(markdown, encoding="utf-8")
            ficheiros.append(str(pasta / f"{nome}.md"))
    curto = {k: v for k, v in resultado.items() if not isinstance(v, (list, dict)) or k in ("avisos", "resumo")}
    curto["ficheiros"] = ficheiros
    print(json.dumps(curto, ensure_ascii=False, default=str))


def fmt(x: float | None, casas: int = 1) -> str:
    if x is None:
        return "—"
    s = f"{x:,.{casas}f}".replace(",", " ").replace(".", ",")
    return s
