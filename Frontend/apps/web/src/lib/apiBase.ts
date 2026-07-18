/**
 * Resolve the BE3 API base URL for browser fetch.
 *
 * Priority:
 * 1. `window.__LEXSOCIAL_API_URL__` (runtime — set in index.html / config.js on Railway)
 * 2. `VITE_API_URL` (build-time — must be public https://…up.railway.app, NOT *.railway.internal)
 * 3. Localhost only when the page itself is localhost
 */
declare global {
  interface Window {
    __LEXSOCIAL_API_URL__?: string;
  }
}

function trimSlash(url: string): string {
  return url.replace(/\/+$/, '');
}

export function resolveApiBase(): string {
  const runtime =
    typeof window !== 'undefined'
      ? (window.__LEXSOCIAL_API_URL__ || '').trim()
      : '';
  if (runtime) return trimSlash(runtime);

  const baked = (import.meta.env.VITE_API_URL as string | undefined)?.trim();
  if (baked) return trimSlash(baked);

  if (typeof window !== 'undefined') {
    const host = window.location.hostname;
    if (host === 'localhost' || host === '127.0.0.1') {
      return 'http://localhost:8000';
    }
    console.error(
      '[LexSocial] Missing API URL. Set VITE_API_URL to your public Backend URL ' +
        '(e.g. https://api-xxxx.up.railway.app) at build time, or set window.__LEXSOCIAL_API_URL__.',
    );
    return '';
  }

  return 'http://localhost:8000';
}

export function apiFetchErrorMessage(err: unknown, apiBase: string): string {
  const raw = err instanceof Error ? err.message : String(err);
  if (/failed to fetch|networkerror|load failed|network request failed/i.test(raw)) {
    const target = apiBase || '(chưa cấu hình VITE_API_URL)';
    return (
      `Không kết nối được API (${target}). ` +
      `Trên Railway: đặt VITE_API_URL = URL public HTTPS của service Backend (không dùng *.railway.internal), rồi Redeploy Frontend.`
    );
  }
  return raw;
}
