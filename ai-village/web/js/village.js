// Mapa da vila: cena SVG ao anoitecer (Japão futurista). Cada unidade é um edifício; cada agente está à porta
// do seu edifício; o ORQUESTRADOR fica junto ao torii central. Todo o estado (ocupado/bloqueado…) vem do backend.
// Interação por data-attributes + teclado (role=button, tabindex=0). Animação opcional (reduced-motion desliga).
import { esc } from './ui.js';
import { portraitMarkup, defaultLook } from './avatar.js';

const W = 1600;
function rng(seed) { let a = seed >>> 0; return () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }

const STATUS_COLOR = { disponivel: '#34d399', ocupado: '#22d3ee', bloqueado: '#fbbf24', inativo: '#7480b3', arquivado: '#7480b3' };
const STATUS_GLYPH = { disponivel: '●', ocupado: '⚙', bloqueado: '!', inativo: '⏸', arquivado: '▫' };
const STATUS_PT = { disponivel: 'disponível', ocupado: 'ocupado', bloqueado: 'bloqueado', inativo: 'inativo', arquivado: 'arquivado' };

// slots [x, baselineY, scale] — fila de trás (rio ao fundo) e fila da frente
const SLOTS = [[800, 575, 1.12], [390, 560, 1.0], [1210, 560, 1.0], [190, 850, .95], [600, 850, .95], [1000, 850, .95], [1410, 850, .95]];

function pagodaRoof(hw, h, trim = '#ff5a4d', fill = 'url(#roofG)') {
  return `<path d="M${-hw - 16} -10 C${-hw + 8} 10 ${-hw * 0.45} 8 ${-hw * 0.18} ${-h * 0.62} L-10 ${-h} L10 ${-h} L${hw * 0.18} ${-h * 0.62} C${hw * 0.45} 8 ${hw - 8} 10 ${hw + 16} -10 C${hw - 18} 18 ${-hw + 18} 18 ${-hw - 16} -10Z" fill="${fill}" stroke="rgba(160,190,255,.35)" stroke-width="1"/>
  <path d="M${-hw - 16} -10 C${-hw + 18} 18 ${hw - 18} 18 ${hw + 16} -10" fill="none" stroke="${trim}" stroke-width="3" opacity=".9"/>
  <path d="M${-hw * 0.2} ${-h * 0.62} L-10 ${-h} L10 ${-h} L${hw * 0.2} ${-h * 0.62}" fill="none" stroke="rgba(190,215,255,.45)" stroke-width="1.2"/>`;
}
const windows = (x0, y0, cols, rows, dx, dy, w, h, lit = .7, color = '#ffd88a', seed = 3) => {
  const r = rng(seed); let out = '';
  for (let i = 0; i < cols; i++) for (let j = 0; j < rows; j++) {
    const on = r() < lit;
    out += `<rect x="${x0 + i * dx}" y="${y0 + j * dy}" width="${w}" height="${h}" rx="1.5" fill="${on ? color : '#1a2250'}" opacity="${on ? .92 : .8}"${on && r() < .15 ? ' class="anim-flicker"' : ''}/>`;
  }
  return out;
};
const kanjiSign = (txt, x, y, color = '#22d3ee') => `<g transform="translate(${x},${y})"><rect x="-17" y="-44" width="34" height="88" rx="4" fill="#070b20" stroke="${color}" stroke-width="1.6" filter="url(#glow)"/>
  ${[...txt].slice(0, 3).map((c, i, a) => `<text x="0" y="${-22 + i * (a.length > 2 ? 24 : 32) + 12}" text-anchor="middle" font-size="${a.length > 2 ? 22 : 26}" font-weight="700" fill="${color}" filter="url(#glow)">${esc(c)}</text>`).join('')}</g>`;

const base = (w = 165) => `<ellipse cx="0" cy="8" rx="${w + 24}" ry="12" fill="#000" opacity=".5"/>
  <path d="M${-w} 0 L${w} 0 L${w - 16} -14 L${-w + 16} -14Z" fill="url(#stoneG)" stroke="rgba(180,200,255,.25)"/>
  <path d="M${-w + 16} -14 L${w - 16} -14" stroke="rgba(34,211,238,.55)" stroke-width="2" filter="url(#glow)"/>`;

