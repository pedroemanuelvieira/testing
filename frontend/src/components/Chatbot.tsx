import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api, safeStorage } from "../api";
import { useApp } from "../lib/context";
import type { ChatMessage } from "../types";
import { Icon } from "./Icon";
import { TermChip } from "./TermChip";
import { Badge, Markdown } from "./ui";

const TOOL_LABEL: Record<string, string> = {
  pesquisar_conhecimento: "Pesquisa no conhecimento", obter_termo_glossario: "Glossário", listar_casos_de_uso: "Casos de uso",
  obter_caso_de_uso: "Caso de uso", obter_modelo: "Catálogo de modelos", recomendar_parametros: "Conselheiro de parâmetros",
  validar_parametros: "Validação de parâmetros", listar_projetos: "Projetos", estado_projeto: "Estado do projeto",
  listar_agentes: "Agentes", executar_agente: "Execução de agente",
};

function suggestions(path: string, hasProject: boolean): string[] {
  if (hasProject) return ["Qual é o próximo passo?", "Explica os resultados da avaliação", "Que parâmetros recomendas para o LightGBM neste projeto?", "Há risco de data leakage?"];
  if (path.startsWith("/conselheiro")) return ["Que parâmetros uso no XGBoost para fraude com 1% de positivos?", "O que é a learning rate?", "Como evito overfitting?"];
  if (path.startsWith("/dados")) return ["Como ligo a plataforma ao Power BI?", "O que é uma consulta EVALUATE?", "Que granularidade deve ter a tabela?"];
  if (path.startsWith("/glossario")) return ["Diferença entre precisão e recall", "O que é o PSI?", "Explica a validação cruzada"];
  return ["Quero prever que clientes vão cancelar", "O que é a AUC?", "Como escolho o limiar de decisão?", "Que modelo devo usar?"];
}

export function Chatbot() {
  const { chatOpen, openChat, closeChat, consumePrefill, chatPrefill, currentProject, meta } = useApp();
  const loc = useLocation();
  const nav = useNavigate();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [convId, setConvId] = useState<string | null>(safeStorage("chat_conversation"));
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (convId && !messages.length) {
      api.get<{ messages: ChatMessage[] }>(`/api/chat/${convId}`).then((r) => setMessages(r.messages)).catch(() => { setConvId(null); safeStorage("chat_conversation", null); });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight, behavior: "smooth" }); }, [messages, busy, chatOpen]);

  useEffect(() => {
    if (chatOpen && chatPrefill) {
      const p = consumePrefill();
      if (p) void send(p);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chatOpen, chatPrefill]);

  async function send(text: string) {
    const msg = text.trim();
    if (!msg || busy) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text: msg }]);
    setBusy(true);
    try {
      const r = await api.post<any>("/api/chat", { message: msg, conversation_id: convId, project_id: currentProject?.id, page: loc.pathname });
      setConvId(r.conversation_id);
      safeStorage("chat_conversation", r.conversation_id);
      setMessages((m) => [...m, { role: "assistant", text: r.reply, mode: r.mode, tools: r.tools, sources: r.sources }]);
    } catch (e) {
      setMessages((m) => [...m, { role: "assistant", text: `Erro: ${e instanceof Error ? e.message : e}`, mode: "erro" }]);
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    if (convId) api.del(`/api/chat/${convId}`).catch(() => undefined);
    setConvId(null);
    safeStorage("chat_conversation", null);
    setMessages([]);
  }

  if (!chatOpen) {
    return (
      <button className="chat-fab" onClick={() => openChat()} aria-label="Abrir assistente" title="Assistente">
        <Icon name="message-circle" size={24} />
      </button>
    );
  }
  const mode = meta?.assistant.mode ?? "offline";
  return (
    <div className="chat-panel" role="dialog" aria-label="Assistente">
      <div className="chat-head">
        <Icon name="sparkles" size={20} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 700 }}>Assistente de ML</div>
          <div className="tiny" style={{ opacity: 0.85 }}>
            {mode === "llm" ? `IA (${meta?.assistant.model})` : "Modo offline — base de conhecimento"}
            {currentProject ? ` · projeto: ${currentProject.name}` : ""}
          </div>
        </div>
        <button className="icon-btn" style={{ color: "#fff" }} onClick={reset} title="Nova conversa"><Icon name="refresh" size={16} /></button>
        <button className="icon-btn" style={{ color: "#fff" }} onClick={closeChat} title="Fechar"><Icon name="x" size={18} /></button>
      </div>
      <div className="chat-body" ref={bodyRef}>
        {!messages.length && (
          <div className="stack">
            <div className="msg assistant">
              <Markdown text={"Olá! Posso explicar conceitos de ML, aconselhar **hiperparâmetros** para o seu caso, sugerir **casos de uso** e orientar o **próximo passo** do projeto. Pergunte à vontade."} />
              {mode === "offline" && <div className="tiny muted" style={{ marginTop: 6 }}>{meta?.assistant.detail}</div>}
            </div>
            <div className="stack tight">
              {suggestions(loc.pathname, !!currentProject).map((s) => (
                <button key={s} className="chip" style={{ justifyContent: "flex-start" }} onClick={() => send(s)}>{s}</button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            {m.role === "user" ? m.text : (
              <>
                {m.tools && m.tools.length > 0 && (
                  <div className="row" style={{ gap: 4, marginBottom: 6 }}>
                    {m.tools.map((t, k) => <Badge key={k} tone={t.error ? "crit" : "purple"}><Icon name="wrench" size={11} />{TOOL_LABEL[t.name] ?? t.name}</Badge>)}
                  </div>
                )}
                <Markdown text={m.text} />
                {m.sources && (m.sources.terms.length > 0 || m.sources.use_cases.length > 0) && (
                  <div className="row" style={{ gap: 4, marginTop: 8 }}>
                    {m.sources.terms.map((t) => <TermChip key={t.id} id={t.id} label={t.term.split(" (")[0]} />)}
                    {m.sources.use_cases.map((u) => <button key={u.id} className="badge blue" style={{ border: 0, cursor: "pointer" }} onClick={() => nav(`/casos-de-uso?caso=${u.id}`)}>{u.name}</button>)}
                  </div>
                )}
                {m.mode === "offline" && <div className="tiny muted" style={{ marginTop: 4 }}>resposta offline</div>}
              </>
            )}
          </div>
        ))}
        {busy && <div className="msg assistant"><span className="typing"><span /><span /><span /></span></div>}
      </div>
      <form className="chat-input" onSubmit={(e) => { e.preventDefault(); void send(input); }}>
        <textarea className="input" placeholder="Escreva a sua dúvida…" value={input} onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(input); } }} />
        <button className="btn primary" disabled={busy || !input.trim()} aria-label="Enviar"><Icon name="send" size={16} /></button>
      </form>
    </div>
  );
}
