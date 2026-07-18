/** Router/Vite public path. Default `/` (Railway / standalone). Set `VITE_BASE_PATH=/admin` for path-prefix deploys. */
export function appBasename(): string {
  const raw = (import.meta.env.VITE_BASE_PATH as string | undefined)?.trim() || '/';
  if (!raw || raw === '/') return '/';
  const withSlash = raw.startsWith('/') ? raw : `/${raw}`;
  return withSlash.replace(/\/+$/, '') || '/';
}
