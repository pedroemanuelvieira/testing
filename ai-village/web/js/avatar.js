// Retratos PROCEDURAIS de aparência humana (provisórios, REQUISITOS §8: «retratos provisórios marcados»).
// Rosto, cabelo, olhos, roupa e luz de contorno são gerados por parâmetros; cada agente pode ainda ter
// uma fotografia/ilustração real carregada (appearance.type='image'). Não imita ninguém real.
import { esc } from './ui.js';

export const SKINS = [
  ['#fbe3d2', '#efc3a6', '#c98f72'], ['#f3d1b5', '#e2a985', '#b97b5a'], ['#e5b998', '#cb8f68', '#9c6342'],
  ['#c9926b', '#a8704a', '#7c4e30'], ['#9b6a47', '#7b4f31', '#573520'], ['#6e4630', '#523022', '#3a2217'],
];
export const HAIRS = ['#14121a', '#2a1b14', '#4a2f1f', '#7a5232', '#a07a4a', '#9aa0a6', '#c9c9d1', '#3b2f6b', '#1f4e79', '#7a1f3d'];
export const STYLES = ['short', 'sidepart', 'spiky', 'undercut', 'buzz', 'bob', 'long', 'bun'];
export const OUTFITS = ['suit', 'techwear', 'kimono', 'labcoat', 'hoodie', 'haori'];
export const ACCENTS = ['#22d3ee', '#a78bfa', '#34d399', '#f472b6', '#f4c24a', '#fb923c', '#60a5fa', '#f87171'];
export const EYES = ['#2a1b10', '#3a2a1c', '#1f2937', '#1f4e79', '#3b5d3a'];

export const defaultLook = (seed = 0) => ({
  type: 'procedural', gender: seed % 2 ? 'f' : 'm', skin: seed % 6, hair: HAIRS[seed % HAIRS.length], style: STYLES[seed % STYLES.length],
  eyes: EYES[seed % EYES.length], outfit: OUTFITS[seed % OUTFITS.length], accent: ACCENTS[seed % ACCENTS.length], glasses: false,
});

const shade = (hex, amt) => {
  const n = parseInt(hex.slice(1), 16);
  const f = (v) => Math.max(0, Math.min(255, Math.round(v + amt * 2.55)));
  return `#${[(n >> 16) & 255, (n >> 8) & 255, n & 255].map(f).map((v) => v.toString(16).padStart(2, '0')).join('')}`;
};

function hairBack(style, c, id) {
  const g = `url(#${id}hg)`;
  if (style === 'long') return `<path d="M26 44 C22 70 24 92 20 104 L80 104 C76 92 78 70 74 44 C74 20 26 20 26 44Z" fill="${g}"/>`;
  if (style === 'bob') return `<path d="M27 42 C24 62 28 70 32 72 L68 72 C72 70 76 62 73 42 C73 22 27 22 27 42Z" fill="${g}"/>`;
  if (style === 'bun') return `<circle cx="50" cy="14" r="9" fill="${g}"/><path d="M30 38 C30 20 70 20 70 38Z" fill="${g}"/>`;
  return '';
}
function hairFront(style, c, id) {
  const g = `url(#${id}hg)`;
  switch (style) {
    case 'short': return `<path d="M30 42 C28 18 72 16 70 42 C68 33 60 27 50 27 C40 27 32 33 30 42Z" fill="${g}"/>`;
    case 'sidepart': return `<path d="M30 43 C27 17 73 14 70 43 C69 34 64 28 56 26 C48 31 38 31 33 36 C31 38 30 40 30 43Z" fill="${g}"/><path d="M56 26 C60 24 66 26 69 33" stroke="${shade(c, 30)}" stroke-width=".8" fill="none" opacity=".6"/>`;
    case 'spiky': return `<path d="M30 42 L27 24 L35 30 L38 15 L45 26 L51 12 L57 26 L64 15 L65 30 L73 24 L70 42 C68 34 60 29 50 29 C40 29 32 34 30 42Z" fill="${g}"/>`;
    case 'undercut': return `<path d="M31 40 C30 18 70 16 69 40 C66 31 60 24 50 24 C40 24 34 31 31 40Z" fill="${g}"/><path d="M30 44 C30 36 31 34 32 33 L32 46Z M70 44 C70 36 69 34 68 33 L68 46Z" fill="${c}" opacity=".5"/>`;
    case 'buzz': return `<path d="M30 40 C30 22 70 22 70 40 C66 32 58 29 50 29 C42 29 34 32 30 40Z" fill="${c}" opacity=".7"/>`;
    case 'bob': return `<path d="M28 44 C26 18 74 16 72 44 C70 34 62 27 50 27 C38 27 30 34 28 44Z" fill="${g}"/><path d="M28 44 C27 56 30 62 33 64 L35 50Z M72 44 C73 56 70 62 67 64 L65 50Z" fill="${g}"/>`;
    case 'long': return `<path d="M28 46 C25 16 75 14 72 46 C70 34 62 26 50 26 C38 26 30 34 28 46Z" fill="${g}"/><path d="M28 46 C26 62 28 74 24 90 L34 88 L35 52Z M72 46 C74 62 72 74 76 90 L66 88 L65 52Z" fill="${g}"/>`;
    case 'bun': return `<path d="M30 42 C29 22 71 22 70 42 C68 33 60 28 50 28 C40 28 32 33 30 42Z" fill="${g}"/>`;
    default: return '';
  }
}

