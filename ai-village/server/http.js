// Camada HTTP: router mínimo, sessão+CSRF, cabeçalhos de segurança e rotas da API.
// Toda a autorização é feita aqui e nos módulos (servidor) — o browser só mostra.
import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { mkdirSync, writeFileSync, existsSync, readFileSync, readdirSync } from 'node:fs';
import { join, extname, normalize, dirname, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { HttpError, bad, notFound, forbidden, unprocessable, redact, sha256, json as j, parseJson } from './lib/util.js';
import * as authm from './auth.js';
import { OWNER } from './modules/policy.js';
import * as org from './modules/org.js';
import * as tasks from './modules/tasks.js';
import * as chat from './modules/chat.js';
import * as art from './modules/artifacts.js';
import * as appr from './modules/approvals.js';
import * as conns from './modules/connections.js';
import * as pol from './modules/policy.js';
import * as bi from './modules/bi.js';
import * as aud from './modules/audit.js';
import * as settingsm from './modules/settings.js';
import * as ret from './modules/retention.js';
import { runOnce } from './modules/worker.js';
import { capabilityList } from './modules/capabilities.js';
import { createBackup } from './backup.js';

const here = dirname(fileURLToPath(import.meta.url));
const WEB_DIR = join(here, '..', 'web');
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp', '.json': 'application/json', '.ico': 'image/x-icon', '.txt': 'text/plain; charset=utf-8' };
const CSP = "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'";

const SAMPLE_CSV_F01 = 'registo,grupo,quantidade\nS01,A,2\nS02,B,3\nS03,A,\nS02,B,3\n';

function readBody(req, limit = 2_000_000) {
  return new Promise((resolve, reject) => {
    const chunks = []; let size = 0;
    req.on('data', (c) => { size += c.length; if (size > limit) { reject(new HttpError(413, 'payload_too_large', 'Pedido demasiado grande.')); req.destroy(); } else chunks.push(c); });
    req.on('end', () => {
      if (!chunks.length) return resolve(null);
      try { resolve(JSON.parse(Buffer.concat(chunks).toString('utf8'))); } catch { reject(bad('JSON inválido', 'json_invalid')); }
    });
    req.on('error', reject);
  });
}

const cookies = (req) => Object.fromEntries((req.headers.cookie || '').split(';').map((c) => c.trim().split('=')).filter((p) => p[0]).map(([k, ...v]) => [k, v.join('=')]));

function compile(pattern) {
  const keys = [];
  const re = new RegExp('^' + pattern.replace(/:[a-z_]+/g, (m) => { keys.push(m.slice(1)); return '([^/]+)'; }) + '/?$');
  return { re, keys };
}

export function buildRoutes(app) {
  const R = [];
  const add = (method, pattern, handler, opts = {}) => R.push({ method, ...compile(pattern), handler, opts });
  const W = (p) => `/api/w/:w${p}`;

  // ---- sessão ----
  add('POST', '/api/login', async (c) => {
    const s = authm.login(app.meta, c.ip, c.body?.passcode);
    c.setCookie = `vsid=${s.token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=${s.maxAge}${c.secure ? '; Secure' : ''}`;
    return { ok: true, csrf: s.csrf };
  }, { public: true });
  add('GET', '/api/session', (c) => (c.session ? { authenticated: true, csrf: c.session.csrf, user: { id: OWNER.id, name: 'Pedro' } } : { authenticated: false }), { public: true });
  add('POST', '/api/logout', (c) => { authm.logout(app.meta, c.token); c.setCookie = 'vsid=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'; return { ok: true }; });

  // ---- mundos / visão geral ----
  add('GET', '/api/worlds', () => app.worlds().map((w) => {
    const orc = org.getOrchestrator(w);
    return { id: w.id, name: w.name, kind: w.kind, policy: w.policy, account_alias: w.db.prepare('SELECT alias FROM accounts WHERE id=?').get(w.accountId)?.alias, orchestrator: orc ? { id: orc.id, name: orc.display_name } : null };
  }));
  add('GET', W('/overview'), (c) => ({
    world: { id: c.w.id, name: c.w.name, kind: c.w.kind, policy: c.w.policy },
    kpis: bi.kpis(c.w), settings: settingsm.getSettings(c.w),
    worker: workerStatus(c.w), capabilities: capabilityList(),
    pending_approvals: appr.listApprovals(c.w, { state: 'pending' }).length,
  }));

  // ---- organização ----
  add('GET', W('/org'), (c) => org.loadOrg(c.w, { includeArchived: c.query.archived === '1' }));
  add('GET', W('/agents/:id'), (c) => org.getAgent(c.w, c.params.id));
  add('POST', W('/units'), (c) => org.createUnit(c.w, OWNER, c.body));
  add('PATCH', W('/units/:id'), (c) => org.updateUnit(c.w, OWNER, c.params.id, c.body));
  add('POST', W('/units/:id/archive'), (c) => org.archiveUnit(c.w, OWNER, c.params.id, c.body?.expected_version));
  add('POST', W('/roles'), (c) => org.createRole(c.w, OWNER, c.body));
  add('PATCH', W('/roles/:id'), (c) => org.updateRole(c.w, OWNER, c.params.id, c.body));
  add('POST', W('/roles/:id/archive'), (c) => org.archiveRole(c.w, OWNER, c.params.id, c.body?.expected_version));
  add('POST', W('/agents'), (c) => org.createAgent(c.w, OWNER, c.body));
  add('PATCH', W('/agents/:id'), (c) => org.updateAgent(c.w, OWNER, c.params.id, c.body));
  add('POST', W('/agents/:id/archive'), (c) => org.archiveAgent(c.w, OWNER, c.params.id, c.body || {}));
  add('GET', W('/capabilities'), () => capabilityList());

  // ---- conversas ----
  add('GET', W('/agents/:id/conversations'), (c) => chat.listConversations(c.w, c.params.id));
  add('POST', W('/agents/:id/conversations'), (c) => chat.createConversation(c.w, OWNER, c.params.id, c.body || {}));
  add('GET', W('/conversations/:id/messages'), (c) => chat.listMessages(c.w, c.params.id, { after: c.query.after }));
  add('POST', W('/conversations/:id/messages'), (c) => chat.postMessage(c.w, OWNER, c.params.id, c.body, app.deps));

  // ---- tarefas ----
  add('GET', W('/tasks'), (c) => tasks.listTasks(c.w, c.query));
  add('POST', W('/tasks'), (c) => {
    designGuard(c.w, c.body);
    const t = tasks.createTask(c.w, OWNER, c.body);
    if (c.body?.conversation_id && !t.idempotent_replay) {
      chat.addSystemMessage(c.w, c.body.conversation_id, `Tarefa criada no backend: «${t.title}» (${t.state === 'assigned' ? 'atribuída' : t.state}).`, { task_refs: [t.id] });
    }
    c.status = 201; return t;
  });
  add('GET', W('/tasks/:id'), (c) => tasks.taskDetail(c.w, c.params.id));
  add('POST', W('/tasks/:id/transition'), (c) => tasks.transitionTask(c.w, OWNER, c.params.id, c.body?.to, c.body || {}));
  add('POST', W('/tasks/:id/retry'), (c) => tasks.retryTask(c.w, OWNER, c.params.id));
  add('POST', W('/tasks/:id/start-manual'), (c) => tasks.startManual(c.w, OWNER, c.params.id));
  add('POST', W('/tasks/:id/complete-manual'), (c) => tasks.completeManual(c.w, OWNER, c.params.id, c.body));
  add('POST', W('/tasks/:id/priority'), (c) => tasks.approvePriority(c.w, OWNER, c.params.id, c.body || {}));

  // ---- artefactos / provas ----
  add('POST', W('/artifacts'), (c) => {
    if (c.w.policy.execution === false) throw forbidden('Mundo apenas de desenho: não aceita ficheiros de dados.', 'world_design_only');
    c.status = 201;
    return art.createArtifact(c.w, OWNER, { name: c.body?.name, kind: c.body?.kind || 'text', media_type: c.body?.media_type || 'text/plain', content: c.body?.content });
  });
  add('GET', W('/artifacts/:id'), (c) => art.artifactMeta(c.w, c.params.id));
  add('GET', W('/artifacts/:id/content'), (c) => { const a = art.readArtifact(c.w, c.params.id); return { id: a.id, name: a.name, digest: a.digest, content: a.content }; });
  add('GET', W('/evidence'), (c) => art.listEvidence(c.w, { taskId: c.query.task_id }));
  add('GET', W('/evidence/:id'), (c) => art.getEvidence(c.w, c.params.id));

  // ---- ações / aprovações ----
  add('POST', W('/intents'), (c) => { c.status = 201; return appr.createIntent(c.w, OWNER, c.body); });
  add('GET', W('/intents/:id'), (c) => appr.intentView(c.w, c.params.id));
  add('POST', W('/intents/:id/payload'), (c) => appr.changePayload(c.w, OWNER, c.params.id, c.body?.payload));
  add('POST', W('/intents/:id/request-approval'), (c) => appr.requestApproval(c.w, OWNER, c.params.id));
  add('GET', W('/approvals'), (c) => appr.listApprovals(c.w, { state: c.query.state }));
  add('POST', W('/approvals/:id/approve'), (c) => appr.approve(c.w, OWNER, c.params.id));
  add('POST', W('/approvals/:id/deny'), (c) => appr.deny(c.w, OWNER, c.params.id, c.body?.reason));
  add('POST', W('/approvals/:id/revoke'), (c) => appr.revoke(c.w, OWNER, c.params.id, c.body?.reason));
  add('POST', W('/approvals/:id/execute'), (c) => appr.execute(c.w, OWNER, c.params.id));

  // ---- ligações ----
  add('GET', W('/connections'), (c) => conns.listConnections(c.w));
  add('PATCH', W('/connections/:id'), (c) => conns.updateConnection(c.w, OWNER, c.params.id, c.body));
  add('POST', W('/connections/:id/verify'), async (c) => {
    const conn = conns.getConnection(c.w, c.params.id);
    if (c.w.policy.execution === false && conn.provider_id !== 'demo-adapter') {
      throw forbidden('Mundo apenas de desenho: sem ligações reais nesta conta. Configura-as no ambiente profissional aprovado (G3).', 'world_design_only');
    }
    return conns.verifyConnection(c.w, OWNER, c.params.id, app.deps);
  });
  add('POST', W('/connections/:id/disconnect'), (c) => conns.disconnect(c.w, OWNER, c.params.id, { revoke: Boolean(c.body?.revoke) }));

  // ---- permissões / auditoria / definições ----
  add('GET', W('/permissions'), (c) => pol.listPermissions(c.w));
  add('POST', W('/permissions'), (c) => { c.status = 201; return pol.grantPermission(c.w, OWNER, c.body); });
  add('POST', W('/permissions/:id/revoke'), (c) => pol.revokePermission(c.w, OWNER, c.params.id));
  add('GET', W('/audit'), (c) => aud.listAudit(c.w, c.query));
  add('GET', W('/audit/verify'), (c) => aud.verifyAuditChain(c.w));
  add('GET', W('/settings'), (c) => settingsm.getSettings(c.w));
  add('PATCH', W('/settings'), (c) => settingsm.updateSettings(c.w, OWNER, c.body || {}));
  add('POST', W('/retention/sweep'), (c) => ret.sweep(c.w));

  // ---- BI ----
  add('GET', W('/bi/kpis'), (c) => bi.kpis(c.w));
  add('GET', W('/bi/export/:table'), (c) => {
    const table = c.params.table.replace(/\.csv$/, '');
    c.raw = { type: 'text/csv; charset=utf-8', body: bi.exportCsv(c.w, table), headers: { 'Content-Disposition': `attachment; filename="${c.w.id}_${table}.csv"` } };
  });

  // ---- worker ----
  add('GET', W('/worker/status'), (c) => workerStatus(c.w));
  add('POST', W('/worker/run'), (c) => {
    if (c.w.policy.execution === false) throw forbidden('Mundo apenas de desenho: sem execução.', 'world_design_only');
    return { processed: runOnce(c.w) };
  });

  // ---- cenário guiado F01 (CA06) ----
  add('POST', W('/demo/f01'), (c) => {
    if (c.w.policy.execution === false) throw forbidden('Mundo apenas de desenho.', 'world_design_only');
    const exec = org.loadOrg(c.w).agents.find((a) => a.lifecycle_status === 'active' && a.capability_ids.includes('csv.validate'));
    if (!exec) throw unprocessable('Não existe agente ativo com a capacidade csv.validate.', 'no_executor');
    const a = art.createArtifact(c.w, OWNER, { name: 'F01_fixture_sintetica.csv', kind: 'csv', media_type: 'text/csv', content: SAMPLE_CSV_F01 });
    const t = tasks.createTask(c.w, OWNER, { title: 'Validar CSV sintético F01', objective: 'Validar a fixture F01 (4 linhas) e provar o resultado no worker.', capability: 'csv.validate', assigned_agent_id: exec.id, input_refs: [a.id], config: { numeric_column: 'quantidade' }, expected_output: '4 lidas · 3 válidas · 1 inválida · 1 duplicado · soma 8' });
    c.status = 201; return { task: t, artifact: a, agent: { id: exec.id, name: exec.display_name } };
  });

  // ---- retratos (assets de aparência) ----
  add('POST', W('/portraits'), (c) => {
    const m = /^data:(image\/(?:png|jpeg|webp));base64,([A-Za-z0-9+/=]+)$/.exec(c.body?.data_url || '');
    if (!m) throw bad('Imagem inválida (PNG/JPEG/WEBP em data URL).', 'image_invalid');
    const buf = Buffer.from(m[2], 'base64');
    if (buf.length > 2_000_000) throw new HttpError(413, 'too_large', 'Imagem acima de 2 MB.');
    const ok = (m[1] === 'image/png' && buf.subarray(0, 4).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47])))
      || (m[1] === 'image/jpeg' && buf[0] === 0xff && buf[1] === 0xd8 && buf[2] === 0xff)
      || (m[1] === 'image/webp' && buf.subarray(0, 4).toString() === 'RIFF' && buf.subarray(8, 12).toString() === 'WEBP');
    if (!ok) throw bad('O conteúdo não corresponde ao tipo de imagem.', 'image_invalid');
    const ext = m[1] === 'image/png' ? 'png' : m[1] === 'image/jpeg' ? 'jpg' : 'webp';
    const file = `${sha256(buf).slice(0, 32)}.${ext}`;
    const dir = join(app.dataDir, 'uploads', c.w.id);
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, file), buf);
    c.status = 201; return { file, appearance: { type: 'image', file } };
  }, { bodyLimit: 3_500_000 });
  add('GET', W('/portraits/:file'), (c) => {
    if (!/^[a-f0-9]{32}\.(png|jpg|webp)$/.test(c.params.file)) throw notFound();
    const p = join(app.dataDir, 'uploads', c.w.id, c.params.file);
    if (!existsSync(p)) throw notFound();
    c.raw = { type: MIME[extname(p)] || 'application/octet-stream', body: readFileSync(p), headers: { 'Cache-Control': 'private, max-age=3600' } };
  });

  // ---- admin ----
  add('POST', '/api/admin/backup', (c) => {
    const pass = process.env.VILLAGE_BACKUP_PASSPHRASE;
    if (!pass) throw unprocessable('Define VILLAGE_BACKUP_PASSPHRASE no servidor para criar backups cifrados.', 'backup_passphrase_missing');
    const r = createBackup({ app, passphrase: pass, outDir: join(app.dataDir, 'backups') });
    return { file: r.file.split(sep).pop(), bytes: r.bytes, worlds: r.worlds.map((x) => x.id) };
  });
  add('GET', '/api/admin/backups', () => {
    const d = join(app.dataDir, 'backups');
    return existsSync(d) ? readdirSync(d).filter((f) => f.endsWith('.vbk')).sort().reverse() : [];
  });
  return R;

  function workerStatus(w) {
    const hb = w.db.prepare("SELECT value FROM meta WHERE key='worker_heartbeat'").get();
    const online = hb ? (Date.now() - Date.parse(hb.value)) < 15000 : false;
    const queued = w.db.prepare("SELECT COUNT(*) c FROM tasks WHERE state='assigned' AND capability IN ('csv.validate','csv.profile','report.village_kpis')").get().c;
    return { online, last_heartbeat: hb?.value || null, queued, execution_enabled: w.policy.execution !== false, jobs_suspended: settingsm.getSettings(w).jobs_suspended };
  }
  function designGuard(w, body) {
    if (w.policy.execution === false && body?.capability && ['csv.validate', 'csv.profile', 'report.village_kpis'].includes(body.capability)) {
      throw forbidden('Mundo apenas de desenho: capacidades com execução automática estão desativadas aqui.', 'world_design_only');
    }
  }
}

