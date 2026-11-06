import { h } from './ui.js';
import { portraitSVG } from './avatar.js';
import { S } from './state.js';

/** Avatar de um agente: fotografia carregada (se existir) ou retrato procedural provisório. */
export function avatarEl(agent, size = '') {
  const st = agent.activity_status || 'disponivel';
  const box = h('div', { class: `avatar ${size} s-${st}`, 'aria-hidden': 'true' });
  const ap = agent.appearance;
  if (ap?.type === 'image' && /^[a-f0-9]{32}\.(png|jpg|webp)$/.test(ap.file || '')) {
    box.append(h('img', { src: `/api/w/${S.world}/portraits/${ap.file}`, alt: '', loading: 'lazy' }));
  } else {
    box.innerHTML = portraitSVG(ap, agent.id, `Retrato provisório de ${agent.display_name}`);
  }
  return box;
}

export const modeTag = (mode) => mode === 'demo' ? h('span', { class: 'badge demo-tag', title: 'Resposta de regras fixas — sem modelo de IA' }, 'DEMO')
  : mode === 'real' ? h('span', { class: 'badge real-tag', title: 'Resposta de um modelo real via API' }, 'REAL') : null;

export const shortHash = (s) => (s ? `${s.slice(0, 8)}…${s.slice(-4)}` : '—');
