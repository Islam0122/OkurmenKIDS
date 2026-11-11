# Okurmen Kids Digital — public website

An independent React application, the academy's public website. It is a
separate app from the LMS frontend (`../frontend`), with its own build and its
own Vercel project. It reads only the **public, unauthenticated** API of the
existing Django backend (`../backend`), so visitors never sign in. All
content comes from the backend.

```bash
cp .env.example .env.local       # VITE_API_URL, VITE_SITE_URL
npm install
npm run dev                      # http://localhost:5173
npm run build                    # dist/ + dist/sitemap.xml
npm test                         # vitest
npm run lint && npm run typecheck
node scripts/responsive-audit.cjs   # responsive audit, see the header of the script
```

| Variable | |
|---|---|
| `VITE_API_URL` | **required** — the Django backend, e.g. `https://okurmenkids.up.railway.app` |
| `VITE_SITE_URL` | this site's public address — canonical URLs, hreflang, Open Graph, sitemap |
| `VITE_MEDIA_URL` | where `/media/...` is served from (default: `VITE_API_URL`) |
| `VITE_USE_MOCKS` | `true` = clearly-labelled demo data for UI work only. Never in production |

## Pages

| Route | Data |
|---|---|
| `/` | `GET /api/v1/public/site/home/` (one request: hero, stats, blocks in CMS order, featured content) |
| `/about` | settings (story, mission, vision, stats) + photos from published events / achievements |
| `/courses`, `/courses/:slug` | `public/site/courses/` — course pages linked to `academy.Course`; detail shows published student projects of the course's category |
| `/projects`, `/projects/:slug` | `public/projects/` — published by trainers in the LMS (apps.projects); the slug is the opaque project key |
| `/achievements`, `/achievements/:slug` | `public/site/achievements/` |
| `/news`, `/news/:slug` | `public/news/` (apps.academy_news) |
| `/events`, `/events/:slug` | `public/site/events/` + `POST …/register/` while registration is open |
| `/team` | `public/site/team/` — only approved public profiles; photo only with consent |
| `/testimonials` | `public/site/testimonials/` — only with the author's consent |
| `/contacts` | settings (contacts, branches with Google Maps) + enrollment form |
| `/preview/:token` | a draft opened from the LMS editor (signed link, `noindex`) |

Every page also exists at `/ky/...` (Kyrgyz) and `/en/...` (English).

## Architecture

```
src/
  app/          config (env, nav), providers (TanStack Query, motion), router (language branches, lazy pages)
  i18n/         provider + ru/ky/en dictionaries (TypeScript enforces the same keys in all three)
  services/     api/client.ts (axios, VITE_API_URL, error mapping) · endpoints/ (one function per endpoint)
  hooks/        queries.ts (TanStack Query hooks, language in every key) · useListParams (filters in the URL)
  types/        api.ts — exactly what the backend returns
  components/   layout (Header, Footer, SiteLayout, ArticleLayout) · navigation · sections · cards · forms · shared
  features/     enrollment (form, dialog, zod schema, UTM) · events (registration) · content (safe markup renderer, video, gallery)
  pages/        one folder per section
  mocks/        demo fixtures (VITE_USE_MOCKS only; lazy-loaded, labelled «Демо» everywhere)
```

* **Design tokens** live in `src/styles/index.css` (`@theme`): golden yellow
  `#F5B51B` for actions, deep purple `#29136D` for type, white backgrounds,
  light purple `#F4EEFF` and soft gray `#F8F8FC` surfaces. The fonts are
  Nunito (headings) and Inter (text), both with Cyrillic and Kyrgyz glyphs.
  Icons come from Lucide. The logo is the original, unchanged.
* **Every data view has a state**: loading skeletons, empty states, error states
  with retry, and a 404 for unpublished or unknown slugs.
* **Rich content** (news, events, achievements, courses) is plain text in a
  small safe markup that the CMS editor writes. `features/content/markup.ts`
  parses it, and the app never injects HTML from the API.
* **Forms**: react-hook-form + zod (same rules as the backend), a honeypot
  field, the button locked while sending, server field errors mapped to the
  matching inputs, rate-limit and network messages. The server merges repeat
  leads from the same phone within 24 h. UTM parameters from the landing URL
  are attached to the lead.
* **Mock data** (`VITE_USE_MOCKS=true`): fictional fixtures with no images,
  and a banner on every page. Production builds never call them.

## SEO and performance

* Language-prefixed URLs, with `hreflang` alternates and a canonical URL on
  every page. `<Seo>` sets the title, description, Open Graph / Twitter tags
  and JSON-LD (EducationalOrganization, Course, Event, NewsArticle,
  CreativeWork, BreadcrumbList, ItemList).
* `scripts/generate-sitemap.mjs` runs after `vite build`. It writes
  `dist/sitemap.xml` with every page in all three languages, taking content
  URLs from `GET /api/v1/public/site/sitemap/`. If the API is unreachable at
  build time, it still writes the static pages.
* `public/robots.txt` keeps `/preview/` out of the index.
* **Rendering strategy:** the app is a client-rendered SPA. Google renders
  JavaScript, so it indexes the dynamic content. Crawlers that don't run JS
  (link previews in Telegram, WhatsApp, Facebook, X and others) get the real
  title, description and image for courses, events, news, achievements and
  projects from `middleware.ts`, a Vercel Routing Middleware that reads the
  same API. If full prerendering is needed later, the page components already
  get all their data from typed loaders, so a move to SSR or SSG (e.g. a
  React Router framework-mode build) only changes the build, not the
  components.
* Performance: pages are code-split per route, and the enrollment form loads
  on first open. Vendor chunks are cached for a year (`vercel.json`). Images
  come from the backend's WebP thumb / large copies via `srcset`, lazy-loaded,
  with their dimensions reserved. Videos load only on click
  (youtube-nocookie). Animations respect `prefers-reduced-motion`.
* Accessibility: skip link, landmarks, focus-trapped dialogs, visible focus
  rings, labelled form fields with `aria-invalid` / `role="alert"` errors,
  touch targets ≥ 44 px.

## Deployment (Vercel)

1. New Vercel project from this repository, **Root Directory**
   `okurmen-public-website` (framework: Vite; `vercel.json` sets everything else).
2. Environment variables: `VITE_API_URL`, `VITE_SITE_URL` (and
   `VITE_MEDIA_URL` if media is served from a CDN).
3. Domain: add it in Vercel → Domains (e.g. `okurmenkids.kg` + `www`).
4. Backend (Railway) env:
   * `PUBLIC_WEBSITE_ORIGINS=https://okurmenkids.kg,https://www.okurmenkids.kg` (CORS)
   * `PUBLIC_WEBSITE_URL=https://okurmenkids.kg` (preview links from the CMS)
   * optional `WEBSITE_REQUIRE_APPROVAL=true` (marketing → director approval)
5. Check: `/`, a course page, the enrollment form (a lead appears in LMS →
   Маркетинг → Сайт → Заявки), `/sitemap.xml`, and a Telegram link preview of a
   news article.

The integration with the LMS (endpoints, roles, what was added to the backend)
is described in `../backend/docs/website.md`.
