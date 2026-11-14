# Google brand search: «Okurmen Kids» and «Окурмен Кидс»

**Date:** 2026-11-14 · **Scope:** `okurmen-public-website/` (https://www.okurmenkids.com)

## 1. Why the Cyrillic query was weak

Before this change, «Окурмен Кидс» appeared on the site **only** inside the JSON-LD
`alternateName`. It was not in any `<title>`, meta description, heading or visible text.
Google uses `alternateName` mainly to choose the site name, not as ranking text. So a
Cyrillic query had almost nothing on the page to match, while «okurmenkids» matched the
domain itself.

Technical SEO was already sound and is unchanged:
- Googlebot gets **200**.
- The raw HTML is prerendered per page and language.
- Robots: `index, follow`.
- Canonical and hreflang ru/ky/en/x-default are in place.
- The sitemap has 80 URLs and is linked from `robots.txt`.

## 2. What changed

| | Before | After |
|---|---|---|
| Home `<title>` (RU) | `OKURMEN Kids — IT-академия и программирование для детей` | `Okurmen Kids — Академия программирования для детей в Бишкеке` |
| Home description (RU) | Latin brand only | `Окурмен Кидс (Okurmen Kids) — образовательная академия для детей в Бишкеке. Программирование, IT-курсы, Python, веб-разработка и современные технологии.` |
| Home title / description (KG) | Latin brand only | `Okurmen Kids — балдар үчүн программалоо академиясы, Бишкек` / `Окурмен Кидс (Okurmen Kids) — Бишкектеги балдар үчүн билим берүү академиясы. …` |
| Visible homepage text (RU/KG) | no Cyrillic brand | hero lead: «Okurmen Kids (Окурмен Кидс) — академия программирования для детей в Бишкеке…» |
| Footer on every page (RU/KG) | no Cyrillic brand | «Okurmen Kids (Окурмен Кидс) — IT-академия для детей и подростков в Бишкеке…» |
| `WebSite` JSON-LD | name `OKURMEN Kids` | name `Okurmen Kids`, alternateName `Окурмен Кидс`, `ОкурменKids`, `Окурмен Кидс Бишкек`, `Окурмэн Кидс`, `Окурмэн`, `okurmenkids` |
| `Organization` JSON-LD | name `OKURMEN Kids`, url without `/` | name `Okurmen Kids`, the **same six** alternateName values as `WebSite` (one list, `BRAND_ALT` in `src/seo/core.js`); linked to the WebSite by `@id` (`publisher` → `#organization`), url `…/`, logo `/icon-512.png` (512×512). Address «Улица Орозбекова, 136, Бишкек» and phone `+996504677725` come from the CMS. Description mentions «Окурмен Кидс» |
| Brand in all titles / `og:site_name` / schema | `OKURMEN Kids` | `Okurmen Kids` (one constant: `src/seo/core.js`) |

The English pages don't get the Cyrillic spelling in their text: it wouldn't read
naturally there. Each string has exactly one Cyrillic mention, and a test enforces that.

What was **not** changed:
- the logo, the visible «OKURMEN Kids» in the footer © line, and the PWA manifest name;
- no duplicate pages or URLs were created for Cyrillic keywords;
- the word «Digital» was not added anywhere.

The spellings «Окурмэн Кидс» and «Окурмэн» match the official round logo, which reads «ОКУРМЭН». All six spellings are emitted on the RU, KG and EN versions of home, `/about` and `/contacts`. They are kept out of titles, descriptions and visible text on purpose, to avoid keyword stuffing.

## 3. Verification (production build with live API data)

- **Schema Markup Validator** (validator.schema.org): home, `/about` and `/contacts` in RU/KG/EN (9 pages), plus `/courses` and `/ky/team`, all return **0 errors and 0 warnings**. All six `alternateName` values are recognized. On the homepage it
  recognizes the `WebSite` with all four `alternateName` values, and the
  `Organization`/`EducationalOrganization` (via `publisher`) with telephone and address.
- **30 static pages × raw HTML:**
  - titles and descriptions are all unique;
  - each page has exactly one `<title>`, description and canonical;
  - every canonical is `https://www.okurmenkids.com/…`;
  - hreflang ru/ky/en/x-default is present and reciprocal on every page;
  - no page has `noindex`;
  - all JSON-LD parses.
- **sitemap.xml:** 80 URLs, all on `https://www.`, no duplicates.
- **robots.txt:** `Allow: /`. Only `/preview/` and `/enroll` are blocked. It points to the sitemap.
- **Tests:** 69/69 pass. The tests check the exact alternate-name list, that it has no duplicates, and that WebSite and Organization carry the same list in every language and are linked by `@id`. Typecheck and lint are clean.

## 4. Required manual step: make `okurmenkids.com` → `www` permanent

The live apex `https://okurmenkids.com/` answers **307 Temporary Redirect** → `https://www.okurmenkids.com/`.
A temporary redirect tells Google to keep the apex URL as a separate candidate. That splits
signals between two hosts and is a likely reason results are inconsistent.

The site's canonical host is **www**: every canonical, hreflang, sitemap and JSON-LD URL
uses it. The redirect doesn't come from the code; it comes from Vercel's domain settings.

1. Go to **Vercel → project `okurmen-public-website` → Settings → Domains → `okurmenkids.com`**.
2. Choose **Edit → Redirect to `www.okurmenkids.com`** with status **308 Permanent Redirect**.
3. Check the result:

```bash
curl -sI https://okurmenkids.com/ | head -3
```

It should print `HTTP/2 308` and `location: https://www.okurmenkids.com/`.

If you'd rather have the **apex** as the canonical host, that's a separate decision.
You'd set `VITE_SITE_URL=https://okurmenkids.com` in Vercel, flip the redirect direction
(www → apex, 308), and redeploy. Don't do it half-way: canonical and redirect must agree.

## 5. Google Search Console: after deploy (and after step 4)

The property should be the **Domain property `okurmenkids.com`**: it covers apex and www.

1. **Sitemaps** → submit (or re-submit) `https://www.okurmenkids.com/sitemap.xml`.
2. **URL Inspection** → paste each URL → **Test live URL** → check "URL is available to Google",
   then use **Request indexing**. Google allows about 10–12 requests per day, so go in this order:

```
https://www.okurmenkids.com/
https://www.okurmenkids.com/ky
https://www.okurmenkids.com/about
https://www.okurmenkids.com/contacts
https://www.okurmenkids.com/courses
https://www.okurmenkids.com/ky/about
https://www.okurmenkids.com/ky/contacts
https://www.okurmenkids.com/ky/courses
https://www.okurmenkids.com/en
https://www.okurmenkids.com/team
https://www.okurmenkids.com/ky/team
https://www.okurmenkids.com/projects
```

3. Also inspect `https://okurmenkids.com/` (apex). Once step 4 is done it should show as a
   redirect to www, with "Google-selected canonical" = `https://www.okurmenkids.com/`.
4. **Rich results / Enhancements:** after recrawl, confirm there are no structured-data errors.
5. Re-check the queries «Окурмен Кидс», «окурмен кидс бишкек» and «okurmenkids» in
   **Performance → Search results** after 1–3 weeks. Brand changes need a recrawl first.
   Nobody can make Google rank instantly.

Helpful off-site signals (not code):
- Use the same name «Okurmen Kids (Окурмен Кидс)», address and phone in **Google Business
  Profile**, **2GIS** and the **Instagram** bio.
- Link the website from each of those.
