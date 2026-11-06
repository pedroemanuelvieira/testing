// Cliente da API. O browser nunca decide nada: só envia pedidos e mostra o que o servidor devolve.
let csrf = '';
export const setCsrf = (t) => { csrf = t; };

export class ApiError extends Error {
  constructor(status, body) {
    super(body?.error?.message || `Erro ${status}`);
    this.status = status; this.code = body?.error?.code || 'error'; this.details = body?.error?.details;
  }
}

export async function api(method, path, body) {
  const res = await fetch(path, {
    method, credentials: 'same-origin',
    headers: { ...(body !== undefined ? { 'content-type': 'application/json' } : {}), ...(method !== 'GET' ? { 'x-csrf-token': csrf } : {}) },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const ct = res.headers.get('content-type') || '';
  const data = ct.includes('json') ? await res.json() : await res.text();
  if (!res.ok) {
    if (res.status === 401 && path !== '/api/login') window.dispatchEvent(new CustomEvent('village:unauth'));
    throw new ApiError(res.status, data);
  }
  return data;
}
export const get = (p) => api('GET', p);
export const post = (p, b = {}) => api('POST', p, b);
export const patch = (p, b) => api('PATCH', p, b);
