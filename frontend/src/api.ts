// Cliente HTTP da API do BI ML Studio.
import type { Job } from "./types";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const isForm = init.body instanceof FormData;
  const res = await fetch(path, {
    ...init,
    headers: isForm ? init.headers : { "Content-Type": "application/json", ...(init.headers || {}) },
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* resposta sem JSON */
    }
    throw new ApiError(detail, res.status);
  }
  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) => request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  del: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  upload: <T>(path: string, form: FormData) => request<T>(path, { method: "POST", body: form }),
};

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Acompanha uma tarefa assíncrona até terminar, reportando o progresso. */
export async function waitJob(jobId: string, onProgress?: (job: Job) => void, intervalMs = 700): Promise<Job> {
  for (;;) {
    const job = await api.get<Job>(`/api/jobs/${jobId}`);
    onProgress?.(job);
    if (job.status === "done") return job;
    if (job.status === "error") throw new ApiError(job.error || "A tarefa falhou.", 400);
    await sleep(intervalMs);
  }
}

export const exportUrl = (path: string) => `/api/exports/${path.split("/").map(encodeURIComponent).join("/")}`;

export function safeStorage(key: string, value?: string | null): string | null {
  try {
    if (value === undefined) return window.localStorage.getItem(key);
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    /* armazenamento indisponível (modo privado) */
  }
  return null;
}
