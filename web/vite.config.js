import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// npm run dev      -> proxy /api to localhost:8000 (live server)
// npm run dev:8001 -> proxy /api to localhost:8001 (test server, launch/localhost_8001)
export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss()],
  server: {
    host: '0.0.0.0',
    allowedHosts: true,
    port: 5173,
    proxy: { '/api': `http://localhost:${mode === 'test' ? 8001 : 8000}` },
  },
  build: { outDir: 'dist', emptyOutDir: true },
}));