export function createHttpServer(app) {
  const routes = buildRoutes(app);

  async function serveStatic(req, res, pathname) {
    let rel = normalize(decodeURIComponent(pathname)).replace(/^([/\\])+/, '');
    if (!rel || rel.endsWith(sep)) rel += 'index.html';
    const file = join(WEB_DIR, rel);
    if (!file.startsWith(WEB_DIR)) throw notFound();
    try {
      const st = await stat(file);
      if (!st.isFile()) throw new Error('x');
      const body = await readFile(file);
      res.writeHead(200, { 'Content-Type': MIME[extname(file)] || 'application/octet-stream', 'Cache-Control': 'no-cache' });
      res.end(body);
    } catch {
      // SPA: qualquer rota sem extensão volta ao index
      if (!extname(rel)) { res.writeHead(200, { 'Content-Type': MIME['.html'], 'Cache-Control': 'no-cache' }); res.end(await readFile(join(WEB_DIR, 'index.html'))); return; }
      throw notFound();
    }
  }

  const handler = async (req, res) => {
    const url = new URL(req.url, 'http://x');
    const base = {
      'Content-Security-Policy': CSP, 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
      'X-Frame-Options': 'DENY', 'Permissions-Policy': 'camera=(), microphone=(), geolocation=()', 'Cross-Origin-Opener-Policy': 'same-origin',
    };
    const send = (status, body, headers = {}) => { res.writeHead(status, { ...base, ...headers }); res.end(body); };
    try {
      if (!url.pathname.startsWith('/api/')) {
        for (const [k, v] of Object.entries(base)) res.setHeader(k, v);
        return await serveStatic(req, res, url.pathname);
      }
      const method = req.method;
      let matched = null, params = {};
      for (const r of routes) {
        if (r.method !== method) continue;
        const m = r.re.exec(url.pathname);
        if (m) { matched = r; r.keys.forEach((k, i) => { params[k] = decodeURIComponent(m[i + 1]); }); break; }
      }
      if (!matched) throw notFound('Rota não encontrada');
      const token = cookies(req).vsid;
      const session = authm.getSession(app.meta, token);
      if (!matched.opts.public && !session) throw new HttpError(401, 'unauthenticated', 'Sessão necessária.');
      if (method !== 'GET' && !matched.opts.public) {
        const origin = req.headers.origin;
        if (origin && new URL(origin).host !== req.headers.host) throw forbidden('Origem não permitida.', 'bad_origin');
        if (req.headers['x-csrf-token'] !== session.csrf) throw forbidden('Token CSRF inválido.', 'csrf');
      }
      if (method === 'POST' && matched.pattern === undefined && !matched.opts.public && req.headers['content-type'] && !req.headers['content-type'].includes('json') && Number(req.headers['content-length'] || 0) > 0) {
        throw new HttpError(415, 'unsupported_media_type', 'Content-Type deve ser application/json.');
      }
      const body = ['POST', 'PATCH', 'PUT'].includes(method) ? await readBody(req, matched.opts.bodyLimit) : null;
      const ctx = {
        req, res, params, body, token, session, ip: req.socket.remoteAddress || 'local', secure: req.headers['x-forwarded-proto'] === 'https',
        query: Object.fromEntries(url.searchParams), status: 200,
      };
      if (params.w) ctx.w = app.world(params.w);
      const result = await matched.handler(ctx);
      const extra = ctx.setCookie ? { 'Set-Cookie': ctx.setCookie } : {};
      if (ctx.raw) return send(200, ctx.raw.body, { 'Content-Type': ctx.raw.type, ...ctx.raw.headers, ...extra, 'Cache-Control': 'no-store' });
      return send(ctx.status, JSON.stringify(result ?? { ok: true }), { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', ...extra });
    } catch (e) {
      if (e instanceof HttpError) {
        return send(e.status, JSON.stringify({ error: { code: e.code, message: e.message, details: e.details } }), { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
      }
      console.error('[erro]', redact(e?.stack || e));
      return send(500, JSON.stringify({ error: { code: 'internal', message: 'Erro interno.' } }), { 'Content-Type': 'application/json; charset=utf-8' });
    }
  };
  return createServer(handler);
}
