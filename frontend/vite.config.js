import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
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
      '/health': 'http://localhost:8000',
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: [],
  },
})
