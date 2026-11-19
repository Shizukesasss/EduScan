import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  if (mode === 'vercel') {
    const { VITE_API_URL } = loadEnv(mode, process.cwd());
    const api = URL.canParse(VITE_API_URL) ? new URL(VITE_API_URL) : null;
    if (!api || api.protocol !== 'https:' || api.pathname !== '/api' || api.search || api.hash
      || api.username || api.password || api.href !== VITE_API_URL) {
      throw new Error('Set VITE_API_URL to the persistent API HTTPS URL ending in /api.');
    }
  }
  return {
    plugins: [react()],
    build: { sourcemap: false },
  };
})