function outfit(kind, accent, id) {
  const body = 'M6 104 C6 82 26 74 50 74 C74 74 94 82 94 104Z';
  const g = (c1, c2) => `<linearGradient id="${id}og" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${c1}"/><stop offset="1" stop-color="${c2}"/></linearGradient>`;
  switch (kind) {
    case 'suit': return `<defs>${g('#2b3359', '#141a36')}</defs><path d="${body}" fill="url(#${id}og)"/><path d="M38 75 L50 96 L62 75 L56 74 L50 84 L44 74Z" fill="#f2f4ff"/><path d="M38 75 L30 78 L46 104 L50 96Z M62 75 L70 78 L54 104 L50 96Z" fill="#0f1430"/><path d="M50 84 L47 104 L53 104Z" fill="${accent}" opacity=".9"/>`;
    case 'techwear': return `<defs>${g('#1d2447', '#0b1028')}</defs><path d="${body}" fill="url(#${id}og)"/><path d="M36 74 L38 66 L62 66 L64 74 C58 78 42 78 36 74Z" fill="#161d3f" stroke="${accent}" stroke-width="1"/><path d="M14 96 L34 80 M86 96 L66 80" stroke="${accent}" stroke-width="1.2" opacity=".8"/><circle cx="50" cy="90" r="2.4" fill="${accent}"/>`;
    case 'kimono': return `<defs>${g('#3a2a55', '#1b1233')}</defs><path d="${body}" fill="url(#${id}og)"/><path d="M36 74 L52 104 M64 74 L50 98" stroke="#efe6ff" stroke-width="3.2" fill="none" stroke-linecap="round"/><path d="M36 74 L52 104 L60 104 L40 74Z" fill="${accent}" opacity=".35"/><path d="M6 104 L94 104 L94 98 L6 98Z" fill="#14102a" opacity=".5"/>`;
    case 'labcoat': return `<defs>${g('#f4f6ff', '#c8cfee')}</defs><path d="${body}" fill="url(#${id}og)"/><path d="M40 74 L50 92 L60 74Z" fill="${accent}" opacity=".85"/><path d="M38 74 L46 94 L40 104 L30 104 L33 80Z M62 74 L54 94 L60 104 L70 104 L67 80Z" fill="#e3e8ff" stroke="#aab4e0" stroke-width=".6"/>`;
    case 'hoodie': return `<defs>${g('#262f5c', '#121838')}</defs><path d="M30 76 C28 66 36 62 50 62 C64 62 72 66 70 76Z" fill="#1a2145"/><path d="${body}" fill="url(#${id}og)"/><path d="M42 76 L40 92 M58 76 L60 92" stroke="#cfd6ff" stroke-width="1.4" stroke-linecap="round"/><path d="M36 76 C42 82 58 82 64 76" stroke="${accent}" stroke-width="1.2" fill="none"/>`;
    case 'haori': return `<defs>${g('#1b1f3d', '#0a0d22')}</defs><path d="${body}" fill="url(#${id}og)"/><path d="M42 74 L38 104 M58 74 L62 104" stroke="${accent}" stroke-width="2" opacity=".85"/><path d="M40 74 L50 90 L60 74Z" fill="#e9ecff" opacity=".9"/><circle cx="50" cy="96" r="3.2" fill="none" stroke="${accent}" stroke-width="1.2"/>`;
    default: return `<path d="${body}" fill="#1c2347"/>`;
  }
}

