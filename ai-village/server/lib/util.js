// Utilitários partilhados: ids opacos, digests, relógio injectável, erros HTTP.
import { randomBytes, createHash } from 'node:crypto';

const ALPHABET = 'abcdefghjkmnpqrstvwxyz23456789';
export function newId(prefix) {
  const bytes = randomBytes(16);
  let s = '';
  for (const b of bytes) s += ALPHABET[b % ALPHABET.length];
  return `${prefix}_${s}`;
}

export const sha256 = (data) => createHash('sha256').update(data).digest('hex');

// JSON canónico (chaves ordenadas) para digests estáveis.
export function canonical(value) {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  return `{${Object.keys(value).sort().map((k) => `${JSON.stringify(k)}:${canonical(value[k])}`).join(',')}}`;
}
export const digestOf = (value) => sha256(canonical(value));

// Relógio injectável: testes controlam o tempo (retenção, leases, expiração).
let offsetMs = 0;
let fixed = null;
export const clock = {
  now: () => (fixed ?? Date.now() + offsetMs),
  iso: () => new Date(clock.now()).toISOString(),
  set(ms) { fixed = ms; },
  advance(ms) { if (fixed !== null) fixed += ms; else offsetMs += ms; },
  reset() { fixed = null; offsetMs = 0; },
};
export const addMs = (iso, ms) => new Date(Date.parse(iso) + ms).toISOString();
export const addDays = (iso, d) => addMs(iso, d * 86400000);

export class HttpError extends Error {
  constructor(status, code, message, details) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}
export const bad = (msg, code = 'invalid_request', details) => new HttpError(400, code, msg, details);
export const notFound = (msg = 'Recurso não encontrado') => new HttpError(404, 'not_found', msg);
export const forbidden = (msg = 'Operação negada', code = 'forbidden') => new HttpError(403, code, msg);
export const conflict = (msg, code = 'conflict', details) => new HttpError(409, code, msg, details);
export const unprocessable = (msg, code = 'unprocessable', details) => new HttpError(422, code, msg, details);

export const json = (v) => JSON.stringify(v ?? null);
export const parseJson = (s, fallback = null) => {
  if (s === null || s === undefined) return fallback;
  try { return JSON.parse(s); } catch { return fallback; }
};

// Redacção defensiva de segredos em strings de log/erro (CA21).
const SECRET_PATTERNS = [
  /sk-ant-[A-Za-z0-9_\-]{10,}/g,
  /sk-[A-Za-z0-9]{20,}/g,
  /(api[_-]?key|token|secret|authorization|passcode)["'\s:=]+[A-Za-z0-9_\-\.]{8,}/gi,
  /CANARIO_SEGREDO_[A-Za-z0-9_]+/g,
];
export function redact(text) {
  let out = String(text ?? '');
  for (const re of SECRET_PATTERNS) out = out.replace(re, '[REDACTED]');
  return out;
}
