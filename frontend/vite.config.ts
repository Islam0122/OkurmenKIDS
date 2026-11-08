import { fileURLToPath, URL } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { loadEnv } from 'vite'
import { defineConfig } from 'vitest/config'

// The static <title> before React starts: the OKURMENKIDS DIGITAL launcher
// build (VITE_APP_MODE=portal) names itself, every other build keeps the LMS title.
function brandTitle(mode: string) {
  const portal = loadEnv(mode, process.cwd(), 'VITE_').VITE_APP_MODE === 'portal'
  return {
    name: 'okurmenkids-digital-title',
    transformIndexHtml: (html: string) =>
      portal ? html.replace(/<title>[^<]*<\/title>/, '<title>OkurmenKids Digital — Образовательная экосистема</title>') : html,
  }
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss(), brandTitle(mode)],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    proxy: {
      // Lets the Vite dev server and the Django API share an origin, so
      // cookies/CORS never enter the picture locally — same trick a
      // reverse proxy would do in front of a real deployment.
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/media': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: true,
  },
}))
