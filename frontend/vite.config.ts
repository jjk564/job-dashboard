import { defineConfig, type ProxyOptions } from 'vite'
import react from '@vitejs/plugin-react'

type ProxyServer = Parameters<NonNullable<ProxyOptions['configure']>>[0]

/**
 * Land hadoku.me's session cookie on localhost for the dev server.
 *
 * It arrives `Domain=.hadoku.me`, which a localhost page refuses, so the domain
 * is stripped. hadoku.me also sends a second `hadoku_session=; Max-Age=0`
 * clearing a legacy cookie; once the first is host-only too, that would delete
 * the session it follows, so it is dropped. (Same as hadoku-jobplatform's dev
 * server.)
 */
function onLocalhost(proxy: ProxyServer) {
  proxy.on('proxyRes', res => {
    const cookies = res.headers['set-cookie']
    if (!cookies) return
    res.headers['set-cookie'] = cookies
      .filter(c => !/;\s*Max-Age=0\b/i.test(c))
      .map(c => c.replace(/;\s*Domain=[^;]*/i, ''))
  })
}

const hadoku: ProxyOptions = {
  target: 'https://hadoku.me',
  changeOrigin: true,
  secure: true,
  configure: onLocalhost,
}

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    hmr: {
      overlay: true,
    },
    watch: {
      usePolling: false,
    },
    proxy: {
      // The hadoku jobplatform API and its sign-in, both on production. Every
      // request carries the hadoku_session cookie, exactly as on hadoku.me.
      '/jobplatform/api': hadoku,
      '/session': hadoku,
      // The local FastAPI backend, until each call has moved (docs/HADOKU_MERGE.md).
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