const BUILD = {
  tower(kanji) {
    let s = base(170);
    const hw = [115, 95, 75, 55];
    for (let i = 0; i < 4; i++) {
      const yb = -14 - i * 92, bh = hw[i];
      s += `<rect x="${-bh}" y="${yb - 62}" width="${bh * 2}" height="62" fill="url(#glassG)" stroke="rgba(150,200,255,.35)"/>
      ${Array.from({ length: Math.round(bh / 19) * 2 + 1 }, (_, k) => `<rect x="${-bh + k * 19 - 1}" y="${yb - 62}" width="3" height="62" fill="url(#woodG)"/>`).join('')}
      ${windows(-bh + 8, yb - 50, Math.floor(bh / 12), 2, 24, 22, 14, 12, .75, '#ffd88a', 11 + i)}
      <g transform="translate(0,${yb - 62})">${pagodaRoof(bh + 26, 30)}</g>`;
    }
    s += `<rect x="-2" y="${-14 - 4 * 92 - 4}" width="4" height="46" fill="#9aa8d8"/><circle cx="0" cy="${-14 - 4 * 92 - 12}" r="10" fill="#22d3ee" filter="url(#glow)" class="anim-pulse"/><circle cx="0" cy="${-14 - 4 * 92 - 12}" r="4" fill="#e6fcff"/>`;
    s += kanjiSign(kanji || '本社', 0, -48);
    return s;
  },
  lab(kanji) {
    let s = base(175);
    s += `<rect x="-150" y="-104" width="300" height="90" fill="url(#glassG)" stroke="rgba(150,200,255,.4)"/>
      ${Array.from({ length: 11 }, (_, k) => `<rect x="${-150 + k * 30 - 1}" y="-104" width="3" height="90" fill="url(#woodG)" opacity=".85"/>`).join('')}
      <rect x="-150" y="-110" width="300" height="8" fill="#0a1030" stroke="#22d3ee" stroke-width="1.4" filter="url(#glow)"/>
      ${windows(-136, -92, 9, 3, 30, 26, 16, 14, .65, '#8ff3ff', 21)}
      <path d="M-110 -104 A110 58 0 0 1 110 -104Z" fill="url(#domeG)" stroke="rgba(160,240,255,.6)" stroke-width="1.4"/>
      ${[-70, -35, 0, 35, 70].map((x) => `<path d="M${x} -104 Q${x * 0.75} -146 0 -161" stroke="rgba(160,240,255,.35)" fill="none"/>`).join('')}
      <ellipse cx="0" cy="-176" rx="86" ry="14" fill="none" stroke="#a78bfa" stroke-width="1.6" opacity=".8" filter="url(#glow)"/>
      ${[0, 1, 2, 3, 4].map((i) => `<rect class="anim-holo" style="animation-delay:${i * .35}s" x="${-50 + i * 22}" y="${-228 + (4 - i) * 6}" width="14" height="${40 - (4 - i) * 6}" rx="2" fill="${['#22d3ee', '#a78bfa', '#f472b6', '#34d399', '#f4c24a'][i]}" opacity=".9" filter="url(#glow)"/>`).join('')}
      <path d="M-62 -186 L62 -186" stroke="rgba(160,240,255,.5)"/>`;
    s += kanjiSign(kanji || '分析', 0, -52, '#8ff3ff');
    return s;
  },
  workshop(kanji) {
    let s = base(160);
    s += `<rect x="-130" y="-92" width="260" height="78" fill="#161d44" stroke="rgba(150,180,255,.35)"/>
      ${Array.from({ length: 6 }, (_, k) => `<rect x="${-120 + k * 42}" y="-84" width="34" height="62" rx="3" fill="#0b1030" stroke="rgba(120,160,255,.4)"/>
         ${Array.from({ length: 5 }, (_, j) => `<rect x="${-115 + k * 42}" y="${-78 + j * 11}" width="24" height="5" rx="1" fill="${(k + j) % 3 ? '#34d399' : '#22d3ee'}" opacity=".85" class="${(k * j) % 4 === 0 ? 'anim-flicker' : ''}"/>`).join('')}`).join('')}
      <rect x="-110" y="-160" width="220" height="68" fill="url(#woodG)" stroke="rgba(0,0,0,.3)"/>
      ${Array.from({ length: 18 }, (_, k) => `<rect x="${-108 + k * 12}" y="-158" width="4" height="64" fill="rgba(0,0,0,.28)"/>`).join('')}
      ${windows(-90, -146, 4, 1, 48, 0, 30, 34, .8, '#ffd88a', 5)}
      <g transform="translate(0,-160)">${pagodaRoof(140, 38, '#22d3ee')}</g>
      <rect x="112" y="-232" width="3" height="76" fill="#9aa8d8"/><path d="M96 -228 Q113 -250 130 -228 Q113 -236 96 -228Z" fill="#cfd8ff" stroke="#8c99d6"/>
      <circle cx="113.5" cy="-236" r="3.4" fill="#ff5a4d" filter="url(#glow)" class="anim-pulse"/>`;
    s += kanjiSign(kanji || '技術', -88, -48, '#f472b6');
    return s;
  },
  dock(kanji) {
    let s = base(165);
    s += `<rect x="-140" y="-92" width="250" height="78" fill="#1a2250" stroke="rgba(150,180,255,.3)"/>
      ${Array.from({ length: 22 }, (_, k) => `<rect x="${-138 + k * 11.4}" y="-92" width="3" height="78" fill="rgba(0,0,0,.25)"/>`).join('')}
      <path d="M-150 -90 L-120 -112 L120 -112 L150 -90Z" fill="url(#roofG)" stroke="rgba(160,190,255,.35)"/>
      <rect x="-50" y="-70" width="100" height="56" fill="#ffd88a" opacity=".9" class="anim-flicker"/><rect x="-50" y="-70" width="100" height="22" fill="#0b1030"/>
      ${Array.from({ length: 4 }, (_, k) => `<rect x="${-50 + k * 25}" y="-70" width="2" height="56" fill="rgba(0,0,0,.35)"/>`).join('')}
      <rect x="128" y="-72" width="52" height="30" fill="#fb923c" stroke="#7a3410"/><rect x="128" y="-42" width="52" height="28" fill="#60a5fa" stroke="#1f4a85"/><rect x="146" y="-100" width="52" height="28" fill="#34d399" stroke="#17664a"/>
      <rect x="-186" y="-230" width="6" height="216" fill="#ffb347"/><path d="M-186 -230 L-40 -230 L-40 -222 L-186 -222Z" fill="#ffb347"/>
      <path d="M-70 -222 L-70 -150" stroke="#cfd8ff" stroke-width="1.6"/><rect x="-96" y="-150" width="52" height="28" fill="#f472b6" stroke="#8a2a5e"/>
      <g transform="translate(-62,-160)"><rect x="-26" y="-14" width="52" height="30" fill="none"/></g>`;
    s += kanjiSign(kanji || '実行', 0, -50, '#ffb347');
    return s;
  },
  dojo(kanji) {
    let s = base(160);
    s += `<rect x="-120" y="-92" width="240" height="78" fill="#2a1a12"/>
      ${Array.from({ length: 6 }, (_, k) => `<rect x="${-112 + k * 44}" y="-90" width="10" height="76" fill="url(#woodG)"/>`).join('')}
      ${Array.from({ length: 5 }, (_, k) => `<g><rect x="${-100 + k * 44}" y="-86" width="34" height="68" fill="#ffe2a8" opacity=".92" class="anim-flicker"/>
        ${[1, 2, 3].map((j) => `<path d="M${-100 + k * 44} ${-86 + j * 17} h34" stroke="rgba(110,70,30,.55)"/>`).join('')}${[1, 2].map((j) => `<path d="M${-100 + k * 44 + j * 11.3} -86 v68" stroke="rgba(110,70,30,.55)"/>`).join('')}</g>`).join('')}
      <g transform="translate(0,-92)">${pagodaRoof(148, 40, '#f4c24a', 'url(#roofG)')}</g>
      <g transform="translate(0,-132)">${pagodaRoof(96, 46, '#f4c24a', 'url(#roofG)')}</g>
      <circle cx="-138" cy="-112" r="5" fill="#f4c24a"/><circle cx="138" cy="-112" r="5" fill="#f4c24a"/>
      <g transform="translate(-158,0)"><rect x="-6" y="-44" width="12" height="30" fill="#8e99c4"/><rect x="-14" y="-58" width="28" height="14" rx="2" fill="#a5b0d8"/><rect x="-8" y="-52" width="16" height="7" fill="#ffd88a" class="anim-flicker"/><path d="M-18 -58 L0 -72 L18 -58Z" fill="#8e99c4"/></g>`;
    s += kanjiSign(kanji || '学', 0, -176, '#f4c24a');
    return s;
  },
  garden(kanji) {
    let s = base(165);
    s += `<rect x="-90" y="-80" width="150" height="66" fill="#3a2418"/>
      <rect x="-82" y="-74" width="134" height="54" fill="#ffe2a8" opacity=".92" class="anim-flicker"/>
      ${[0, 1, 2, 3].map((k) => `<rect x="${-82 + k * 33.5}" y="-74" width="2.5" height="54" fill="rgba(110,70,30,.6)"/>`).join('')}
      <circle cx="-15" cy="-47" r="19" fill="#0b1030" stroke="#f4c24a" stroke-width="2"/><circle cx="-15" cy="-47" r="15" fill="#ffd88a" opacity=".85"/>
      <g transform="translate(-15,-80)">${pagodaRoof(110, 38, '#f9a8d4', 'url(#roofG)')}</g>
      <g transform="translate(128,0)"><rect x="-9" y="-92" width="18" height="92" rx="6" fill="#4a2f1f"/>
        ${[[-34, -122, 36], [10, -138, 40], [-4, -170, 34], [34, -118, 30], [-52, -92, 28], [50, -92, 26]].map(([x, y, r], i) => `<circle cx="${x}" cy="${y}" r="${r}" fill="${['#f9a8d4', '#f7b8dc', '#f58cc0'][i % 3]}" opacity=".9"/>`).join('')}</g>
      <ellipse cx="-92" cy="-4" rx="52" ry="10" fill="#14395a" stroke="rgba(160,230,255,.4)"/><ellipse cx="-80" cy="-6" rx="9" ry="3" fill="#ff8a4d"/><ellipse cx="-100" cy="-3" rx="8" ry="2.6" fill="#f4f1e8"/>`;
    s += kanjiSign(kanji || '暮', 66, -56, '#f9a8d4');
    return s;
  },
  vault(kanji) {
    let s = base(150);
    s += `<rect x="-110" y="-110" width="220" height="96" fill="#e9ecf8"/>
      ${Array.from({ length: 9 }, (_, i) => Array.from({ length: 4 }, (_, j) => `<path d="M${-110 + i * 24.5} ${-110 + j * 24} l12 12 l12 -12 M${-110 + i * 24.5} ${-86 + j * 24} l12 -12" stroke="#1d2140" stroke-width="1.6" fill="none" opacity=".75"/>`).join('')).join('')}
      <rect x="-110" y="-110" width="220" height="96" fill="url(#shadeG)"/>
      <rect x="-30" y="-84" width="60" height="70" rx="4" fill="#1b2350" stroke="#94a3b8" stroke-width="3"/>
      <circle cx="0" cy="-52" r="17" fill="#070b20" stroke="#22d3ee" stroke-width="2.4" filter="url(#glow)"/><circle cx="0" cy="-52" r="6" fill="#22d3ee" class="anim-pulse"/>
      <path d="M-17 -52 h-9 M17 -52 h9" stroke="#94a3b8" stroke-width="3"/>
      <rect x="-96" y="-90" width="36" height="22" rx="3" fill="#0b1030" stroke="#94a3b8"/><rect x="60" y="-90" width="36" height="22" rx="3" fill="#0b1030" stroke="#94a3b8"/>
      ${[-84, -72, -60].map((x) => `<path d="M${x} -90 v22" stroke="#94a3b8"/>`).join('')}${[72, 84, 96].map((x) => `<path d="M${x - 12} -90 v22" stroke="#94a3b8"/>`).join('')}
      <g transform="translate(0,-110)">${pagodaRoof(138, 56, '#94a3b8', 'url(#roofDarkG)')}</g>`;
    s += kanjiSign(kanji || '監査', 82, -150, '#94a3b8');
    return s;
  },
  hall(kanji) {
    let s = base(150);
    s += `<rect x="-110" y="-92" width="220" height="78" fill="url(#glassG)" stroke="rgba(150,200,255,.35)"/>
      ${windows(-98, -80, 8, 2, 26, 30, 18, 22, .7, '#ffd88a', 9)}
      <g transform="translate(0,-92)">${pagodaRoof(130, 44)}</g>`;
    s += kanjiSign(kanji || '村', 0, -50);
    return s;
  },
};

