/* Okurmen Kids — service worker.
 *
 * Source file: pwa/sw.js. The build (vite.config.ts → pwaPlugin) prepends
 * `self.__PWA_BUILD__ = { version, precache, apiBase }` and emits it as
 * dist/sw.js. It is never registered by the dev server (src/pwa/register.ts).
 *
 * Strategies
 *   navigations             network-first → precached app shell → offline.html
 *   /assets/* (hashed)      cache-first   (immutable, file name changes per build)
 *   same-origin images      stale-while-revalidate (icons, logo)
 *   <api>/public/* GET      network-first → last good copy (public, no login)
 *   everything else         not touched: authenticated API calls, POST/PUT/…,
 *                           requests carrying Authorization, /media/, other origins
 *
 * Privacy: a request with an Authorization header is never intercepted, and
 * only the anonymous public endpoints are ever written to a cache — so no
 * token, no personal or student data can end up in Cache Storage.
 *
 * Updates: a new build installs next to the running one and waits. The page
 * shows «Доступна новая версия» and posts SKIP_WAITING; the page then reloads
 * on `controllerchange`. Navigations are network-first, so even a user who
 * never clicks it gets the newest index.html on the next online load.
 */
/* global self, caches, clients */

const BUILD = self.__PWA_BUILD__ || { version: 'dev', precache: [], apiBase: '/api/v1' }

const PREFIX = 'okurmen-'
const SHELL_CACHE = `${PREFIX}shell-${BUILD.version}`
const ASSET_CACHE = `${PREFIX}assets-v1`
const STATIC_CACHE = `${PREFIX}static-v1`
const PUBLIC_API_CACHE = `${PREFIX}public-api-v1`
const KNOWN_CACHES = [SHELL_CACHE, ASSET_CACHE, STATIC_CACHE, PUBLIC_API_CACHE]

const ASSET_LIMIT = 400
const STATIC_LIMIT = 60
const PUBLIC_API_LIMIT = 80
const PUBLIC_API_TIMEOUT_MS = 6000

const SHELL_URL = '/index.html'
const OFFLINE_URL = '/offline.html'

const API_BASE = new URL(BUILD.apiBase, self.location.origin).href.replace(/\/$/, '')
const PUBLIC_API_PREFIX = `${API_BASE}/public/`

// Paths on this origin that are not part of the SPA (dev proxy / backend).
const NON_SPA_PATHS = ['/api/', '/media/', '/admin/', '/static/']

const isHashedAsset = (url) => url.origin === self.location.origin && url.pathname.startsWith('/assets/')

// ---------------------------------------------------------------- lifecycle

self.addEventListener('install', (event) => {
  event.waitUntil(
    (async () => {
      const shell = await caches.open(SHELL_CACHE)
      const assets = await caches.open(ASSET_CACHE)
      await Promise.all(
        BUILD.precache.map(async (path) => {
          const request = new Request(path, { cache: 'reload' })
          const response = await fetch(request)
          if (!response.ok) throw new Error(`precache ${path}: ${response.status}`)
          await (isHashedAsset(new URL(path, self.location.origin)) ? assets : shell).put(path, response)
        }),
      )
      // The very first install has nothing to replace: take over at once.
      if (!self.registration.active) await self.skipWaiting()
    })(),
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const names = await caches.keys()
      await Promise.all(
        names.filter((name) => name.startsWith(PREFIX) && !KNOWN_CACHES.includes(name)).map((name) => caches.delete(name)),
      )
      if (self.registration.navigationPreload) {
        await self.registration.navigationPreload.enable().catch(() => {})
      }
      await self.clients.claim()
    })(),
  )
})

self.addEventListener('message', (event) => {
  const type = event.data && event.data.type
  if (type === 'SKIP_WAITING') {
    self.skipWaiting()
  } else if (type === 'CLEAR_USER_DATA') {
    // Logout: nothing private is cached, but drop the API copies anyway so a
    // shared device starts clean for the next person.
    event.waitUntil(caches.delete(PUBLIC_API_CACHE))
  } else if (type === 'GET_VERSION' && event.ports && event.ports[0]) {
    event.ports[0].postMessage({ version: BUILD.version })
  }
})

// ---------------------------------------------------------------- fetch

self.addEventListener('fetch', (event) => {
  const { request } = event
  if (request.method !== 'GET') return
  if (request.headers.has('authorization') || request.headers.has('range')) return

  const url = new URL(request.url)

  if (request.mode === 'navigate') {
    if (url.origin !== self.location.origin) return
    if (NON_SPA_PATHS.some((path) => url.pathname.startsWith(path))) return
    event.respondWith(handleNavigation(event))
    return
  }

  if (isHashedAsset(url)) {
    event.respondWith(cacheFirst(request, ASSET_CACHE, ASSET_LIMIT))
    return
  }

  if (url.href.startsWith(PUBLIC_API_PREFIX)) {
    event.respondWith(networkFirstPublicApi(event))
    return
  }

  if (
    url.origin === self.location.origin &&
    !NON_SPA_PATHS.some((path) => url.pathname.startsWith(path)) &&
    (request.destination === 'image' || request.destination === 'font' || request.destination === 'manifest')
  ) {
    event.respondWith(staleWhileRevalidate(event, STATIC_CACHE, STATIC_LIMIT))
  }
})

