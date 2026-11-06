// Motor CSV determinístico e restrito (RF05). Corre SEMPRE no backend/worker.
// Princípios: o ficheiro é DADO — nunca se executam fórmulas nem instruções (RNF09).
import { HttpError } from '../lib/util.js';

export const CSV_LIMITS = { maxBytes: 1_000_000, maxRows: 10_000, maxCols: 60 }; // H06

export class CsvError extends HttpError {
  constructor(code, message) { super(422, code, message); }
}

export function decodeUtf8(input) {
  const buf = typeof input === 'string' ? Buffer.from(input, 'utf8') : Buffer.from(input);
  if (buf.length > CSV_LIMITS.maxBytes) throw new CsvError('csv_too_large', `Ficheiro acima do limite de ${CSV_LIMITS.maxBytes} bytes.`);
  let text;
  try { text = new TextDecoder('utf-8', { fatal: true }).decode(buf); }
  catch { throw new CsvError('csv_bad_utf8', 'O ficheiro não é UTF-8 válido.'); }
  return text.charCodeAt(0) === 0xfeff ? text.slice(1) : text;
}

function detectDelimiter(firstLine) {
  const counts = { ',': 0, ';': 0, '\t': 0 };
  let inQ = false;
  for (const ch of firstLine) {
    if (ch === '"') inQ = !inQ;
    else if (!inQ && ch in counts) counts[ch]++;
  }
  return Object.entries(counts).sort((a, b) => b[1] - a[1])[0][1] > 0
    ? Object.entries(counts).sort((a, b) => b[1] - a[1])[0][0] : ',';
}

export function parseCsv(text, limits = CSV_LIMITS) {
  if (!text.trim()) throw new CsvError('csv_empty', 'O ficheiro está vazio.');
  const delimiter = detectDelimiter(text.split(/\r?\n/, 1)[0]);
  const rows = [];
  let row = [], field = '', inQ = false, i = 0;
  const n = text.length;
  const pushField = () => { row.push(field); field = ''; };
  const pushRow = () => {
    pushField();
    if (!(row.length === 1 && row[0] === '')) rows.push(row); // ignora linhas totalmente vazias
    row = [];
    if (rows.length > limits.maxRows + 1) throw new CsvError('csv_too_many_rows', `Mais de ${limits.maxRows} linhas de dados.`);
  };
  while (i < n) {
    const ch = text[i];
    if (inQ) {
      if (ch === '"') {
        if (text[i + 1] === '"') { field += '"'; i += 2; continue; }
        inQ = false; i++; continue;
      }
      field += ch; i++; continue;
    }
    if (ch === '"' && field === '') { inQ = true; i++; continue; }
    if (ch === delimiter) { pushField(); i++; continue; }
    if (ch === '\r') { i++; continue; }
    if (ch === '\n') { pushRow(); i++; continue; }
    field += ch; i++;
  }
  if (inQ) throw new CsvError('csv_malformed', 'Aspas por fechar: CSV malformado.');
  if (field !== '' || row.length) pushRow();
  if (rows[0] && rows[0].length > limits.maxCols) throw new CsvError('csv_too_many_cols', `Mais de ${limits.maxCols} colunas.`);
  return { delimiter, header: rows[0] || [], data: rows.slice(1) };
}

const NUM_RE = /^[+-]?\d+(?:[.,]\d+)?$/;
const FORMULA_START = /^[=+\-@]/;
export const parseNumber = (s) => (NUM_RE.test(s.trim()) ? Number(s.trim().replace(',', '.')) : null);
export const isFormulaLike = (s) => FORMULA_START.test(s.trim()) && !NUM_RE.test(s.trim());

/**
 * Valida o CSV e calcula as métricas contratuais.
 * - rows_read: linhas de dados (sem cabeçalho)
 * - valid_numeric / invalid_numeric: coluna numérica definida
 * - duplicates_exact: linhas idênticas a uma anterior (além da primeira ocorrência)
 * - sum_numeric: soma dos valores válidos SEM deduplicar (política explícita)
 */
