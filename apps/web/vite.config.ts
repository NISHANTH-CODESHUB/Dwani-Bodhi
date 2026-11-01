/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      injectRegister: false, // registered from src/main.tsx via virtual:pwa-register
      includeAssets: ['icons/*.png', 'icons/*.svg'],
      manifest: {
        name: 'Dhwani-Bodhi',
        short_name: 'Dhwani-Bodhi',
        description: "Teacher's companion — reading and maths checks",
        lang: 'en-IN',
        dir: 'ltr',
        start_url: '/',
        scope: '/',
        display: 'standalone',
        orientation: 'portrait',
        background_color: '#f4f6fa',
        theme_color: '#0e1a33',
        icons: [
          { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: '/icons/maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        // App shell + Cheenu's pre-recorded prompts are precached; API data lives in IndexedDB (Dexie).
        globPatterns: ['**/*.{js,css,html,png,svg,ico,webmanifest,mp3,json}'],
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/v1\//, /^\/health/, /^\/docs/],
        cleanupOutdatedCaches: true,
        clientsClaim: true,
        skipWaiting: true,
      },
      devOptions: { enabled: false },
    }),
  ],
  // `npm run dev` / `npm run preview`: forward API calls to the local FastAPI server (README "Run it locally").
  server: { proxy: { '/v1': 'http://localhost:8000', '/health': 'http://localhost:8000' } },
  preview: { proxy: { '/v1': 'http://localhost:8000', '/health': 'http://localhost:8000' } },
  build: { target: 'es2020', sourcemap: false },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
});
