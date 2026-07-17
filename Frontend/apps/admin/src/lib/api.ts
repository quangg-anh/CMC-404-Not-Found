// API client for the Admin portal. Talks to the BE3 gateway envelope:
//   success => { ok: true, data: <T>, meta: {...} }
//   error   => { ok: false, data: { message, code, details }, meta: {...} }
// Admin endpoints require a bearer token (RBAC). Until a real IdP is wired, we store a
// deterministic dev token at login (see Login.tsx) — the backend accepts these in dev/eval mode.
const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000';
const TOKEN_KEY = 'lexsocial_admin_token';

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) ?? 'test-admin-multi';
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export interface ApiEnvelope<T> {
  ok: boolean;
  data: T;
  meta?: Record<string, unknown>;
}

function headers(json: boolean): Record<string, string> {
  const h: Record<string, string> = { Accept: 'application/json', Authorization: `Bearer ${getToken()}` };
  if (json) h['Content-Type'] = 'application/json';
  return h;
}

async function parse<T>(res: Response): Promise<T> {
  const json = (await res.json().catch(() => null)) as ApiEnvelope<T> | null;
  if (!res.ok || !json || json.ok !== true) {
    const message =
      (json?.data as { message?: string } | undefined)?.message ??
      `Yêu cầu thất bại (HTTP ${res.status})`;
    throw new Error(message);
  }
  return json.data;
}

export async function apiGet<T>(path: string): Promise<T> {
  return parse<T>(await fetch(`${API_BASE}${path}`, { headers: headers(false) }));
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  return parse<T>(await fetch(`${API_BASE}${path}`, { method: 'POST', headers: headers(true), body: JSON.stringify(body) }));
}

export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return parse<T>(await fetch(`${API_BASE}${path}`, { method: 'PATCH', headers: headers(true), body: JSON.stringify(body) }));
}

// Multipart upload (e.g. raw legal files). Do NOT set Content-Type — the browser sets the
// multipart boundary automatically. Auth header is still attached.
export async function apiUpload<T>(path: string, form: FormData): Promise<T> {
  const h: Record<string, string> = { Accept: 'application/json', Authorization: `Bearer ${getToken()}` };
  return parse<T>(await fetch(`${API_BASE}${path}`, { method: 'POST', headers: h, body: form }));
}
