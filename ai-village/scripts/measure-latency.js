// CA29/H07: 30 execuções SEQUENCIAIS (concorrência 1) da fixture F01.  npm run measure
//  - feedback  = tempo até o backend aceitar o pedido (criar tarefa)       · meta proposta: p95 ≤ 2 s
//  - conclusão = do pedido aceite até o resultado + prova disponíveis       · meta proposta: p95 ≤ 10 s
// Resultado = amostra desta máquina/versão (registada abaixo). NÃO é um SLA.
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir, cpus, platform, release } from 'node:os';
import { join } from 'node:path';
import { createApp } from '../server/app.js';
import { createHttpServer } from '../server/http.js';
import { runOnce } from '../server/modules/worker.js';
import { loadOrg } from '../server/modules/org.js';

const N = 30;
const F01 = 'registo,grupo,quantidade\nS01,A,2\nS02,B,3\nS03,A,\nS02,B,3\n';
const dir = mkdtempSync(join(tmpdir(), 'village-measure-'));
const app = createApp({ dataDir: dir, passcode: 'm' });
const server = createHttpServer(app);
await new Promise((r) => server.listen(0, '127.0.0.1', r));
const base = `http://127.0.0.1:${server.address().port}`;
let cookie = '', csrf = '';
const call = async (m, p, b) => {
  const res = await fetch(base + p, { method: m, headers: { 'content-type': 'application/json', ...(cookie ? { cookie } : {}), ...(m !== 'GET' ? { 'x-csrf-token': csrf } : {}) }, body: b ? JSON.stringify(b) : undefined });
  const sc = res.headers.get('set-cookie'); if (sc) cookie = sc.split(';')[0];
  return res.json();
};
csrf = (await call('POST', '/api/login', { passcode: 'm' })).csrf;
const w = app.world('personal');
const rin = loadOrg(w).agents.find((a) => a.display_name === 'Rin Okada');
const pct = (a, p) => { const s = [...a].sort((x, y) => x - y); return s[Math.min(s.length - 1, Math.ceil((p / 100) * s.length) - 1)]; };
const feedback = [], done = [], errors = [];
for (let i = 0; i < N; i++) {
  const t0 = performance.now();
  const art = await call('POST', '/api/w/personal/artifacts', { name: `f${i}.csv`, kind: 'csv', content: F01 });
  const task = await call('POST', '/api/w/personal/tasks', { title: `F01 #${i}`, capability: 'csv.validate', assigned_agent_id: rin.id, input_refs: [art.id], config: { numeric_column: 'quantidade' } });
  const t1 = performance.now();
  runOnce(w);
  const d = await call('GET', `/api/w/personal/tasks/${task.id}`);
  const t2 = performance.now();
  if (d.state !== 'completed' || d.evidence.length !== 1) errors.push(`#${i}: ${d.state}`);
  feedback.push(t1 - t0); done.push(t2 - t0);
}
const r = (x) => Math.round(x * 10) / 10;
const out = {
  amostra: `${N} execuções sequenciais, concorrência 1, fixture F01 (4 linhas)`, ambiente: { node: process.version, so: `${platform()} ${release()}`, cpu: cpus()[0]?.model, cpus: cpus().length },
  feedback_ms: { p50: r(pct(feedback, 50)), p95: r(pct(feedback, 95)), max: r(Math.max(...feedback)) }, conclusao_ms: { p50: r(pct(done, 50)), p95: r(pct(done, 95)), max: r(Math.max(...done)) },
  metas_H07: { feedback_p95_ms: 2000, conclusao_p95_ms: 10000 }, erros: errors,
  veredito: pct(feedback, 95) <= 2000 && pct(done, 95) <= 10000 && !errors.length ? 'dentro das metas propostas NESTA amostra (não é SLA)' : 'FORA das metas propostas ou com erros',
};
console.log(JSON.stringify(out, null, 2));
await new Promise((r2) => server.close(r2)); app.close(); rmSync(dir, { recursive: true, force: true });
