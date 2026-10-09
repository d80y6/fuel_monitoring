/// <reference types="vitest" />
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react()],
  build: {
    // The app chunk was 1.54 MB (493 kB gzip) because every dependency was
    // bundled into it. Splitting vendors means a dependency upgrade invalidates
    // only its own chunk instead of the whole app bundle, which matters most for
    // the lazily-loaded 3D tank view that users on the dashboard never fetch.
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return;
          if (id.includes('/three/')) return 'three';
          if (id.includes('/react-three/')) return 'react-three';
          if (id.includes('/react-dom/') || id.includes('/react/')) return 'react';
          if (id.includes('/i18next/') || id.includes('/react-i18next/')) return 'i18n';
          if (id.includes('/zustand/')) return 'state';
          if (id.includes('/echarts/') || id.includes('/zrender/')) return 'charts';
          return 'vendor';
        },
      },
    },
    // Raised from the 500 kB default only to cover two deliberate lazy chunks:
    // `charts` (echarts, 1.04 MB) and `three` (667 kB), both fetched solely by
    // the tank detail page and the 3D view. Everything on the critical path is
    // far smaller -- index is 173 kB and vendor 287 kB -- so a regression past
    // this line still means someone re-inlined a heavy dependency eagerly.
    chunkSizeWarningLimit: 1100,
  },
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
    // Cap worker threads so an oversubscribed 4-CPU box cannot starve jsdom tests
    // past the per-test timeout (observed 15s wall-clock timeouts at max parallelism).
    poolOptions: {
      threads: {
        minThreads: 1,
        maxThreads: 2,
      },
    },
  },
});
