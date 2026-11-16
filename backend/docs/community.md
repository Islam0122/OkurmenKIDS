# «Сообщество» — student community (apps.community)

A private community inside the Student & Parent Portal: `/student/community`
(RU «Сообщество», KG «Коомчулук»). Students are minors, so the design is
safety-first.

## Publication policy

| Rule | How it is enforced |
| --- | --- |
| Nothing is visible to other students before a moderator approves it | Post states `draft → pending → approved / rejected`, plus `hidden`; the feed query is `status=approved` only (`scope.feed_q`) |
| Editing a published post sends it back to review | `services.update_post` → `pending` |
| No contact details | `safety.problems()` refuses phones, e-mails, links, `@handles`, messengers/social networks, home addresses in posts and comments (with the reason) |
| Links only to project sites | `project_url` must be `https://` on GitHub, Replit, Scratch, CodePen, Figma, Vercel, Netlify… (`safety.PROJECT_HOSTS`) |
| Photos never public | Stored in `MEDIA_ROOT/private/community` (not served), re-encoded to WebP without EXIF/GPS, the upload is not kept; served only by signed links valid 6 h (`media.signed_url`), `X-Robots-Tag: noindex`, `Cache-Control: private` |
| Reporting | One report per student per post/comment; 3 reports from different students hide the content until a moderator decides |
| Not indexed | Family API only; `robots.txt` disallows `/student/`, pages add `noindex` |
| Group-only posts | `audience=group` is visible to the author's current group only |

## Who does what

| Role | Can |
| --- | --- |
| Family account (STUDENT_PARENT), as one linked child | Read the feed; post (active/paused students), save drafts, edit/delete own; like; comment and reply; delete own comments; report; view classmates' community profiles (name, group, photo, badges, posts, projects — no contacts, birth date, branch, payments, grades) |
| Admin, director, operations director, team lead, assistant | Moderate everything: approve, reject (with a note for the student), hide, restore, pin; hide/restore comments; close reports; publish academy-wide or group announcements |
| Trainer | The same for students / groups they teach (active GroupTeacher); announcements only to own groups |
| Admin, director | Publish an approved review on the website (below) |

Moderators get no access to student accounts. Family accounts cannot reach
`/api/v1/community/` (portal isolation middleware).

## Notifications

Stored per child (`CommunityNotification`): comment, reply, like (once per
liker), approved, rejected (with the moderator's note), hidden. Shown in the
community bell (marked read on open) and in the portal's existing
notifications list (unread, last 30 days) with links to the post. Portal
accounts have no web-push subscription, so there is no push.

## Website testimonials (okurmenkids.com/testimonials)

The public website (okurmen-public-website) reads
`GET /api/v1/public/site/testimonials/` — `website.Testimonial` records that are
**published** and have **consent** (cached; every save clears the cache). The
same list is shown on `/testimonials`, `/ky/testimonials` and `/en/testimonials`.

A student review reaches it automatically:

1. The family posts a **review** and ticks «Разрешаем показать этот отзыв на сайте».
2. It is stored as a community post, **pending** (not public anywhere).
3. A moderator approves it («Одобрить»).
4. The approval itself publishes it: one `Testimonial` (created once, then
   updated — never a duplicate): «Имя И.», role student, course, text,
   detected language (ru / ky / en); no photo, surname or group.
5. The public API and the website show it on the next request (no redeploy).

Reviews without the family's consent, other categories and pending posts
never go to the site. A published review leaves the site automatically
(archived, kept) when it is rejected, hidden (moderator or reports), edited
back to review or deleted. A director / administrator can take one off by hand
(«Снять с сайта») and put it back («Опубликовать на сайте» — moderation tab
«Для сайта», or Управление сайтом → Отзывы). Testimonials made by hand in the
site CMS are untouched.

Migration `community.0002_publish_approved_reviews` published, once, the
reviews approved with consent before approval became automatic (those with
no testimonial yet; a review taken off by an administrator is left off).
`manage.py community_website_audit` shows every review's LMS status, consent,
testimonial and public-API state (read-only).

## API

Family — `/api/v1/portal/students/<id>/community/`: `GET/POST` (feed / new
post, multipart), `summary/`, `mine/`, `posts/<id>/` (`GET/PATCH/DELETE`),
`posts/<id>/like/`, `posts/<id>/comments/`, `posts/<id>/report/`,
`comments/<id>/` (`DELETE`), `comments/<id>/report/`, `profiles/<student>/`,
`notifications/` (`GET`, `POST` = mark read).

Staff — `/api/v1/community/`: `meta/`, `posts/?status=`, `posts/<id>/`,
`posts/<id>/{approve,reject,hide,pin,to-website}/`, `announcements/`,
`reports/`, `reports/<id>/close/`, `comments/<id>/hide/`,
`media/<signed token>/`.
