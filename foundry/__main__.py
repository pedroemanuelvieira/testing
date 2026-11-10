"""Linha de comandos do escritório: `python -m foundry <comando>`."""
from __future__ import annotations
import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from . import __version__, config

AJUDA = f"""Neo-Edo Data Foundry {__version__} · escritório de IA da equipa de BI e ML

Escritório
  preparar                 cria pastas e base de dados, valida a configuração e o Claude Code CLI
  servir                   abre a interface em http://localhost:8765 e liga o escalonador de rotinas
  correr <rotina>          corre uma rotina agora          (ex.: correr morning-audit)
  correr --agente X --pedido "…"   pedido direto a um funcionário
  estado                   resumo do escritório no terminal
  agenda [--crontab]       rotinas e próximas execuções (ou linhas prontas para o crontab)
  validar                  verifica equipa.json, rotinas.json, agentes e skills
  demo                     copia os dados fictícios de exemplos/ para inbox/

Registo (usado pelos funcionários)
  tarefa criar|atualizar|listar …      quadro de tarefas
  evento "título" [--agente X] [--nivel info|ok|aviso|erro] [--detalhe "…"]
  arquivar <ficheiro>      move uma entrada tratada de inbox/ para done/ (nunca apaga)

Ferramentas determinísticas (usadas pelas skills)
  perfil <csv>             qualidade de um CSV: nulos, duplicados, tipos, frescura, extremos
  tmdl lint|doc|rls <pasta>   revisão, dicionário e matriz de RLS de um modelo semântico (PBIP/TMDL)
  drift psi|anomalias …    deriva entre duas amostras e anomalias numa série
  kpis <csv> …             período atual contra o anterior, com contributos por dimensão
  refresh <csv>            falhas, atrasos e durações anómalas de refreshes e pipelines
  fronteira [caminhos]     procura dados sensíveis antes de partilhar ou fazer commit
  ml <comando> …           motor bi_ml 0.10 (check, forecast, churn, …) · `ml demo` para dados sintéticos

Acrescenta --simulado a `servir` ou `correr` para testar sem invocar o Claude.
"""


def _preparar(_a) -> int:
    from . import db, runner
    for p in config.PASTAS:
        (config.RAIZ / p).mkdir(parents=True, exist_ok=True)
    db.ligar().close()
    print(f"Pastas e base de dados prontas ({config.caminho_bd().name}).")
    erros = config.validar()
    for e in erros:
        print("  ERRO:", e)
    eq = config.equipa()
    print(f"Configuração: {len(eq['agentes'])} funcionários, {len(config.rotinas())} rotinas, "
          f"{len(eq.get('projetos_ml', []))} projetos ML" + (" · com erros" if erros else " · válida"))
    cli = runner.claude_cli()
    print("Claude Code CLI:", cli or "NÃO encontrado. Instala-o e faz `claude` uma vez para iniciar sessão.")
    em_falta = [m for m in ("pandas", "numpy", "scipy", "sklearn") if not _tem_modulo(m)]
    print("Motor ML:", "pronto" if not em_falta else
          f"faltam {', '.join(em_falta)} · instala com: python -m pip install -r motor_ml/requirements.txt")
    gancho = config.RAIZ / ".git" / "hooks" / "pre-commit"
    if (config.RAIZ / ".git").is_dir() and not gancho.exists():
        gancho.write_text("#!/bin/sh\n# Fronteira de dados: bloqueia commits com dados sensíveis.\n"
                          "(python3 -m foundry fronteira --staged || python -m foundry fronteira --staged)\n", encoding="utf-8")
        gancho.chmod(0o755)
        print("Gancho pre-commit instalado (fronteira de dados).")
    print("\nPronto. Próximo passo: python -m foundry servir   (ou abre o Claude Code nesta pasta e escreve: morning)")
    return 1 if erros else 0


def _tem_modulo(nome: str) -> bool:
    import importlib.util
    return importlib.util.find_spec(nome) is not None


