"""Assistente da plataforma: Claude com ferramentas (modo IA) ou motor local (modo offline).

Modo IA
-------
* Messages API com ciclo de tool use gerido no servidor (as ferramentas operam
  sobre os projetos e dados locais, que não saem da infraestrutura da empresa
  exceto o texto das respostas das ferramentas).
* Modelo ``claude-opus-5-5`` (configurável), raciocínio adaptativo e ``effort``
  configurável; fallback server-side em caso de recusa ativado por omissão.
* Histórico só-de-acréscimo: o ``system`` e as ferramentas são fixos e o
  contexto da página/projeto entra como texto na mensagem do utilizador, para
  que os blocos de raciocínio reenviados continuem válidos e o prompt cache
  funcione.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import uuid
from pathlib import Path
from typing import Any, Optional

from ..core.agent import now_iso
from .offline import OfflineAssistant
from .tools import TOOLS, ToolExecutor

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """És o assistente da plataforma "BI ML Studio", usada por uma equipa de Business Intelligence para \
construir projetos de machine learning sobre dados do Power BI Service (através de um conector interno).

Responde sempre em português de Portugal, de forma clara, prática e orientada ao negócio. Os utilizadores dominam \
Power BI, DAX e análise de dados mas podem ter pouca experiência de ML: explica conceitos com exemplos de BI e \
liga-os ao glossário.

A plataforma organiza cada projeto num percurso de 13 passos, cada um executado por um agente especializado: \
enquadramento, dados (Power BI), perfil, qualidade, features, seleção de modelos, hiperparâmetros (conselheiro), \
treino, avaliação, explicabilidade, governança, implementação no Power BI e monitorização. Há agentes especialistas \
para previsão de séries temporais, segmentação, anomalias e cabaz de compras, e um agente de relatórios.

