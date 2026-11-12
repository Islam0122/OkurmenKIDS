# Public website: www ↔ apex redirect loop

> **Status:** the code fix is in this branch and was checked against a local
> production build. **Production isn't fixed until the branch is deployed AND the
> Vercel Domains setting below is changed.** Neither can be checked from the build
> sandbox, which has no access to `okurmenkids.com`.

## 1. Root cause

There were **two redirect rules for the same project, pointing in opposite
directions**:

| Source | Rule | Status |
|---|---|---|
| `okurmen-public-website/vercel.json` (commit `e48a75a`, merged in PR #317) | `www.okurmenkids.com/*` → `https://okurmenkids.com/*` | **308** (`"permanent": true`) |
| Vercel → Project → Settings → **Domains** | `okurmenkids.com` → `www.okurmenkids.com` (Vercel's suggested default when an apex domain is added) | **307** |

Nothing in the code can send a 307. The only redirect in the repo is the 308
above. There's no `window.location` redirect, no `<base href>`, Vite's `base` is
`/` (assets are root-relative `/assets/…`), there's no service worker in this app,
and `middleware.ts` only rewrites HTML for social bots and excludes every path
with a file extension. So the `307 Temporary Redirect` on
`https://okurmenkids.com/site.webmanifest` comes from the Domains setting.

What happened for each error:

1. `GET www/logo.png` → 308 → `okurmenkids.com/logo.png` → 307 →
   `www/logo.png` → … → **`ERR_TOO_MANY_REDIRECTS`**.
2. The manifest and lazy JS chunks (`EventsPage-*.js`) are requested from a
   page on `www`. The 308 sends them to `okurmenkids.com`, a **different
   origin**. Module scripts and `<link rel=manifest>` are fetched in CORS
   mode, so once a request is redirected cross-origin the browser needs
   `Access-Control-Allow-Origin` on the next response. Vercel's 307 redirect
   response has none, so the browser reports **"blocked by CORS policy"**.

CORS was a symptom, not the cause. Adding `Access-Control-Allow-Origin` would
hide the loop without fixing it, so it wasn't done.

## 2. Code changes (`okurmen-public-website/`)

| File | Change | Why |
|---|---|---|
| `vercel.json` | **Removed** the `redirects` block (www → apex) | This is one half of the loop. The www redirect belongs in the Vercel Domains setting only, so there is one source of truth. Removing it also stops the loop straight away, even before the dashboard is changed (the site would then be served on www until step 3 below). |
| `vercel.json` | `/site.webmanifest` header: `Content-Type: application/manifest+json; charset=utf-8`, `Cache-Control: public, max-age=0, must-revalidate` | Explicit, correct type; browsers re-check it after this incident |
| `public/site.webmanifest` | Added `"id": "/"`, `"scope": "/"` (`start_url` stays `/`) | Relative, origin-independent identity and scope. Still valid JSON; icon `/logo.png` exists (PNG, 236×213) |
| `public/favicon.ico` (new) | 16/32/48 px ICO made from `logo.png` (padded to square) | `/favicon.ico` used to fall through the SPA rewrite and return `index.html` (HTML) |
| `index.html` | `<link rel="icon" href="/favicon.ico" sizes="any">`; `og:image` → `https://okurmenkids.com/og-image.png` | A relative `og:image` is ignored by link-preview crawlers. Everything else stays root-relative |
| `../PRODUCTION_DOMAIN_MIGRATION.md` | www redirect: Vercel Domains only, no `vercel.json` rule | Prevents the same mistake again |

Unchanged on purpose: routes, React code, `middleware.ts`, the SPA rewrite,
`robots.txt`, `sitemap.xml`, and asset cache headers.

## 3. Required Vercel dashboard change (manual)

Go to **Vercel → project `okurmen-public-website` → Settings → Domains**:

1. **`okurmenkids.com`** → Edit → **Connect to an environment: Production**.
   Make sure **no redirect** is set on it. Today it redirects to www with 307.
2. **`www.okurmenkids.com`** → Edit → **Redirect to `okurmenkids.com`**, status
   **308 Permanent Redirect**.
3. Optional: in the domain list, use **⋯ → Set as primary** on `okurmenkids.com`.
4. Check the other projects (LMS, admin) don't also have
   `okurmenkids.com` or `www.okurmenkids.com` attached. A domain can belong to
   only one project.
5. At the DNS provider, make sure there's no registrar-level **URL forwarding**
   for `@` or `www`. It would add a third redirect source.

Order: deploy the branch first (that stops the loop), then change the Domains
setting. If you change the dashboard first, the old `vercel.json` rule and the
new setting agree (www → apex), which also works.

## 4. Build verification (local, not production)

Production build with `VITE_SITE_URL=https://okurmenkids.com`. `dist/` was served
by a small server that applies `vercel.json` the way Vercel does (headers, then
the filesystem, then the `/(.*)` → `/index.html` rewrite):

```
200  redirects=0  text/html                              /
200  redirects=0  application/manifest+json; charset=utf-8  /site.webmanifest
200  redirects=0  image/png                              /logo.png
200  redirects=0  image/x-icon                           /favicon.ico
200  redirects=0  image/png                              /og-image.png
200  redirects=0  text/plain                             /robots.txt
200  redirects=0  application/xml                        /sitemap.xml
200  redirects=0  text/html                              /en/team   /ky/news   /events
200  redirects=0  application/javascript                 /assets/index-*.js, react-*.js, query-*.js
```

Headless Chromium loaded `/`, `/en/team`, `/events` and `/ky/contacts` directly,
then **reloaded** each one. Every route rendered its own `<h1>` after the reload.
The manifest was fetched with 200, `redirected: false`. There were **0
redirects, 0 failed same-origin requests, 0 CORS errors**, and no console errors
other than the API calls the sandbox blocks. Unit tests: 14/14 passed. Lint:
0 errors.

This proves the build and `vercel.json` are correct. It doesn't prove the domain
setup, which only exists in Vercel.

## 5. Production verification (run after deploy + dashboard change)

```bash
curl -sIL https://www.okurmenkids.com/ | grep -iE '^(HTTP|location)'
```
Expected: exactly **one** `HTTP/2 308` with `location: https://okurmenkids.com/`, then `HTTP/2 200`.

```bash
for p in / /site.webmanifest /logo.png /favicon.ico /robots.txt /sitemap.xml /en/team; do curl -s -o /dev/null -w "%{http_code} redirects=%{num_redirects} %{content_type} $p\n" "https://okurmenkids.com$p"; done
```
Expected: `200 redirects=0` for every line; manifest `application/manifest+json`, sitemap XML, `/en/team` `text/html`.

```bash
curl -sI https://www.okurmenkids.com/logo.png | grep -iE '^(HTTP|location)'
```
Expected: `308` with `location: https://okurmenkids.com/logo.png`, a single hop, no loop.

```bash
curl -sI https://okurmenkids.com/ | grep -iE '^(HTTP|location)'
```
Expected: `200` with **no** `location` header. Any 307 here means step 3.1 wasn't applied.

In the browser, open `https://okurmenkids.com/events` and use DevTools →
Network with "Disable cache" on. All `/assets/*` requests should be 200 from
`okurmenkids.com`, with no redirects and no CORS errors in the Console. Reload
`/en/team`: it should render the page, not a 404. Under Application → Manifest
there should be no errors.

**Stale browser state:** browsers cache 308s (and HSTS) for a long time. If
a tester still sees the loop after the fix, clear site data for both hosts
(DevTools → Application → Storage → Clear site data) or use a private window.
This site has no service worker, so there's no SW cache to purge. (The LMS
`frontend/` has one, but it's a different origin and isn't involved.)

## 6. Remaining deployment actions

- [ ] Merge and deploy this branch to Vercel Production.
- [ ] Apply the Domains change in §3 (apex → Production with no redirect; www → 308 → apex).
- [ ] Set `VITE_SITE_URL=https://okurmenkids.com` in the project's Production
      env, or canonical and hreflang URLs fall back to whichever host served the
      page. Redeploy after setting it.
- [ ] Run §5 and record the results.
- [ ] Re-submit `https://okurmenkids.com/sitemap.xml` in Google Search Console.