function defs() {
  return `<defs>
  <linearGradient id="skyG" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#070a22"/><stop offset=".35" stop-color="#1b1148"/><stop offset=".62" stop-color="#6b2263"/><stop offset=".82" stop-color="#e0605f"/><stop offset="1" stop-color="#ffb06b"/></linearGradient>
  <radialGradient id="moonG"><stop offset="0" stop-color="#fffdf2"/><stop offset=".7" stop-color="#f3ecd2"/><stop offset="1" stop-color="#d9d0b0"/></radialGradient>
  <radialGradient id="moonGlow"><stop offset="0" stop-color="#fff2cf" stop-opacity=".55"/><stop offset="1" stop-color="#fff2cf" stop-opacity="0"/></radialGradient>
  <linearGradient id="fujiG" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3a2f78"/><stop offset="1" stop-color="#241a56"/></linearGradient>
  <linearGradient id="ridgeG" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2a1d63"/><stop offset="1" stop-color="#150f3b"/></linearGradient>
  <linearGradient id="riverG" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#e0605f" stop-opacity=".85"/><stop offset=".4" stop-color="#6b2263"/><stop offset="1" stop-color="#0d1236"/></linearGradient>
  <linearGradient id="groundG" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1a2150"/><stop offset=".5" stop-color="#10163a"/><stop offset="1" stop-color="#0a0e26"/></linearGradient>
  <linearGradient id="glassG" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#2c4a8f" stop-opacity=".9"/><stop offset=".5" stop-color="#14224f"/><stop offset="1" stop-color="#3a2a78" stop-opacity=".9"/></linearGradient>
  <linearGradient id="domeG" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#8ff3ff" stop-opacity=".75"/><stop offset=".6" stop-color="#2a6fb0" stop-opacity=".55"/><stop offset="1" stop-color="#a78bfa" stop-opacity=".6"/></linearGradient>
  <linearGradient id="woodG" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#7a4a2a"/><stop offset=".5" stop-color="#9a6238"/><stop offset="1" stop-color="#5a3420"/></linearGradient>
  <linearGradient id="roofG" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3d4a9e"/><stop offset=".5" stop-color="#232c70"/><stop offset="1" stop-color="#121744"/></linearGradient>
  <linearGradient id="roofDarkG" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3b3f57"/><stop offset="1" stop-color="#171a2b"/></linearGradient>
  <linearGradient id="stoneG" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#5b6498"/><stop offset="1" stop-color="#2a3160"/></linearGradient>
  <linearGradient id="shadeG" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#1b2350" stop-opacity="0"/><stop offset="1" stop-color="#1b2350" stop-opacity=".45"/></linearGradient>
  <filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  <filter id="soft" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="14"/></filter>
</defs>`;
}

