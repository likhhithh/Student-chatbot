import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/ask': 'http://localhost:8000',
      '/ask/stream': 'http://localhost:8000',
      '/upload': 'http://localhost:8000',
      '/session': 'http://localhost:8000',
      '/healthz': 'http://localhost:8000',
      '/documents': 'http://localhost:8000',
      '/page-preview': 'http://localhost:8000',
    },
  },
  build: {
    outDir: '../app/static',
    emptyOutDir: true,
    assetsDir: 'assets',
  },
})