/** Devolve markup SVG interno (viewBox 0 0 100 100). `uid` evita colisões de ids entre vários retratos. */
export function portraitMarkup(look, uid) {
  const L = { ...defaultLook(0), ...(look || {}) };
  const id = `p${String(uid).replace(/[^a-z0-9]/gi, '')}`;
  const [sl, sm, sd] = SKINS[Math.max(0, Math.min(SKINS.length - 1, Number(L.skin) || 0))];
  const hair = /^#[0-9a-f]{6}$/i.test(L.hair) ? L.hair : '#2a1b14';
  const eyes = /^#[0-9a-f]{6}$/i.test(L.eyes) ? L.eyes : '#2a1b10';
  const accent = /^#[0-9a-f]{6}$/i.test(L.accent) ? L.accent : '#22d3ee';
  const fem = L.gender === 'f';
  const lash = fem ? 1.5 : 1.15;
  return `
<defs>
  <radialGradient id="${id}bg" cx=".5" cy=".3" r=".9"><stop offset="0" stop-color="${accent}" stop-opacity=".55"/><stop offset=".55" stop-color="#1a2150"/><stop offset="1" stop-color="#090c22"/></radialGradient>
  <radialGradient id="${id}sk" cx=".42" cy=".34" r=".8"><stop offset="0" stop-color="${sl}"/><stop offset=".62" stop-color="${sm}"/><stop offset="1" stop-color="${sd}"/></radialGradient>
  <linearGradient id="${id}nk" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${sd}"/><stop offset="1" stop-color="${sm}"/></linearGradient>
  <linearGradient id="${id}hg" x1=".2" y1="0" x2=".8" y2="1"><stop offset="0" stop-color="${shade(hair, 22)}"/><stop offset=".5" stop-color="${hair}"/><stop offset="1" stop-color="${shade(hair, -22)}"/></linearGradient>
  <radialGradient id="${id}ir" cx=".35" cy=".3" r=".9"><stop offset="0" stop-color="${shade(eyes, 40)}"/><stop offset="1" stop-color="${eyes}"/></radialGradient>
  <linearGradient id="${id}rim" x1="0" y1="0" x2="1" y2="0"><stop offset=".55" stop-color="${accent}" stop-opacity="0"/><stop offset="1" stop-color="${accent}" stop-opacity=".55"/></linearGradient>
  <clipPath id="${id}hc"><ellipse cx="50" cy="45" rx="19" ry="23"/></clipPath>
</defs>
<rect width="100" height="100" fill="url(#${id}bg)"/>
<circle cx="50" cy="46" r="40" fill="${accent}" opacity=".08"/>
${hairBack(L.style, hair, id)}
${outfit(L.outfit, accent, id)}
<path d="M42 58 L42 76 C46 80 54 80 58 76 L58 58Z" fill="url(#${id}nk)"/>
<ellipse cx="31" cy="48" rx="3.2" ry="5.2" fill="${sm}"/><ellipse cx="69" cy="48" rx="3.2" ry="5.2" fill="${sm}"/>
<ellipse cx="31.5" cy="48.5" rx="1.4" ry="3" fill="${sd}" opacity=".5"/><ellipse cx="68.5" cy="48.5" rx="1.4" ry="3" fill="${sd}" opacity=".5"/>
<ellipse cx="50" cy="45" rx="19" ry="23" fill="url(#${id}sk)"/>
<g clip-path="url(#${id}hc)">
  <path d="M31 56 C36 72 64 72 69 56 L69 70 L31 70Z" fill="${sd}" opacity=".28"/>
  <rect x="50" y="20" width="22" height="50" fill="url(#${id}rim)"/>
  <ellipse cx="37" cy="53" rx="5" ry="3.2" fill="#ff8aa0" opacity="${fem ? '.28' : '.14'}"/><ellipse cx="63" cy="53" rx="5" ry="3.2" fill="#ff8aa0" opacity="${fem ? '.28' : '.14'}"/>
</g>
${hairFront(L.style, hair, id)}
<path d="M33 36.5 Q40 ${fem ? '33.6' : '34.4'} 46 36" stroke="${shade(hair, -8)}" stroke-width="${fem ? 1.4 : 2}" fill="none" stroke-linecap="round" opacity=".92"/>
<path d="M54 36 Q60 ${fem ? '33.6' : '34.4'} 67 36.5" stroke="${shade(hair, -8)}" stroke-width="${fem ? 1.4 : 2}" fill="none" stroke-linecap="round" opacity=".92"/>
<g>
  <path d="M35.5 44.5 Q41 41 46.5 44.5 Q41 47.8 35.5 44.5Z" fill="#f8f9ff"/>
  <path d="M53.5 44.5 Q59 41 64.5 44.5 Q59 47.8 53.5 44.5Z" fill="#f8f9ff"/>
  <circle cx="41" cy="44.4" r="2.5" fill="url(#${id}ir)"/><circle cx="59" cy="44.4" r="2.5" fill="url(#${id}ir)"/>
  <circle cx="41" cy="44.4" r="1.05" fill="#05060c"/><circle cx="59" cy="44.4" r="1.05" fill="#05060c"/>
  <circle cx="41.9" cy="43.6" r=".7" fill="#fff" opacity=".95"/><circle cx="59.9" cy="43.6" r=".7" fill="#fff" opacity=".95"/>
  <path d="M35.2 44.6 Q41 40.6 46.8 44.6" stroke="#0a0a14" stroke-width="${lash}" fill="none" stroke-linecap="round"/>
  <path d="M53.2 44.6 Q59 40.6 64.8 44.6" stroke="#0a0a14" stroke-width="${lash}" fill="none" stroke-linecap="round"/>
  <path d="M37 46.6 Q41 48.4 45 46.6" stroke="${sd}" stroke-width=".6" fill="none" opacity=".6"/><path d="M55 46.6 Q59 48.4 63 46.6" stroke="${sd}" stroke-width=".6" fill="none" opacity=".6"/>
</g>
<path d="M50 46 Q47.6 53.5 48.6 55.4 Q50 56.4 51.4 55.4 Q52.4 53.5 50 46Z" fill="${sd}" opacity=".32"/>
<path d="M47.4 55.6 Q50 57 52.6 55.6" stroke="${sd}" stroke-width=".9" fill="none" opacity=".6" stroke-linecap="round"/>
<path d="M44 61.4 Q50 63.8 56 61.4 Q50 60 44 61.4Z" fill="${fem ? '#c25b6b' : '#b0705c'}"/>
<path d="M44.4 61.8 Q50 66 55.6 61.8 Q50 64.4 44.4 61.8Z" fill="${fem ? '#d9788a' : '#c58470'}"/>
<path d="M45 61.6 Q50 62.7 55 61.6" stroke="#6b2a35" stroke-width=".5" fill="none" opacity=".6"/>
${L.glasses ? `<g fill="${accent}" fill-opacity=".08" stroke="#0d1024" stroke-width="1.15"><rect x="33.4" y="40" width="15" height="9.6" rx="3.6"/><rect x="51.6" y="40" width="15" height="9.6" rx="3.6"/><path d="M48.4 44 Q50 42.8 51.6 44" fill="none"/><path d="M33.4 43.4 L30 42.4 M66.6 43.4 L70 42.4" fill="none"/></g><path d="M36 41.8 L40 41.8" stroke="#fff" stroke-width=".8" opacity=".5" stroke-linecap="round"/>` : ''}
${L.outfit === 'techwear' ? `<path d="M69.5 50 q4 4 0 9 q-2 2.4 -5 3" stroke="${accent}" stroke-width="1.1" fill="none" stroke-linecap="round"/><circle cx="64.6" cy="62.2" r="1.2" fill="${accent}"/>` : ''}`;
}

/** SVG autónomo (para listas/gavetas). */
export function portraitSVG(look, uid, title) {
  return `<svg viewBox="0 0 100 100" role="img" aria-label="${esc(title || 'Retrato provisório')}" xmlns="http://www.w3.org/2000/svg">${portraitMarkup(look, uid)}</svg>`;
}
