import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath } from 'node:url'
import { readFileSync, writeFileSync } from 'node:fs'
import { createHash } from 'node:crypto'

export default defineConfig(({ mode }) => {
  const root = fileURLToPath(new URL('..', import.meta.url))
  const env = loadEnv(mode, root, '')
  const host = env.APP_HOST === '0.0.0.0' ? '127.0.0.1' : (env.APP_HOST || '127.0.0.1')
  const target = `http://${host.includes(':') ? `[${host}]` : host}:${env.APP_PORT || '8000'}`
  const proxy = { '/api': { target, changeOrigin: true } }
  return {
    plugins: [vue(), {
      name: 'independent-phone-shell',
      transformIndexHtml() {
        if (mode === 'phone-e2e') return [{ tag: 'p', attrs: { style: 'padding:12px;text-align:center;background:#fff0d5;margin:0', role: 'status' }, children: 'Synthetic Google HTTP fixture · real IndexedDB and encryption · no live account', injectTo: 'body-prepend' }]
      },
      writeBundle(options, bundle) {
        const output = options.dir ?? 'dist'
        const assets = new Set<string>()
        function collect(name: string) {
          if (assets.has('/' + name)) return
          assets.add('/' + name)
          const chunk = bundle[name]
          if (chunk?.type === 'chunk') { chunk.imports.forEach(collect); chunk.dynamicImports.forEach(collect) }
        }
        const html = readFileSync(output + '/phone/index.html', 'utf8')
        for (const match of html.matchAll(/(?:src|href)="(\/assets\/[^\"]+)"/g)) collect(match[1]!.slice(1))
        const list = [...assets].sort()
        // HTML, manifest and worker-only changes must also rotate the shell cache.
        const hash = createHash('sha256').update(html)
        for (const name of [...list, '/phone/manifest.webmanifest', '/phone/sw.js', '/icons/icon-192.png', '/icons/icon-512.png']) hash.update(readFileSync(output + name))
        const version = hash.digest('hex').slice(0, 16)
        const worker = readFileSync(output + '/phone/sw.js', 'utf8').replace('/*PHONE_ASSETS*/ []', JSON.stringify(list)).replace("/*PHONE_VERSION*/ 'development'", JSON.stringify(version))
        writeFileSync(output + '/phone/sw.js', worker)
      },
    }],
    resolve: mode === 'phone-e2e' ? { alias: [{ find: /^\.\/runtime$/, replacement: fileURLToPath(new URL('./tests/sync/browserRuntime.ts', import.meta.url)) }] } : undefined,
    build: { ...(mode === 'phone-e2e' ? { outDir: root + '/.run/phone-browser-build', emptyOutDir: true } : {}), rollupOptions: { input: { main: fileURLToPath(new URL('./index.html', import.meta.url)), phone: fileURLToPath(new URL('./phone/index.html', import.meta.url)) } } },
    envDir: root,
    server: { host: '127.0.0.1', port: 5173, strictPort: true, proxy },
    preview: { host: '127.0.0.1', port: 4173, strictPort: true, proxy },
  }
})
