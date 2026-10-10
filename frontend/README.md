# OkurmenKIDS — Кабинет тренера

A Vite + React 19 + TypeScript single-page app (client-side routing via `react-router-dom`'s `createBrowserRouter`, data fetching via TanStack Query). No SSR, no Next.js — the whole app is static assets plus one `index.html`.

## Local development

```bash
npm install
npm run dev
```

The dev server proxies `/api` and `/media` to `http://localhost:8000` (see `vite.config.ts`), so a local Django backend needs no CORS setup and `VITE_API_BASE_URL` can stay unset.

## Production build

```bash
npm run build   # tsc -b && vite build → dist/
npm run preview # serve the build locally to sanity-check it
```

## Deploying to Vercel

This is a pure client-side SPA, so two things matter beyond the default Vite build:

1. **Client-side routing needs a rewrite.** Vercel's static file server only serves files that physically exist in `dist/` — a deep link like `/app/groups/12` or an F5 refresh on any non-root route has no matching file, so without help it 404s before React Router ever loads. `vercel.json` fixes this with a catch-all rewrite to `/index.html`; real static assets (JS/CSS bundles, images) are still matched and served directly first, since Vercel checks the filesystem before applying rewrites.
2. **The API base URL must point at the real backend.** The frontend and the Django API are deployed separately (Vercel + Railway) — there is no built-in proxy in production. Set `VITE_API_BASE_URL` in the Vercel project's **Settings → Environment Variables** to the backend's absolute HTTPS URL, e.g. `https://<your-backend>.up.railway.app/api/v1`. Leaving it unset makes the app call its own Vercel domain and fail every request. See `.env.example` for details.

Vercel project settings for this app: framework **Vite**, build command `npm run build`, output directory `dist` (all also pinned in `vercel.json` so a dashboard misconfiguration can't silently break a deploy).

### After every deploy, verify

- Open a nested route directly (not by navigating from `/`) and refresh it — e.g. `/app/groups/1`.
- Log out and back in; open a link in a new tab.
- Open a URL that doesn't exist — should show the in-app 404, not Vercel's own error page.
- Check the Network tab: API calls should go to the production backend, never `localhost`.
- Temporarily block the API host (or check with the backend down) — the app should show a friendly "server unavailable" state, not a blank page or a forced logout.

## OkurmenKIDS Schedule (public schedule site)

A public, read-only schedule for parents, students, trainers and visitors —
**no login**. The same app, its own pages and header (no LMS navigation):

| URL | |
|---|---|
| `/schedule` | today (or the last view of this tab) |
| `/schedule/day?date=YYYY-MM-DD` | the day, a column per room, 08:00–24:00 |
| `/schedule/week?date=…` | the week, hours × days |

Filters live in the URL (`group`, `trainer`, `room` — opaque public keys —
and `q`), so a link opens the same view. Phones get a list by day.

It reads only the public API (GET only, no auth, rate-limited, cached):
`/api/v1/public/schedule/options/` and `/api/v1/public/schedule/?start=&end=&group=&trainer=&room=`
— a closed whitelist of fields: date, time, duration, group, course, subject,
trainer name + color, room, status. No students, contacts, attendance,
homework, scores, KPI, comments or database ids. The page re-reads it every
minute and on window focus; a lesson saved in the LMS clears the server cache.

Backend switches (env): `PUBLIC_SCHEDULE_SHOW_TRAINERS`, `PUBLIC_SCHEDULE_SHOW_ROOMS`
(default on), `PUBLIC_SCHEDULE_PAST_DAYS` (31), `PUBLIC_SCHEDULE_FUTURE_DAYS` (120),
`PUBLIC_SCHEDULE_CACHE_SECONDS` (60), `PUBLIC_SCHEDULE_RATE` (`1200/hour` per IP).

**Own domain** (e.g. `schedule.okurmenkids.com`): a second Vercel project on
this repo, root directory `frontend`, the same `vercel.json`, with
`VITE_APP_MODE=schedule` (so `/` opens the schedule) and the same
`VITE_API_BASE_URL`. On the backend add the domain to `SCHEDULE_SITE_ORIGINS`
(CORS). No second backend or database.
