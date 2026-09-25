# Feedback surveys (`apps.feedback`)

Admins build surveys for **parents** or **students**, publish them, share a
public link (WhatsApp/Telegram) and review responses and analytics.

## Where things live

| Piece | Location |
|---|---|
| Models | `apps/feedback/models.py` — `Survey`, `SurveyQuestion`, `QuestionOption`, `SurveyResponse`, `SurveyAnswer`, `SurveyAnswerOption` |
| Builder rules (questions, options, lifecycle, audit log) | `apps/feedback/services/builder.py` |
| Answer validation (single write path for public answers) | `apps/feedback/services/submission.py` |
| Analytics / CSV export | `apps/feedback/services/analytics.py`, `services/export.py` |
| Admin JSON API | `apps/feedback/views.py`, `urls.py` |
| Public page (server-rendered) | `apps/feedback/public_views.py`, `templates/feedback/` |
| Admin pages (Jazzmin) | `apps/feedback/admin.py`, `admin_views.py`, `templates/admin/feedback/`, `static/feedback/` |

## Admin routes (ADMIN role only)

| Route | Page |
|---|---|
| `/admin/feedback/survey/` | Survey list |
| `/admin/feedback/survey/add/` | Create survey (settings) → redirects to builder |
| `/admin/feedback/survey/<id>/change/` | Survey settings |
| `/admin/feedback/survey/<id>/builder/` | Question builder, publish/close/reopen, public link, share buttons |
| `/admin/feedback/survey/<id>/preview/` | Preview, rendered with the same template as the public page (submit disabled) |
| `/admin/feedback/survey/<id>/responses/` | Responses (search, filters, pagination, delete, CSV export) |
| `/admin/feedback/survey/<id>/analytics/` | Per-question analytics |
| `/admin/feedback/survey/analytics/` | Overview analytics (filters: survey, audience, group, teacher, subject, dates, visibility) |

Sidebar group: **«Обратная связь»**.

## Public route

`/feedback/s/<token>/` shows the form (it works without JavaScript) and `/feedback/s/<token>/done/` shows the confirmation.
The link uses the host the admin is on. Set `FEEDBACK_PUBLIC_BASE_URL` (e.g.
`https://kids.okurmen.kg`) to force a specific origin.

## API (`/api/v1/`)

Admin endpoints need the ADMIN role (JWT or session + CSRF).

| Method | Path | Purpose |
|---|---|---|
| GET/POST | `feedback/surveys/` | List (filters `audience`, `status`, `visibility_mode`, `search`) / create |
| GET/PATCH/PUT/DELETE | `feedback/surveys/{id}/` | Retrieve (with questions) / update settings / delete (only without responses) |
| POST | `feedback/surveys/{id}/publish/` · `close/` · `reopen/` · `regenerate-link/` · `duplicate/` | Lifecycle |
| POST | `feedback/surveys/{id}/questions/` | Add question (`options: [{text}]`) |
| POST | `feedback/surveys/{id}/questions/reorder/` | `{"order": [question ids…]}` (must list every question exactly once) |
| GET/PUT/PATCH/DELETE | `feedback/questions/{id}/` | Question; `options: [{id?, text}]` is the full ordered list (add/edit/delete/reorder) |
| POST | `feedback/questions/{id}/duplicate/` | Copy question right after the original |
| GET | `feedback/surveys/{id}/responses/` | Paginated responses (`visibility`, `date_from`, `date_to`, `search`) |
| GET | `feedback/surveys/{id}/analytics/` | Per-question stats |
| GET | `feedback/surveys/{id}/export/` | CSV |
| GET | `feedback/analytics/overview/` | Totals, open/anonymous split, per-survey counts |

Public endpoints need no login and are IP-throttled (`feedback_view` 300/h, `feedback_submit` 30/h):

| Method | Path | Purpose |
|---|---|---|
| GET | `feedback/public/{token}/` | Form definition, or `{availability, message}` if unavailable. Drafts return 404 |
| POST | `feedback/public/{token}/submit/` | `{visibility, respondent_name, child_name, answers: {question_id: text \| option_id \| [option_ids]}}` → 201 / 400 `{errors}` / 409 already submitted |

## Lifecycle

`draft → published ⇄ closed`. Publishing requires at least one question and at least two options per choice question.
An end date, if set, must be in the future. A published survey accepts answers only inside
`starts_at`/`ends_at` and while it is under `max_responses`. Regenerating the link invalidates the old one immediately.

**Editing after responses:** a question that has answers is locked. Its type can't change and it
can't be deleted, and options that were chosen can't be removed. You can still fix wording and add questions or options.
For a different structure, duplicate the survey. The database enforces this too (`PROTECT` on answer → question/option).

## Privacy model

- OkurmenKIDS has **no parent/student accounts**, so every respondent is an unauthenticated visitor.
  Names are *self-reported*. The child name is labelled "со слов родителя" and is never matched against `Student`.
- **Anonymous** responses store no respondent name; a DB check constraint enforces this.
  **No response ever stores IP, user agent, phone or e-mail.**
- A child name is collected in anonymous mode only if the admin enables
  `ask_child_name_when_anonymous`. The public form then warns that the answer is not fully anonymous.
- Duplicate protection is a signed cookie only, with nothing stored server-side. Clearing cookies bypasses it.
  The IP is used only as a transient throttle cache key.
- Analytics text lists never show identity. Open-response names appear only on the Responses tab and in the CSV (admins only).
- **Teachers have no access** to surveys or responses. There is no organisational policy for that yet.
- Audit trail: publish, close, reopen, new link, duplicate, response deletion and CSV export are written to
  Django's admin log ("История"). Free-text answers are never logged.
- CSV export escapes formula prefixes (`= + - @`) against spreadsheet injection.

## Not implemented / limitations

- Authenticated parent/student flows (picking linked children, verified identity): these need parent/student accounts, which the LMS doesn't have.
- No response rate (a public link has no known number of recipients) and no composite teacher/satisfaction score.
- No "Other (write your own)" option and no moderation status for text answers, only deletion.
- No teacher-facing view of feedback.
