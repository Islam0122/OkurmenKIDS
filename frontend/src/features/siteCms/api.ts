import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiClient } from '@/api/client'
import type { Paginated } from '@/types/common'

import { CmsFormatError } from './errors'
import { parseOverview } from './overview'

export { CmsFormatError, cmsErrorMessage } from './errors'

/**
 * CMS публичного сайта (okurmen-public-website) — backend apps.website.cms,
 * /api/v1/marketing/site/. Права проверяет сервер: контент — маркетинг,
 * директор, администратор; заявки — ещё и отдел продаж.
 */
const BASE = '/marketing/site'

export type ResourceKey = 'courses' | 'events' | 'achievements' | 'news' | 'team' | 'testimonials' | 'stats' | 'branches' | 'banners'
export type Row = Record<string, unknown> & { id: number }
export type WorkflowState = 'draft' | 'review' | 'scheduled' | 'published' | 'archived'

export interface Choice {
  value: string
  label: string
}

export interface SiteMeta {
  permissions: { can_edit: boolean; can_approve: boolean; require_approval: boolean; can_delete_leads: boolean }
  public_site_url: string | null
  user_id?: number
  /** Who can be responsible for a lead. */
  staff?: { id: number; name: string; role: string }[]
  choices: Record<string, Choice[]>
  lms?: {
    courses: { id: number; name: string; lessons: number }[]
    teachers: { id: number; name: string; position: string }[]
    projects: { id: number; title: string; date: string }[]
    news: { id: number; title: string; published_at: string }[]
  }
}

export type Body = Record<string, unknown>

/** One CMS record as the dashboard sees it (backend cms.CONTENT_TYPES). */
export interface ContentSummary {
  resource: string
  type_label: string
  id: number
  title: string
  state: WorkflowState
  cover: string | null
  updated_at: string
  published_at: string
  /** cover · excerpt · ky · en · seo — what is still missing. */
  issues: ('cover' | 'excerpt' | 'ky' | 'en' | 'seo')[]
}

export type StateCounts = Record<WorkflowState, number>

/**
 * GET /marketing/site/overview/ after `parseOverview` (overview.ts). `null`
 * means «the server did not send this» (e.g. a server without the latest
 * update) — pages show it as unavailable instead of crashing or inventing data.
 */
export interface Overview {
  courses: StateCounts | null
  events: StateCounts | null
  achievements: StateCounts | null
  news: StateCounts | null
  team: StateCounts | null
  testimonials: StateCounts | null
  leads_new: number | null
  leads_by_status: Record<string, number> | null
  registrations_new: number | null
  upcoming_events: number | null
  media: number | null
  projects: number | null
  featured_projects: number | null
  recent: ContentSummary[] | null
  recently_published: ContentSummary[] | null
  drafts: ContentSummary[] | null
  attention: ContentSummary[] | null
  coverage: Record<string, { total: number; ky: number; en: number; seo: number }> | null
}

export interface CmsProject {
  id: number
  title: string
  short_description: string
  student: string | null
  group: string | null
  date: string
  technologies: string[]
  cover: string | null
  public_url: string | null
  is_featured: boolean
}

/** JSON, or multipart when a File is present (cover, photo…). `null` clears an image. */
function payload(body: Body): Body | FormData {
  const hasFile = Object.values(body).some((v) => v instanceof File)
  if (!hasFile) return body
  const form = new FormData()
  for (const [key, value] of Object.entries(body)) {
    if (value === undefined) continue
    if (value instanceof File) form.append(key, value)
    else if (Array.isArray(value)) value.forEach((v) => form.append(key, String(v)))
    else form.append(key, value === null ? '' : String(value))
  }
  return form
}

