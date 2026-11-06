// Processo do worker: polling curto; regista heartbeat; recupera leases; faz retenção periódica.
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createApp } from './app.js';
import { runOnce } from './modules/worker.js';
import { sweep, sweepBackups } from './modules/retention.js';
import { getSettings } from './modules/settings.js';
import { clock } from './lib/util.js';

const here = dirname(fileURLToPath(import.meta.url));
const dataDir = process.env.VILLAGE_DATA_DIR || join(here, '..', 'data');
const app = createApp({ dataDir });
let lastSweep = 0;

function tick() {
  for (const w of app.worlds()) {
    try {
      w.db.prepare("INSERT OR REPLACE INTO meta(key,value) VALUES ('worker_heartbeat', ?)").run(clock.iso());
      if (w.policy.execution !== false) runOnce(w);
      if (Date.now() - lastSweep > 3600_000) {
        sweep(w);
        sweepBackups(dataDir, getSettings(w).backup_retention_days);
      }
    } catch (e) { console.error(`[worker:${w.id}]`, e?.message || e); }
  }
  if (Date.now() - lastSweep > 3600_000) lastSweep = Date.now();
}
console.log('[worker] a correr');
tick();
const timer = setInterval(tick, 700);
for (const s of ['SIGINT', 'SIGTERM']) process.on(s, () => { clearInterval(timer); app.close(); process.exit(0); });
