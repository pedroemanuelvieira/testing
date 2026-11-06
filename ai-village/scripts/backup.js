// Backup cifrado das BDs dos mundos.  VILLAGE_BACKUP_PASSPHRASE=… npm run backup
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createApp } from '../server/app.js';
import { createBackup } from '../server/backup.js';
import { sweepBackups } from '../server/modules/retention.js';
import { getSettings } from '../server/modules/settings.js';

const here = dirname(fileURLToPath(import.meta.url));
const dataDir = process.env.VILLAGE_DATA_DIR || join(here, '..', 'data');
const pass = process.env.VILLAGE_BACKUP_PASSPHRASE;
if (!pass) { console.error('Define VILLAGE_BACKUP_PASSPHRASE (a frase fica só contigo; sem ela o backup não abre).'); process.exit(2); }
const app = createApp({ dataDir });
const r = createBackup({ app, passphrase: pass, outDir: join(dataDir, 'backups') });
const removed = sweepBackups(dataDir, getSettings(app.world('personal')).backup_retention_days);
console.log(`Backup cifrado: ${r.file} (${r.bytes} bytes) · mundos: ${r.worlds.map((w) => w.id).join(', ')} · backups vencidos removidos: ${removed}`);
app.close();
