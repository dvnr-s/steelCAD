import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // Vitest transforms JSX with esbuild (not plugin-react) — use the automatic
  // runtime so test files don't need `import React`.
  esbuild: { jsx: 'automatic' },
  server: {
    port: 5173,
    proxy: {
      '/auth': 'http://localhost:8000',
      '/designs': 'http://localhost:8000',
      '/customers': 'http://localhost:8000',
      '/estimates': 'http://localhost:8000',
      '/price': 'http://localhost:8000',
      '/rates': 'http://localhost:8000',
      '/users': 'http://localhost:8000',
      '/settings': 'http://localhost:8000',
      '/audit': 'http://localhost:8000',
      '/trash': 'http://localhost:8000',
      '/dashboard': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/setupTests.js'],
  },
})
