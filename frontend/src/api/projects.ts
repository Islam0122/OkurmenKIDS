import type { AxiosProgressEvent } from 'axios'

import { apiClient } from '@/api/client'
import type { Paginated } from '@/types/common'
import type {
  ProjectDetail,
  ProjectFilters,
  ProjectImage,
  ProjectInput,
  ProjectListItem,
  ProjectOptions,
  ProjectStats,
} from '@/types/projects'

const BASE = '/projects'

function clean(filters: ProjectFilters): Record<string, string | number> {
  return Object.fromEntries(Object.entries(filters).filter(([, value]) => value !== undefined && value !== '')) as Record<string, string | number>
}

export const projectsApi = {
  list: async (filters: ProjectFilters = {}) =>
    (await apiClient.get<Paginated<ProjectListItem>>(`${BASE}/`, { params: clean(filters) })).data,
  get: async (id: number) => (await apiClient.get<ProjectDetail>(`${BASE}/${id}/`)).data,
  stats: async () => (await apiClient.get<ProjectStats>(`${BASE}/stats/`)).data,
  options: async () => (await apiClient.get<ProjectOptions>(`${BASE}/options/`)).data,
  create: async (data: ProjectInput) => (await apiClient.post<ProjectDetail>(`${BASE}/`, data)).data,
  update: async (id: number, data: Partial<ProjectInput>) => (await apiClient.patch<ProjectDetail>(`${BASE}/${id}/`, data)).data,
  remove: async (id: number) => {
    await apiClient.delete(`${BASE}/${id}/`)
  },
  uploadImage: async (id: number, file: File, isCover: boolean, onProgress?: (percent: number) => void) => {
    const form = new FormData()
    form.append('image', file)
    form.append('is_cover', isCover ? 'true' : 'false')
    const { data } = await apiClient.post<ProjectImage>(`${BASE}/${id}/images/`, form, {
      onUploadProgress: (event: AxiosProgressEvent) => {
        if (onProgress && event.total) onProgress(Math.round((event.loaded / event.total) * 100))
      },
    })
    return data
  },
  setCover: async (id: number, imageId: number) =>
    (await apiClient.patch<ProjectImage>(`${BASE}/${id}/images/${imageId}/`, { is_cover: true })).data,
  removeImage: async (id: number, imageId: number) => {
    await apiClient.delete(`${BASE}/${id}/images/${imageId}/`)
  },
}
