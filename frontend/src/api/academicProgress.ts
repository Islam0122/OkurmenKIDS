import { apiClient } from '@/api/client'
import type { GroupAcademicProgress, ProgramDetail, ProgramInput, ProgramRow, ProgressMeta } from '@/types/academicProgress'

const BASE = '/academic-progress'

export const academicProgressApi = {
  meta: async () => (await apiClient.get<ProgressMeta>(`${BASE}/meta/`)).data,
  programs: async () => (await apiClient.get<{ results: ProgramRow[] }>(`${BASE}/programs/`)).data.results,
  program: async (id: number) => (await apiClient.get<ProgramDetail>(`${BASE}/programs/${id}/`)).data,
  saveProgram: async (id: number, data: ProgramInput) => (await apiClient.put<ProgramDetail>(`${BASE}/programs/${id}/`, data)).data,
  group: async (id: number) => (await apiClient.get<GroupAcademicProgress>(`${BASE}/groups/${id}/`)).data,
  confirmHistory: async (id: number, lessonsBeforeLms: number, comment = '') =>
    (await apiClient.put<GroupAcademicProgress>(`${BASE}/groups/${id}/history/`, { lessons_before_lms: lessonsBeforeLms, comment })).data,
}