function backdrop(H) {
  const r = rng(7);
  const stars = Array.from({ length: 90 }, () => `<circle cx="${(r() * W).toFixed(0)}" cy="${(r() * 260).toFixed(0)}" r="${(r() * 1.3 + .3).toFixed(1)}" fill="#fff" opacity="${(r() * .7 + .2).toFixed(2)}"${r() < .2 ? ' class="anim-flicker"' : ''}/>`).join('');
  const towers = Array.from({ length: 34 }, (_, i) => {
    const x = i * 49 + (r() * 20 - 10), h = 40 + r() * 120, w = 26 + r() * 22;
    const neon = ['#22d3ee', '#f472b6', '#a78bfa'][i % 3];
    return `<g opacity="${.5 + (i % 3) * .1}"><rect x="${x}" y="${430 - h}" width="${w}" height="${h}" fill="#150f3b"/>
      ${Array.from({ length: Math.floor(h / 14) }, (_, k) => (r() < .45 ? `<rect x="${x + 4 + (k % 2) * 8}" y="${430 - h + 6 + k * 14}" width="5" height="4" fill="${r() < .3 ? neon : '#ffd88a'}" opacity=".85"/>` : '')).join('')}
      <rect x="${x + w / 2 - 1}" y="${430 - h - 14}" width="2" height="14" fill="${neon}" opacity=".9"/></g>`;
  }).join('');
  const petals = Array.from({ length: 16 }, (_, i) => `<ellipse class="anim-petal" style="animation-delay:${-(i * 0.9).toFixed(1)}s;animation-duration:${10 + (i % 5) * 2}s" cx="${(r() * 1500 + 150).toFixed(0)}" cy="0" rx="5" ry="3" fill="#f9a8d4" opacity=".85"/>`).join('');
  return { stars, towers, petals };
}