async function handleNavigation(event) {
  try {
    const preloaded = await event.preloadResponse
    if (preloaded) return preloaded
    return await fetch(event.request)
  } catch {
    // Offline (or DNS/TLS failure): boot the SPA from the precached shell.
    // The app then shows its own offline state — no data is faked.
    const shell = await caches.match(SHELL_URL, { cacheName: SHELL_CACHE, ignoreVary: true })
    if (shell) return shell
    const offline = await caches.match(OFFLINE_URL, MATCH)
    if (offline) return offline
    return new Response('Нет подключения к интернету.', {
      status: 503,
      headers: { 'Content-Type': 'text/plain; charset=utf-8' },
    })
  }
}

/** Safe to keep: a real file of the expected kind, not the SPA's index.html
 * fallback that the host returns (with 200) for a missing chunk. */
function isCacheableAsset(response) {
  if (!response || !response.ok || response.type === 'opaque') return false
  const type = response.headers.get('content-type') || ''
  return !type.includes('text/html')
}

// `ignoreVary`: hosts send «Vary: Origin», and module scripts are requested in
// CORS mode (with an Origin header) while the precache fetched them without
// one — the content of a hashed file is the same either way.
const MATCH = { ignoreVary: true }

async function cacheFirst(request, cacheName, limit) {
  const cache = await caches.open(cacheName)
  const cached = await cache.match(request, MATCH)
  if (cached) return cached
  const response = await fetch(request)
  if (isCacheableAsset(response)) {
    await cache.put(request, response.clone())
    trimCache(cacheName, limit)
  }
  return response
}

async function staleWhileRevalidate(event, cacheName, limit) {
  const cache = await caches.open(cacheName)
  const cached = await cache.match(event.request, MATCH)
  const network = fetch(event.request)
    .then(async (response) => {
      if (isCacheableAsset(response)) {
        await cache.put(event.request, response.clone())
        trimCache(cacheName, limit)
      }
      return response
    })
    .catch(() => undefined)
  if (cached) {
    event.waitUntil(network)
    return cached
  }
  const response = await network
  return response || Response.error()
}

function isPublicCacheable(response) {
  if (!response || !response.ok) return false
  const cacheControl = (response.headers.get('cache-control') || '').toLowerCase()
  if (cacheControl.includes('no-store') || cacheControl.includes('private')) return false
  return (response.headers.get('content-type') || '').includes('application/json')
}

async function networkFirstPublicApi(event) {
  const cache = await caches.open(PUBLIC_API_CACHE)
  try {
    const response = await fetchWithTimeout(event.request, PUBLIC_API_TIMEOUT_MS)
    if (isPublicCacheable(response)) {
      event.waitUntil(cache.put(event.request, response.clone()).then(() => trimCache(PUBLIC_API_CACHE, PUBLIC_API_LIMIT)))
    }
    return response
  } catch (error) {
    const cached = await cache.match(event.request, MATCH)
    if (!cached) throw error
    // Mark it so the UI can tell a saved copy from live data.
    const headers = new Headers(cached.headers)
    headers.set('X-Okurmen-Offline-Copy', '1')
    return new Response(cached.body, { status: cached.status, statusText: cached.statusText, headers })
  }
}

function fetchWithTimeout(request, ms) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('timeout')), ms)
    fetch(request).then(
      (response) => {
        clearTimeout(timer)
        resolve(response)
      },
      (error) => {
        clearTimeout(timer)
        reject(error)
      },
    )
  })
}

async function trimCache(cacheName, limit) {
  const cache = await caches.open(cacheName)
  const keys = await cache.keys()
  // Cache.keys() is in insertion order: drop the oldest first.
  for (let i = 0; i < keys.length - limit; i += 1) {
    await cache.delete(keys[i])
  }
}

// ---------------------------------------------------------------- push

self.addEventListener('push', (event) => {
  let data = {}
  try {
    data = event.data ? event.data.json() : {}
  } catch {
    data = { body: event.data ? event.data.text() : '' }
  }
  const title = data.title || 'Okurmen Kids'
  event.waitUntil(
    self.registration.showNotification(title, {
      body: data.body || '',
      icon: '/icons/icon-192.png',
      badge: '/icons/maskable-192.png',
      tag: data.tag || undefined,
      lang: 'ru',
      data: { url: safePath(data.url) },
    }),
  )
})

/** Only a path on this origin may be opened from a notification. */
function safePath(value) {
  if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//')) return '/'
  return value
}

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const target = new URL(safePath(event.notification.data && event.notification.data.url), self.location.origin).href
  event.waitUntil(
    (async () => {
      const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
      const existing = windows.find((client) => new URL(client.url).origin === self.location.origin)
      if (existing) {
        await existing.focus()
        if ('navigate' in existing && existing.url !== target) {
          return existing.navigate(target).catch(() => self.clients.openWindow(target))
        }
        return existing
      }
      return self.clients.openWindow(target)
    })(),
  )
})

self.addEventListener('pushsubscriptionchange', (event) => {
  // The worker holds no credentials, so it cannot re-register with the API
  // itself: tell open windows; the app re-syncs on its next start anyway
  // (src/pwa/push.ts → syncPushSubscription).
  event.waitUntil(
    self.clients.matchAll({ type: 'window' }).then((windows) => {
      windows.forEach((client) => client.postMessage({ type: 'PUSH_SUBSCRIPTION_CHANGED' }))
    }),
  )
})
