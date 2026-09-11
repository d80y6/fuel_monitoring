/// <reference types="vitest" />
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    // This box is heavily oversubscribed (loadavg reached 7-9+ on 4 CPUs during CI
    // runs; userEvent-heavy tests measured up to ~15s of wall-clock starvation).
    // The 5000ms default testTimeout is too tight; 15s gives evidence-backed headroom.
    testTimeout: 15_000,
    hookTimeout: 15_000,
  },
});