function torii(x, y, s = 1) {
  return `<g transform="translate(${x},${y}) scale(${s})" filter="url(#glow)">
    <rect x="-62" y="-118" width="12" height="118" fill="#ff5a4d"/><rect x="50" y="-118" width="12" height="118" fill="#ff5a4d"/>
    <path d="M-92 -128 Q0 -104 92 -128 L88 -144 Q0 -122 -88 -144Z" fill="#161a3a" stroke="#ff5a4d" stroke-width="3"/>
    <rect x="-70" y="-100" width="140" height="10" fill="#ff5a4d"/><rect x="-6" y="-120" width="12" height="22" fill="#ff5a4d"/></g>`;
}

function lantern(x, y) {
  return `<g transform="translate(${x},${y})"><rect x="-5" y="-24" width="10" height="24" fill="#6a76a8"/><rect x="-11" y="-42" width="22" height="18" rx="2" fill="#7b86b8"/><rect x="-7" y="-38" width="14" height="10" fill="#ffd88a" class="anim-flicker" filter="url(#glow)"/><path d="M-15 -42 L0 -54 L15 -42Z" fill="#6a76a8"/></g>`;
}

function agentToken(a, x, y, R, opts = {}) {
  const st = a.activity_status || 'disponivel';
  const col = STATUS_COLOR[st] || '#7480b3';
  const clipId = `ck${a.id}`;
  const img = a.appearance?.type === 'image' && /^[a-f0-9]{32}\.(png|jpg|webp)$/.test(a.appearance.file || '')
    ? `<image href="/api/w/${opts.world}/portraits/${a.appearance.file}" x="${-R}" y="${-R}" width="${2 * R}" height="${2 * R}" preserveAspectRatio="xMidYMid slice"/>`
    : `<svg x="${-R}" y="${-R}" width="${2 * R}" height="${2 * R}" viewBox="0 0 100 100">${portraitMarkup(a.appearance || defaultLook(a.id.length), a.id)}</svg>`;
  const label = `${a.display_name}, ${a.title || 'agente'}, ${STATUS_PT[st] || st}${a.orchestrator_flag ? ', orquestrador' : ''}`;
  const dim = st === 'inativo' || st === 'arquivado';
  return `<g class="agent" data-agent="${esc(a.id)}" role="button" tabindex="0" aria-label="${esc(label)}" transform="translate(${x},${y})"${dim ? ' opacity=".6"' : ''}>
    <ellipse cx="0" cy="${R + 4}" rx="${R * .8}" ry="${R * .22}" fill="#000" opacity=".45"/>
    <circle class="focus-ring" r="${R + 9}" fill="none" stroke="#22d3ee" stroke-width="2" stroke-dasharray="5 4"/>
    <circle r="${R + 3}" fill="${a.orchestrator_flag ? '#f4c24a' : 'none'}" fill-opacity=".25" stroke="${a.orchestrator_flag ? '#f4c24a' : col}" stroke-width="${a.orchestrator_flag ? 3.5 : 3}"${st === 'ocupado' ? ' class="anim-pulse"' : ''}/>
    <clipPath id="${clipId}"><circle r="${R}"/></clipPath><g clip-path="url(#${clipId})">${img}</g>
    <g transform="translate(${R * .72},${R * .72})"><circle r="9" fill="#070b20" stroke="${col}" stroke-width="2"/><text y="4" text-anchor="middle" font-size="11" font-weight="700" fill="${col}">${STATUS_GLYPH[st] || '●'}</text></g>
    ${a.orchestrator_flag ? `<g transform="translate(0,${-R - 12})"><path d="M-9 4 L-12 -6 L-5 -1 L0 -9 L5 -1 L12 -6 L9 4Z" fill="#f4c24a" stroke="#7a5a10"/></g>` : ''}
    <g class="tag"><text y="${R + 20}" text-anchor="middle" font-size="${opts.big ? 15 : 13}" font-weight="700" fill="#eef1ff">${esc(a.display_name)}</text>
    <text y="${R + 34}" text-anchor="middle" font-size="10.5" fill="#b9c3ee">${esc((a.title || '').replace(/\s*\(\d+\)\s*$/, '').slice(0, 21))}</text></g></g>`;
}

