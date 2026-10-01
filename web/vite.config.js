import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// npm run dev      -> proxy /api and /cameras_bkk.json to localhost:8000 (live server)
// npm run dev:8001 -> proxy /api and /cameras_bkk.json to localhost:8001 (test server, launch/test)
// The camera list comes from the server's config/cameras_bkk.json, so dev and production show the same cameras.
// npm run build    -> web/dist, which no server reads. Each server serves instances/<name>/dist, built by
//                     launch\build_web.bat (or npm run build -- --outDir ../instances/test/dist).
export default defineConfig(({ mode }) => {
  const server = `http://localhost:${mode === 'test' ? 8001 : 8000}`;
  return {
    plugins: [react(), tailwindcss()],
    server: {
      host: '0.0.0.0',
      allowedHosts: true,
      port: 5173,
      proxy: { '/api': server, '/cameras_bkk.json': server },
    },
    build: { outDir: 'dist', emptyOutDir: true },
  };
});
