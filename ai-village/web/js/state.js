// Estado do cliente = espelho do backend (nunca fonte de verdade). localStorage só guarda preferências de UI.
import { get } from './api.js';

const pref = {
  get(k, d) { try { return localStorage.getItem(`village.${k}`) ?? d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(`village.${k}`, v); } catch { /* storage indisponível: ignora */ } },
};
export { pref };

export const S = { world: pref.get('world', 'personal'), worlds: [], org: null, overview: null, user: null };
export const W = () => `/api/w/${S.world}`;
const subs = new Set();
export const subscribe = (fn) => { subs.add(fn); return () => subs.delete(fn); };
export const emit = () => subs.forEach((f) => { try { f(); } catch (e) { console.error(e); } });

export async function loadWorlds() { S.worlds = await get('/api/worlds'); }
export async function loadWorld() {
  const [org, overview] = await Promise.all([get(`${W()}/org`), get(`${W()}/overview`)]);
  S.org = org; S.overview = overview; emit();
}
export function setWorld(id) { S.world = id; pref.set('world', id); S.org = null; S.overview = null; }

export const agents = () => S.org?.agents || [];
export const units = () => S.org?.units || [];
export const roles = () => S.org?.roles || [];
export const agentById = (id) => agents().find((a) => a.id === id);
export const unitById = (id) => units().find((u) => u.id === id);
export const roleById = (id) => roles().find((r) => r.id === id);
export const capById = (id) => S.overview?.capabilities?.find((c) => c.id === id);
export const orchestrator = () => agents().find((a) => a.orchestrator_flag);
export const designOnly = () => S.overview?.world?.policy?.execution === false;
