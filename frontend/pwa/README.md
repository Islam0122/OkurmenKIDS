# Okurmen Kids — PWA

The LMS frontend is an installable Progressive Web App. Nothing here changes
routing, authentication or the API; it adds an app identity, a service worker,
an offline experience and (optionally) push notifications.

## Files

| Path | Role |
| --- | --- |
| `public/manifest.webmanifest` | Name «Okurmen Kids» / «Okurmen», icons, standalone, theme `#2f8f5b`, background `#f7f9f7`, shortcuts |
| `public/icons/*` | 192/512 «any», 192/512 «maskable», 180 Apple touch icon |
| `public/splash/*` | iOS/iPadOS launch screens (linked from `index.html`) |
| `public/offline.html` | Self-contained last-resort offline page |
| `pwa/sw.js` | Service worker source |
| `pwa/vitePlugin.ts` | Build step: emits `dist/sw.js` with version + precache list |
| `pwa/badge.svg`, `pwa/generate-icons.mjs` | Icon art and generator (`node pwa/generate-icons.mjs`, needs Playwright) |
| `pwa/verify.mjs` | End-to-end checks in Chromium (see Testing) |
| `src/pwa/*` | Runtime: platform detection, state store, registration/updates, install, push |
| `src/components/pwa/*` | UI: install card, «Приложение» dialog/card, update banner, connection status |

## Service worker strategies

| Request | Strategy |
| --- | --- |
| Navigations (SPA routes) | network-first → precached `index.html` → `offline.html` |
| `/assets/*` (content-hashed) | cache-first, kept across deploys, max 400 entries |
| Same-origin images/fonts/manifest | stale-while-revalidate |
| `GET <API>/public/*` (news, schedule, leaderboard, projects, careers) | network-first (6 s) → last good copy, marked `X-Okurmen-Offline-Copy: 1` |
| Anything with an `Authorization` header, non-GET, `/media/`, other origins | **not intercepted, never cached** |

Precached on install: `index.html`, `offline.html`, manifest, icon, the entry
JS/CSS with its fonts and logo. Route chunks are cached the first time a
section is opened, so the whole LMS is not downloaded up front.

**Privacy.** Tokens live only in `localStorage` (unchanged). The worker never
sees an authenticated response body, so Cache Storage holds no tokens and no
personal or student data. On logout the app unsubscribes this device from push
and tells the worker to drop its API cache.

**Updates.** The worker version is a hash of all emitted file names, so every
deploy produces a new worker. It installs in the background and waits; the app
shows «Доступна новая версия → Обновить» (no forced reload that could lose a
half-filled form). HTML is network-first, so any fresh online start already
runs the newest build. Old shell caches are deleted on activation; the app
checks for updates hourly and when it returns to the foreground.

**Kill switch.** Build with `VITE_PWA_DISABLED=true`. The deploy then ships a
worker that deletes the `okurmen-*` caches, unregisters itself and reloads open
tabs. The site keeps working as a plain website.

## Offline behaviour

* A connection pill says plainly that data on screen is not updating and that
  changes will not be saved. It confirms when the connection returns, and
  React Query refetches.
* Mutations use `networkMode: 'always'`: offline they fail at once with
  «Нет подключения к интернету — данные не отправлены…». Forms keep their
  input, and nothing is silently queued or reported as saved.
* Signed-in users who cannot reach the API see the existing «Сервер недоступен»
  screen (the session is kept). It now shows connection status and retries
  automatically when the network returns.
* A section never opened on this device shows «Раздел недоступен без
  интернета» and reopens by itself when the connection is back.

## Install UX

* Chromium (Chrome/Edge on Windows, macOS, Android): `beforeinstallprompt` is
  captured before React starts. The app shows its own card at most once per
  visit: only after 30 s **and** a real interaction, never on `/login` or TV
  dashboards (`?tv=`, `/monthly-performance`). «Не сейчас» snoozes it for 21
  days; after 3 dismissals it never appears on its own again.
* iOS/iPadOS Safari: the same card leads to step-by-step «Поделиться → На экран
  „Домой“» instructions. macOS Safari 17+ gets «Добавить в Dock». In-app
  browsers are told to open the real browser.
* Always available: the download icon in every cabinet header (only while
  installation is possible), the link at the bottom of the notifications panel,
  and «Приложение и уведомления» on the profile pages.
* Once installed (standalone), every prompt disappears.

## Push notifications

The browser asks for permission **only** when the user turns on the switch in
«Приложение и уведомления». The public VAPID key comes from
`GET /api/v1/push/config/`; when the backend has no keys the section says push
is not enabled yet. Categories: tasks, reports, KPI/issues. See
`backend/docs/push.md`.

## Installing (users)

* **Windows / macOS — Chrome or Edge:** the install icon in the address bar, or
  the app's own «Установить» button. Okurmen Kids then opens in its own window
  and appears in Start / Launchpad / Dock.
* **macOS — Safari 17+:** File → «Добавить в Dock».
* **Android — Chrome:** «Установить» on the card, or ⋮ → «Установить приложение».
* **iPhone / iPad — Safari:** Поделиться → «На экран „Домой“» → «Добавить».
  Push works in the installed app on iOS/iPadOS 16.4+.

## Deployment

HTTPS is required (except on `localhost`). `vercel.json` serves `sw.js` and
`index.html` with `no-cache`, the manifest with `application/manifest+json`,
and hashed assets as immutable. The worker must stay at `/sw.js` (scope `/`).
Other hosts need the same headers. Dev (`npm run dev`) never registers a
worker.

## Testing

```bash
npm test                                   # unit tests (incl. src/pwa, components/pwa)
npm run build && npx vite preview --port 4173 &
node pwa/verify.mjs                        # 30 end-to-end checks in Chromium
```

To run a Lighthouse PWA audit, use Lighthouse ≤ 11 (v12 removed the PWA category).
