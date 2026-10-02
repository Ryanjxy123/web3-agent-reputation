import { env } from 'node:process';
import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

export default defineConfig({
  plugins: [vue()],
  server: { host: '127.0.0.1', proxy: { '/health': env.PLATFORM_API_ORIGIN || 'http://127.0.0.1:8000', '/api': env.PLATFORM_API_ORIGIN || 'http://127.0.0.1:8000' } },
});
