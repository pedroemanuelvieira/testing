"""Modelos semânticos Power BI em TMDL (projetos PBIP): revisão, dicionário e matriz de RLS.

  python -m foundry tmdl lint <pasta> [--out pasta]   boas práticas de DAX e de modelo, com regra, gravidade e linha
  python -m foundry tmdl doc  <pasta> [--out pasta]   dicionário de tabelas, colunas, medidas, relações e papéis
  python -m foundry tmdl rls  <pasta> [--out pasta]   papel × tabela, tabelas não protegidas e casos de teste

Só lê ficheiros .tmdl (texto). Nunca abre nem altera binários PBIX/PBIT nem o serviço Power BI.
A revisão é estática: não mede desempenho nem valida resultados; isso faz-se no Power BI Desktop.
"""
from __future__ import annotations
import argparse
import re
from pathlib import Path
from . import comum

_NOME = r"(?:'(?:[^']|'')+'|[^\s=:.]+)"
_RE_OBJ = re.compile(rf"^(table|measure|column|partition|relationship|role|tablePermission|hierarchy|expression)\s+({_NOME})\s*(?:=\s*(.*))?$")
_RE_PROP = re.compile(r"^([A-Za-z]\w*)\s*(?::\s*(.*))?$")
_RE_REF_COL = re.compile(r"(?:'((?:[^']|'')+)'|\b([A-Za-z_]\w*))\[([^\]]+)\]")
_RE_REF_SOLTA = re.compile(r"(?<![\w'\]])\[([^\]]+)\]")
_FUNCOES_UTILIZADOR = ("USERPRINCIPALNAME", "USERNAME", "CUSTOMDATA", "USEROBJECTID")


def _limpar(nome: str) -> str:
    nome = nome.strip()
    return nome[1:-1].replace("''", "'") if nome.startswith("'") and nome.endswith("'") else nome


def _nivel(linha: str) -> int:
    n = 0
    for ch in linha:
        if ch == "\t":
            n += 4
        elif ch == " ":
            n += 1
        else:
            break
    return n // 4


def _sem_ruido(dax: str) -> str:
    """Retira comentários e literais de texto para as regras não dispararem dentro deles."""
    dax = re.sub(r"/\*.*?\*/", " ", dax, flags=re.S)
    dax = re.sub(r"(//|--)[^\n]*", " ", dax)
    return re.sub(r'"(?:[^"]|"")*"', '""', dax)


def ler_modelo(pasta: str) -> dict:
    raiz = Path(pasta)
    ficheiros = sorted(raiz.rglob("*.tmdl")) if raiz.is_dir() else ([raiz] if raiz.suffix == ".tmdl" else [])
    if not ficheiros:
        raise ValueError(f"nenhum ficheiro .tmdl em {pasta} (o projeto tem de estar em formato PBIP/TMDL)")
    m = {"pasta": str(pasta), "tabelas": {}, "relacoes": [], "papeis": [], "ficheiros": len(ficheiros)}
    for f in ficheiros:
        _ler_ficheiro(f, str(f.relative_to(raiz)) if raiz.is_dir() else f.name, m)
    return m


