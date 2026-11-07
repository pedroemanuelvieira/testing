// Helpers de UI sem dependências: construção segura de DOM (texto nunca vira HTML), gaveta/modal
// com armadilha de foco + restauro de foco, toasts anunciados por leitor de ecrã.
// append/prepend/replaceChildren nativos escrevem a palavra «null» no DOM e não aceitam arrays.
// Normaliza globalmente: ignora null/undefined/false e achata listas.
for (const m of ['append', 'prepend', 'replaceChildren']) {
  const orig = Element.prototype[m];
  Element.prototype[m] = function patched(...args) { return orig.apply(this, args.flat(Infinity).filter((x) => x !== null && x !== undefined && x !== false)); };
}

export function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === 'html') el.innerHTML = v; // só para SVG gerado localmente (já escapado)
    else if (k in el && k !== 'list' && typeof v !== 'object') { try { el[k] = v; } catch { el.setAttribute(k, v); } }
    else el.setAttribute(k, v === true ? '' : v);
  }
  add(el, children);
  return el;
}
function add(el, children) {
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c.nodeType ? c : document.createTextNode(String(c)));
  }
}
export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export const clear = (el) => { while (el.firstChild) el.removeChild(el.firstChild); return el; };

export function toast(msg, kind = 'ok', ms = 4200) {
  const box = document.getElementById('toasts');
  const t = h('div', { class: `toast ${kind}`, role: kind === 'error' ? 'alert' : 'status' }, msg);
  box.append(t);
  setTimeout(() => t.remove(), ms);
}

const FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';
const stack = [];

function trap(layer, onClose) {
  const opener = document.activeElement;
  const onKey = (e) => {
    if (stack[stack.length - 1] !== layer) return;
    if (e.key === 'Escape') { e.stopPropagation(); onClose(); return; }
    if (e.key !== 'Tab') return;
    const f = [...layer.querySelectorAll(FOCUSABLE)].filter((x) => x.offsetParent !== null);
    if (!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  };
  document.addEventListener('keydown', onKey, true);
  stack.push(layer);
  return () => {
    document.removeEventListener('keydown', onKey, true);
    stack.splice(stack.indexOf(layer), 1);
    if (opener && document.contains(opener)) opener.focus();
  };
}

export function openDrawer({ title, header, body, onClose, label }) {
  const scrim = h('div', { class: 'scrim' });
  const closeBtn = h('button', { class: 'btn icon', 'aria-label': 'Fechar painel', onclick: () => close() }, '✕');
  const bodyEl = h('div', { class: 'body' }, body);
  const headEl = h('header', {}, header, h('span', { class: 'grow' }), closeBtn);
  const drawer = h('aside', { class: 'drawer', role: 'dialog', 'aria-modal': 'true', 'aria-label': label || title }, headEl, bodyEl);
  document.body.append(scrim, drawer);
  const release = trap(drawer, () => close());
  scrim.addEventListener('click', () => close());
  let closed = false;
  function close() { if (closed) return; closed = true; release(); scrim.remove(); drawer.remove(); onClose?.(); }
  (drawer.querySelector('[data-autofocus]') || closeBtn).focus();
  return { close, bodyEl, headEl, el: drawer };
}

const modalStack = [];
export function openModal({ title, body, actions = [], wide = false, onClose }) {
  const scrim = h('div', { class: 'scrim' });
  const titleId = `m${Math.random().toString(36).slice(2, 8)}`;
  const box = h('div', { class: `box${wide ? ' wide' : ''}`, role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': titleId },
    h('header', {}, h('h2', { id: titleId }, title), h('span', { class: 'grow' }), h('button', { class: 'btn icon', 'aria-label': 'Fechar', onclick: () => close() }, '✕')),
    body, actions.length ? h('div', { class: 'foot' }, actions) : null);
  const wrap = h('div', { class: 'modal' }, box);
  scrim.style.zIndex = 65;
  // Modal por cima de modal: esconde o de baixo (sem ficar a espreitar) e repõe-no ao fechar.
  const below = modalStack[modalStack.length - 1];
  if (below) { below.wrap.style.visibility = 'hidden'; below.scrim.style.visibility = 'hidden'; }
  const entry = { wrap, scrim }; modalStack.push(entry);
  document.body.append(scrim, wrap);
  const release = trap(box, () => close());
  let closed = false;
  scrim.addEventListener('click', () => close());
  function close() {
    if (closed) return; closed = true; release(); scrim.remove(); wrap.remove();
    modalStack.splice(modalStack.indexOf(entry), 1);
    const top = modalStack[modalStack.length - 1];
    if (top) { top.wrap.style.visibility = ''; top.scrim.style.visibility = ''; }
    onClose?.();
  }
  (box.querySelector('[data-autofocus]') || box.querySelector(FOCUSABLE))?.focus();
  return { close, box };
}

export function confirmDialog(message, { okLabel = 'Confirmar', danger = false } = {}) {
  return new Promise((resolve) => {
    let done = false;
    const finish = (v) => { if (!done) { done = true; resolve(v); } };
    const m = openModal({
      title: 'Confirmar', body: h('p', {}, message), onClose: () => finish(false),
      actions: [h('button', { class: 'btn', onclick: () => m.close() }, 'Cancelar'),
        h('button', { class: `btn ${danger ? 'danger' : 'primary'}`, 'data-autofocus': '', onclick: () => { finish(true); m.close(); } }, okLabel)],
    });
  });
}

/** Diálogo de texto acessível (substitui window.prompt). Resolve null se cancelado. */
export function promptDialog(label, { okLabel = 'Confirmar', required = true, multiline = false } = {}) {
  return new Promise((resolve) => {
    let done = false;
    const finish = (v) => { if (!done) { done = true; resolve(v); } };
    const input = multiline ? h('textarea', { 'data-autofocus': '' }) : h('input', { type: 'text', 'data-autofocus': '' });
    const ok = h('button', { class: 'btn primary' }, okLabel);
    const m = openModal({
      title: label, onClose: () => finish(null), body: field('Texto', input),
      actions: [h('button', { class: 'btn', onclick: () => m.close() }, 'Cancelar'), ok],
    });
    const go = () => { if (required && !input.value.trim()) { input.focus(); return; } finish(input.value.trim()); m.close(); };
    ok.addEventListener('click', go);
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !multiline) { e.preventDefault(); go(); } });
  });
}

