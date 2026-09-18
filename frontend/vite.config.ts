import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath } from 'node:url'

export default defineConfig(({ mode }) => {
  const root = fileURLToPath(new URL('..', import.meta.url))
  const env = loadEnv(mode, root, '')
  const host = env.APP_HOST === '0.0.0.0' ? '127.0.0.1' : (env.APP_HOST || '127.0.0.1')
  const target = `http://${host.includes(':') ? `[${host}]` : host}:${env.APP_PORT || '8000'}`
  const proxy = { '/api': { target, changeOrigin: true } }
  return {
    plugins: [vue()],
    server: { host: '127.0.0.1', port: 5173, strictPort: true, proxy },
    preview: { host: '127.0.0.1', port: 4173, strictPort: true, proxy },
  }
})