def _ler_ficheiro(f: Path, rel: str, m: dict) -> None:
    linhas = f.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    pilha: list[tuple[int, dict]] = []   # (nível, objeto) dos objetos abertos
    descricao: list[str] = []
    multi: dict | None = None            # objeto cuja expressão continua nas linhas seguintes
    multi_nivel = 0
    for n, bruta in enumerate(linhas, 1):
        if not bruta.strip():
            continue
        nivel, texto = _nivel(bruta), bruta.strip()
        if multi is not None:
            if nivel >= multi_nivel + 2 or texto.startswith("```"):
                if not texto.startswith("```"):
                    multi["expr"] += ("\n" if multi["expr"] else "") + texto
                continue
            multi = None
        if texto.startswith("///"):
            descricao.append(texto[3:].strip())
            continue
        while pilha and pilha[-1][0] >= nivel:
            pilha.pop()
        o = _RE_OBJ.match(texto)
        pai = pilha[-1][1] if pilha else None
        if o and (nivel == 0 or pai is not None):
            tipo, nome, expr = o.group(1), _limpar(o.group(2)), o.group(3)
            obj = {"tipo": tipo, "nome": nome, "expr": (expr or "").strip(), "props": {}, "ficheiro": rel, "linha": n,
                   "descricao": " ".join(descricao)}
            descricao = []
            if tipo == "table":
                obj.update(colunas=[], medidas=[], particoes=[])
                m["tabelas"][nome] = obj
            elif tipo == "relationship":
                m["relacoes"].append(obj)
            elif tipo == "role":
                obj["filtros"] = []
                m["papeis"].append(obj)
            elif pai is not None and pai["tipo"] == "table":
                obj["tabela"] = pai["nome"]
                {"measure": pai["medidas"], "column": pai["colunas"], "partition": pai["particoes"]}.get(tipo, []).append(obj)
            elif pai is not None and pai["tipo"] == "role" and tipo == "tablePermission":
                pai["filtros"].append(obj)
            pilha.append((nivel, obj))
            if expr is not None and not obj["expr"] and tipo in ("measure", "column", "tablePermission"):
                multi, multi_nivel = obj, nivel
            elif obj["expr"].startswith("```"):
                obj["expr"] = obj["expr"].strip("`").strip()
                multi, multi_nivel = obj, nivel
            continue
        descricao = []
        p = _RE_PROP.match(texto)
        if p and pai is not None:
            pai["props"][p.group(1)] = (p.group(2) or "true").strip()
            if p.group(1) == "description" and not pai.get("descricao"):
                pai["descricao"] = (p.group(2) or "").strip().strip('"')


def _ref(texto: str) -> tuple[str, str]:
    partes = re.findall(_NOME, texto.strip())
    return (_limpar(partes[0]), _limpar(partes[1])) if len(partes) >= 2 else (texto.strip(), "")


def _relacoes(m: dict) -> list[dict]:
    saida = []
    for r in m["relacoes"]:
        de, para = _ref(r["props"].get("fromColumn", "")), _ref(r["props"].get("toColumn", ""))
        saida.append({"de_tabela": de[0], "de_coluna": de[1], "para_tabela": para[0], "para_coluna": para[1],
                      "bidirecional": r["props"].get("crossFilteringBehavior") == "bothDirections",
                      "ativa": r["props"].get("isActive", "true") != "false",
                      "muitos_para_muitos": r["props"].get("toCardinality") == "many" and r["props"].get("fromCardinality", "many") == "many",
                      "ficheiro": r["ficheiro"], "linha": r["linha"]})
    return saida


def _dependencias(expr: str, medidas: set[str]) -> tuple[list[str], list[str]]:
    limpo = _sem_ruido(expr)
    cols = sorted({f"{a or b}[{c}]" for a, b, c in _RE_REF_COL.findall(limpo)})
    soltas = sorted({x for x in _RE_REF_SOLTA.findall(limpo)})
    return [s for s in soltas if s in medidas], cols