export function renderVillage({ units, agents, world }) {
  const active = units.filter((u) => u.lifecycle_status === 'active').sort((a, b) => a.plot - b.plot);
  const extra = Math.max(0, active.length - SLOTS.length);
  const rows = Math.ceil(extra / 4);
  const H = active.length <= 3 ? 860 : 1120 + rows * 400;
  const { stars, towers, petals } = backdrop(H);

  const slots = [...SLOTS];
  for (let i = 0; i < extra; i++) slots.push([200 + (i % 4) * 400, 1330 + Math.floor(i / 4) * 400, .9]);

  let buildings = '';
  let tokens = ''; // agentes numa camada própria, sempre por cima dos edifícios e decorações
  const order = active.map((u, i) => ({ u, slot: slots[i] })).sort((a, b) => a.slot[1] - b.slot[1]);
  for (const { u, slot } of order) {
    const [sx, sy, sc] = slot;
    const members = agents.filter((a) => a.org_unit_id === u.id && a.lifecycle_status !== 'archived')
      .sort((a, b) => (b.orchestrator_flag - a.orchestrator_flag) || ((b.id === u.responsible_agent_id) - (a.id === u.responsible_agent_id)) || a.display_name.localeCompare(b.display_name));
    const fn = BUILD[u.theme] || BUILD.hall;
    const shown = members.slice(0, 6), more = members.length - shown.length;
    const gap = 90, startX = sx - (((shown.length + (more > 0 ? 1 : 0)) - 1) * gap) / 2;
    const ay = sy + 82 + (sc > 1 ? 6 : 0);
    const busy = members.filter((a) => a.activity_status === 'ocupado').length;
    buildings += `<g class="unit" data-unit="${esc(u.id)}" role="button" tabindex="0" aria-label="Unidade ${esc(u.name)}: ${members.length} agente(s)${busy ? `, ${busy} ocupado(s)` : ''}">
      <g transform="translate(${sx},${sy}) scale(${sc})">${fn(u.kanji)}
        <g transform="translate(0,34)"><rect x="-96" y="-10" width="192" height="24" rx="6" fill="rgba(5,8,22,.82)" stroke="rgba(139,156,255,.5)"/><text y="7" text-anchor="middle" font-size="13.5" font-weight="700" fill="#eef1ff">${esc(u.name.slice(0, 26))}</text></g>
      </g>
      <rect class="focus-ring" x="${sx - 180 * sc}" y="${sy - 250 * sc}" width="${360 * sc}" height="${300 * sc}" fill="none" stroke="#22d3ee" stroke-width="2" stroke-dasharray="8 6" rx="12"/>
    </g>`;
    shown.forEach((a, i) => { tokens += agentToken(a, startX + i * gap, ay + 24 + (i % 2) * 40, 25, { world }); });
    if (more > 0) tokens += `<g class="unit" data-unit="${esc(u.id)}" role="button" tabindex="0" aria-label="Mais ${more} agentes na unidade ${esc(u.name)}" transform="translate(${startX + shown.length * gap},${ay + 24 + (shown.length % 2) * 40})"><circle r="25" fill="#10163a" stroke="rgba(139,156,255,.6)" stroke-width="2"/><text y="6" text-anchor="middle" font-size="16" font-weight="700" fill="#eef1ff">+${more}</text></g>`;
  }

  const hubX = 800, hubY = 650;
  const lanterns = [[250, 650], [560, 700], [1040, 700], [1350, 650], [395, 905], [800, 960], [1205, 905]].filter(([, y]) => y < H - 60).map(([x, y]) => lantern(x, y)).join('');

  const grid = Array.from({ length: 9 }, (_, i) => `<path d="M${800 + (i - 4) * 40} 500 L${800 + (i - 4) * 260} ${H}" stroke="rgba(139,156,255,.1)"/>`).join('')
    + Array.from({ length: 10 }, (_, i) => `<path d="M0 ${510 + i * i * 6 + i * 20} H${W}" stroke="rgba(139,156,255,.09)"/>`).join('');
  const paths = active.map((_, i) => { const [x, y] = slots[i]; return `<path d="M${hubX} ${hubY} Q${(hubX + x) / 2} ${y - 30} ${x} ${y + 60}" fill="none" stroke="#22d3ee" stroke-opacity=".28" stroke-width="2.4" stroke-dasharray="3 9" stroke-linecap="round"/>`; }).join('');

  return `<svg class="village-svg" viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" role="group" aria-label="Mapa da vila: unidades e agentes. Todas as ações do mapa existem também na lista.">
  ${defs()}
  <rect width="${W}" height="${H}" fill="url(#skyG)"/>
  <rect y="430" width="${W}" height="${H - 430}" fill="url(#groundG)"/>
  ${stars}
  <circle cx="1240" cy="150" r="190" fill="url(#moonGlow)"/><circle cx="1240" cy="150" r="64" fill="url(#moonG)"/><circle cx="1220" cy="140" r="9" fill="#cfc7a6" opacity=".6"/><circle cx="1262" cy="168" r="12" fill="#cfc7a6" opacity=".5"/><circle cx="1250" cy="124" r="5" fill="#cfc7a6" opacity=".5"/>
  <path d="M0 430 L0 360 L150 300 L260 350 L380 290 L520 360 L620 330 L700 430Z" fill="url(#ridgeG)" opacity=".85"/>
  <path d="M520 430 L760 190 L800 175 L840 190 L1080 430Z" fill="url(#fujiG)"/><path d="M696 262 L736 226 L760 244 L780 214 L800 205 L820 214 L842 244 L866 226 L906 262 L880 256 L850 280 L820 252 L800 284 L780 252 L750 280 L720 256Z" fill="#e9eaff" opacity=".9"/>
  <path d="M1000 430 L1130 330 L1230 380 L1350 310 L1480 370 L1600 330 L1600 430Z" fill="url(#ridgeG)" opacity=".9"/>
  <ellipse cx="400" cy="210" rx="190" ry="22" fill="#6b2263" opacity=".35" filter="url(#soft)"/><ellipse cx="1000" cy="260" rx="240" ry="24" fill="#a03a7a" opacity=".3" filter="url(#soft)"/>
  ${towers}
  <g class="anim-drift" style="animation-duration:52s" opacity=".9"><circle cx="0" cy="120" r="3" fill="#22d3ee" filter="url(#glow)"/><circle cx="26" cy="128" r="2" fill="#f472b6" filter="url(#glow)"/></g>
  <g class="anim-drift" style="animation-duration:75s;animation-delay:-30s" opacity=".8"><circle cx="0" cy="190" r="3" fill="#f4c24a" filter="url(#glow)"/></g>
  <rect y="430" width="${W}" height="78" fill="url(#riverG)"/>
  ${Array.from({ length: 14 }, (_, i) => `<path d="M${i * 120 + 20} ${450 + (i % 3) * 18} h${50 + (i % 4) * 14}" stroke="#fff" stroke-opacity=".18" stroke-width="2" stroke-linecap="round"/>`).join('')}
  <ellipse cx="1240" cy="470" rx="46" ry="6" fill="#fff2cf" opacity=".35"/>
  <path d="M690 478 Q800 400 910 478" fill="none" stroke="#ff5a4d" stroke-width="12" stroke-linecap="round"/><path d="M690 478 Q800 400 910 478" fill="none" stroke="#2b1030" stroke-width="5" stroke-linecap="round"/>
  ${[722, 760, 800, 840, 878].map((x, i) => `<rect x="${x - 2}" y="${446 - (i === 2 ? 4 : Math.abs(i - 2) * -9) - 18 + (i === 2 ? 0 : 0)}" width="4" height="22" fill="#ff5a4d"/>`).join('')}
  <g fill="#ff8a4d" opacity=".9"><ellipse cx="300" cy="480" rx="9" ry="3.4"/><ellipse cx="1050" cy="490" rx="8" ry="3"/><ellipse cx="520" cy="468" rx="7" ry="2.6" fill="#f4f1e8"/></g>
  <g>${grid}</g>
  ${paths}
  ${torii(800, H < 900 ? 790 : 905, 0.72)}
  ${buildings}
  ${lanterns}
  <g transform="translate(40,700)"><rect x="-10" y="-80" width="20" height="220" rx="9" fill="#3a2418"/>${[[-50, -110, 60], [30, -150, 70], [-10, -190, 60], [70, -100, 50], [-80, -70, 46]].map(([x, y, r], i) => `<circle cx="${x}" cy="${y}" r="${r}" fill="${['#f9a8d4', '#f58cc0', '#fbc4e0'][i % 3]}" opacity=".88"/>`).join('')}</g>
  <g transform="translate(1565,720)"><rect x="-10" y="-80" width="20" height="200" rx="9" fill="#3a2418"/>${[[-40, -110, 56], [20, -150, 64], [-6, -190, 54], [-70, -80, 44]].map(([x, y, r], i) => `<circle cx="${x}" cy="${y}" r="${r}" fill="${['#f9a8d4', '#f58cc0', '#fbc4e0'][i % 3]}" opacity=".88"/>`).join('')}</g>
  ${tokens}
  ${petals}
  </svg>`;
}

/** Liga cliques/teclado por delegação. */
export function bindVillage(root, { onAgent, onUnit }) {
  const pick = (t) => t.closest('[data-agent],[data-unit]');
  const act = (el) => { if (!el) return; if (el.dataset.agent) onAgent(el.dataset.agent); else if (el.dataset.unit) onUnit(el.dataset.unit); };
  root.addEventListener('click', (e) => act(pick(e.target)));
  root.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { const el = pick(e.target); if (el) { e.preventDefault(); act(el); } } });
}
