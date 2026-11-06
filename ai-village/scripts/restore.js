// Restauro ISOLADO: destino tem de estar vazio. Suspende os jobs e reaplica revogações/expurgos posteriores.
//   VILLAGE_BACKUP_PASSPHRASE=… npm run restore -- <ficheiro.vbk> <pasta-destino> [pasta-data-com-tombstones]
import { restoreBackup } from '../server/backup.js';

const [file, target, tomb] = process.argv.slice(2);
const pass = process.env.VILLAGE_BACKUP_PASSPHRASE;
if (!file || !target || !pass) { console.error('Uso: VILLAGE_BACKUP_PASSPHRASE=… npm run restore -- <ficheiro.vbk> <pasta-destino> [pasta-data-com-tombstones]'); process.exit(2); }
try {
  const rep = restoreBackup({ file, passphrase: pass, targetDir: target, tombstonesDir: tomb });
  for (const w of rep.worlds) {
    console.log(`\nMundo ${w.id}: esquema v${w.schema_version} · auditoria ${w.audit_chain.ok ? 'ÍNTEGRA' : 'QUEBRADA'} (${w.audit_chain.checked} eventos) · jobs suspensos: ${w.jobs_suspended}`);
    console.log('  contagens:', JSON.stringify(w.counts));
    console.log('  confere com o backup:', w.matches_backup ? 'sim' : 'NÃO', '| tombstones reaplicados:', w.tombstones_reapplied.length);
  }
  console.log(`\nRestaurado em ${target}. Arranca com VILLAGE_DATA_DIR=${target} npm start (jobs ficam suspensos até os reativares em Configuração → Definições).`);
} catch (e) { console.error('Restauro falhou:', e.message); process.exit(1); }
