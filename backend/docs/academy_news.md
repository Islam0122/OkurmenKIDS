# Public academy news (OkurmenKids Digital — /news)

`apps.academy_news` — the news visitors read at `/news` and `/news/<slug>`.
Not to be confused with `apps.news`: internal notices for trainers in the LMS
(audience, read receipts, 7-day expiry), which stay exactly as they were.

## Writing news (Django admin → «Новости академии (публичный сайт)»)

* **Create / edit / delete** an article: title, slug (empty → made from the
  title, Cyrillic transliterated: «Наш хакатон» → `nash-hakaton`),
  category, short description, text.
* **Text**: blank line = new paragraph, `## ` = subheading, `- ` = list
  item. Plain text only — no HTML is ever rendered.
* **Cover** with a caption.
* **Photos**: «Добавить фотографии» takes several files at once (up to 40);
  captions and order are edited in the «Фотографии» table below.
* **Status**: «Черновик» — not on the site; «Опубликована» — on the site from
  «Дата публикации»; a future date schedules the article.
* List actions: «Опубликовать сейчас», «Снять с публикации (в черновики)».
* «Главная новость» puts an article in the large block at the top of /news
  (otherwise the newest article is shown there).
* «Показывать автора на сайте» — the author's name is public only with this
  box ticked.

Who may do it: Django model permissions — a superuser, or a staff account
given the «Новость академии» / «Фотография» permissions.

## Photos

Uploads: JPEG, PNG or WebP, up to 15 MB and 60 MP, checked by Pillow. On save
every cover and photo gets two WebP copies — `large` (≤ 1600 px) and `thumb`
(≤ 640 px), EXIF rotation applied, metadata dropped — and its width/height
is stored, so the site reserves the right space and loads the small copy in
grids (`srcset`), the large one in the article and the lightbox. Deleting an
article or a photo deletes all its files. Media storage: see `media.md`.

## Public API (no login, GET only)

| | |
|---|---|
| `GET /api/v1/public/news/?q=&category=&page=&page_size=` | cards, newest first; `category` = `all`, `events`, `achievements`, `competitions`, `education`, `announcements`, `activities`; `counts` per category; `featured` on the first unfiltered page |
| `GET /api/v1/public/news/<slug>/` | the article with photos and up to 3 related articles; 404 for drafts, scheduled and unknown slugs |

Only `status = published` **and** `published_at <= now` (checked on every
request, so scheduled articles appear on time). Fields: slug, title, excerpt,
body, category, date, cover and photos (url, thumb, width, height, caption),
author name only with `show_author`.

## Settings (env)

| Variable | Default | |
|---|---|---|
| `PUBLIC_NEWS_CACHE_SECONDS` | `120` | server cache; any article/photo change clears it at once |
| `PUBLIC_NEWS_RATE` | `1200/hour` | per-IP rate limit |
