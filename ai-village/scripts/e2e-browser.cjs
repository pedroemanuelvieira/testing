// E2E opcional no browser (Playwright). Arranca um servidor NOVO e descartável e percorre as jornadas principais.
//   npm i -D playwright && npx playwright install chromium   (uma vez)
//   npm run e2e
const { spawn } = require('node:child_process');
const { mkdtempSync, rmSync } = require('node:fs');
const { tmpdir } = require('node:os');
const { join } = require('node:path');
const assert = require('node:assert/strict');

let chromium;
try { ({ chromium } = require('playwright')); } catch { console.error('Playwright não está instalado (npm i -D playwright).'); process.exit(2); }

const dir = mkdtempSync(join(tmpdir(), 'village-e2e-'));
const PORT = 4300 + Math.floor(Math.random() * 400);
const BASE = `http://127.0.0.1:${PORT}`;
const server = spawn(process.execPath, ['--disable-warning=ExperimentalWarning', join(__dirname, '..', 'server', 'index.js')], {
  env: { ...process.env, VILLAGE_DATA_DIR: dir, VILLAGE_PASSCODE: 'e2e-pass', PORT: String(PORT) }, stdio: 'ignore',
});
const cleanup = () => { server.kill('SIGTERM'); setTimeout(() => rmSync(dir, { recursive: true, force: true }), 500); };

(async () => {
  await new Promise((r) => setTimeout(r, 2000));
  const browser = await chromium.launch();
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  const step = (m) => console.log(`✔ ${m}`);

  await page.goto(BASE);
  await page.fill('input[type=password]', 'e2e-pass'); await page.click('button[type=submit]');
  await page.waitForSelector('.village-svg'); step('login e mapa da vila');

  // 1) cenário guiado F01: worker (processo separado) executa e prova 4·3·1·1·8
  await page.click('text=Executar cenário guiado F01'); await page.waitForSelector('.board');
  await page.waitForSelector('.lane:last-child .tcard', { timeout: 15000 });
  await page.click('.lane:last-child .tcard'); await page.click('text=Ver prova'); await page.waitForSelector('.modal .kpis');
  const kp = await page.$$eval('.modal .kpi .v', (e) => e.map((x) => x.textContent));
  assert.deepEqual(kp, ['4', '3', '1', '1', '8']); step(`F01 executado no worker: ${kp.join(' · ')}`);
  await page.keyboard.press('Escape'); await page.keyboard.press('Escape');

  // 2) chat demo: sugestão → tarefa (CSV colado) → prova
  await page.goto(`${BASE}/#/vila`); await page.waitForSelector('.village-svg');
  await page.click('.agent[aria-label^="Kai Pessoal"]'); await page.waitForSelector('.drawer');
  await page.fill('.drawer textarea', 'quero validar um csv'); await page.keyboard.press('Enter');
  await page.click('text=Criar tarefa para Rin Okada'); await page.waitForSelector('.modal .box');
  await page.fill('.modal textarea[placeholder^="registo"]', 'produto,regiao,vendas\nA,N,10\nB,S,20\nA,N,10\nC,N,abc\n');
  await page.click('.modal button:has-text("Criar tarefa")'); await page.waitForSelector('text=Tarefa criada: ');
  step('chat demo → tarefa criada com CSV colado');
  await page.keyboard.press('Escape');

  // 3) D1: mensagem com dado real é bloqueada e não guardada
  await page.click('.agent[aria-label^="Kai Pessoal"]'); await page.waitForSelector('.drawer');
  await page.fill('.drawer textarea', 'o meu email é joao.silva@empresa-real.pt'); await page.keyboard.press('Enter');
  await page.waitForSelector('text=bloqueada pela guarda D1'); step('guarda D1 bloqueou a mensagem'); await page.keyboard.press('Escape');

  // 4) novo agente sem código (a unidade tem poucos membros → aparece no mapa)
  const NAME = `E2E ${Date.now().toString(36)}`;
  await page.click('button:has-text("＋ Agente")'); await page.waitForSelector('.modal .box');
  await page.fill('.modal input[type=text] >> nth=0', NAME);
  await page.selectOption('.modal select >> nth=0', { label: 'Aprendizagem' });
  await page.click('.modal button:has-text("Criar agente")'); await page.waitForSelector('text=Agente criado.');
  const n = await page.$$eval('.agent', (a, nm) => a.filter((x) => x.getAttribute('aria-label').startsWith(nm)).length, NAME);
  assert.equal(n, 1); step('novo agente criado e visível no mapa');

  // 5) aprovações simuladas: pedir → aprovar → executar uma só vez
  await page.goto(`${BASE}/#/trabalho/aprovacoes`); await page.click('text=Nova ação simulada');
  await page.click('.modal button:has-text("Pedir aprovação")'); await page.waitForSelector('text=Aprovar esta ação exata');
  await page.click('text=Aprovar esta ação exata'); await page.click('text=Executar simulação');
  await page.waitForSelector('text=nada saiu da app'); step('aprovação simulada executada uma vez');

  // 6) Hoje (rotinas) no mundo profissional: registar uma execução
  await page.goto(`${BASE}/#/vila`); await page.click('button:has-text("Profissional")'); await page.waitForTimeout(500);
  await page.goto(`${BASE}/#/trabalho/hoje`); await page.waitForSelector('text=Rotinas da equipa');
  await page.click('tr:has-text("Saúde do ETL") button:has-text("Registar")'); await page.click('.modal button:has-text("Registar")');
  await page.waitForSelector('text=Execução registada.'); step('Hoje: execução de rotina registada');

  // 7) mobile 390px sem scroll horizontal
  const mp = await (await browser.newContext({ viewport: { width: 390, height: 844 } })).newPage();
  await mp.goto(BASE); await mp.fill('input[type=password]', 'e2e-pass'); await mp.click('button[type=submit]'); await mp.waitForSelector('.kpis');
  const [sw, iw] = await mp.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
  assert.ok(sw <= iw, `scroll horizontal em 390px (${sw}>${iw})`); step('390 px sem scroll horizontal');

  assert.deepEqual(errors, [], `erros de consola: ${errors.join('; ')}`); step('sem erros de consola');
  await browser.close();
})().then(() => { cleanup(); }).catch((e) => { console.error('✖ E2E FALHOU:', e.message); cleanup(); process.exit(1); });