# ------------------------------------------------------------------ lint
def lint(pasta: str) -> dict:
    m = ler_modelo(pasta)
    rels = _relacoes(m)
    ach: list[dict] = []

    def a(regra, grav, obj, msg, o):
        ach.append({"regra": regra, "gravidade": grav, "objeto": obj, "mensagem": msg, "ficheiro": o["ficheiro"], "linha": o["linha"]})

    medidas = {md["nome"] for t in m["tabelas"].values() for md in t["medidas"]}
    colunas = {(t["nome"], c["nome"]) for t in m["tabelas"].values() for c in t["colunas"]}
    nomes_col = {c for _, c in colunas}
    vistas: dict[str, str] = {}
    for t in m["tabelas"].values():
        if re.match(r"(LocalDateTable_|DateTableTemplate_)", t["nome"]):
            a("T01", "aviso", t["nome"], "tabela de datas automática: desligar «Data/hora automática» e usar um calendário próprio", t)
            continue
        ligada = any(t["nome"] in (r["de_tabela"], r["para_tabela"]) for r in rels)
        if not ligada and not t["medidas"] and len(m["tabelas"]) > 1:
            a("T02", "info", t["nome"], "tabela sem relações nem medidas: confirmar se é necessária", t)
        for md in t["medidas"]:
            alvo, limpo = f"{t['nome']}[{md['nome']}]", _sem_ruido(md["expr"])
            if not md["expr"]:
                a("M00", "erro", alvo, "medida sem expressão", md)
                continue
            if "formatString" not in md["props"] and "formatStringDefinition" not in md["props"]:
                a("M01", "aviso", alvo, "sem formatString: o valor aparece sem formato nos visuais", md)
            if not md["descricao"]:
                a("M02", "info", alvo, "sem descrição (/// antes da medida): entra vazia no dicionário e no Copilot", md)
            if re.search(r"/\s*(?!\s*\d+(?:\.\d+)?\s*(?:[)\n,+\-*]|$))", limpo.replace("//", "")):
                a("M03", "aviso", alvo, "divisão com «/»: usar DIVIDE(numerador, denominador) para tratar a divisão por zero", md)
            if re.search(r"\b(IFERROR|ISERROR)\s*\(", limpo, re.I):
                a("M04", "aviso", alvo, "IFERROR/ISERROR força avaliação linha a linha: tratar a causa (DIVIDE, valores em branco)", md)
            for f in re.finditer(r"\bFILTER\s*\(\s*(?:'((?:[^']|'')+)'|([A-Za-z_]\w*))\s*,", limpo, re.I):
                if (f.group(1) or f.group(2)) in m["tabelas"] and re.search(r"\bCALCULATE(TABLE)?\s*\(", limpo, re.I):
                    a("M05", "aviso", alvo, f"FILTER sobre a tabela inteira «{f.group(1) or f.group(2)}» dentro de CALCULATE: filtrar colunas (KEEPFILTERS ou predicado simples)", md)
                    break
            norm = re.sub(r"\s+", "", limpo).lower()
            if norm in vistas and len(norm) > 12:
                a("M06", "info", alvo, f"expressão igual à de {vistas[norm]}: manter uma só medida", md)
            vistas.setdefault(norm, alvo)
            for solta in set(_RE_REF_SOLTA.findall(limpo)):
                if solta not in medidas and solta not in nomes_col:
                    a("M07", "erro", alvo, f"referência [{solta}] não corresponde a nenhuma medida ou coluna do modelo", md)
            for tab, tab2, col in set(_RE_REF_COL.findall(limpo)):
                tb = tab or tab2
                if tb in m["tabelas"] and (tb, col) not in colunas and col not in medidas:
                    a("M07", "erro", alvo, f"referência {tb}[{col}] não existe no modelo", md)
            if len(re.findall(r"\bIF\s*\(", limpo, re.I)) >= 3:
                a("M08", "info", alvo, "três ou mais IF: SWITCH(TRUE(), …) é mais legível", md)
        fks = {r["de_coluna"] for r in rels if r["de_tabela"] == t["nome"]}
        for c in t["colunas"]:
            alvo = f"{t['nome']}[{c['nome']}]"
            tipo, soma = c["props"].get("dataType", ""), c["props"].get("summarizeBy", "none")
            if re.search(r"(?i)(id|key|sk|codigo|código|code|nif)$", c["nome"]) and tipo in ("int64", "decimal", "double") and soma != "none":
                a("C01", "aviso", alvo, f"coluna de identificação com summarizeBy={soma}: pôr «none» para não ser somada por engano", c)
            if c["nome"] in fks and "isHidden" not in c["props"]:
                a("C02", "info", alvo, "chave estrangeira visível: ocultar para o utilizador filtrar pela dimensão", c)
            if c["expr"]:
                a("C03", "info", alvo, "coluna calculada em DAX: preferir a origem ou o Power Query quando possível", c)
    for r, bruto in zip(rels, m["relacoes"]):
        alvo = f"{r['de_tabela']}[{r['de_coluna']}] → {r['para_tabela']}[{r['para_coluna']}]"
        for tb, col in ((r["de_tabela"], r["de_coluna"]), (r["para_tabela"], r["para_coluna"])):
            if tb in m["tabelas"] and (tb, col) not in colunas:
                a("R00", "erro", alvo, f"a relação usa {tb}[{col}], que não existe", bruto)
        if r["bidirecional"]:
            a("R01", "aviso", alvo, "relação bidirecional: risco de ambiguidade e de RLS inesperado; justificar ou passar a sentido único", bruto)
        if not r["ativa"]:
            a("R02", "info", alvo, "relação inativa: confirmar que há medidas com USERELATIONSHIP que a usam", bruto)
        if r["muitos_para_muitos"]:
            a("R03", "aviso", alvo, "relação muitos-para-muitos: confirmar a granularidade ou criar tabela de ponte", bruto)
    for p in m["papeis"]:
        if not p["filtros"]:
            a("S01", "info", f"papel {p['nome']}", "papel sem filtros: quem o tiver vê todos os dados", p)
        for f in p["filtros"]:
            alvo = f"papel {p['nome']} · {f['nome']}"
            if f["nome"] not in m["tabelas"]:
                a("S03", "erro", alvo, f"o filtro aplica-se à tabela «{f['nome']}», que não existe", f)
            for tab, tab2, col in set(_RE_REF_COL.findall(_sem_ruido(f["expr"]))):
                tb = tab or tab2
                if tb in m["tabelas"] and (tb, col) not in colunas:
                    a("S03", "erro", alvo, f"o filtro refere {tb}[{col}], que não existe", f)
            if not any(fn in f["expr"].upper() for fn in _FUNCOES_UTILIZADOR):
                a("S02", "info", alvo, "filtro estático (sem USERPRINCIPALNAME): correto para papéis por região/área, a confirmar", f)
    ordem = {"erro": 0, "aviso": 1, "info": 2}
    ach.sort(key=lambda x: (ordem[x["gravidade"]], x["ficheiro"], x["linha"]))
    cont = {g: sum(1 for x in ach if x["gravidade"] == g) for g in ordem}
    estado = "falhou" if cont["erro"] else ("avisos" if cont["aviso"] else "ok")
    return {"modelo": pasta, "tabelas": len(m["tabelas"]), "medidas": len(medidas), "relacoes": len(rels), "papeis": len(m["papeis"]),
            "erros": cont["erro"], "avisos_n": cont["aviso"], "infos": cont["info"], "estado": estado,
            "avisos": [f"{x['regra']} {x['objeto']}: {x['mensagem']}" for x in ach if x["gravidade"] != "info"][:12], "achados": ach}