export const siteCmsApi = {
  meta: () => apiClient.get<SiteMeta>(`${BASE}/meta/`).then((r) => r.data),
  overview: () => apiClient.get<unknown>(`${BASE}/overview/`).then((r) => parseOverview(r.data)),
  projects: (search?: string) => apiClient.get<{ count: number; results: CmsProject[] }>(`${BASE}/projects/`, { params: { search: search || undefined } }).then((r) => r.data),
  featureProject: (id: number, featured: boolean) => apiClient.post(`${BASE}/projects/`, { id, featured }).then((r) => r.data),
  list: (resource: string, params: Record<string, unknown>) =>
    apiClient.get<unknown>(`${BASE}/${resource}/`, { params }).then((r) => parseList(r.data)),
  save: (resource: string, id: number | null, body: Body) =>
    (id === null ? apiClient.post<Row>(`${BASE}/${resource}/`, payload(body)) : apiClient.patch<Row>(`${BASE}/${resource}/${id}/`, payload(body))).then((r) => r.data),
  remove: (resource: string, id: number) => apiClient.delete(`${BASE}/${resource}/${id}/`).then(() => undefined),
  action: (resource: string, id: number, name: string, body: Body = {}) =>
    apiClient.post<Row>(`${BASE}/${resource}/${id}/${name}/`, body).then((r) => r.data),
  addPhotos: (resource: string, id: number, files: File[]) => {
    const form = new FormData()
    files.forEach((f) => form.append('files', f))
    return apiClient.post<Row>(`${BASE}/${resource}/${id}/photos/`, form).then((r) => r.data)
  },
  /** Gallery photos picked from the media library (copied on the server). */
  addLibraryPhotos: (resource: string, id: number, media: number[]) =>
    apiClient.post<Row>(`${BASE}/${resource}/${id}/photos/`, { media }).then((r) => r.data),
  updatePhoto: (resource: string, id: number, photoId: number, body: { caption?: string; order?: number }) =>
    apiClient.patch<Row>(`${BASE}/${resource}/${id}/photos/${photoId}/`, body).then((r) => r.data),
  deletePhoto: (resource: string, id: number, photoId: number) =>
    apiClient.delete<Row>(`${BASE}/${resource}/${id}/photos/${photoId}/`).then((r) => r.data),
  settings: () => apiClient.get<Row>(`${BASE}/settings/`).then((r) => r.data),
  saveSettings: (body: Body) => apiClient.patch<Row>(`${BASE}/settings/`, payload(body)).then((r) => r.data),
  sections: () => apiClient.get<Row[]>(`${BASE}/sections/`).then((r) => r.data),
  saveSection: (id: number, body: Body) => apiClient.patch<Row>(`${BASE}/sections/${id}/`, body).then((r) => r.data),
  reorderSections: (keys: string[]) => apiClient.post<Row[]>(`${BASE}/sections/reorder/`, { keys }).then((r) => r.data),
}

/** A CMS list is either a plain array (small lookups) or a DRF page `{count, results}`; anything else is an error, not an empty list. */
function parseList(data: unknown): Paginated<Row> | Row[] {
  if (Array.isArray(data)) return data as Row[]
  if (typeof data === 'object' && data !== null && Array.isArray((data as Paginated<Row>).results)) {
    const page = data as Paginated<Row>
    return { ...page, count: typeof page.count === 'number' ? page.count : page.results.length }
  }
  throw new CmsFormatError('список')
}

export const toList = (data: Paginated<Row> | Row[] | undefined): { rows: Row[]; count: number } =>
  !data ? { rows: [], count: 0 } : Array.isArray(data) ? { rows: data, count: data.length } : { rows: data.results, count: data.count }

export function useSiteOverview(enabled = true) {
  return useQuery({ queryKey: ['site-cms', 'overview'], queryFn: siteCmsApi.overview, enabled })
}

export function useSiteSettings() {
  return useQuery({ queryKey: ['site-cms', 'settings'], queryFn: siteCmsApi.settings })
}

export function useSiteMeta() {
  return useQuery({ queryKey: ['site-cms', 'meta'], queryFn: siteCmsApi.meta, staleTime: 5 * 60_000 })
}

export function useSiteList(resource: string, params: Record<string, unknown>, enabled = true) {
  return useQuery({ queryKey: ['site-cms', resource, params], queryFn: () => siteCmsApi.list(resource, params), placeholderData: keepPreviousData, enabled })
}

/** One record (for the editor page). */
export function useSiteItem(resource: string, id: number | null) {
  return useQuery({
    queryKey: ['site-cms', resource, 'item', id],
    queryFn: () => apiClient.get<Row>(`${BASE}/${resource}/${id}/`).then((r) => r.data),
    enabled: id !== null,
    staleTime: 0,
  })
}

/** Invalidate everything of the CMS after a change (lists, overview, meta options). */
export function useSiteInvalidate() {
  const client = useQueryClient()
  return () => client.invalidateQueries({ queryKey: ['site-cms'] })
}

export function useSiteMutation<T>(fn: (arg: T) => Promise<unknown>) {
  const invalidate = useSiteInvalidate()
  return useMutation({ mutationFn: fn, onSuccess: () => invalidate() })
}
