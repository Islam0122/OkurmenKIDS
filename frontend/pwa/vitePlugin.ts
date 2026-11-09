import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'

import type { Plugin } from 'vite'

/** Files from public/ that make up the offline app shell besides the JS/CSS. */
const STATIC_SHELL = ['/index.html', '/offline.html', '/manifest.webmanifest', '/icons/icon-192.png', '/logo.png']

/** Emitted instead of the real worker when VITE_PWA_DISABLED=true: it takes
 * over from any previously installed worker, deletes its caches and
 * unregisters itself — the emergency off switch for a bad release. */
const KILL_SWITCH = `self.addEventListener('install', () => self.skipWaiting())
self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys()
    await Promise.all(names.filter((n) => n.startsWith('okurmen-')).map((n) => caches.delete(n)))
    await self.registration.unregister()
    const windows = await self.clients.matchAll({ type: 'window' })
    windows.forEach((client) => client.navigate(client.url))
  })())
})
`

interface PwaPluginOptions {
  apiBase: string
  disabled: boolean
}

/**
 * Builds dist/sw.js from pwa/sw.js (build only — the dev server never
 * registers a worker). Injects:
 *   version  — a hash of every emitted file name; Vite file names are content
 *              hashes, so any code change yields a new worker → update prompt.
 *   precache — index.html, offline page, manifest, icon, the entry chunk with
 *              its CSS, fonts, images and statically imported chunks. Route
 *              chunks are cached on first use instead of downloading the
 *              whole LMS up front.
 *   apiBase  — VITE_API_BASE_URL, so the worker can recognise the public API.
 */
export function pwaPlugin({ apiBase, disabled }: PwaPluginOptions): Plugin {
  return {
    name: 'okurmen-pwa-service-worker',
    apply: 'build',
    generateBundle(_options, bundle) {
      if (disabled) {
        this.emitFile({ type: 'asset', fileName: 'sw.js', source: KILL_SWITCH })
        return
      }

      const shell = new Set<string>()
      const visit = (fileName: string) => {
        const chunk = bundle[fileName]
        if (!chunk || shell.has(`/${fileName}`)) return
        shell.add(`/${fileName}`)
        if (chunk.type === 'chunk') {
          chunk.viteMetadata?.importedCss.forEach((css) => shell.add(`/${css}`))
          // Images and fonts the shell itself uses (logo, Manrope) — so the
          // offline login screen looks exactly like the online one.
          chunk.viteMetadata?.importedAssets.forEach((asset) => {
            // Font subsets for scripts the LMS never shows are fetched on demand only.
            if (!/-(greek|vietnamese)-/.test(asset)) shell.add(`/${asset}`)
          })
          chunk.imports.forEach(visit)
        }
      }
      Object.values(bundle)
        .filter((item) => item.type === 'chunk' && item.isEntry)
        .forEach((chunk) => visit(chunk.fileName))

      const precache = [...STATIC_SHELL, ...[...shell].sort()]
      const hash = createHash('sha256')
        .update(Object.keys(bundle).sort().join('\n'))
        .update(readFileSync(fileURLToPath(new URL('./sw.js', import.meta.url))))
      // public/ files are not in the bundle: hash the precached ones too, so a
      // new icon or offline page alone still ships a new worker (fresh copies).
      STATIC_SHELL.filter((path) => path !== '/index.html').forEach((path) =>
        hash.update(readFileSync(fileURLToPath(new URL(`../public${path}`, import.meta.url)))),
      )
      const version = hash.digest('hex').slice(0, 12)

      const header = `self.__PWA_BUILD__ = ${JSON.stringify({ version, precache, apiBase })};\n`
      const source = readFileSync(fileURLToPath(new URL('./sw.js', import.meta.url)), 'utf8')
      this.emitFile({ type: 'asset', fileName: 'sw.js', source: header + source })
    },
  }
}