export function validateCsv(text, config = {}) {
  const { header, data, delimiter } = parseCsv(text);
  const col = config.numeric_column;
  if (!col) throw new CsvError('config_missing_column', 'Indica a coluna numérica (numeric_column).');
  const idx = header.map((h) => h.trim()).indexOf(col);
  if (idx < 0) throw new CsvError('column_not_found', `Coluna «${col}» não existe no cabeçalho.`);

  const seen = new Set();
  const missing = Object.fromEntries(header.map((h) => [h.trim(), 0]));
  let valid = 0, invalid = 0, dup = 0, sum = 0, sumDedup = 0, ragged = 0, formulas = 0;
  const issues = [];
  const note = (line, code, detail) => { if (issues.length < 25) issues.push({ line, code, detail }); };

  data.forEach((r, k) => {
    const line = k + 2; // linha no ficheiro (cabeçalho = 1)
    if (r.length !== header.length) { ragged++; note(line, 'colunas_inconsistentes', `${r.length} colunas, esperadas ${header.length}`); }
    r.forEach((cell, c) => {
      if (cell.trim() === '' && header[c] !== undefined) missing[header[c].trim()]++;
      if (isFormulaLike(cell)) { formulas++; note(line, 'celula_tipo_formula', 'tratada como texto; nunca executada'); }
    });
    const key = JSON.stringify(r);
    const isDup = seen.has(key);
    if (isDup) dup++; else seen.add(key);

    const raw = r[idx] ?? '';
    const num = raw.trim() === '' ? null : parseNumber(raw);
    if (num === null) {
      invalid++;
      note(line, raw.trim() === '' ? 'numerico_em_falta' : 'numerico_invalido', `coluna ${col}`);
    } else {
      valid++; sum += num;
      if (!isDup) sumDedup += num;
    }
  });

  const round = (x) => Math.round(x * 1e9) / 1e9;
  return {
    delimiter,
    columns: header.map((h) => h.trim()),
    numeric_column: col,
    duplicate_policy: 'linha_exata_alem_da_primeira_ocorrencia',
    rows_read: data.length,
    valid_numeric: valid,
    invalid_numeric: invalid,
    duplicates_exact: dup,
    sum_numeric: round(sum),
    sum_numeric_deduplicated: round(sumDedup),
    missing_by_column: missing,
    ragged_rows: ragged,
    formula_like_cells: formulas,
    issues,
  };
}

/** Perfil de colunas (BI): tipos, nulos, distintos, min/max/média e valores mais frequentes. */
export function profileCsv(text) {
  const { header, data, delimiter } = parseCsv(text);
  const columns = header.map((name, c) => {
    const vals = data.map((r) => (r[c] ?? '').trim());
    const filled = vals.filter((v) => v !== '');
    const nums = filled.map(parseNumber).filter((x) => x !== null);
    const freq = new Map();
    for (const v of filled) freq.set(v, (freq.get(v) || 0) + 1);
    const top = [...freq.entries()].sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1)).slice(0, 3)
      .map(([value, count]) => ({ value: isFormulaLike(value) ? `[texto] ${value}` : value, count }));
    const isNumeric = filled.length > 0 && nums.length === filled.length;
    const out = {
      name: name.trim(), inferred_type: isNumeric ? 'numerico' : 'texto',
      non_empty: filled.length, empty: vals.length - filled.length, distinct: freq.size, top_values: top,
    };
    if (isNumeric) {
      const s = nums.reduce((a, b) => a + b, 0);
      Object.assign(out, { min: Math.min(...nums), max: Math.max(...nums), sum: Math.round(s * 1e9) / 1e9, mean: Math.round((s / nums.length) * 1e9) / 1e9 });
    }
    return out;
  });
  return { delimiter, rows_read: data.length, columns_count: header.length, columns };
}
