// Autenticação de utilizador único (H01): passcode (scrypt) + sessão HttpOnly + CSRF.
// O passcode vem de VILLAGE_PASSCODE ou é gerado no primeiro arranque (mostrado uma vez na consola).
import { scryptSync, randomBytes, timingSafeEqual } from 'node:crypto';
import { sha256, clock, HttpError } from './lib/util.js';

const SESSION_TTL_MS = 12 * 3600 * 1000;
const MAX_ATTEMPTS = 8, WINDOW_MS = 5 * 60 * 1000;

const hashPass = (pass, salt) => scryptSync(pass, salt, 32, { N: 16384 }).toString('hex');

export function initAuth(meta, { passcode } = {}) {
  meta.exec(`CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, csrf TEXT NOT NULL, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS login_attempts (ip TEXT NOT NULL, at INTEGER NOT NULL);`);
  const row = meta.prepare("SELECT value FROM kv WHERE key='passcode'").get();
  let generated = null;
  const wanted = passcode || (row ? null : (generated = randomBytes(9).toString('base64url')));
  if (wanted) {
    const salt = randomBytes(16).toString('hex');
    meta.prepare("INSERT OR REPLACE INTO kv(key,value) VALUES ('passcode', ?)").run(JSON.stringify({ salt, hash: hashPass(wanted, salt) }));
    // Mudar o passcode invalida todas as sessões existentes.
    meta.exec('DELETE FROM sessions');
  }
  return { generated };
}

export function login(meta, ip, pass) {
  const now = clock.now();
  meta.prepare('DELETE FROM login_attempts WHERE at < ?').run(now - WINDOW_MS);
  const n = meta.prepare('SELECT COUNT(*) c FROM login_attempts WHERE ip=?').get(ip).c;
  if (n >= MAX_ATTEMPTS) throw new HttpError(429, 'too_many_attempts', 'Demasiadas tentativas. Aguarda uns minutos.');
  const rec = JSON.parse(meta.prepare("SELECT value FROM kv WHERE key='passcode'").get().value);
  const ok = typeof pass === 'string' && timingSafeEqual(Buffer.from(hashPass(pass, rec.salt), 'hex'), Buffer.from(rec.hash, 'hex'));
  if (!ok) {
    meta.prepare('INSERT INTO login_attempts(ip,at) VALUES (?,?)').run(ip, now);
    throw new HttpError(401, 'bad_credentials', 'Passcode incorreto.');
  }
  const token = randomBytes(32).toString('base64url');
  const csrf = randomBytes(24).toString('base64url');
  meta.prepare('INSERT INTO sessions(token_hash,csrf,created_at,expires_at) VALUES (?,?,?,?)').run(sha256(token), csrf, now, now + SESSION_TTL_MS);
  return { token, csrf, maxAge: SESSION_TTL_MS / 1000 };
}

export function getSession(meta, token) {
  if (!token) return null;
  const s = meta.prepare('SELECT * FROM sessions WHERE token_hash=?').get(sha256(token));
  if (!s) return null;
  if (s.expires_at < clock.now()) { meta.prepare('DELETE FROM sessions WHERE token_hash=?').run(s.token_hash); return null; }
  return { csrf: s.csrf };
}

export function logout(meta, token) { if (token) meta.prepare('DELETE FROM sessions WHERE token_hash=?').run(sha256(token)); }
