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

## OkurmenKIDS — Общая статистика (academy statistics site)

A separate site, **not an LMS cabinet page** (no LMS sidebar, own layout):
`/monthly-performance` — daily attendance, homework completion, active groups
and active students for a month, with four charts and a TV mode (`?tv=1`,
1920×1080, auto-refresh every 5 minutes, Esc to exit). It reads only
`/api/v1/monthly-performance/*` (aggregates only, no personal data).

Access: a staff login (the same as the LMS) or a read-only dashboard key for
an office TV — `/monthly-performance?key=<key>&tv=1` (the key is remembered in
the browser and removed from the address bar). Keys are created with
`python manage.py create_dashboard_key "Телевизор в офисе"` or in Django admin;
see `backend/docs/performance.md`.

**Own domain** (e.g. `stats.okurmenkids.com`): a Vercel project on this repo,
root directory `frontend`, with `VITE_APP_MODE=statistics` (so `/` opens the
statistics) and the same `VITE_API_BASE_URL`; add the domain to
`STATISTICS_SITE_ORIGINS` on the backend. The existing `vercel.json` rewrite
already serves `/monthly-performance` on a direct page refresh.

## OkurmenKIDS Leaderboard (public leaderboard site)

A public, read-only leaderboard — **no login**: `/leaderboard` (top students)
and `/leaderboard/groups` (top groups), each for a year, a month or a week
(`?period=month&year=2026&month=10`, `?period=week&week=2026-10-12`). It reads
only `/api/v1/public/leaderboard/*` (see `backend/docs/leaderboard.md` for the
XP rules and the group methodology).

**Own domain** (e.g. `leaderboard.okurmenkids.com`): a Vercel project on this
repo, root directory `frontend`, with `VITE_APP_MODE=leaderboard` and the same
`VITE_API_BASE_URL`; add the domain to `LEADERBOARD_SITE_ORIGINS` on the backend.

## OKURMENKIDS DIGITAL (application launcher)

One white screen that launches every academy application: `/portal`
(and `/portal/programs` for «Our Programs»). No login is needed to see it.
The header has the language switch (RU / KG / EN, remembered in the browser),
About and Help dialogs, and Login — or the signed-in user with a log-out
button. The footer opens About, Help and Privacy. Texts in all three
languages live in `src/features/portal/i18n.tsx`.

| Card | Default destination |
|---|---|
| LMS | `/app/dashboard` (sign-in; a signed-in employee lands in their own cabinet) |
| Training & Exams | `https://training-portal-theta.vercel.app/` |
| Schedule | `/schedule` |
| Leaderboard | `/leaderboard` |
| News | `/app/news` (sign-in; hidden for roles without the LMS) |
| Monthly Performance | `https://okurmen-kids-drab.vercel.app/monthly-performance` |
| Our Programs | `/portal/programs` |

Under the grid, **More from Okurmen** has four compact services:

| Service | Destination |
|---|---|
| Student Projects | `/projects` — the public gallery (below), for everyone |
| Our Feedback | no public address exists (surveys are answered by per-survey links) — assistant and admin open `/assistant/surveys`; others see «Soon» until `VITE_PORTAL_FEEDBACK_URL` is set |
| Our Website | «Soon» until `VITE_PORTAL_WEBSITE_URL` is set — the official site URL is not configured anywhere in the project |
| Our Careers | `/careers` (the careers site of this build), in a new tab |

Every destination and icon lives in `src/features/portal/config.ts`.
Each can be overridden at build time — an app route of this build or an
absolute URL of another deployment: `VITE_PORTAL_LMS_URL`,
`VITE_PORTAL_TRAINING_URL`, `VITE_PORTAL_SCHEDULE_URL`,
`VITE_PORTAL_LEADERBOARD_URL`, `VITE_PORTAL_NEWS_URL`,
`VITE_PORTAL_PERFORMANCE_URL`, `VITE_PORTAL_PROGRAMS_URL`, `VITE_PORTAL_PROJECTS_URL`,
`VITE_PORTAL_FEEDBACK_URL`, `VITE_PORTAL_WEBSITE_URL`, `VITE_PORTAL_CAREERS_URL`. Absolute URLs open
in a new tab; keys `1`–`7` open the cards.

**Own domain** (e.g. `digital.okurmenkids.com`): a Vercel project on this repo,
root directory `frontend`, with `VITE_APP_MODE=portal` (so `/` opens the
launcher) and the same `VITE_API_BASE_URL`; add the domain to
`PORTAL_SITE_ORIGINS` on the backend. Schedule, Leaderboard, Programs, the LMS
and News are served by that same build. On the existing LMS deployment the
launcher is already available at `/portal` with no extra setup.

## Student Projects (public gallery)

`/projects` and `/projects/<key>` — a public, read-only gallery of the
projects trainers have **published** in the LMS. **No login**, never a
redirect to `/login`. Search, technology filters (HTML/CSS, JavaScript,
React, Python, Other — `?q=` and `?category=` stay in the URL), «Show more»
paging, a details page with screenshots, a full-size viewer and the demo link,
and loading / empty / no-results / error / not-found states.

Projects are still created, edited and published only in the LMS
(`/trainer/projects`); moving a project back to «Черновик» removes it from
the gallery at once.

It reads only `GET /api/v1/public/projects/` and `GET /api/v1/public/projects/<key>/`
(no auth, rate-limited, cached) — a closed whitelist of fields: title,
descriptions, technologies, date, demo link, images, the group name and the
student as «First name + initial» (no name at all when the student's
«Показывать в публичном рейтинге» switch is off). Never: trainer comments,
ratings, GitHub/Figma links, contacts, database ids. The trainer's name
appears only with `PUBLIC_PROJECTS_SHOW_TRAINER=true` on the backend (see
`backend/docs/public_projects.md`).
