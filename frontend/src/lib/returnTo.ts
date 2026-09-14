/**
 * The one shared "where do I go back to" mechanism for flows that leave a
 * page to do something elsewhere and need to return afterwards (e.g.
 * Lesson Detail → fill Attendance → back to that same Lesson Detail).
 *
 * `returnTo` travels as a plain query param rather than router `state` so it
 * survives a full page reload of the destination page — but that also means
 * it's attacker-shareable in a URL, so every value coming back from
 * `location`/`searchParams` MUST go through `resolveReturnTo` before being
 * handed to `navigate()`. Never `navigate(rawQueryValue)` directly.
 */

/** True only for a same-app relative path — never an absolute URL
 * (`https://evil.com`), a protocol-relative one (`//evil.com`, browsers
 * treat it as `https://evil.com`), or anything embedding a scheme. */
export function isSafeInternalPath(path: string | null | undefined): path is string {
  if (!path) return false
  if (!path.startsWith('/')) return false
  if (path.startsWith('//')) return false
  if (path.includes('://')) return false
  return true
}

/** `candidate` if (and only if) it's a safe internal path, else `fallback`.
 * `fallback` itself is trusted (always a literal in calling code) and
 * returned as-is. */
export function resolveReturnTo(candidate: string | null | undefined, fallback: string): string {
  return isSafeInternalPath(candidate) ? candidate : fallback
}

/** The current location (path + query) as a `returnTo` value — capture this
 * at the point a flow is *left*, so whatever filters/tab/date the
 * originating page had in its own URL survive the round trip. */
export function currentPathAsReturnTo(pathname: string, search: string): string {
  return `${pathname}${search}`
}

/** Builds the URL to open the attendance editor for one lesson, remembering
 * where to return to after saving. The one place this URL shape is built —
 * every caller (Lesson Detail today, any future "quick attendance" entry
 * point) stays in sync through this instead of hand-building query strings. */
export function attendanceUrlFor(lessonId: number, returnTo: string): string {
  const params = new URLSearchParams({ lesson: String(lessonId), returnTo })
  return `/app/attendance?${params.toString()}`
}
