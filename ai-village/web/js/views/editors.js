// Editores de organização: agente (com desenhador de aparência), unidade e função.
// Tudo é dado — acrescentar uma função/agente não exige código (CA01).
import { h, field, openModal, toast, busy } from '../ui.js';
import { post, patch, ApiError } from '../api.js';
import { S, W, units, roles, agents, agentById, loadWorld } from '../state.js';
import { portraitSVG, SKINS, HAIRS, STYLES, OUTFITS, ACCENTS, EYES, defaultLook } from '../avatar.js';

const errMsg = (e) => (e instanceof ApiError ? e.message : 'Falhou. Tenta de novo.');
const STYLE_PT = { short: 'curto', sidepart: 'risco ao lado', spiky: 'espetado', undercut: 'undercut', buzz: 'rapado', bob: 'bob', long: 'comprido', bun: 'carrapito' };
const OUTFIT_PT = { suit: 'fato', techwear: 'techwear', kimono: 'quimono', labcoat: 'bata de laboratório', hoodie: 'hoodie', haori: 'haori' };
export const THEMES = [['tower', 'Torre (pagode-tecnológico)'], ['lab', 'Laboratório de vidro'], ['workshop', 'Oficina'], ['dock', 'Cais / armazém'], ['dojo', 'Dojo de madeira'], ['garden', 'Casa de chá e jardim'], ['vault', 'Kura (cofre)'], ['hall', 'Salão']];
export const TIERS = [['ceo', 'CEO'], ['c_level', 'C-level'], ['director', 'Diretor/a'], ['specialist', 'Especialista'], ['orchestrator', 'Orquestrador'], ['control', 'Controlo']];

function checks(items, selected, name) {
  const set = new Set(selected);
  return h('div', { class: 'col', style: { gap: '4px', maxHeight: '180px', overflow: 'auto', padding: '4px' } },
    items.map((it) => h('label', { class: 'row', style: { gap: '8px', fontSize: '.88rem' } }, h('input', { type: 'checkbox', name, value: it.value, checked: set.has(it.value) }), it.label)));
}
const picked = (root, name) => [...root.querySelectorAll(`input[name="${name}"]:checked`)].map((i) => i.value);

function appearanceDesigner(initial, agentId) {
  let look = { ...defaultLook(Math.floor(Math.random() * 20)), ...(initial?.type === 'procedural' ? initial : {}) };
  let image = initial?.type === 'image' ? initial : null;
  const preview = h('div', { class: 'avatar lg', style: { width: '120px', height: '120px' }, 'aria-label': 'Pré-visualização do retrato' });
  const draw = () => {
    if (image) { preview.replaceChildren(h('img', { src: `/api/w/${S.world}/portraits/${image.file}`, alt: 'Retrato carregado' })); return; }
    preview.innerHTML = portraitSVG(look, `ed${agentId || 'new'}`, 'Pré-visualização');
  };
  const sw = (list, key, fmt = (v) => v) => h('div', { class: 'swatches', role: 'group' }, list.map((v, i) => {
    const val = key === 'skin' ? i : v;
    const b = h('button', { type: 'button', class: 'swatch', 'aria-label': `${key} ${i + 1}`, style: { background: key === 'skin' ? SKINS[i][1] : fmt(v) }, 'aria-pressed': String(look[key] === val),
      onclick: () => { look[key] = val; image = null; b.parentNode.querySelectorAll('.swatch').forEach((x) => x.setAttribute('aria-pressed', 'false')); b.setAttribute('aria-pressed', 'true'); draw(); } });
    return b;
  }));
  const sel = (key, map, list) => { const s = h('select', { 'aria-label': key }, list.map((v) => h('option', { value: v, selected: look[key] === v }, map[v] || v))); s.addEventListener('change', () => { look[key] = s.value; image = null; draw(); }); return s; };
  const gender = h('select', {}, [['m', 'Masculino'], ['f', 'Feminino']].map(([v, l]) => h('option', { value: v, selected: look.gender === v }, l)));
  gender.addEventListener('change', () => { look.gender = gender.value; image = null; draw(); });
  const glasses = h('input', { type: 'checkbox', checked: Boolean(look.glasses) });
  glasses.addEventListener('change', () => { look.glasses = glasses.checked; image = null; draw(); });
  const file = h('input', { type: 'file', accept: 'image/png,image/jpeg,image/webp' });
  file.addEventListener('change', async () => {
    const f = file.files[0]; if (!f) return;
    if (f.size > 2_000_000) { toast('Imagem acima de 2 MB.', 'error'); return; }
    const data_url = await new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(r.result); r.onerror = rej; r.readAsDataURL(f); });
    try { const r = await post(`${W()}/portraits`, { data_url }); image = r.appearance; draw(); toast('Retrato carregado.'); } catch (e) { toast(errMsg(e), 'error'); }
  });
  const node = h('div', { class: 'card flat' }, h('h3', {}, 'Aparência'),
    h('div', { class: 'note', style: { marginBottom: '10px' } }, 'Os retratos gerados são PROVISÓRIOS. Para um rosto realista a sério, carrega uma fotografia/ilustração licenciada ou gerada por ti (PNG/JPEG/WEBP até 2 MB) — fica guardada no servidor e substitui o provisório.'),
    h('div', { class: 'row', style: { alignItems: 'flex-start' } }, preview, h('div', { class: 'col grow', style: { minWidth: '220px' } },
      h('div', { class: 'grid2' }, field('Género do retrato', gender), field('Cabelo (estilo)', sel('style', STYLE_PT, STYLES))),
      h('div', { class: 'field' }, h('span', { class: 'lbl' }, 'Pele'), sw(SKINS, 'skin')),
      h('div', { class: 'field' }, h('span', { class: 'lbl' }, 'Cor do cabelo'), sw(HAIRS, 'hair')),
      h('div', { class: 'field' }, h('span', { class: 'lbl' }, 'Olhos'), sw(EYES, 'eyes')),
      h('div', { class: 'grid2' }, field('Roupa', sel('outfit', OUTFIT_PT, OUTFITS)), h('div', { class: 'field' }, h('span', { class: 'lbl' }, 'Cor de destaque'), sw(ACCENTS, 'accent'))),
      h('label', { class: 'row' }, glasses, 'Óculos'), field('Ou carregar retrato (substitui o provisório)', file))));
  draw();
  return { node, value: () => image || look };
}