/** Diálogo de escolha (select). Resolve o value escolhido ou null. */
export function selectDialog(label, options, { okLabel = 'Escolher' } = {}) {
  return new Promise((resolve) => {
    let done = false;
    const finish = (v) => { if (!done) { done = true; resolve(v); } };
    const sel = h('select', { 'data-autofocus': '' }, options.map((o) => h('option', { value: o.value }, o.label)));
    const ok = h('button', { class: 'btn primary' }, okLabel);
    const m = openModal({
      title: label, onClose: () => finish(null), body: field('Opção', sel),
      actions: [h('button', { class: 'btn', onclick: () => m.close() }, 'Cancelar'), ok],
    });
    ok.addEventListener('click', () => { finish(sel.value); m.close(); });
  });
}

export function field(label, input, hint) {
  const id = `f${Math.random().toString(36).slice(2, 8)}`;
  if (input.tagName) input.id = id;
  return h('div', { class: 'field' }, h('label', { for: id }, label), input, hint ? h('span', { class: 'hint' }, hint) : null);
}

export const fmtTime = (iso) => (iso ? new Date(iso).toLocaleString('pt-PT', { timeZone: 'Europe/Lisbon', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' }) + ' (Lisboa)' : '—');
export const fmtShort = (iso) => (iso ? new Date(iso).toLocaleString('pt-PT', { timeZone: 'Europe/Lisbon', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—');

export const STATE_PT = {
  draft: 'rascunho', pending: 'pendente', assigned: 'atribuída', running: 'em execução', awaiting_approval: 'a aguardar aprovação',
  completed: 'concluída', blocked: 'bloqueada', failed: 'falhada', cancelled: 'cancelada',
};
export const STATE_BADGE = { draft: 'dim', pending: 'info', assigned: 'info', running: 'cyan', awaiting_approval: 'violet', completed: 'ok', blocked: 'warn', failed: 'bad', cancelled: 'dim' };
export const stateBadge = (s) => h('span', { class: `badge ${STATE_BADGE[s] || 'dim'}` }, STATE_PT[s] || s);

export const ACTIVITY = {
  disponivel: { label: 'Disponível', icon: '●', hint: 'Sem tentativa de execução ativa.' },
  ocupado: { label: 'Ocupado', icon: '⚙', hint: 'Há uma tentativa de execução real em curso.' },
  bloqueado: { label: 'Bloqueado', icon: '!', hint: 'Tem tarefas falhadas ou bloqueadas à espera de decisão.' },
  inativo: { label: 'Inativo', icon: '‖', hint: 'Desativado: não recebe novos trabalhos.' },
  arquivado: { label: 'Arquivado', icon: '▫', hint: 'Arquivado: histórico preservado.' },
};
export const activityBadge = (st) => {
  const a = ACTIVITY[st] || ACTIVITY.disponivel;
  return h('span', { class: `status s-${st}`, title: a.hint }, h('span', { 'aria-hidden': 'true' }, a.icon), a.label);
};

export function debounce(fn, ms = 250) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }
export async function busy(btn, fn) {
  btn.disabled = true;
  try { return await fn(); } finally { btn.disabled = false; }
}
