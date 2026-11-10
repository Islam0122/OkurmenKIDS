import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiClient } from '@/api/client'
import type { Paginated } from '@/types/common'

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
  choices: Record<string, Choice[]>
  lms?: {
    courses: { id: number; name: string; lessons: number }[]
    teachers: { id: number; name: string; position: string }[]
    projects: { id: number; title: string; date: string }[]
    news: { id: number; title: string; published_at: string }[]
  }
}

export type Body = Record<string, unknown>

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
  overview: () => apiClient.get<Record<string, Record<string, number> | number>>(`${BASE}/overview/`).then((r) => r.data),
  list: (resource: string, params: Record<string, unknown>) =>
    apiClient.get<Paginated<Row> | Row[]>(`${BASE}/${resource}/`, { params }).then((r) => r.data),
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

export const toList = (data: Paginated<Row> | Row[] | undefined): { rows: Row[]; count: number } =>
  !data ? { rows: [], count: 0 } : Array.isArray(data) ? { rows: data, count: data.length } : { rows: data.results, count: data.count }

export function useSiteMeta() {
  return useQuery({ queryKey: ['site-cms', 'meta'], queryFn: siteCmsApi.meta, staleTime: 5 * 60_000 })
}

export function useSiteList(resource: string, params: Record<string, unknown>) {
  return useQuery({ queryKey: ['site-cms', resource, params], queryFn: () => siteCmsApi.list(resource, params), placeholderData: keepPreviousData })
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
