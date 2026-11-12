# Okurmen Kids Digital — SEO audit & roadmap

**Date:** 2026-11-12 · **Scope:** public website (`okurmen-public-website/`, live at https://www.okurmenkids.com) · **Phase:** investigation and plan. **No changes have been made yet.**

**How this was measured:**
* rendered crawl of **90 live URLs** with Chromium and the Googlebot-mobile user agent (`/`, `/ky`, `/en` plus every internal link found);
* raw no-JavaScript fetches with the Googlebot user agent;
* Lighthouse 12 mobile on 3 pages;
* the live public API;
* the source code at `master` @ `7305c63`;
* web search for the target queries;
* a direct fetch of https://www.okurmen.com.

**Not available:** Google Search Console, GA4, Google Business Profile, keyword-volume tools. Search volumes and current positions are therefore **not verified**, and the plan includes collecting them in week 1.

**Content rule used throughout:** only facts that already exist in the CMS or API are used (courses, projects, achievements, news, team, testimonials, branch, stats). Nothing here invents a branch, a statistic, a testimonial or a course.

---

## 1. Executive summary

The site's **on-page foundation is good**:
* every page has a unique title and description, exactly one H1, a canonical, hreflang for ru/ky/en, Open Graph tags and JSON-LD;
* Lighthouse SEO score is 100.

What holds it back from ranking for "IT курсы для детей Бишкек" is a short list of concrete problems:

| # | Problem | Evidence | Impact |
|---|---|---|---|
| 1 | **No course pages.** `/courses` has 45 words and **0 published courses** | API `public/site/courses/` returns 0; sitemap feed `courses: 0` | The commercial pages that should rank for "Python для детей", "Scratch курсы" etc. don't exist |
| 2 | **Canonical host conflict.** Pages declare `https://www.okurmenkids.com/…` as canonical, while `sitemap.xml` and `robots.txt` use `https://okurmenkids.com/…`, which **307-redirects** to www | live crawl: canonical host is www on 90/90 pages; `curl -I https://okurmenkids.com/` → 307 | Google gets contradictory signals and sitemap URLs that redirect |
| 3 | **Content only after JavaScript.** Raw HTML of every list page is ~10 words with one generic title; detail pages get title and OG tags from the middleware, but no body text | raw fetch with the Googlebot user agent | Google indexes later (render queue), Yandex and social bots see almost nothing, and nothing ranks before rendering |
| 4 | **Untranslated duplicates.** `/ky/...` and `/en/...` news, projects, achievements and team pages show the **Russian** text but are labelled ky/en with hreflang | crawl: identical title and description ×3 for every CMS item (8+ groups) | Duplicate content and wrong language signals across 60+ URLs |
| 5 | **10.6 MB homepage, LCP 4.3 s on mobile** | Lighthouse: performance 66; one student-project cover is a **4.5 MB PNG**; 7.7 MB could be saved with WebP | Fails the Core Web Vitals LCP threshold (2.5 s) on mobile, which is the main device for parents |
| 6 | **The brand competes with itself.** `okurmen.com/kids` ("Okurmen Kids — балдар үчүн IT", server-rendered, Kyrgyz, with courses for ages 7–10 and 11–14) **doesn't link to okurmenkids.com** | live fetch | Google is likely to treat okurmen.com as the authority for "Okurmen Kids" |
| 7 | **No analytics or conversion tracking**, and the CMS SEO fields are empty | no gtag or GA code; `settings.seo = {title: null, description: null, image: null}` | Organic leads can't be measured |
| 8 | The sitemap has only the 30 static URLs; 60 content URLs are missing | `VITE_SITE_URL` isn't set at build time, so the build skipped the API-based sitemap | Slower discovery of projects, news and team pages |

Market check: searching "IT курсы для детей Бишкек" returns 2GIS, MLDC (AUCA), Codify, ALG Academy, Algoritmika, GeekBrains, KIBERone and IT-RUN KIDS. **okurmenkids.com doesn't appear** in the standard or extended results, and a search for "Okurmen Kids Бишкек" finds no okurmenkids.com page. The winners all have **one dedicated page per course and age group** (for example KIBERone has separate Scratch and Python module pages; Algoritmika has "Python Start 12–13 лет").

---

## 2. Technical SEO audit

| Area | Status | Evidence | Action |
|---|---|---|---|
| Crawlable links | **PASS** | 90 pages found from 3 entry points through real `<a href>` links; no 404s reached | — |
| Unique titles and descriptions per URL | **PASS for ru**, **FAIL across languages** | 0 duplicates within a language; CMS items share a title across ru/ky/en | §5.T4 |
| One H1 per page | **PASS** | 90/90 | — |
| Canonical | **FAIL** | www canonical vs apex sitemap/robots, plus a 307 | §5.T1 (needs your decision) |
| Redirects | **WARNING** | apex → www is **307 (temporary)**; no loops, single hop | change to 308 in Vercel Domains |
| robots.txt | **WARNING** | correct rules; the `Sitemap:` line points to the apex host, which redirects | §5.T1 |
| sitemap.xml | **WARNING** | valid XML, 30 URLs, hreflang; the 60 content URLs are missing | §5.T2 |
| Soft 404s | **WARNING** | unknown URLs return HTTP 200 with a `noindex` "not found" page (SPA) | acceptable with noindex; better: return a real 404 via middleware (§5.T6) |
| Rendering | **FAIL (partial)** | list pages: ~10 words before JS | §5.T3 build-time prerender |
| Mobile | **PASS** | responsive layout, tap targets; Lighthouse accessibility 96 | — |
| Core Web Vitals (lab, mobile) | **FAIL on home** | home: LCP 4.3 s, TBT 530 ms, 10.6 MB · `/courses`: LCP 4.1 s, **CLS 0.258** · `/en/team`: LCP 3.0 s | §5.T5 |
| Images | **FAIL** | project covers are full PNGs (4.5 MB, 2.4 MB, 1.1 MB…); 10 of 20 images on the home page have no `alt` | §5.T5 |
| Open Graph / Twitter | **PASS** | per page at runtime; bot middleware for detail pages; absolute `og:image` | — |
| Structured data | **PASS (basic)** | EducationalOrganization (home, about, team, contacts), BreadcrumbList, NewsArticle, CreativeWork, Person, Course (detail pages; none live), Event, ItemList | §5.T7: add geo, opening hours, telephone, sameAs; fix a zero-width space in the address |
| HTML `lang` | **PASS** | `ru` / `ky` / `en` per branch | — |
| HTTPS / HSTS | **PASS** | valid certificates, HSTS on all hosts | — |
| Legacy duplicates | **WARNING** | `okurmen-public-website.vercel.app` still serves the whole site with 200; one project page links to it | point it at the main domain or add `noindex` |
| Data quality | **WARNING** | branch address starts with an invisible U+200B character; projects "Теннис", "Баластан" and "ShopVerce" have one-line descriptions (98 words per page) | CMS clean-up |

### Structured data: what Google should see for the organization (all values from the CMS)
`EducationalOrganization` + `LocalBusiness` (type `EducationalOrganization`, plus `ChildCare` **only if** that's accurate, otherwise not) with:
* name;
* `address` "ул. Орозбекова, 136, Бишкек";
* `geo` 42.885375, 74.603386;
* `openingHours` "Mo-Su 10:00-20:00";
* `telephone` +996504677725;
* `email`;
* `sameAs` [Instagram, 2GIS];
* `aggregateRating` **only** from the 8 published testimonials.

Google's guidelines disallow self-serving review stars for organizations, so `aggregateRating` stays out of the markup. It's mentioned only to rule it out.

---

## 3. Keyword map (RU + KY)

Volumes aren't verified (no keyword tool access); priority is by intent and competition seen in the search results. Week 1 of the plan replaces these with Search Console and Keyword Planner data.

| Cluster | RU queries | KY queries | Intent | Target URL | Status |
|---|---|---|---|---|---|
| Core local | IT курсы для детей Бишкек · программирование для детей Бишкек · детские IT курсы Кыргызстан · IT школа для детей | балдар үчүн IT курстар Бишкек · балдар үчүн программалоо · балдарга IT мектеп | commercial, local | `/` (ru) · `/ky` | exists, needs stronger copy |
| Python | Python для детей Бишкек · курсы Python для школьников · программирование на Python для подростков | балдар үчүн Python курсу · Python окуучулар үчүн | commercial | `/courses/<python-slug>` | **missing (no course published)** |
| Scratch | Scratch для детей · курсы Scratch Бишкек · программирование для детей 7 лет | Scratch балдар үчүн · 7 жаштан программалоо | commercial | `/courses/<scratch-slug>` | **missing** |
| Web | HTML CSS JavaScript для детей · создание сайтов для школьников · веб-разработка для подростков | балдар үчүн сайт түзүү · HTML CSS балдарга | commercial | `/courses/<web-slug>` | **missing** |
| Robotics | робототехника для детей Бишкек | балдар үчүн робототехника | commercial | `/courses/<robotics-slug>` | **only if the academy really teaches it.** It's in the meta description, but no course exists. Confirm before creating, or remove it from the description |
| Computer literacy | компьютерные курсы для детей · компьютерная грамотность для детей | балдар үчүн компьютердик курстар | commercial | `/courses/<…>` | confirm whether this program exists |
| Trial / price | пробный урок программирование ребенку · стоимость IT курсов для детей Бишкек | акысыз сынамык сабак | transactional | `/contacts#enroll` + every course page | exists (form) |
| Proof | проекты учеников · отзывы IT школа для детей | окуучулардын долбоорлору · пикирлер | trust | `/projects`, `/testimonials`, `/achievements` | exists |
| Brand | Okurmen Kids · Окурмен Кидс · okurmenkids | Окурмен Кидс | navigational | `/` | at risk from `okurmen.com/kids` |
| Informational (blog) | с какого возраста учить ребенка программированию · Scratch или Python что выбрать · чем полезно программирование детям | балага программалоону канча жаштан үйрөтүү керек | informational | `/news/<article>` (category "Полезное") | missing; 1 article per month written by trainers |

**Rule:** one primary cluster per URL. No pages per city district, no near-duplicate copies with swapped keywords.

---

## 4. SEO architecture

| Requested page | Existing route | Data source | Conversion goal | Gap / action |
|---|---|---|---|---|
| Homepage | `/`, `/ky`, `/en` | CMS settings + featured content | trial lesson form / WhatsApp | strengthen H1/H2 copy around the core cluster; fill the CMS SEO fields |
| Courses | `/courses` | `public/site/courses/` | open a course | **publish courses in the CMS** (marketing) |
| Python for Kids · Scratch · HTML/CSS/JS · Robotics | `/courses/:slug` (template exists, with Course JSON-LD) | CMS `CoursePage` linked to `academy.Course` | trial lesson form | **content needed from the academy:** age range, duration, format, outcomes, trainer, real student projects in that category. `okurmen.com/kids` already lists *Scratch & Python 7–10* and *Web & Mobile 11–14*; confirm this is the same program |
| Branches | `/contacts` (branches from the CMS) | `settings.branches` (**1 branch**) | call / route / form | keep it on Contacts while there's one branch. A `/branches/:slug` page only when a second real branch exists |
| Student projects | `/projects`, `/projects/:slug` | apps.projects (6 published) | trust → form | improve the thin descriptions; WebP covers |
| Achievements | `/achievements`, `/achievements/:slug` | 3 published | trust | — |
| Testimonials | `/testimonials` | 8 published, with consent | trust → form | add a call to action under the list |
| About | `/about` | CMS settings | trust → form | 239 words; add the methodology and trainers' expertise (real people from `/team`) |
| Blog / resources | `/news`, `/news/:slug` (5 articles) | apps.academy_news | newsletter / form | add a "Полезное" category with educational articles by trainers |
| Events | `/events` | 0 events | registration | 39 words: hide it from navigation and the sitemap while empty, or publish real events |
| Team | `/team`, `/team/:slug` | 6 people | trust (E-E-A-T) | — |

**LMS data:** the site already uses only public, whitelisted endpoints (`public/site/*`, `public/news`, `public/projects`, `public/careers`). There's no need to read LMS data directly. All new pages above come from data the academy publishes on purpose through the CMS; no private student data is involved.

---

## 5. Implementation plan

### Technical (code, low risk, reversible)
| ID | Change | Files | Measurable result |
|---|---|---|---|
| **T1** | **One canonical host**: set it via `VITE_SITE_URL`, and generate robots.txt and sitemap from the same value. Apex → www **308** (or the reverse) in Vercel Domains | `public/robots.txt`, `public/sitemap.xml`, Vercel env + Domains (**you**) | canonical = sitemap = robots = final URL on 100% of pages |
| T2 | Build-time sitemap with content URLs (enabled by T1) | env only | 30 → 90+ URLs (≈ 30 static + 60 content) |
| **T3** | **Build-time prerender** of the static routes and published content into `dist/**/index.html` (headless render after `vite build`; same HTML for users and bots, so no cloaking). React then renders on top as today. Rebuild on CMS publish via a Vercel Deploy Hook | `scripts/prerender.mjs`, `package.json` build script, a Deploy Hook (**you**) | raw HTML word count ≈ rendered word count; Yandex and social previews show real content |
| **T4** | **Untranslated items:** the API marks which languages a CMS item really has; untranslated ky/en variants get `noindex` + canonical to ru and are left out of hreflang and the sitemap | `backend/apps/website/public.py` (+ `academy_news`, `projects` public): an extra read-only field, no schema change · `Seo.tsx`, `generate-sitemap.mjs` | 0 duplicate titles across languages |
| **T5** | **Images:** WebP thumb/large for student-project covers at upload time (as the website CMS media already does), `width`/`height`, `loading="lazy"`, `alt` on all images; preconnect to the API origin; fix the `/courses` CLS (skeleton height) | `apps/projects` (image derivatives; **needs a migration or derived-file naming, which I'll confirm with you**), `ProjectCard.tsx`, `index.html`, `CoursesPage.tsx` | home weight 10.6 MB → < 2 MB; mobile LCP < 2.5 s; CLS < 0.1 |
| T6 | Real 404 status for unknown URLs (middleware checks the route table) | `middleware.ts` | soft 404s → 404 |
| T7 | Organization/LocalBusiness JSON-LD from CMS data (geo, opening hours, telephone, sameAs); Course JSON-LD gets duration, age and format when present | `Seo.tsx`, `CourseDetailPage.tsx` | Rich Results Test: 0 errors |
| T8 | Analytics: GA4 + Search Console; events `generate_lead` (form success), `click_whatsapp`, `click_phone`; UTM is already stored with each lead | `src/app/analytics.ts`, `EnrollmentForm.tsx`; env `VITE_GA_MEASUREMENT_ID` (**you**) | organic leads per week visible |

### Content and off-site (academy / marketing; I can draft templates, not facts)
| ID | Task | Owner |
|---|---|---|
| C1 | Publish 3–5 real course pages in the CMS (one per program and age group) with ru + ky text (≥ 400 useful words each, FAQ, real projects, trainer) | marketing + trainers |
| C2 | Fill in the CMS SEO fields (home title and description in ru/ky/en) | marketing |
| C3 | Translate the top CMS items into Kyrgyz, or accept `noindex` on the ky versions (T4) | marketing |
| C4 | 1 educational article per month by a trainer ("Scratch или Python: с чего начать в 7–10 лет") | trainers |
| C5 | **Link from `okurmen.com/kids` to `okurmenkids.com`** (same brand). This is the single most valuable link available | owner of okurmen.com |
| C6 | Google Business Profile (verify or create) with the real address, hours, photos and website link; keep 2GIS consistent (name, address, phone written exactly the same way) | owner |
| C7 | Backlinks: 2GIS card → site; Instagram bio → site; partners mentioned in the news (e.g. Ololo visit); local media (stories about student projects); school and parent communities | marketing |
| C8 | Ask satisfied parents for reviews on Google Business Profile and 2GIS (real reviews only) | marketing |

### Competitor: https://www.okurmen.com
| | okurmen.com | okurmenkids.com |
|---|---|---|
| Audience | adult IT careers (AI Web Developer, Python…) + a `/kids` page | children and teenagers |
| Rendering | **server-rendered Next.js**, about 1,040 words in raw HTML | client-side SPA, about 10 words in raw HTML |
| Language | Kyrgyz first (`lang="ky"`), RU/KG switch | ru / ky / en |
| robots / sitemap | **404 / none** | present |
| canonical / hreflang / JSON-LD | **none** | present |
| Kids content | `/kids`: 194 words, Scratch & Python 7–10, Web & Mobile 11–14 | 0 published courses |

* **Overlap:** brand queries ("Okurmen Kids") and Kyrgyz children's queries ("балдар үчүн IT").
* **Gaps okurmen.com leaves open:** no structured data, no sitemap, no per-course children's pages, no Russian children's content depth, no projects or testimonials for children.
* **Opportunity:** don't compete for adult IT queries. Own the children's queries with course pages, real student projects and reviews, and get the `/kids` page to link here.

---

## 6. Validation report (current state, baseline)

| Check | Result |
|---|---|
| Pages crawled (rendered) | 90 (30 per language) |
| Duplicate titles and descriptions within a language | 0 |
| Duplicate titles across languages | 8+ CMS items × 3 languages |
| Pages with ≠ 1 H1 | 0 |
| Canonical points to the page's own URL | 90/90 (host: www) |
| hreflang links per page | 4 (ru, ky, en, x-default) on 90/90 |
| Pages under 150 words | 15 (courses, events, contacts, 3 projects, achievements list; ×ky) |
| Images without `alt` | home 10/20, projects 8/8, about 3/6 |
| JSON-LD | valid JSON on all crawled pages; types listed in §2 |
| Lighthouse mobile (perf / SEO) | home 66 / 100 · courses 70 / 100 · en/team 90 / 100 |
| LCP / TBT / CLS | home 4.3 s / 530 ms / 0 · courses 4.1 s / 130 ms / **0.258** · en/team 3.0 s / 100 ms / 0 |
| Present in the "IT курсы для детей Бишкек" results (web search) | **not found** |

Every change in §5 will be re-validated with the same crawl, Lighthouse, Google's Rich Results Test (structured data) and a sitemap validator before deployment. The results will be added to this file.

---

## 7. 90-day growth dashboard

**Baseline: NOT VERIFIED** (no Search Console access). Week 1 records the real numbers, and the targets below are then adjusted to them.

| Metric (source) | Week 0 baseline | Day 30 | Day 60 | Day 90 |
|---|---|---|---|---|
| Indexed pages (GSC → Pages) | record | ≥ 60 | ≥ 90 | all valid sitemap URLs |
| Canonical / sitemap conflicts (GSC) | record | 0 | 0 | 0 |
| Published course pages | 0 | 3 | 5 | 5 + FAQ |
| Mobile CWV "Good" URLs (GSC → Core Web Vitals) | record | ≥ 75% | ≥ 90% | ≥ 90% |
| Impressions, children's IT cluster (GSC, query filter) | record | +50% | ×2 | ×3 |
| Clicks from organic search (GSC) | record | +30% | ×2 | ×3 |
| CTR on brand queries (GSC) | record | ≥ 30% | ≥ 35% | ≥ 40% |
| Avg position "IT курсы для детей Бишкек" (GSC) | record | top 30 | top 15 | **top 10** |
| Avg position "Python для детей Бишкек" / "Scratch для детей" | record | indexed | top 20 | top 10 |
| Organic leads (GA4 `generate_lead`, source = organic; CMS leads with UTM/referrer) | record | measurable | +25% | +50% |
| Google Business Profile: views, calls, website clicks | record | live + verified | +30% | +60% |
| Referring domains (GSC → Links) | record | +3 (okurmen.com, 2GIS, GBP) | +6 | +10 |

Review cadence: weekly check of GSC coverage and leads; monthly content review (a new article, course page updates).

---

## 8. Decisions needed before implementation
1. **Canonical host:** **www** (matches today's live setup and your objective; only the sitemap and robots need to follow) or **apex** (matches the sitemap and robots; the Vercel Domains setting must be flipped)?
2. **Phase 1 scope:** approve T1, T2, T4, T6, T7 and the frontend parts of T5? Then T3 (prerender) and T8 (GA4, which needs a Measurement ID from you).
3. **Project image derivatives (T5):** a small migration on `apps.projects` (adds thumbnail fields), or derived files with no schema change?
4. **Programs:** which courses and age groups are real (Scratch, Python, Web, Robotics, computer literacy), and who provides the course texts?
5. **okurmen.com/kids:** is it the same organization, and can it link to okurmenkids.com?