export function openAgentEditor(agent, { onSaved } = {}) {
  const isNew = !agent;
  const f = {
    name: h('input', { type: 'text', value: agent?.display_name || '', maxLength: 60, 'data-autofocus': '', required: true }),
    title: h('input', { type: 'text', value: agent?.title || '', maxLength: 80, placeholder: 'ex.: Diretor de BI' }),
    unit: h('select', {}, h('option', { value: '' }, '— sem unidade —'), units().filter((u) => u.lifecycle_status === 'active').map((u) => h('option', { value: u.id, selected: u.id === agent?.org_unit_id }, u.name))),
    manager: h('select', {}, h('option', { value: '' }, '— sem superior —'), agents().filter((a) => a.id !== agent?.id && a.lifecycle_status !== 'archived').map((a) => h('option', { value: a.id, selected: a.id === agent?.manager_agent_id }, `${a.display_name} (${a.title})`))),
    desc: h('textarea', { maxLength: 800 }, agent?.description || ''),
    orch: h('input', { type: 'checkbox', checked: Boolean(agent?.orchestrator_flag) }),
  };
  const roleBox = checks(roles().filter((r) => r.lifecycle_status === 'active').map((r) => ({ value: r.id, label: `${r.name} (${r.tier})` })), agent?.role_ids || [], 'role');
  const capBox = checks((S.overview?.capabilities || []).map((c) => ({ value: c.id, label: `${c.label}${c.auto_execute ? ' ⚙' : ''}` })), agent?.capability_ids || [], 'cap');
  const apply = h('button', { type: 'button', class: 'btn sm', onclick: () => {
    const props = new Set(picked(roleBox, 'role').flatMap((id) => roles().find((r) => r.id === id)?.default_capability_proposals || []));
    capBox.querySelectorAll('input').forEach((i) => { if (props.has(i.value)) i.checked = true; });
    toast(props.size ? 'Propostas das funções aplicadas (podes ajustar).' : 'As funções escolhidas não têm propostas.');
  } }, 'Aplicar capacidades propostas pelas funções');
  const look = appearanceDesigner(agent?.appearance, agent?.id);
  const err = h('div', { class: 'note bad hide', role: 'alert' });
  const save = h('button', { class: 'btn primary' }, isNew ? 'Criar agente' : 'Guardar');
  const m = openModal({
    title: isNew ? 'Novo agente' : `Editar ${agent.display_name}`, wide: true,
    body: h('div', {}, h('div', { class: 'grid2' }, field('Nome', f.name), field('Cargo / título', f.title)),
      h('div', { class: 'grid2' }, field('Unidade', f.unit), field('Reporta a', f.manager)),
      field('Missão / descrição', f.desc),
      h('div', { class: 'grid2' }, h('div', { class: 'field' }, h('span', { class: 'lbl' }, 'Funções (cargos)'), roleBox, h('span', { class: 'hint' }, 'A função descreve missão e limites. NÃO concede acesso.')),
        h('div', { class: 'field' }, h('span', { class: 'lbl' }, 'Capacidades (o que sabe fazer)'), capBox, apply, h('span', { class: 'hint' }, '⚙ = executa no worker; as restantes são trabalho manual com prova.'))),
      h('label', { class: 'row' }, f.orch, h('span', {}, 'Orquestrador deste mundo (só pode existir um ativo)')),
      look.node, err),
    actions: [h('button', { class: 'btn', onclick: () => m.close() }, 'Cancelar'), save],
  });
  save.addEventListener('click', () => busy(save, async () => {
    err.classList.add('hide');
    const body = {
      display_name: f.name.value, title: f.title.value, org_unit_id: f.unit.value || null, manager_agent_id: f.manager.value || null, description: f.desc.value,
      role_ids: picked(roleBox, 'role'), capability_ids: picked(capBox, 'cap'), orchestrator_flag: f.orch.checked, appearance: look.value(),
    };
    try {
      if (isNew) await post(`${W()}/agents`, body); else await patch(`${W()}/agents/${agent.id}`, { ...body, expected_version: agent.record_version });
      toast(isNew ? 'Agente criado.' : 'Agente guardado.'); m.close(); await loadWorld(); onSaved?.();
    } catch (e) { err.textContent = errMsg(e); err.classList.remove('hide'); }
  }));
}

