// AI Village · arranque da app: sessão, navegação (4 destinos, H03), troca de mundo e polling do backend.
import { h, toast, busy, clear } from './ui.js';
import { get, post, setCsrf, ApiError } from './api.js';
import { S, W, loadWorld, loadWorlds, setWorld, subscribe } from './state.js';
import { renderVillage } from './village.js';
import { homeView } from './views/home.js';
import { workView } from './views/work.js';
import { connectionsView } from './views/connections.js';
import { settingsView } from './views/settings.js';

const root = document.getElementById('root');
let view = null, tickTimer = null, route = { page: 'vila', sub: '' };

const NAV = [['vila', 'Vila', '村'], ['trabalho', 'Trabalho', '仕'], ['ligacoes', 'Ligações', '繋'], ['config', 'Configuração', '設']];
const LOGO = `<svg viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="9" fill="#0b1022" stroke="rgba(139,156,255,.5)"/><path d="M4 12.5h24M7 12.5V9.6c3 1.6 15 1.6 18 0v2.9M10.5 12.5V27M21.5 12.5V27" stroke="#ff5a4d" stroke-width="2.4" fill="none" stroke-linecap="round"/><circle cx="16" cy="19.5" r="3" fill="#22d3ee"/></svg>`;

function parseRoute() {
  const [, page = 'vila', sub = ''] = location.hash.split('/');
  route = { page: NAV.some(([id]) => id === page) ? page : 'vila', sub };
}

function loginScreen(message) {
  clear(root);
  const pass = h('input', { type: 'password', autocomplete: 'current-password', 'data-autofocus': '', placeholder: 'Passcode', 'aria-label': 'Passcode' });
  const err = h('div', { class: 'note bad', role: 'alert', style: message ? {} : { display: 'none' } }, message || '');
  const go = h('button', { class: 'btn primary', type: 'submit', style: { width: '100%' } }, 'Entrar na vila');
  const form = h('form', { onsubmit: (e) => { e.preventDefault(); busy(go, async () => {
    try { const r = await post('/api/login', { passcode: pass.value }); setCsrf(r.csrf); await start(); } catch (x) { err.textContent = x instanceof ApiError ? x.message : 'Falhou.'; err.style.display = ''; pass.select(); }
  }); } },
  h('div', { class: 'row', style: { marginBottom: '16px' } }, h('span', { html: LOGO, style: { width: '44px', height: '44px', display: 'inline-block' } }), h('div', {}, h('h1', { style: { letterSpacing: '.16em' } }, 'AI VILLAGE'), h('div', { class: 'muted' }, '未来村 · a tua empresa de agentes'))),
  h('div', { class: 'field' }, h('label', { for: 'pc' }, 'Passcode'), Object.assign(pass, { id: 'pc' })), err, go,
  h('p', { class: 'hint faint', style: { marginTop: '12px' } }, 'O passcode foi mostrado na consola do servidor no primeiro arranque, ou define-o com VILLAGE_PASSCODE.'));
  const scene = h('div', { class: 'scene', 'aria-hidden': 'true', html: renderVillage({ units: [], agents: [], world: 'personal' }) });
  scene.firstChild.style.cssText = 'width:100%;height:100%;min-width:0;object-fit:cover';
  scene.firstChild.setAttribute('preserveAspectRatio', 'xMidYMid slice');
  root.append(h('div', { class: 'login' }, scene, h('div', { class: 'card' }, form)));
  pass.focus();
}

async function shell() {
  clear(root);
  const worldSwitch = h('div', { class: 'world-switch', role: 'group', 'aria-label': 'Mundo' });
  const workerChip = h('span', { class: 'chip', title: 'Estado do worker (processo que executa as tarefas)' });
  const nav = h('nav', { class: 'nav', 'aria-label': 'Principal' });
  const main = h('main', { id: 'main', tabindex: -1 });
  const paintWorlds = () => worldSwitch.replaceChildren(...S.worlds.map((w) => h('button', { 'aria-pressed': String(S.world === w.id), title: w.policy.label, onclick: async () => { if (S.world === w.id) return; setWorld(w.id); await loadWorld(); paintWorlds(); mount(); } }, w.kind === 'personal' ? 'Pessoal' : 'Profissional')));
  const paintNav = () => nav.replaceChildren(...NAV.map(([id, label, k]) => h('button', { 'aria-current': route.page === id ? 'page' : null, onclick: () => { location.hash = `#/${id}`; } }, h('span', { class: 'k', 'aria-hidden': 'true' }, k), label)));
  const paintChip = () => {
    const w = S.overview?.worker;
    if (!w) return;
    workerChip.textContent = !w.execution_enabled ? 'execução desativada (desenho)' : w.jobs_suspended ? 'jobs suspensos' : w.online ? `worker online${w.queued ? ` · ${w.queued} na fila` : ''}` : 'worker offline';
    workerChip.className = `chip ${w.online && w.execution_enabled && !w.jobs_suspended ? 'on' : ''}`;
  };
  const logout = h('button', { class: 'btn sm', onclick: async () => { try { await post('/api/logout'); } catch { /* sessão já terminada */ } stop(); loginScreen(); } }, 'Sair');
  const top = h('header', { class: 'topbar' },
    h('a', { class: 'brand', href: '#/vila', 'aria-label': 'AI Village — Vila' }, h('span', { html: LOGO, style: { display: 'inline-flex' } }), h('div', {}, h('b', {}, 'AI VILLAGE'), h('small', {}, '未来村'))),
    nav, h('span', { class: 'spacer' }), workerChip, worldSwitch, logout);
  root.append(h('div', { class: 'app' }, top, main));
  window.__main = main;
  subscribe(paintChip);
  paintWorlds(); paintNav(); paintChip();
  window.__repaintNav = paintNav;
}

async function mount() {
  parseRoute();
  window.__repaintNav?.();
  const main = window.__main; if (!main) return;
  view?.destroy?.(); view = null; clear(main);
  try {
    if (route.page === 'vila') view = homeView(main);
    else if (route.page === 'trabalho') view = workView(main, route.sub || 'hoje');
    else if (route.page === 'ligacoes') view = await connectionsView(main);
    else view = settingsView(main, route.sub || 'org');
  } catch (e) { main.append(h('div', { class: 'note bad' }, `Erro ao abrir a vista: ${e.message}`)); console.error(e); }
  document.title = `${{ vila: 'Vila', trabalho: 'Trabalho', ligacoes: 'Ligações', config: 'Configuração' }[route.page]} · AI Village`;
}

function stop() { clearInterval(tickTimer); tickTimer = null; }
async function tick() {
  if (document.hidden) return;
  try { await loadWorld(); await view?.tick?.(); } catch (e) { if (!(e instanceof ApiError && e.status === 401)) console.warn('tick', e.message); }
}

async function start() {
  await loadWorlds();
  if (!S.worlds.some((w) => w.id === S.world)) setWorld(S.worlds[0].id);
  await loadWorld();
  await shell();
  await mount();
  stop(); tickTimer = setInterval(tick, 2500);
}

window.addEventListener('hashchange', () => { if (window.__main) mount(); });
window.addEventListener('village:unauth', () => { stop(); loginScreen('A sessão terminou. Entra de novo.'); });
document.addEventListener('visibilitychange', () => { if (!document.hidden && tickTimer) tick(); });

(async () => {
  try {
    const s = await get('/api/session');
    if (s.authenticated) { setCsrf(s.csrf); await start(); } else loginScreen();
  } catch (e) { loginScreen(`Não foi possível contactar o servidor: ${e.message}`); }
})();
void W; void toast;