def _md_lint(r: dict) -> str:
    l = [f"# Revisão do modelo · {r['modelo']}", "",
         f"**Estado:** {r['estado']} · {r['erros']} erro(s) · {r['avisos_n']} aviso(s) · {r['infos']} nota(s) · "
         f"{r['tabelas']} tabelas, {r['medidas']} medidas, {r['relacoes']} relações, {r['papeis']} papéis", "",
         "| Gravidade | Regra | Objeto | O que rever | Onde |", "| --- | --- | --- | --- | --- |"]
    l += [f"| {x['gravidade']} | {x['regra']} | {x['objeto']} | {x['mensagem']} | {x['ficheiro']}:{x['linha']} |" for x in r["achados"]]
    return "\n".join(l) + "\n\nRevisão estática: não mede desempenho nem valida números. Publicar só depois de revisão humana.\n"


# ------------------------------------------------------------------ doc
def doc(pasta: str) -> tuple[dict, str]:
    m = ler_modelo(pasta)
    rels = _relacoes(m)
    medidas = {md["nome"] for t in m["tabelas"].values() for md in t["medidas"]}
    l = [f"# Dicionário do modelo · {Path(pasta).name}", "", f"Gerado a partir de {m['ficheiros']} ficheiro(s) TMDL. Não editar à mão: voltar a gerar.", ""]
    n_med = n_col = sem_desc = 0
    dic_medidas = []
    for t in sorted(m["tabelas"].values(), key=lambda x: x["nome"]):
        if re.match(r"(LocalDateTable_|DateTableTemplate_)", t["nome"]):
            continue
        l += [f"## {t['nome']}", "", t["descricao"] or "_Sem descrição._", ""]
        if t["colunas"]:
            l += ["| Coluna | Tipo | Visível | Descrição |", "| --- | --- | --- | --- |"]
            for c in t["colunas"]:
                n_col += 1
                l.append(f"| {c['nome']} | {c['props'].get('dataType', 'calculada' if c['expr'] else '')} | {'não' if 'isHidden' in c['props'] else 'sim'} | {c['descricao']} |")
            l.append("")
        for md in t["medidas"]:
            n_med += 1
            sem_desc += not md["descricao"]
            dm, dc = _dependencias(md["expr"], medidas - {md["nome"]})
            dic_medidas.append({"tabela": t["nome"], "medida": md["nome"], "descricao": md["descricao"], "formato": md["props"].get("formatString", ""),
                                "pasta": md["props"].get("displayFolder", ""), "expressao": md["expr"], "depende_de_medidas": dm, "depende_de_colunas": dc})
            l += [f"### {md['nome']}", "", md["descricao"] or "_Sem descrição._", "",
                  f"- Formato: `{md['props'].get('formatString', '—')}` · Pasta: {md['props'].get('displayFolder', '—')}",
                  f"- Depende de: {', '.join(dm + dc) or '—'}", "", "```dax", md["expr"], "```", ""]
    if rels:
        l += ["## Relações", "", "| De (muitos) | Para (um) | Sentido | Ativa |", "| --- | --- | --- | --- |"]
        l += [f"| {r['de_tabela']}[{r['de_coluna']}] | {r['para_tabela']}[{r['para_coluna']}] | {'ambos' if r['bidirecional'] else 'único'} | {'sim' if r['ativa'] else 'não'} |" for r in rels]
        l += ["", "```mermaid", "flowchart LR"] + [f"  {_mm(r['para_tabela'])} --> {_mm(r['de_tabela'])}" for r in rels] + ["```", ""]
    if m["papeis"]:
        l += ["## Papéis (RLS)", "", "| Papel | Tabela | Filtro |", "| --- | --- | --- |"]
        for p in m["papeis"]:
            l += [f"| {p['nome']} | {f['nome']} | `{f['expr']}` |" for f in p["filtros"]] or [f"| {p['nome']} | — | sem filtros |"]
        l.append("")
    res = {"modelo": pasta, "tabelas": len(m["tabelas"]), "colunas": n_col, "medidas": n_med, "medidas_sem_descricao": sem_desc,
           "relacoes": len(rels), "papeis": len(m["papeis"]), "estado": "avisos" if sem_desc else "ok",
           "avisos": [f"{sem_desc} medida(s) sem descrição"] if sem_desc else [], "dicionario_medidas": dic_medidas}
    return res, "\n".join(l)