Regras:
- Usa as ferramentas para obter factos (glossário, casos de uso, catálogo de modelos, conselheiro de parâmetros, \
estado do projeto) em vez de responder de memória quando a pergunta é sobre a plataforma, os dados ou o projeto.
- Quando recomendares hiperparâmetros, usa a ferramenta recomendar_parametros (com projeto_id quando houver um \
projeto em contexto) e explica o porquê de cada valor e o efeito de o subir ou descer.
- Nunca inventes métricas, resultados ou nomes de colunas: se não os tiveres, diz que o agente correspondente ainda \
não foi executado e indica qual.
- Só executes agentes quando o utilizador o pedir explicitamente. Não publicas nada no Power BI: isso é feito na \
página do projeto.
- Assinala riscos de data leakage, desequilíbrio de classes, enviesamento e requisitos de RGPD/AI Act quando forem \
relevantes.
- Sê conciso: usa listas e tabelas Markdown curtas; termina com o próximo passo concreto quando fizer sentido."""

MAX_ITERATIONS = 8


def llm_available(settings: Any) -> tuple[bool, str]:
    if settings.chat_offline:
        return False, "Modo offline forçado (MLSTUDIO_CHAT_OFFLINE=1)."
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False, "Biblioteca 'anthropic' não instalada."
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        return False, "Sem credenciais da API Claude (defina ANTHROPIC_API_KEY)."
    return True, f"Claude ({settings.chat_model})"


class ConversationStore:
    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, cid: str) -> Path:
        if not re.fullmatch(r"conv_\w+", cid):
            raise KeyError(cid)
        return self.folder / f"{cid}.json"

    def new(self) -> dict[str, Any]:
        return {"id": "conv_" + uuid.uuid4().hex[:12], "created_at": now_iso(), "api_messages": [], "display": []}

    def get(self, cid: str) -> dict[str, Any]:
        path = self._path(cid)
        if not path.exists():
            raise KeyError(cid)
        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, conv: dict[str, Any]) -> None:
        with self._lock:
            self._path(conv["id"]).write_text(json.dumps(conv, ensure_ascii=False, default=str), encoding="utf-8")

    def delete(self, cid: str) -> None:
        self._path(cid).unlink(missing_ok=True)


class Assistant:
    def __init__(self, orchestrator: Any):
        self.o = orchestrator
        self.settings = orchestrator.settings
        self.store = ConversationStore(self.settings.chats_dir)
        self._client = None

    def status(self) -> dict[str, Any]:
        ok, detail = llm_available(self.settings)
        return {"mode": "llm" if ok else "offline", "detail": detail, "model": self.settings.chat_model if ok else None}

    def _get_client(self) -> Any:
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(max_retries=2, timeout=120.0)
        return self._client

    # ------------------------------------------------------------------ API pública
    def chat(self, message: str, conversation_id: Optional[str] = None, project_id: Optional[str] = None,
             page: Optional[str] = None) -> dict[str, Any]:
        message = (message or "").strip()
        if not message:
            raise ValueError("Mensagem vazia.")
        try:
            conv = self.store.get(conversation_id) if conversation_id else self.store.new()
        except KeyError:
            conv = self.store.new()
        tools = ToolExecutor(self.o)
        ok, detail = llm_available(self.settings)
        note = None
        result: Optional[dict[str, Any]] = None
        if ok:
            try:
                result = self._llm_turn(conv, message, project_id, page, tools)
            except Exception as exc:  # noqa: BLE001 - degradação graciosa para o modo offline
                note = self._error_note(exc)
                log.warning("Assistente IA indisponível: %s", exc)
        if result is None:
            off = OfflineAssistant(tools).answer(message, project_id)
            result = {"text": off["text"], "tools": off["tools"], "mode": "offline"}
            if note:
                result["text"] = f"_{note}_\n\n" + result["text"]
            elif not ok:
                result["detail"] = detail
        sources = self._sources(tools)
        entry_user = {"role": "user", "text": message, "ts": now_iso(), "project_id": project_id, "page": page}
        entry_bot = {"role": "assistant", "text": result["text"], "ts": now_iso(), "mode": result["mode"],
                     "tools": result.get("tools", []), "sources": sources}
        conv["display"] += [entry_user, entry_bot]
        conv["updated_at"] = now_iso()
        self.store.save(conv)
        return {"conversation_id": conv["id"], "reply": result["text"], "mode": result["mode"], "tools": result.get("tools", []),
                "sources": sources, "detail": result.get("detail")}

    def history(self, conversation_id: str) -> dict[str, Any]:
        conv = self.store.get(conversation_id)
        return {"conversation_id": conv["id"], "messages": conv["display"]}

    # ------------------------------------------------------------------ modo IA
    def _context_text(self, project_id: Optional[str], page: Optional[str]) -> str:
        parts = []
        if page:
            parts.append(f"página atual: {page}")
        if project_id:
            try:
                p = self.o.store.get(project_id)
                uc = self.o.kb.use_case(p.use_case_id)
                parts.append(f"projeto em contexto: id={p.id}, nome='{p.name}', tipo={p.problem_type}, "
                             f"caso de uso={uc.name if uc else 'personalizado'}, alvo={p.target or '—'}")
            except KeyError:
                pass
        return f"[Contexto da interface — {'; '.join(parts)}]" if parts else ""

    def _llm_turn(self, conv: dict[str, Any], message: str, project_id: Optional[str], page: Optional[str],
                  tools: ToolExecutor) -> dict[str, Any]:

        client = self._get_client()
        ctx_text = self._context_text(project_id, page)
        content = ([{"type": "text", "text": ctx_text}] if ctx_text else []) + [{"type": "text", "text": message}]
        # cópia de trabalho: só é persistida se o turno terminar bem (histórico só-de-acréscimo)
        messages = list(conv["api_messages"]) + [{"role": "user", "content": content}]
        trace: list[dict[str, Any]] = []
        texts: list[str] = []
        kwargs: dict[str, Any] = {
            "model": self.settings.chat_model, "max_tokens": 16000,
            "system": [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            "tools": TOOLS, "messages": messages, "output_config": {"effort": self.settings.chat_effort},
        }
        use_fallbacks = self.settings.chat_fallbacks not in ("off", "0", "false", "")
        for _ in range(MAX_ITERATIONS):
            if use_fallbacks:
                resp = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
            else:
                resp = client.messages.create(**kwargs)
            blocks = resp.to_dict().get("content", [])
            messages.append({"role": "assistant", "content": blocks})
            texts += [b.text for b in resp.content if getattr(b, "type", None) == "text" and b.text.strip()]
            if resp.stop_reason == "refusal":
                texts.append("Não posso ajudar com esse pedido. Reformule a pergunta ou contacte a equipa responsável.")
                break
            if resp.stop_reason == "pause_turn":
                continue
            if resp.stop_reason == "max_tokens":
                texts.append("_(resposta truncada por limite de tamanho)_")
                break
            if resp.stop_reason != "tool_use":
                break
            results = []
            for b in resp.content:
                if getattr(b, "type", None) != "tool_use":
                    continue
                args = b.input if isinstance(b.input, dict) else json.loads(b.input or "{}")
                out, is_error = tools.execute(b.name, args)
                trace.append({"name": b.name, "input": args, "error": is_error})
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": out, "is_error": is_error})
            messages.append({"role": "user", "content": results})
        else:
            texts.append("_(limite de passos atingido — peça para continuar)_")
        conv["api_messages"] = messages
        return {"text": "\n\n".join(texts).strip() or "…", "tools": trace, "mode": "llm"}

    @staticmethod
    def _error_note(exc: Exception) -> str:
        try:
            import anthropic

            if isinstance(exc, anthropic.AuthenticationError):
                return "Credenciais da API Claude inválidas — a responder em modo offline."
            if isinstance(exc, anthropic.RateLimitError):
                return "Limite de pedidos da API Claude atingido — a responder em modo offline."
            if isinstance(exc, anthropic.APIConnectionError):
                return "Sem ligação à API Claude — a responder em modo offline."
            if isinstance(exc, anthropic.APIStatusError):
                return f"API Claude indisponível ({exc.status_code}) — a responder em modo offline."
        except ImportError:
            pass
        return "Assistente IA indisponível — a responder em modo offline."

    def _sources(self, tools: ToolExecutor) -> dict[str, list[dict[str, str]]]:
        terms, seen = [], set()
        for tid in tools.referenced_terms:
            t = self.o.kb.term(tid)
            if t and tid not in seen:
                seen.add(tid)
                terms.append({"id": t.id, "term": t.term, "short": t.short})
        ucs = []
        for uid in dict.fromkeys(tools.referenced_use_cases):
            uc = self.o.kb.use_case(uid)
            if uc:
                ucs.append({"id": uc.id, "name": uc.name})
        return {"terms": terms[:8], "use_cases": ucs[:4]}
