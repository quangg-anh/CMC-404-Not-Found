import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

const redirectPlugin = (basePath: string) => ({
  name: 'redirect-plugin',
  configureServer(server: any) {
    if (basePath === '/') return
    const prefix = basePath.replace(/\/+$/, '')
    server.middlewares.use((req: any, res: any, next: any) => {
      if (req.url === prefix) {
        res.writeHead(301, { Location: `${prefix}/` });
        res.end();
      } else {
        next();
      }
    });
  }
});

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const raw = (env.VITE_BASE_PATH || '/').trim() || '/'
  const base = raw === '/' ? '/' : `${raw.replace(/\/+$/, '')}/`

  return {
    plugins: [react(), redirectPlugin(base === '/' ? '/' : base.replace(/\/+$/, ''))],
    base,
    server: {
      host: '0.0.0.0',
      port: 5173,
      strictPort: true,
      // Railway / public tunnels send custom Host headers — do not block them.
      allowedHosts: true,
    },
    preview: {
      host: '0.0.0.0',
      port: 5173,
      strictPort: true,
      allowedHosts: true,
    },
  }
})
