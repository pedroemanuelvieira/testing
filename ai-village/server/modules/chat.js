// Conversas persistentes no backend (RF03). Uma mensagem NÃO prova execução (RF03).
// Modo demo/real é gravado em cada mensagem e nunca muda depois; falha do real não vira demo.
import { newId, clock, addDays, json, parseJson, bad, conflict, forbidden, notFound, unprocessable, HttpError, redact } from '../lib/util.js';
import { tx } from '../lib/db.js';
import { str, oneOf, requireBody, mustGet } from './common.js';
import { audit } from './audit.js';
import { classifyD1, d1Notice } from './d1.js';
import { getSettings } from './settings.js';
import * as demo from '../adapters/demo.js';
import * as anthropic from '../adapters/anthropic.js';
import { activeModelConnection } from './connections.js';

const MAX_CHARS = 4000;

const msgOut = (m) => ({
  id: m.id, conversation_id: m.conversation_id, sequence: m.sequence, author_type: m.author_type, content: m.content, state: m.state, mode: m.mode,
  provider_ref: m.provider_ref, task_refs: parseJson(m.task_refs, []), evidence_refs: parseJson(m.evidence_refs, []), meta: parseJson(m.meta, {}),
  reason_code: m.reason_code, request_id: m.request_id, created_at: m.created_at,
});

export function listConversations(w, agentId) {
  return w.db.prepare('SELECT * FROM conversations WHERE world_id=? AND account_id=? AND agent_id=? ORDER BY updated_at DESC').all(w.id, w.accountId, agentId);
}

export function createConversation(w, actor, agentId, body = {}) {
  const agent = mustGet(w, 'agents', agentId, 'Agente');
  if (agent.lifecycle_status !== 'active') throw unprocessable('O agente não está activo.', 'agent_inactive');
  const mode = oneOf(body.mode, ['demo', 'real'], 'mode') || 'demo';
  let binding = null;
  if (mode === 'real') {
    const conn = activeModelConnection(w, body.connection_id);
    if (!conn || !conn.usable || conn.row.provider_id !== 'anthropic-api') {
      throw conflict('Conversa real indisponível: a ligação ao modelo não está verificada/ligada com o âmbito «chat». Nada foi trocado para demo.', 'real_not_available');
    }
    binding = conn.row.id;
  }
  const id = newId('conv'), now = clock.iso();
  const st = getSettings(w);
  w.db.prepare(`INSERT INTO conversations(id,world_id,account_id,agent_id,owner_id,title,mode,model_binding_ref,retention_until,created_at,updated_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,?)`).run(id, w.id, w.accountId, agentId, actor.id, str(body.title, 'title', { max: 80 }) || `Conversa com ${agent.display_name}`, mode, binding, addDays(now, st.retention_content_days), now, now);
  audit(w, { actor: actor.ref, action: 'conversation.create', resource: id, reason: mode });
  return mustGet(w, 'conversations', id);
}

export function listMessages(w, conversationId, { after = 0 } = {}) {
  mustGet(w, 'conversations', conversationId, 'Conversa');
  return w.db.prepare('SELECT * FROM messages WHERE conversation_id=? AND sequence>? ORDER BY sequence').all(conversationId, Number(after) || 0).map(msgOut);
}

function insertMessage(w, conv, m) {
  const id = newId('msg'), now = clock.iso();
  const seq = conv.last_sequence + 1;
  conv.last_sequence = seq;
  const st = getSettings(w);
  w.db.prepare(`INSERT INTO messages(id,world_id,account_id,conversation_id,sequence,author_type,content,state,mode,provider_ref,task_refs,evidence_refs,meta,request_id,reason_code,created_at,updated_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`).run(id, w.id, w.accountId, conv.id, seq, m.author_type, m.content ?? null, m.state || 'ok', m.mode,
    m.provider_ref || null, json(m.task_refs || []), json(m.evidence_refs || []), json(m.meta || {}), m.request_id || null, m.reason_code || null, now, now);
  w.db.prepare('UPDATE conversations SET last_sequence=?, updated_at=?, retention_until=?, record_version=record_version+1 WHERE id=?').run(seq, now, addDays(now, st.retention_content_days), conv.id);
  return mustGet(w, 'messages', id);
}

/** Mensagem do sistema (ex.: «tarefa criada»), gerada pelo backend — com ligação à tarefa real. */
export function addSystemMessage(w, conversationId, text, { task_refs = [], evidence_refs = [] } = {}) {
  return tx(w.db, () => {
    const conv = mustGet(w, 'conversations', conversationId, 'Conversa');
    return msgOut(insertMessage(w, conv, { author_type: 'system', content: text, mode: 'system', task_refs, evidence_refs }));
  });
}

