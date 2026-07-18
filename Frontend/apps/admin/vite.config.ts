import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const redirectPlugin = () => ({
  name: 'redirect-plugin',
  configureServer(server: any) {
    server.middlewares.use((req: any, res: any, next: any) => {
      if (req.url === '/admin') {
        res.writeHead(301, { Location: '/admin/' });
        res.end();
      } else {
        next();
      }
    });
  }
});

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), redirectPlugin()],
  base: '/',
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
  },
  preview: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
  }
})
