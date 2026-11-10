"""Servidor local do escritório: interface web, API JSON, fila de execuções e escalonador de rotinas."""
from __future__ import annotations
import hmac
import json
import queue
import threading
import time
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from . import __version__, config, cron, db, runner

_fila: "queue.Queue[tuple[int, str, str | None, str | None, str]]" = queue.Queue()
_LOOPBACK = ("127.0.0.1", "localhost", "::1")


# ------------------------------------------------------------------ fila (uma execução de cada vez)
def enfileirar(agente_id: str, rotina_id: str | None, pedido: str | None, origem: str) -> int:
    rot = config.rotina(rotina_id) if rotina_id else None
    if rotina_id and not rot:
        raise ValueError(f"rotina desconhecida: {rotina_id}")
    ag = config.agente(rot["agente"] if rot else agente_id)
    if not ag:
        raise ValueError(f"agente desconhecido: {agente_id}")
    if not rot and not (pedido or "").strip():
        raise ValueError("escolhe uma rotina ou escreve um pedido")
    eid = db.execucao_abrir(ag["id"], origem, rot["id"] if rot else None, pedido)
    _fila.put((eid, ag["id"], rot["id"] if rot else None, pedido, origem))
    return eid


def _operario() -> None:
    while True:
        eid, agente_id, rotina_id, pedido, origem = _fila.get()
        try:
            runner.executar(agente_id, rotina_id, pedido, origem, eid=eid)
        except Exception as e:  # nunca deixar a fila morrer
            db.execucao_fechar(eid, "falhou", f"erro interno do motor: {e}"[:300], repr(e), 0)
            db.evento("Erro interno do motor", agente_id, "erro", str(e)[:300])
        finally:
            _fila.task_done()


# ------------------------------------------------------------------ escalonador
def rotina_ativa(rot: dict) -> bool:
    v = db.meta_ler(f"rotina_ativa:{rot['id']}")
    return rot.get("ativa", True) if v is None else v == "1"


def agenda_pausada() -> bool:
    return db.meta_ler("agenda_pausada", "0") == "1"


def devidas(agora: datetime, ultimo_tick: datetime, instalada: datetime) -> list[dict]:
    """Rotinas a disparar neste tique. Cada horário previsto dispara no máximo uma vez.

    Sem `recuperar_h`, uma rotina perdida (máquina desligada) não é repetida. Com `recuperar_h`,
    é recuperada uma única vez se o horário perdido estiver dentro dessa janela e depois da instalação.
    """
    saida = []
    for rot in config.rotinas():
        if not rot.get("cron") or not rotina_ativa(rot):
            continue
        janela = timedelta(hours=rot.get("recuperar_h") or 0)
        desde = max(ultimo_tick, agora - timedelta(minutes=2))
        if janela:
            desde = max(agora - janela, instalada)
        devida, c = None, cron.proxima(rot["cron"], desde)
        while c and c <= agora:
            devida, c = c, cron.proxima(rot["cron"], c)
        if not devida:
            continue
        chave = f"agenda_disparo:{rot['id']}"
        if (db.meta_ler(chave) or "") >= devida.isoformat():
            continue
        db.meta_gravar(chave, devida.isoformat())
        saida.append(rot)
    return saida


def _escalonador(intervalo_s: int = 20) -> None:
    instalada = db.meta_ler("agenda_instalada")
    if not instalada:
        instalada = db.agora()
        db.meta_gravar("agenda_instalada", instalada)
    instalada_dt = datetime.fromisoformat(instalada)
    ultimo = datetime.fromisoformat(db.meta_ler("agenda_ultimo_tick") or db.agora())
    while True:
        agora = datetime.now().replace(microsecond=0)
        try:
            if not agenda_pausada():
                for rot in devidas(agora, ultimo, instalada_dt):
                    enfileirar(rot["agente"], rot["id"], None, "agenda")
            ultimo = agora
            db.meta_gravar("agenda_ultimo_tick", agora.isoformat())
        except Exception as e:
            db.evento("Erro no escalonador", None, "erro", str(e)[:300])
        time.sleep(intervalo_s)


# ------------------------------------------------------------------ estado para a interface
def estado(com_agenda: bool = True) -> dict:
    eq = config.equipa()
    agora = datetime.now()
    ult_r, ult_a = db.ultima_por_rotina(), db.ultima_por_agente()
    execs = db.execucoes(40)
    ocupados = {e["agente"] for e in execs if e["estado"] == "em_curso"}
    rotinas = []
    for r in config.rotinas():
        prox = cron.proxima(r["cron"], agora) if r.get("cron") else None
        rotinas.append({**r, "ativa": rotina_ativa(r), "cadencia": cron.descrever(r["cron"]) if r.get("cron") else "a pedido",
                        "proxima": prox.isoformat(timespec="minutes") if prox else None, "ultima": ult_r.get(r["id"])})
    return {
        "versao": __version__,
        "agora": agora.isoformat(timespec="seconds"),
        "escritorio": eq["escritorio"],
        "subtitulo": eq.get("subtitulo", ""),
        "motor": {"modo": runner.modo(), "claude": bool(runner.claude_cli()), "agenda": com_agenda,
                  "pausada": agenda_pausada(), "em_fila": _fila.qsize()},
        "agentes": [{**a, "ultima": ult_a.get(a["id"]), "ocupado": a["id"] in ocupados} for a in eq["agentes"]],
        "projetos_ml": eq.get("projetos_ml", []),
        "estados_registo": config.ESTADOS_REGISTO,
        "fases": config.FASES,
        "rotinas": rotinas,
        "tarefas": db.tarefas(),
        "eventos": db.eventos(60),
        "execucoes": execs,
        "telemetria": db.telemetria(7),
        "erros_config": config.validar(),
    }