def _servir(a) -> int:
    from . import server
    if a.simulado:
        os.environ["FOUNDRY_MOTOR"] = "simulado"
    server.servir(a.host, a.porta, not a.sem_agenda, a.token or os.environ.get("FOUNDRY_TOKEN"))
    return 0


def _correr(a) -> int:
    from . import runner
    if a.simulado:
        os.environ["FOUNDRY_MOTOR"] = "simulado"
    try:
        e = runner.executar(a.agente or "", a.rotina, a.pedido, "cli")
    except ValueError as err:
        print("Erro:", err, file=sys.stderr)
        return 2
    print(e["saida"] or "")
    print(f"\n[{e['estado']}] {e['resumo']}  ({e['duracao_s']}s · execução #{e['id']})", file=sys.stderr)
    return 0 if e["estado"] in ("ok", "avisos", "ignorada") else 1


def _estado(a) -> int:
    from . import server
    s = server.estado(com_agenda=False)
    if a.json:
        print(json.dumps(s, ensure_ascii=False, indent=1))
        return 0
    t = s["telemetria"]
    print(f"{s['escritorio']} · {s['agora']}")
    print(f"Execuções (7 dias): {t['execucoes']} · sucesso: {str(t['taxa_sucesso']) + '%' if t['taxa_sucesso'] is not None else '—'} · "
          f"hoje: {t['hoje']} · falhas hoje: {t['falhas_hoje']}")
    print("\nRotinas")
    for r in s["rotinas"]:
        u = r["ultima"]
        print(f"  {'●' if r['ativa'] else '○'} {r['id']:<24} {r['agente']:<10} {r['cadencia']:<28} "
              f"última: {(u['estado'] + ' ' + u['inicio'][5:16]) if u else '—'}")
    abertas = [x for x in s["tarefas"] if x["estado"] not in ("concluida",)]
    print(f"\nTarefas abertas: {len(abertas)}")
    for x in abertas[:15]:
        print(f"  #{x['id']:<4}{'★ ' if x['foco'] else '  '}[{x['estado']}] {x['titulo']} · {x['agente'] or 'sem dono'}")
    for e in s["erros_config"]:
        print("ERRO de configuração:", e)
    return 0


def _agenda(a) -> int:
    from . import cron
    agora = datetime.now()
    py = shutil.which("python3") or sys.executable
    for r in config.rotinas():
        if not r.get("cron"):
            continue
        if a.crontab:
            print(f"{r['cron']} cd {config.RAIZ} && {py} -m foundry correr {r['id']} >> out/agenda.log 2>&1")
        else:
            p = cron.proxima(r["cron"], agora)
            print(f"{r['id']:<24} {r['agente']:<10} {cron.descrever(r['cron']):<30} próxima: {p:%a %d-%m %H:%M}")
    return 0


def _validar(_a) -> int:
    erros = config.validar()
    for e in erros:
        print("ERRO:", e)
    print("Configuração válida." if not erros else f"{len(erros)} erro(s).")
    return 1 if erros else 0


def _demo(_a) -> int:
    origem = config.RAIZ / "exemplos"
    mapa = {"pedidos": "inbox/pedidos", "dados": "inbox/dados", "modelo_exemplo": "inbox/modelos/modelo_exemplo",
            "refresh": "inbox/refresh", "reunioes": "inbox/reunioes"}
    for de, para in mapa.items():
        if (origem / de).exists():
            shutil.copytree(origem / de, config.RAIZ / para, dirs_exist_ok=True)
            print(f"exemplos/{de} → {para}")
    print("Dados fictícios copiados. Experimenta: python -m foundry correr triagem --simulado")
    return 0


def _arquivar(a) -> int:
    """Move uma entrada tratada de inbox/ para done/<data>/ (nunca apaga, nunca sobrepõe)."""
    origem = (config.RAIZ / a.ficheiro).resolve()
    inbox = (config.RAIZ / "inbox").resolve()
    if inbox not in origem.parents or not origem.is_file():
        print("Erro: só se arquivam ficheiros existentes dentro de inbox/", file=sys.stderr)
        return 2
    pasta = config.RAIZ / "done" / datetime.now().strftime("%Y-%m-%d") / origem.parent.relative_to(inbox)
    pasta.mkdir(parents=True, exist_ok=True)
    destino, n = pasta / origem.name, 1
    while destino.exists():
        destino, n = pasta / f"{origem.stem}_{n}{origem.suffix}", n + 1
    shutil.move(str(origem), str(destino))
    print(f"arquivado em {destino.relative_to(config.RAIZ)}")
    return 0


