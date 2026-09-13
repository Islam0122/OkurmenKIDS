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