# ------------------------------------------------------------------ HTTP
class Pedido(BaseHTTPRequestHandler):
    server_version = "Foundry/" + __version__
    token: str | None = None
    com_agenda = True

    def log_message(self, *a):  # silencioso: o diário vive na base de dados
        pass

    def _json(self, corpo, codigo: int = 200) -> None:
        dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(dados)

    def _autorizado(self, escrita: bool) -> bool:
        if self.token and not hmac.compare_digest(self.headers.get("X-Foundry-Token", ""), self.token):
            self._json({"status": "error", "message": "token em falta ou inválido"}, 401)
            return False
        if escrita:  # pedidos de escrita só da própria interface (bloqueia páginas de terceiros no navegador)
            origem = self.headers.get("Origin")
            anfitriao = self.headers.get("Host", "")
            if origem and urlparse(origem).netloc != anfitriao:
                self._json({"status": "error", "message": "origem não permitida"}, 403)
                return False
            if not self.token and anfitriao.split(":")[0].strip("[]") not in _LOOPBACK:
                self._json({"status": "error", "message": "anfitrião não permitido"}, 403)
                return False
        return True

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            dados = (config.UI / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(dados)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(dados)
            return
        if not u.path.startswith("/api/"):
            return self._json({"status": "error", "message": "não encontrado"}, 404)
        if not self._autorizado(False):
            return
        q = parse_qs(u.query)
        if u.path == "/api/estado":
            return self._json(estado(self.com_agenda))
        if u.path == "/api/execucao":
            try:
                e = db.execucao(int(q.get("id", ["0"])[0]))
            except ValueError:
                e = None
            return self._json(e or {"status": "error", "message": "execução não encontrada"}, 200 if e else 404)
        if u.path == "/api/ficheiro":
            rel = q.get("caminho", [""])[0]
            alvo = (config.RAIZ / rel).resolve()
            base = (config.RAIZ / "out").resolve()
            if base not in alvo.parents or not alvo.is_file() or alvo.stat().st_size > 2_000_000:
                return self._json({"status": "error", "message": "só ficheiros de out/ até 2 MB"}, 404)
            return self._json({"caminho": rel, "texto": alvo.read_text(encoding="utf-8", errors="replace")})
        return self._json({"status": "error", "message": "não encontrado"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        if not self._autorizado(True):
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n > 200_000:
                return self._json({"status": "error", "message": "pedido demasiado grande"}, 413)
            corpo = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(corpo, dict):
                raise ValueError("corpo JSON inválido")
            if u.path == "/api/run-agent":
                eid = enfileirar(str(corpo.get("agent_id") or ""), corpo.get("rotina") or None,
                                 corpo.get("pedido") or None, "manual")
                return self._json({"status": "started", "id": eid})
            if u.path == "/api/rotina":
                rot = config.rotina(str(corpo.get("id")))
                if not rot:
                    raise ValueError("rotina desconhecida")
                db.meta_gravar(f"rotina_ativa:{rot['id']}", "1" if corpo.get("ativa") else "0")
                return self._json({"status": "success"})
            if u.path == "/api/agenda":
                db.meta_gravar("agenda_pausada", "1" if corpo.get("pausada") else "0")
                db.evento("Escalonador " + ("pausado" if corpo.get("pausada") else "retomado"), None, "aviso" if corpo.get("pausada") else "ok")
                return self._json({"status": "success"})
            if u.path == "/api/tarefa":
                if corpo.get("acao") == "criar":
                    tid = db.tarefa_criar(str(corpo.get("titulo") or "").strip() or _erro("título em falta"), corpo.get("agente") or None,
                                          corpo.get("fase") or "ingestao", "pendente", corpo.get("prazo") or None,
                                          corpo.get("notas") or None, "interface")
                    return self._json({"status": "success", "id": tid})
                db.tarefa_atualizar(int(corpo["id"]), **{k: corpo.get(k) for k in ("titulo", "agente", "fase", "estado", "foco", "prazo", "notas")})
                return self._json({"status": "success"})
            return self._json({"status": "error", "message": "não encontrado"}, 404)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
            return self._json({"status": "error", "message": str(e) or "pedido inválido"}, 400)


def _erro(msg: str):
    raise ValueError(msg)


def servir(host: str = "127.0.0.1", porta: int = 8765, com_agenda: bool = True, token: str | None = None) -> None:
    if host not in _LOOPBACK and not token:
        raise SystemExit("Para expor o escritório fora desta máquina é obrigatório --token <segredo>.")
    orfas = db.fechar_orfas()
    Pedido.token, Pedido.com_agenda = token, com_agenda
    threading.Thread(target=_operario, daemon=True, name="operario").start()
    if com_agenda:
        threading.Thread(target=_escalonador, daemon=True, name="escalonador").start()
    srv = ThreadingHTTPServer((host, porta), Pedido)
    erros = config.validar()
    print(f"Neo-Edo Data Foundry {__version__} · http://{'localhost' if host in _LOOPBACK else host}:{porta}")
    print(f"  motor: {runner.modo()} · Claude Code CLI: {'encontrado' if runner.claude_cli() else 'NÃO encontrado'}"
          f" · escalonador: {'ligado' if com_agenda else 'desligado'}")
    if orfas:
        print(f"  {orfas} execução(ões) interrompida(s) marcada(s) como falhadas")
    for e in erros:
        print("  ERRO de configuração:", e)
    print("  Ctrl+C para parar.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nEscritório fechado.")