export async function postMessage(w, actor, conversationId, body, deps = {}) {
  requireBody(body);
  const text = str(body.content, 'content', { required: true, max: MAX_CHARS });
  const requestId = body.request_id ? str(body.request_id, 'request_id', { max: 80 }) : newId('req');
  const conv0 = mustGet(w, 'conversations', conversationId, 'Conversa');
  const agent = mustGet(w, 'agents', conv0.agent_id, 'Agente');
  if (agent.lifecycle_status !== 'active') throw unprocessable('O agente não está activo.', 'agent_inactive');

  // Retry com o mesmo request_id devolve o par já gravado (idempotência).
  const prev = w.db.prepare("SELECT * FROM messages WHERE conversation_id=? AND request_id=? AND author_type='owner'").get(conversationId, requestId);
  if (prev) {
    const reply = w.db.prepare("SELECT * FROM messages WHERE conversation_id=? AND sequence>? AND author_type<>'owner' ORDER BY sequence LIMIT 1").get(conversationId, prev.sequence);
    return { owner: msgOut(prev), reply: reply ? msgOut(reply) : null, replay: true };
  }

  // Guarda D1 ANTES de guardar: se bloqueia, o conteúdo não é persistido nem resumido.
  const c = classifyD1(text);
  if (c.blocked) {
    return tx(w.db, () => {
      const conv = mustGet(w, 'conversations', conversationId);
      const owner = insertMessage(w, conv, { author_type: 'owner', content: null, state: 'blocked', mode: 'system', request_id: requestId, reason_code: `d1:${c.categories.join(',')}` });
      const reply = insertMessage(w, conv, { author_type: 'system', content: d1Notice(c), mode: 'system', meta: { kind: 'd1_notice' } });
      audit(w, { actor: actor.ref, action: 'chat.blocked_d1', resource: conversationId, result: 'denied', reason: `d1:${c.categories.join(',')}` });
      return { owner: msgOut(owner), reply: msgOut(reply), blocked: true };
    });
  }

  const mode = conv0.mode;
  let conn = null;
  if (mode === 'real') {
    conn = activeModelConnection(w, conv0.model_binding_ref);
    if (!conn || !conn.usable) {
      throw conflict('A ligação ao modelo deixou de estar válida (desligada, revogada ou desactualizada). Nada foi respondido em modo demo.', 'real_not_available');
    }
  }

  const owner = tx(w.db, () => {
    const conv = mustGet(w, 'conversations', conversationId);
    return msgOut(insertMessage(w, conv, { author_type: 'owner', content: text, mode, request_id: requestId }));
  });

  try {
    let result;
    if (mode === 'demo') {
      result = { ...demo.respond({ w, agent, text }), provider_ref: demo.DEMO_PROVIDER_REF };
    } else {
      const history = w.db.prepare("SELECT author_type, content FROM messages WHERE conversation_id=? AND state='ok' AND author_type IN ('owner','agent') ORDER BY sequence").all(conversationId);
      result = await anthropic.respond({ agent, history, conn: conn.row, deps });
    }
    const reply = tx(w.db, () => {
      const conv = mustGet(w, 'conversations', conversationId);
      return msgOut(insertMessage(w, conv, {
        author_type: 'agent', content: result.text, mode, provider_ref: result.provider_ref, meta: result.suggestion ? { suggestion: result.suggestion } : (result.usage ? { usage: result.usage } : {}),
        request_id: null,
      }));
    });
    audit(w, { actor: actor.ref, action: 'chat.message', resource: conversationId, reason: `${mode}:${agent.id}`, correlation: result.request_id || requestId });
    return { owner, reply };
  } catch (e) {
    // O pedido fica conservado; o erro fica visível e acionável (RF03). Sem fallback silencioso para demo.
    const code = e.code || 'adapter_error';
    const errMsg = e instanceof HttpError ? e.message : 'Falha inesperada ao responder.';
    const reply = tx(w.db, () => {
      const conv = mustGet(w, 'conversations', conversationId);
      return msgOut(insertMessage(w, conv, { author_type: 'system', content: redact(errMsg), state: 'error', mode: 'system', reason_code: code, meta: { kind: 'adapter_error' } }));
    });
    audit(w, { actor: actor.ref, action: 'chat.message', resource: conversationId, result: 'error', reason: code });
    return { owner, reply, error: { code, message: redact(errMsg) } };
  }
}