def _mm(nome: str) -> str:
    return re.sub(r"\W", "_", nome) + f'["{nome}"]'


# ------------------------------------------------------------------ rls
def rls(pasta: str) -> tuple[dict, str]:
    m = ler_modelo(pasta)
    rels = [r for r in _relacoes(m) if r["ativa"]]
    tabelas = [t for t in m["tabelas"] if not re.match(r"(LocalDateTable_|DateTableTemplate_)", t)]
    if not m["papeis"]:
        res = {"modelo": pasta, "papeis": 0, "estado": "avisos", "avisos": ["o modelo não tem papéis: todos os utilizadores com acesso veem todos os dados"], "matriz": [], "casos": []}
        return res, f"# RLS · {Path(pasta).name}\n\nO modelo não define papéis.\n"
    matriz, casos, avisos = [], [], []
    for p in m["papeis"]:
        filtradas = {f["nome"]: f["expr"] for f in p["filtros"]}
        alcance = set(filtradas)
        mudou = True
        while mudou:   # o filtro propaga do lado «um» para o lado «muitos» (e nos dois sentidos se bidirecional)
            mudou = False
            for r in rels:
                for origem, destino in ((r["para_tabela"], r["de_tabela"]),) + (((r["de_tabela"], r["para_tabela"]),) if r["bidirecional"] else ()):
                    if origem in alcance and destino not in alcance:
                        alcance.add(destino)
                        mudou = True
        livres = [t for t in tabelas if t not in alcance]
        for t in tabelas:
            matriz.append({"papel": p["nome"], "tabela": t, "protecao": "filtro direto" if t in filtradas else ("por relação" if t in alcance else "sem filtro"),
                           "filtro": filtradas.get(t, "")})
        dinamico = any(fn in e.upper() for e in filtradas.values() for fn in _FUNCOES_UTILIZADOR)
        for t, e in filtradas.items():
            casos.append({"papel": p["nome"], "caso": f"Ver como «{p['nome']}»" + (" com o utilizador <UPN_TESTE_A>" if dinamico else ""),
                          "esperado": f"«{t}» mostra só as linhas em que {e}; os totais das tabelas ligadas descem em conformidade"})
        if dinamico:
            casos.append({"papel": p["nome"], "caso": "Ver como o papel com <UPN_TESTE_B> (outro utilizador)", "esperado": "nenhuma linha de <UPN_TESTE_A> é visível; os totais diferem"})
            casos.append({"papel": p["nome"], "caso": "Ver como o papel com um utilizador sem correspondência", "esperado": "relatório vazio, sem erro e sem totais globais"})
        if filtradas and livres:
            avisos.append(f"papel {p['nome']}: tabelas não alcançadas pelo filtro: {', '.join(livres)}")
            casos.append({"papel": p["nome"], "caso": f"Abrir visuais só com {', '.join(livres)}", "esperado": "confirmar que mostrar estes dados sem filtro é aceitável"})
        if not filtradas:
            avisos.append(f"papel {p['nome']}: sem filtros (vê tudo)")
    res = {"modelo": pasta, "papeis": len(m["papeis"]), "tabelas": len(tabelas), "casos_de_teste": len(casos),
           "estado": "avisos" if avisos else "ok", "avisos": avisos, "matriz": matriz, "casos": casos}
    l = [f"# RLS · {Path(pasta).name}", "", f"**Estado:** {res['estado']} · {res['papeis']} papel(éis) · {len(casos)} casos de teste", ""]
    l += [f"- {x}" for x in avisos] + ["", "## Matriz papel × tabela", "", "| Papel | Tabela | Proteção | Filtro |", "| --- | --- | --- | --- |"]
    l += [f"| {x['papel']} | {x['tabela']} | {x['protecao']} | {('`' + x['filtro'] + '`') if x['filtro'] else ''} |" for x in matriz]
    l += ["", "## Casos de teste (executar no Power BI Desktop: Modelação → Ver como)", "", "| Papel | Caso | Resultado esperado | Passou? |", "| --- | --- | --- | --- |"]
    l += [f"| {c['papel']} | {c['caso']} | {c['esperado']} | ☐ |" for c in casos]
    l += ["", "Esta matriz é uma leitura estática do modelo. O RLS só fica validado depois de os casos serem executados por uma pessoa."]
    return res, "\n".join(l) + "\n"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="python -m foundry tmdl", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("acao", choices=("lint", "doc", "rls")); ap.add_argument("pasta"); ap.add_argument("--out")
    a = ap.parse_args(argv)
    try:
        if a.acao == "lint":
            r = lint(a.pasta)
            comum.emitir(r, a.out, "revisao_modelo", _md_lint(r))
            return 1 if r["erros"] else 0
        r, md = doc(a.pasta) if a.acao == "doc" else rls(a.pasta)
        comum.emitir(r, a.out, "dicionario" if a.acao == "doc" else "rls", md)
    except (ValueError, OSError) as e:
        print(f"Erro de dados: {e}")
        return 2
    return 0
