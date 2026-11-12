/**
 * The «Обзор сайта» response (GET /marketing/site/overview/) checked at the
 * boundary, so no page reads fields the server did not send.
 *
 * Two server versions exist in practice: the current one (counters + lists:
 * recent, drafts, attention, coverage, projects) and the earlier one that
 * sends only counters (until the backend is updated and migrated). A field
 * that is missing becomes `null` — «not available», shown as such — never a
 * made-up zero or an invented row. A response that is not an object at all
 * (an HTML page from a wrong proxy, `null`) is an error.
 */
import type { ContentSummary, Overview, StateCounts, WorkflowState } from './api'
import { CmsFormatError } from './errors'

export const CONTENT_TYPES = ['courses', 'events', 'achievements', 'news', 'team', 'testimonials'] as const
const STATES: WorkflowState[] = ['draft', 'review', 'scheduled', 'published', 'archived']
const ISSUES = new Set(['cover', 'excerpt', 'ky', 'en', 'seo'])


const isObject = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)
const count = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)

/** Per-state counts. A state the server does not track for a type (news has no «review») is 0 — it truly has none. */
function stateCounts(v: unknown): StateCounts | null {
  if (!isObject(v)) return null
  return Object.fromEntries(STATES.map((s) => [s, count(v[s]) ?? 0])) as StateCounts
}

function summary(v: unknown): ContentSummary | null {
  if (!isObject(v) || typeof v.resource !== 'string' || typeof v.id !== 'number') return null
  return {
    resource: v.resource,
    type_label: typeof v.type_label === 'string' ? v.type_label : '',
    id: v.id,
    title: typeof v.title === 'string' && v.title ? v.title : '—',
    state: STATES.includes(v.state as WorkflowState) ? (v.state as WorkflowState) : 'draft',
    cover: typeof v.cover === 'string' ? v.cover : null,
    updated_at: typeof v.updated_at === 'string' ? v.updated_at : '',
    published_at: typeof v.published_at === 'string' ? v.published_at : '',
    issues: Array.isArray(v.issues) ? (v.issues.filter((i) => typeof i === 'string' && ISSUES.has(i)) as ContentSummary['issues']) : [],
  }
}

/** A list the server sent (malformed rows dropped), or null when it did not send one. */
function list(v: unknown): ContentSummary[] | null {
  if (!Array.isArray(v)) return null
  return v.map(summary).filter((row): row is ContentSummary => row !== null)
}

function numberMap(v: unknown): Record<string, number> | null {
  if (!isObject(v)) return null
  return Object.fromEntries(Object.entries(v).map(([k, n]) => [k, count(n) ?? 0]))
}

function coverage(v: unknown): Overview['coverage'] {
  if (!isObject(v)) return null
  const out: NonNullable<Overview['coverage']> = {}
  for (const [key, c] of Object.entries(v)) {
    if (isObject(c)) out[key] = { total: count(c.total) ?? 0, ky: count(c.ky) ?? 0, en: count(c.en) ?? 0, seo: count(c.seo) ?? 0 }
  }
  return out
}

export function parseOverview(raw: unknown): Overview {
  if (!isObject(raw)) throw new CmsFormatError('обзор сайта')
  const counts = Object.fromEntries(CONTENT_TYPES.map((key) => [key, stateCounts(raw[key])])) as Pick<Overview, (typeof CONTENT_TYPES)[number]>
  return {
    ...counts,
    leads_new: count(raw.leads_new),
    leads_by_status: numberMap(raw.leads_by_status),
    registrations_new: count(raw.registrations_new),
    upcoming_events: count(raw.upcoming_events),
    media: count(raw.media),
    projects: count(raw.projects),
    featured_projects: count(raw.featured_projects),
    recent: list(raw.recent),
    recently_published: list(raw.recently_published),
    drafts: list(raw.drafts),
    attention: list(raw.attention),
    coverage: coverage(raw.coverage),
  }
}
