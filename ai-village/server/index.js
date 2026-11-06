// Arranque: servidor HTTP + worker em processo separado (monólito modular + worker, H02).
import { fork } from 'node:child_process';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createApp } from './app.js';
import { createHttpServer } from './http.js';

const here = dirname(fileURLToPath(import.meta.url));
const dataDir = process.env.VILLAGE_DATA_DIR || join(here, '..', 'data');
const port = Number(process.env.PORT || 4173);
const host = process.env.HOST || '127.0.0.1';

const app = createApp({ dataDir, passcode: process.env.VILLAGE_PASSCODE });
const server = createHttpServer(app);

server.listen(port, host, () => {
  console.log(`\n  AI Village a correr em http://${host}:${port}`);
  console.log(`  Dados: ${dataDir}`);
  if (app.generatedPasscode) {
    console.log(`  Passcode (gerado agora, mostrado UMA vez): ${app.generatedPasscode}`);
    console.log('  Para definir o teu: VILLAGE_PASSCODE=... npm start');
  } else console.log('  Passcode: o já definido (ou VILLAGE_PASSCODE).');
});

// Worker separado: sobrevive a reinícios do servidor e recupera leases (CA14).
let child = null, stopping = false;
function startWorker() {
  if (process.env.VILLAGE_NO_WORKER === '1') return;
  child = fork(join(here, 'worker-main.js'), [], { env: { ...process.env, VILLAGE_DATA_DIR: dataDir }, execArgv: ['--disable-warning=ExperimentalWarning'] });
  child.on('exit', (code) => { if (!stopping) { console.error(`[worker] terminou (${code}); reinicia em 2s`); setTimeout(startWorker, 2000); } });
}
startWorker();

function shutdown() {
  stopping = true;
  child?.kill('SIGTERM');
  server.close(() => { app.close(); process.exit(0); });
  setTimeout(() => process.exit(0), 2000).unref();
}
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