def _tarefa(a) -> int:
    from . import db
    try:
        if a.acao == "criar":
            tid = db.tarefa_criar(a.titulo or "", a.agente, a.fase or "ingestao", a.estado or "pendente", a.prazo, a.notas, a.origem)
            print(f"tarefa #{tid} criada")
        elif a.acao == "atualizar":
            db.tarefa_atualizar(a.id, titulo=a.titulo, agente=a.agente, fase=a.fase, estado=a.estado, prazo=a.prazo, notas=a.notas,
                                foco=None if a.foco is None else int(a.foco))
            print(f"tarefa #{a.id} atualizada")
        else:
            for t in db.tarefas():
                print(json.dumps({k: t[k] for k in ("id", "titulo", "agente", "fase", "estado", "foco", "prazo")}, ensure_ascii=False))
    except ValueError as e:
        print("Erro:", e, file=sys.stderr)
        return 2
    return 0


def _evento(a) -> int:
    from . import db
    db.evento(a.titulo, a.agente, a.nivel, a.detalhe)
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not argv or argv[0] in ("ajuda", "-h", "--help", "help"):
        print(AJUDA)
        return 0
    ferramentas = {"perfil": "perfil", "tmdl": "tmdl", "drift": "drift", "kpis": "kpis", "refresh": "refresh",
                   "fronteira": "fronteira", "ml": "ml"}
    if argv[0] in ferramentas:
        import importlib
        return importlib.import_module(f"foundry.tools.{ferramentas[argv[0]]}").main(argv[1:])

    ap = argparse.ArgumentParser(prog="python -m foundry", add_help=False)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("preparar").set_defaults(f=_preparar)
    s = sub.add_parser("servir")
    s.add_argument("--host", default="127.0.0.1"); s.add_argument("--porta", type=int, default=8765)
    s.add_argument("--token"); s.add_argument("--sem-agenda", action="store_true"); s.add_argument("--simulado", action="store_true")
    s.set_defaults(f=_servir)
    c = sub.add_parser("correr")
    c.add_argument("rotina", nargs="?"); c.add_argument("--agente"); c.add_argument("--pedido"); c.add_argument("--simulado", action="store_true")
    c.set_defaults(f=_correr)
    e = sub.add_parser("estado"); e.add_argument("--json", action="store_true"); e.set_defaults(f=_estado)
    g = sub.add_parser("agenda"); g.add_argument("--crontab", action="store_true"); g.set_defaults(f=_agenda)
    sub.add_parser("validar").set_defaults(f=_validar)
    sub.add_parser("demo").set_defaults(f=_demo)
    q = sub.add_parser("arquivar"); q.add_argument("ficheiro"); q.set_defaults(f=_arquivar)
    t = sub.add_parser("tarefa")
    t.add_argument("acao", choices=("criar", "atualizar", "listar")); t.add_argument("--id", type=int)
    for campo in ("titulo", "agente", "fase", "estado", "prazo", "notas", "origem"):
        t.add_argument("--" + campo)
    t.add_argument("--foco", choices=("0", "1"))
    t.set_defaults(f=_tarefa)
    v = sub.add_parser("evento")
    v.add_argument("titulo"); v.add_argument("--agente"); v.add_argument("--nivel", default="info"); v.add_argument("--detalhe")
    v.set_defaults(f=_evento)
    a = ap.parse_args(argv)
    if a.cmd == "tarefa" and a.acao == "atualizar" and a.id is None:
        ap.error("tarefa atualizar exige --id")
    return a.f(a)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:   # saída cortada por `| head` e semelhantes
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        sys.exit(0)
