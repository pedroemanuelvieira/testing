import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createApp } from '../server/app.js';
import { createHttpServer } from '../server/http.js';
import { loadOrg } from '../server/modules/org.js';
import { clock } from '../server/lib/util.js';

export const PASS = 'teste-passcode';

export function makeApp(opts = {}) {
  clock.reset();
  const dir = mkdtempSync(join(tmpdir(), 'village-test-'));
  const app = createApp({ dataDir: dir, passcode: PASS, deps: opts.deps || {} });
  return { app, dir, cleanup() { app.close(); rmSync(dir, { recursive: true, force: true }); clock.reset(); } };
}

export const agentByName = (w, name) => loadOrg(w).agents.find((a) => a.display_name === name);

/** Servidor HTTP real em porta efémera + cliente com cookie/CSRF. */
export async function startServer(opts = {}) {
  const ctx = makeApp(opts);
  const server = createHttpServer(ctx.app);
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  const base = `http://127.0.0.1:${server.address().port}`;
  const state = { cookie: '', csrf: '' };
  async function raw(method, path, body, extraHeaders = {}) {
    const headers = { ...extraHeaders };
    if (body !== undefined) headers['content-type'] = 'application/json';
    if (state.cookie) headers.cookie = state.cookie;
    if (state.csrf && method !== 'GET') headers['x-csrf-token'] = state.csrf;
    const res = await fetch(base + path, { method, headers, body: body !== undefined ? JSON.stringify(body) : undefined });
    const sc = res.headers.get('set-cookie');
    if (sc) state.cookie = sc.split(';')[0];
    const text = await res.text();
    let data; try { data = JSON.parse(text); } catch { data = text; }
    return { status: res.status, data, headers: res.headers };
  }
  const api = async (method, path, body) => {
    const r = await raw(method, path, body);
    return r;
  };
  async function login(pass = PASS) {
    const r = await raw('POST', '/api/login', { passcode: pass });
    if (r.status === 200) state.csrf = r.data.csrf;
    return r;
  }
  return {
    ...ctx, base, api, raw, login, state, server,
    async close() { await new Promise((r) => server.close(r)); ctx.cleanup(); },
  };
}
