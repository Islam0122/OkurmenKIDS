# Okurmen Kids — PWA

The LMS frontend is an installable Progressive Web App. Nothing here changes
routing, authentication or the API; it adds an app identity, a service worker,
an offline experience and (optionally) push notifications.

## Files

| Path | Role |
| --- | --- |
| `public/manifest.webmanifest` | Name «Okurmen Kids» / «Okurmen», `start_url /portal`, `scope /`, `id /`, standalone, theme and background `#ffffff`, shortcuts |
| `public/icons/*` | 192/512 «any», 192/512 «maskable», 180 Apple touch icon — one design: pure white opaque square with the Okurmen Kids logo centred (gold ring `#F5B52B`, violet glasses and «KIDS» `#291078`, gold «ОКУРМЭН»); ring Ø 78% of the icon, inside the maskable safe zone |
| `public/splash/*` | iOS/iPadOS launch screens (linked from `index.html`) |
| `public/offline.html` | Self-contained last-resort offline page |
| `pwa/sw.js` | Service worker source |
| `pwa/vitePlugin.ts` | Build step: emits `dist/sw.js` with version + precache list |
| `pwa/logo.svg`, `pwa/generate-icons.mjs` | Logo art and generator (`node pwa/generate-icons.mjs`, needs Playwright; centres on the actual ink) |
| `pwa/verify.mjs` | End-to-end checks in Chromium (see Testing) |
| `src/pwa/*` | Runtime: platform detection, state store, registration/updates, install, push |
| `src/components/pwa/*` | UI: install card, «Приложение» dialog/card, update banner, connection status |

## Launch flow

```
installed app → /portal (public portal) → LMS card
   signed in  → /app/dashboard → the role's own cabinet (AppLayout / homeFor)
   guest      → /login (remembers /app/dashboard) → login → role dashboard
«Выйти»       → /portal
```

* `start_url` is `/portal` in every build. `id` stays `/`, so apps installed
  before this change update in place (new start page, no second icon).
* The portal never redirects a signed-in user; the LMS card decides.
* An explicit logout sets `signedOut`, and `ProtectedRoute` then sends the user
  to `/portal`. An **expired** session still goes to `/login` with the page to
  return to, so a deep link or a push notification link (`/tasks/12`) lands
  where it pointed after signing in again.
* Deep links and refreshes work on every route: the SPA rewrite on Vercel, and
  network-first navigations with the precached shell in the service worker.
* Theme colour is white in the manifest **and** in `<meta name="theme-color">`.
  Chrome lets the page meta override the manifest for the app's title bar.

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

**Native installation (Chromium: Chrome / Edge on Windows, macOS, Android).**
`beforeinstallprompt` is captured before React starts (`src/pwa/register.ts`):
`preventDefault()`, event saved. Every install button calls the saved event's
`prompt()` directly from the click (`promptInstall()` in `src/pwa/install.ts`),
so Chrome shows its **real** «Install app» dialog. There is no imitation and no
modal in between. `userChoice` is handled (accepted → installed; dismissed → the
button stays). `appinstalled` marks the app installed.

**Portal header (`/portal`, news, projects, programs —
`src/features/portal/InstallButton.tsx`):** a compact white button with a
download icon (label from `lg`, icon only below), in RU / KG / EN.

| State | Button | Click |
| --- | --- | --- |
| Chromium offers install | «Установить приложение» | native Chrome/Edge dialog |
| iOS / iPadOS Safari (no install API) | «Установить приложение» | panel: Поделиться → На экран «Домой» → Добавить |
| macOS Safari 17+ | «Установить приложение» | panel: Файл / Поделиться → Добавить в Dock |
| Chromium, no prompt (yet) | «Установить приложение» | panel: browser menu → Install |
| In-app browser (Instagram, Telegram…) | «Установить приложение» | panel: open in Safari/Chrome first |
| Unsupported (e.g. Firefox desktop) | «Установить приложение» | panel: which browsers can install |
| Installed (browser tab) | «Открыть приложение» | panel: where to open it (Start menu / Dock / Home Screen; Chrome's «Open in app» icon) |
| Running as the app (standalone) | hidden | — |

«Installed» in a tab comes from `appinstalled` / an accepted prompt (stored),
and from `navigator.getInstalledRelatedApps()` (Chromium; the manifest lists
itself in `related_applications`). A new `beforeinstallprompt` means the app
was uninstalled, and the note is cleared. Browsers have no API that lets a page
launch an installed PWA, so «Открыть приложение» says where to open it rather
than opening a tab that looks like the app.

**Cabinet headers:** the download icon calls the native prompt the same way
(Apple browsers: the «Приложение» dialog with the manual steps).

**Floating offer:** a calm card, at most once per visit, after 30 s **and** a
real interaction. It never appears on `/login`, TV dashboards, or a page that
already shows a header install button. «Не сейчас» snoozes it for 21 days;
after 3 dismissals it never appears on its own again. Once installed, every
prompt disappears.

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
# Real Chrome install flow (headed Chromium, normal profile — Chrome never
# fires beforeinstallprompt headless or in Incognito):
xvfb-run -a -s "-screen 0 1280x800x24" node pwa/verify-native-install.mjs
```

To run a Lighthouse PWA audit, use Lighthouse ≤ 11 (v12 removed the PWA category).
