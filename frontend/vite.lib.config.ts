import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

/**
 * The bundle hadoku.me mounts at /jobpulse/ (src/entry.tsx: mount/unmount).
 *
 * External, because hadoku.me's import map provides one shared copy of each
 * to every app on the page: React and the theme context match on module
 * identity, and the logger keeps one cache. A second copy inlined here would
 * be a different module the platform never talks to. hadoku_site's
 * check:mf-externals enforces this list.
 */
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist-lib',
    copyPublicDir: false,
    lib: {
      entry: 'src/entry.tsx',
      formats: ['es'],
      fileName: () => 'index.js',
      cssFileName: 'style',
    },
    rollupOptions: {
      external: [
        'react',
        'react-dom',
        'react-dom/client',
        'react/jsx-runtime',
        '@wolffm/themes',
        '@wolffm/task-ui-components',
        '@wolffm/logger/client',
      ],
    },
  },
})
