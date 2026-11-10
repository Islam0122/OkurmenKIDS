# Public website (okurmen-public-website) — integration with the LMS

```
OkurmenKIDS/
├── backend/                  Django + DRF (the existing LMS) — single backend for everything
│   └── apps/website/         NEW: public site content, CMS API, leads
├── frontend/                 existing LMS (React) — marketing cabinet gained «Сайт» (/marketing/site)
├── training-portal/          existing public training portal
└── okurmen-public-website/   NEW: independent public website (React + Vite), own Vercel project
```

The public website is a separate application. It has no database and no
admin of its own, and it never authenticates. It reads the public API listed
below and posts leads and event registrations. Content is managed inside
the existing LMS.

## What the inspection found

| Need | Existing in the LMS | Decision |
|---|---|---|
| News | `apps.academy_news` — public API `/api/v1/public/news/`, Django admin, WebP copies | **reused unchanged**; marketing can now also manage it from the LMS cabinet (CMS API below) |
| Student projects | `apps.projects` — trainers publish; public API `/api/v1/public/projects/` with privacy rules | **reused unchanged**; the site only displays published projects; the CMS can only *select* which ones appear on the homepage |
| Courses | `academy.Course` (name, lessons, subjects, description) — no slug, age, outcomes | `website.CoursePage` = the public page **of** a course (OneToOne to `academy.Course`), with no academic data duplicated |
| Trainers | `users.Teacher` (photo, bio, experience, phone…) — no consent flag | `website.TeamMember` = an *approved public profile*; the photo is shown only with `photo_approved`, the phone never |
| Marketing | `apps.marketing` (content plan, tasks, campaigns) — **no CRM** (docs/marketing.md) | minimal `website.Lead` inbox; campaign stats stay in `apps.marketing` |
| Roles | marketing / director / sales are `LMS_ONLY_ROLES` → **no Django admin**; marketing reaches `/api/v1/marketing/*` | the CMS is an API under `/api/v1/marketing/site/` + pages in the LMS marketing cabinet |
| Events, achievements, testimonials, homepage, media library | — | new models in `apps.website` |

## Public API — `/api/v1/public/site/` (no login, published only)

| | |
|---|---|
| `GET settings/` | hero, intro video, about texts, contacts (as links), branches, stats, visible homepage blocks in order, active banners |
| `GET home/` | settings + featured courses, projects, news, upcoming events, achievements, team, testimonials (one request) |
| `GET courses/`, `courses/<slug>/` | course pages; detail adds the LMS subjects, number of lessons and 3 published student projects of the course's category |
| `GET events/?phase=upcoming\|ongoing\|completed&category=&page=`, `events/<slug>/` | phase and registration status computed per request |
| `POST events/<slug>/register/` | `{parent_name, phone, child_name?, child_age?, comment?}` → 201 / 200 `duplicate` / 409 closed / 404 |
| `GET achievements/?category=&page=`, `achievements/<slug>/` | with photos and related |
| `GET team/` | published profiles of active trainers / staff |
| `GET testimonials/?kind=text\|photo\|video` | only `consent=True`; `average_rating` |
| `POST leads/` | `{parent_name, phone, child_age, course?(slug), branch?(id), contact_method, message?, language?, source?, utm_*?}` → 201 / 200 `duplicate` / 400 |
| `GET sitemap/` | slugs + dates of every public page (used at build time) |
| `GET preview/<token>/` | any status, signed link from the CMS (7 days), `no-store`, `noindex` |

Every GET takes `?lang=ru|ky|en` (or `Accept-Language`). Translations are
the optional `*_ky` / `*_en` fields, and an empty translation falls back to
Russian. Only `status=published` with `published_at <= now` is returned
(«Запланировано» = published with a future date). The response is a closed
whitelist of fields. There are no LMS ids of students, no contacts of
trainers, and no registrations or leads.

