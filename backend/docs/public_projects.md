# Public student projects gallery

`apps.projects.public` — the read-only API behind `/projects` on
OkurmenKids Digital. The LMS (`/api/v1/projects/`, `access.py`) is unchanged:
only a trainer registers a project, the trainer who registered it (or an
Admin) edits it and moves it between «Черновик» and «Опубликован».

## Endpoints (no login, GET only)

| | |
|---|---|
| `GET /api/v1/public/projects/?q=&category=&page=&page_size=` | published projects, newest first; `category` = `all`, `html-css`, `javascript`, `react`, `python`, `other`; `counts` per category for the current search |
| `GET /api/v1/public/projects/<key>/` | one published project; 404 for drafts and unknown keys |

`<key>` is an opaque HMAC of the id (never the database id).

## What is published

Only projects with status **published**. Fields: key, title, short and full
description, technologies, categories, project date, demo URL (http/https
only), cover and images (`/media/projects/...`), group name, student as
«First name + last-name initial».

* A student whose `show_in_leaderboard` switch is off (the parents' privacy
  switch of the public leaderboard) is published **without a name**, and the
  search cannot find their projects by name.
* The trainer's name only with `PUBLIC_PROJECTS_SHOW_TRAINER=true`.
* Never: trainer comment, rating, GitHub / Figma links, student status or
  contacts, author account, ids.

## Settings (env)

| Variable | Default | |
|---|---|---|
| `PUBLIC_PROJECTS_SHOW_TRAINER` | `false` | show the trainer's name on the details page |
| `PUBLIC_PROJECTS_CACHE_SECONDS` | `120` | server cache; any project, image, technology, student or group change clears it at once |
| `PUBLIC_PROJECTS_RATE` | `1200/hour` | per-IP rate limit |

Categories map technology names (case-insensitive) in `public.CATEGORIES`;
a project with none of them is «other».
