// API client for the Admin portal. Talks to the BE3 gateway envelope:
//   success => { ok: true, data: <T>, meta: {...} }
//   error   => { ok: false, data: { message, code, details }, meta: {...} }
import { apiFetchErrorMessage, resolveApiBase } from './apiBase';

const TOKEN_KEY = 'lexsocial_admin_token';

export function getApiBase(): string {
  return resolveApiBase();
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function getToken(): string {
  // No hardcoded fallback: before a real login there is NO token, so unauthenticated admin
  // requests are rejected by the backend (RBAC) instead of silently running as admin.
  return localStorage.getItem(TOKEN_KEY) ?? '';
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

async function request(path: string, init?: RequestInit): Promise<Response> {
  const base = resolveApiBase();
  if (!base) {
    throw new Error(apiFetchErrorMessage(new Error('Failed to fetch'), base));
  }
  try {
    return await fetch(`${base}${path}`, init);
  } catch (err) {
    throw new Error(apiFetchErrorMessage(err, base));
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  return parse<T>(await request(path, { headers: headers(false) }));
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  return parse<T>(await request(path, { method: 'POST', headers: headers(true), body: JSON.stringify(body) }));
}

export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return parse<T>(await request(path, { method: 'PATCH', headers: headers(true), body: JSON.stringify(body) }));
}

export async function apiDelete<T>(path: string): Promise<T> {
  return parse<T>(await request(path, { method: 'DELETE', headers: headers(false) }));
}

// Multipart upload (e.g. raw legal files). Do NOT set Content-Type — the browser sets the
// multipart boundary automatically. Auth header is still attached.
export async function apiUpload<T>(path: string, form: FormData): Promise<T> {
  const h: Record<string, string> = { Accept: 'application/json', Authorization: `Bearer ${getToken()}` };
  return parse<T>(await request(path, { method: 'POST', headers: h, body: form }));
}

/** Absolute URL for a public raw legal file (browser navigates/downloads directly). */
export function fileUrl(fileId: string): string {
  return `${resolveApiBase()}/citizen/legal/files/${encodeURIComponent(fileId)}`;
}