Leads and registrations: validated (phone normalised to `996…`), throttled
per IP (`PUBLIC_SITE_SUBMIT_RATE`, default `10/hour`), with a honeypot field.
A repeat from the same phone within 24 h updates the first lead
(`repeat_count`, message appended) instead of creating a duplicate. A repeat
registration for the same event returns `duplicate: true`.

## CMS API — `/api/v1/marketing/site/` (LMS cabinet)

| Resource | Who | Notes |
|---|---|---|
| `courses/`, `events/`, `achievements/`, `team/`, `testimonials/` | marketing, director, admin | CRUD; `?status=draft\|review\|scheduled\|published\|archived`; actions `publish` (optional `published_at`, `keep_schedule`), `submit_review`, `unpublish`, `archive`; each record has `workflow_state`, `preview.url`, `public_url` |
| `events/{id}/photos/`, `achievements/{id}/photos/`, `news/{id}/photos/` | same | `POST` multipart `files` (up to 40); `PATCH/DELETE photos/{photo_id}/` |
| `news/` | same | the existing `academy_news.Article` (draft / published / scheduled) |
| `settings/` (GET/PATCH), `sections/` (+ `reorder/`), `stats/`, `branches/`, `banners/` | same | homepage management |
| `media/`, `media-categories/` | same | media library: upload (images, MP4/WebM/MOV, PDF up to 80 MB), folders, search, replace, delete |
| `leads/` (+ `summary/`), `registrations/` | + sales manager, РОП, ДОП | only `status` and `note` are editable; deleting a lead is admin-only |
| `meta/`, `overview/` | site editors (`meta/` also sales) | choices, permissions, LMS options to link (courses, trainers, published projects, news) |

**Workflow:** Черновик → На согласовании → Опубликовано (now) / Запланировано
(future date) → В архиве. With `WEBSITE_REQUIRE_APPROVAL=true`, marketing can
only send content for review, and a director or an admin publishes it
(`reviewed_by` is recorded). Trainers have no access to any of this. They
keep publishing student projects in the LMS as before.

**Rich text:** stored as plain text in a small safe markup (headings, bold and
italic, lists, links, images from the media library, YouTube / Vimeo, quotes,
note blocks, dividers). The LMS editor has a toolbar and a preview, so nobody
types markup by hand. The public site parses it and never renders HTML. Old
news (`##`, `-`) is a subset, so existing articles render correctly.

**Admins** also get every model in the Django admin («Публичный сайт»), with
the same workflow actions and a preview link.

## LMS frontend

`/marketing/site` (Обзор), `/marketing/site/{courses,news,events,achievements,team,testimonials}`,
`/marketing/site/home` (главный экран, блоки, контакты, показатели, филиалы,
баннеры, избранные проекты и новости), `/marketing/site/media`,
`/marketing/site/leads`. The «Сайт» section is open to marketing, director and
admin; «Заявки» also to sales. Code: `frontend/src/features/siteCms/`.

## Settings (env)

| Variable | Default | |
|---|---|---|
| `PUBLIC_WEBSITE_ORIGINS` | — | CORS origins of the website, comma-separated |
| `PUBLIC_WEBSITE_URL` | — | its address — preview and «На сайте» links in the CMS |
| `PUBLIC_SITE_CACHE_SECONDS` | `120` | server cache; any content change clears it at once |
| `PUBLIC_SITE_RATE` / `PUBLIC_SITE_SUBMIT_RATE` | `1200/hour` / `10/hour` | per-IP limits |
| `WEBSITE_REQUIRE_APPROVAL` | `false` | marketing → director / admin approval before publishing |

## Not done / possible next steps

* Notifying sales about a new lead (Telegram / e-mail / LMS notification):
  `apps.operations` has a notifications service that this could reuse.
* An approval step for `academy_news` (its model has only draft / published):
  that would need a migration of an existing app, so it was left unchanged.
* Real photos: the site uses only what is uploaded in the CMS. No stock
  photos and no generated "student work" are bundled.
