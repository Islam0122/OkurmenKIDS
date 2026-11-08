import axios from 'axios'

import { API_BASE_URL } from '@/api/client'

/** A bare client: no auth header, no refresh-on-401 — the public gallery
 * never sends a visitor's (or a staff member's) token anywhere. */
const publicClient = axios.create({ baseURL: API_BASE_URL })

export const PROJECT_CATEGORIES = ['all', 'html-css', 'javascript', 'react', 'python', 'other'] as const
export type ProjectCategory = (typeof PROJECT_CATEGORIES)[number]

/** `GET /public/projects/` item — the backend's closed whitelist (apps.projects.public). */
export interface PublicProjectSummary {
  key: string
  title: string
  short_description: string
  technologies: string[]
  categories: Exclude<ProjectCategory, 'all'>[]
  /** ISO date of the project. */
  date: string
  /** «Алия С.» — or null when the student's name is not published. */
  student: string | null
  group: string | null
  cover_url: string | null
}

export interface PublicProject extends PublicProjectSummary {
  description: string
  /** Only when the academy allows trainer names (PUBLIC_PROJECTS_SHOW_TRAINER). */
  trainer: string | null
  demo_url: string | null
  images: { url: string; is_cover: boolean }[]
}

export interface PublicProjectPage {
  count: number
  page: number
  page_size: number
  num_pages: number
  counts: Record<ProjectCategory, number>
  results: PublicProjectSummary[]
}

export interface GalleryParams {
  q?: string
  category?: ProjectCategory
  page?: number
  page_size?: number
}

function clean(params: object): Record<string, string | number> {
  return Object.fromEntries(Object.entries(params).filter(([key, v]) => v !== undefined && v !== null && v !== '' && !(key === 'category' && v === 'all')))
}

export const publicProjectsApi = {
  list: (params: GalleryParams) =>
    publicClient.get<PublicProjectPage>('/public/projects/', { params: clean(params) }).then((r) => r.data),
  detail: (key: string) => publicClient.get<PublicProject>(`/public/projects/${encodeURIComponent(key)}/`).then((r) => r.data),
}
