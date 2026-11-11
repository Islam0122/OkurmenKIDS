# Массовое заполнение контента (bulk import)

LMS → кабинет «Сайт» → **Массовое заполнение** (`/marketing/site/import`).
Code: `backend/apps/website/content_import/`, `frontend/src/features/siteCms/ContentImportPage.tsx`.

One Excel file (or one CSV per type) → events, achievements and news, all
**unpublished**. Publication stays the normal CMS workflow (preview →
publish, or review → director / admin when `WEBSITE_REQUIRE_APPROVAL=true`).

## Who

Administrator and director. Marketing only with
`WEBSITE_IMPORT_ALLOW_MARKETING=true`. Checked on the server for every
endpoint; the menu item is shown from `meta.permissions.can_import`.

## File format

The repository had no «Seed Content Pack» file, so the format below is what
the templates (`Шаблоны` on the upload step) contain. Headers are matched
tolerantly: `title_ru`, «Название (RU)», `Title KG`, `title_kg`/`title_ky`,
«Обложка», «Примечание» … all work.

| Sheet (any of) | Model |
|---|---|
| `README` | ignored |
| `Events` / «Мероприятия» | `website.Event` |
| `Achievements` / «Достижения» | `website.Achievement` |
| `News` / «Новости» | `academy_news.Article` (unchanged) |

Common columns: `title_ru` (required), `title_ky`, `title_en`, `excerpt_*`,
`body_*`, `category` (required: code or Russian label), `status`, `cover`,
`verification_note`, `slug`.
Events: `starts_at` (required), `ends_at`, `location`, `branch` (name of an
existing branch), `registration_enabled`, `registration_limit`.
Achievements: `date` (required), `recipient`. News: `published_at`.

Dates: `YYYY-MM-DD`, `DD.MM.YYYY`, optional `HH:MM`, or Excel date cells.

## Validation

| Blocking error (row is not imported) | Warning (row is imported) |
|---|---|
| no RU title / category / date | no KG or EN translation (site shows RU) |
| unknown category, status, branch | no image |
| invalid date / number, end before start | `published` in the file → imported as a draft |
| text longer than the field | date without time |
| the same record twice in the file | news KG/EN text (news are single-language: kept in the import report only) |
| | the record already exists (→ skipped, or updated if confirmed) |

## Duplicates

Same slug, or the same title (case and spaces ignored) on the same date
(events: start day, achievements: date, news: title). Default: **skip**.
«Обновить» per row + an explicit confirmation checkbox (the API refuses
`update` without `confirm_update: true`). An update keeps the record's
status. **Published records are never updated** by an import.

## Status

Events and achievements keep `draft`, `review` or `archived` from the file;
`published` becomes `draft`. News are always `draft`. Nothing imported is
public until someone publishes it in the CMS.

## Security

`.xlsx` / `.csv` only, ≤ 5 MB, ≤ 1000 rows per sheet, ≤ 80 columns; XLSX
magic bytes and zip checked (uncompressed size, entry count), macro
workbooks refused, formulas never evaluated (cached values only), control
characters stripped. Image links are **not downloaded** — the server makes no
requests to addresses from a file. The error report escapes spreadsheet
formulas. The file is not stored: the validated rows are kept in the
`ImportBatch`, and the import uses those server-side rows only.

## API — `/api/v1/marketing/site/import/`

| | |
|---|---|
| `GET template/?file_format=xlsx` · `?file_format=csv&type=events` | templates (headers only + README) |
| `POST preview/` multipart `file`, `type` (CSV), `types=events,news` (sheets) | → batch with validated rows; writes no content |
| `POST {id}/commit/` `{rows, update, confirm_update, finalize}` | imports in chunks (UI: 20 rows per request = progress); one transaction per record; a row is never imported twice |
| `POST {id}/cancel/` | |
| `GET /` (history), `GET {id}/`, `GET {id}/errors/` (CSV report) | |

`ImportBatch`: file name and size, admin, content type, totals (rows,
selected, created, updated, skipped, failed), status, created / finished
time, per-row results with the verification notes.
