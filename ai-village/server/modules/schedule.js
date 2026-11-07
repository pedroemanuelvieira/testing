// Agendas em hora de Lisboa (Europe/Lisbon, com horário de verão), sem bibliotecas.
// Formas suportadas: {kind:'weekdays'|'daily'|'weekly'|'monthly', times:['HH:MM',…], weekday?:0-6 (0=dom), day?:1-31}
const DTF = new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Lisbon', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23', weekday: 'short' });
const WD = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };
const WD_PT = ['domingos', 'segundas', 'terças', 'quartas', 'quintas', 'sextas', 'sábados'];

export function lisbonParts(ms) {
  const p = Object.fromEntries(DTF.formatToParts(new Date(ms)).map((x) => [x.type, x.value]));
  return { y: +p.year, m: +p.month, d: +p.day, hh: +p.hour, mm: +p.minute, weekday: WD[p.weekday] };
}
export function lisbonToUtc(y, m, d, hh, mm) {
  let guess = Date.UTC(y, m - 1, d, hh, mm);
  for (let i = 0; i < 2; i++) {
    const p = lisbonParts(guess);
    const asUtc = Date.UTC(p.y, p.m - 1, p.d, p.hh, p.mm);
    guess -= asUtc - Date.UTC(y, m - 1, d, hh, mm);
  }
  return guess;
}
export const lisbonDate = (ms) => { const p = lisbonParts(ms); return `${p.y}-${String(p.m).padStart(2, '0')}-${String(p.d).padStart(2, '0')}`; };

export function validateSchedule(s) {
  if (!s || typeof s !== 'object') return 'Agenda inválida.';
  if (!['weekdays', 'daily', 'weekly', 'monthly'].includes(s.kind)) return 'Tipo de agenda inválido.';
  if (!Array.isArray(s.times) || !s.times.length || s.times.length > 24 || s.times.some((t) => !/^([01]\d|2[0-3]):[0-5]\d$/.test(t))) return 'Horas inválidas (HH:MM).';
  if (s.kind === 'weekly' && !(Number.isInteger(s.weekday) && s.weekday >= 0 && s.weekday <= 6)) return 'Dia da semana inválido.';
  if (s.kind === 'monthly' && !(Number.isInteger(s.day) && s.day >= 1 && s.day <= 28)) return 'Dia do mês inválido (1–28).';
  return null;
}

function runsOn(s, y, m, d) {
  const wd = new Date(Date.UTC(y, m - 1, d)).getUTCDay();
  if (s.kind === 'daily') return true;
  if (s.kind === 'weekdays') return wd >= 1 && wd <= 5;
  if (s.kind === 'weekly') return wd === s.weekday;
  return d === s.day;
}

/** Slots (ms UTC) do dia de Lisboa que contém `dayMs`. */
export function slotsForDay(s, dayMs) {
  const p = lisbonParts(dayMs);
  if (!runsOn(s, p.y, p.m, p.d)) return [];
  return [...s.times].sort().map((t) => lisbonToUtc(p.y, p.m, p.d, +t.slice(0, 2), +t.slice(3)));
}
export function nextSlot(s, fromMs) {
  for (let i = 0; i < 40; i++) { const found = slotsForDay(s, fromMs + i * 86400000).find((x) => x > fromMs); if (found) return found; }
  return null;
}
/** Os últimos `n` slots ≤ ms (mais antigo primeiro). */
export function lastSlots(s, ms, n = 1) {
  const desc = [];
  for (let i = 0; i < 60 && desc.length < n; i++) {
    for (const x of slotsForDay(s, ms - i * 86400000).reverse()) { if (x <= ms && desc.length < n) desc.push(x); }
  }
  return desc.reverse();
}
export function cadenceLabel(s) {
  const times = s.times.join(', ');
  if (s.kind === 'daily') return s.times.length > 1 ? `${s.times.length}×/dia (${times})` : `diária ${times}`;
  if (s.kind === 'weekdays') return `dias úteis ${times}`;
  if (s.kind === 'weekly') return `${WD_PT[s.weekday]} ${times}`;
  return `mensal, dia ${s.day} ${times}`;
}