export function openUnitEditor(unit, { onSaved } = {}) {
  const isNew = !unit;
  const f = {
    name: h('input', { type: 'text', value: unit?.name || '', maxLength: 80, 'data-autofocus': '' }),
    purpose: h('textarea', { maxLength: 400 }, unit?.purpose || ''),
    theme: h('select', {}, THEMES.map(([v, l]) => h('option', { value: v, selected: v === (unit?.theme || 'hall') }, l))),
    kanji: h('input', { type: 'text', value: unit?.kanji || '', maxLength: 6, placeholder: '本社' }),
    resp: h('select', {}, h('option', { value: '' }, '— sem responsável —'), agents().filter((a) => a.lifecycle_status !== 'archived').map((a) => h('option', { value: a.id, selected: a.id === unit?.responsible_agent_id }, a.display_name))),
  };
  const err = h('div', { class: 'note bad hide', role: 'alert' });
  const save = h('button', { class: 'btn primary' }, isNew ? 'Criar unidade' : 'Guardar');
  const m = openModal({ title: isNew ? 'Nova unidade (edifício na vila)' : `Editar ${unit.name}`,
    body: h('div', {}, field('Nome', f.name), field('Propósito', f.purpose), h('div', { class: 'grid2' }, field('Edifício', f.theme), field('Kanji da placa (opcional)', f.kanji)), field('Responsável', f.resp), err),
    actions: [h('button', { class: 'btn', onclick: () => m.close() }, 'Cancelar'), save] });
  save.addEventListener('click', () => busy(save, async () => {
    const body = { name: f.name.value, purpose: f.purpose.value, theme: f.theme.value, kanji: f.kanji.value, responsible_agent_id: f.resp.value || null };
    try {
      if (isNew) { const { responsible_agent_id, ...rest } = body; await post(`${W()}/units`, responsible_agent_id ? body : rest); } else await patch(`${W()}/units/${unit.id}`, { ...body, expected_version: unit.record_version });
      toast('Unidade guardada.'); m.close(); await loadWorld(); onSaved?.();
    } catch (e) { err.textContent = errMsg(e); err.classList.remove('hide'); }
  }));
}

export function openRoleEditor(role, { onSaved } = {}) {
  const isNew = !role;
  const lines = (a) => (a || []).join('\n');
  const f = {
    name: h('input', { type: 'text', value: role?.name || '', maxLength: 80, 'data-autofocus': '' }),
    tier: h('select', {}, TIERS.map(([v, l]) => h('option', { value: v, selected: v === (role?.tier || 'specialist') }, l))),
    mission: h('textarea', { maxLength: 600 }, role?.mission || ''),
    resp: h('textarea', { placeholder: 'uma por linha' }, lines(role?.responsibilities)),
    limits: h('textarea', { placeholder: 'uma por linha' }, lines(role?.limits)),
  };
  const caps = checks((S.overview?.capabilities || []).map((c) => ({ value: c.id, label: c.label })), role?.default_capability_proposals || [], 'cap');
  const err = h('div', { class: 'note bad hide', role: 'alert' });
  const save = h('button', { class: 'btn primary' }, isNew ? 'Criar função' : 'Guardar');
  const m = openModal({ title: isNew ? 'Nova função (cargo)' : `Editar ${role.name}`, wide: true,
    body: h('div', {}, h('div', { class: 'grid2' }, field('Nome do cargo', f.name), field('Nível', f.tier)), field('Missão', f.mission),
      h('div', { class: 'grid2' }, field('Responsabilidades', f.resp), field('Limites (o que NÃO pode)', f.limits)),
      h('div', { class: 'field' }, h('span', { class: 'lbl' }, 'Capacidades propostas'), caps, h('span', { class: 'hint' }, 'São só propostas para pré-preencher agentes. O cargo nunca concede acesso por si.')), err),
    actions: [h('button', { class: 'btn', onclick: () => m.close() }, 'Cancelar'), save] });
  const split = (s) => s.split('\n').map((x) => x.trim()).filter(Boolean);
  save.addEventListener('click', () => busy(save, async () => {
    const body = { name: f.name.value, tier: f.tier.value, mission: f.mission.value, responsibilities: split(f.resp.value), limits: split(f.limits.value), default_capability_proposals: picked(caps, 'cap') };
    try {
      if (isNew) await post(`${W()}/roles`, body); else await patch(`${W()}/roles/${role.id}`, { ...body, expected_version: role.record_version });
      toast('Função guardada.'); m.close(); await loadWorld(); onSaved?.();
    } catch (e) { err.textContent = errMsg(e); err.classList.remove('hide'); }
  }));
}
void agentById;
