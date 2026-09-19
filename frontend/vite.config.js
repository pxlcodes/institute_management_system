import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8080', changeOrigin: true },
      '/auth': { target: 'http://127.0.0.1:8080', changeOrigin: true },
      '/me': { target: 'http://127.0.0.1:8080', changeOrigin: true },
      '/dashboard': { target: 'http://127.0.0.1:8080', changeOrigin: true },
      '/class-routines': { target: 'http://127.0.0.1:8080', changeOrigin: true },
      '/academic-calendar': { target: 'http://127.0.0.1:8080', changeOrigin: true },
      '/students': { target: 'http://127.0.0.1:8080', changeOrigin: true },
      '/due-bills': { target: 'http://127.0.0.1:8080', changeOrigin: true }
    }
  },
  build: {
    outDir: '../web_dist',
    emptyOutDir: true
  }
})
