// Guarda D1: esta instância só aceita dados fictícios/sintéticos (REQUISITOS §7).
// O classificador AUXILIA — não prova anonimização. Quando deteta algo, o chamador
// deve parar o ramo, NÃO guardar, NÃO resumir e NÃO reformular o conteúdo.
//
// Nunca se guarda uma lista de nomes reais como filtro (D1) — só padrões estruturais.

const SAFE_EMAIL_DOMAINS = /(^|\.)(example\.(com|org|net)|example|invalid|test|localhost)$/i;

function luhn(digits) {
  let sum = 0, alt = false;
  for (let i = digits.length - 1; i >= 0; i--) {
    let n = digits.charCodeAt(i) - 48;
    if (alt) { n *= 2; if (n > 9) n -= 9; }
    sum += n; alt = !alt;
  }
  return sum % 10 === 0;
}

const DETECTORS = [
  {
    id: 'email_real',
    label: 'endereço de email aparentemente real',
    test(text) {
      const re = /[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,}|[A-Za-z0-9-]+)/g;
      for (const m of text.matchAll(re)) if (!SAFE_EMAIL_DOMAINS.test(m[1])) return true;
      return false;
    },
  },
  { id: 'iban', label: 'IBAN', test: (t) => /\b[A-Z]{2}\d{2}[ ]?(?:\d{4}[ ]?){4,7}\d{1,4}\b/.test(t) },
  { id: 'nif_rotulado', label: 'NIF/NIPC', test: (t) => /\b(nif|nipc|vat)\b[^\d]{0,12}\d{9}\b/i.test(t) },
  { id: 'telefone_rotulado', label: 'número de telefone', test: (t) => /(\+351[ -]?\d{3}[ -]?\d{3}[ -]?\d{3})|(\b(tel|telefone|telem[óo]vel|tlm)\b[^\d]{0,10}\d{3}[ -]?\d{3}[ -]?\d{3})/i.test(t) },
  {
    id: 'cartao', label: 'número de cartão',
    test(t) {
      for (const m of t.matchAll(/\b(?:\d[ -]?){13,19}\b/g)) {
        const d = m[0].replace(/\D/g, '');
        if (d.length >= 13 && d.length <= 19 && luhn(d)) return true;
      }
      return false;
    },
  },
  { id: 'credencial', label: 'credencial/token', test: (t) => /(sk-ant-[A-Za-z0-9_-]{10,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----)/.test(t) },
  { id: 'segredo_canario', label: 'segredo (canário de teste)', test: (t) => /CANARIO_SEGREDO_[A-Za-z0-9_]+/.test(t) },
  // Canário fictício usado por QA para provar o bloqueio (CA22) sem dados reais.
  { id: 'canario_d1', label: 'conteúdo marcado como proibido (canário D1)', test: (t) => /CANARIO_D1_PROIBIDO/.test(t) },
];

export function classifyD1(text) {
  const s = String(text ?? '');
  const hits = DETECTORS.filter((d) => d.test(s));
  return { blocked: hits.length > 0, categories: hits.map((h) => h.id), labels: hits.map((h) => h.label) };
}

export function d1Notice(result) {
  return `Detetei ${result.labels[0]}${result.labels.length > 1 ? ' (e outros)' : ''}. Parei o processamento e não guardei nem resumi o conteúdo. ` +
    'Envia uma versão higienizada (dados fictícios ou placeholders como <CLIENTE_EXEMPLO>).';
}
