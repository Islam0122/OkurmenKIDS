import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { projectsApi } from '@/api/projects'
import type { ProjectFilters } from '@/types/projects'

export const PROJECTS_KEY = ['projects'] as const

export function useProjects(filters: ProjectFilters) {
  return useQuery({
    queryKey: [...PROJECTS_KEY, 'list', filters],
    queryFn: () => projectsApi.list(filters),
    placeholderData: keepPreviousData,
  })
}

export function useProject(id: number | undefined) {
  return useQuery({
    queryKey: [...PROJECTS_KEY, 'detail', id],
    queryFn: () => projectsApi.get(id as number),
    enabled: id !== undefined && Number.isFinite(id),
  })
}

export function useProjectStats() {
  return useQuery({ queryKey: [...PROJECTS_KEY, 'stats'], queryFn: projectsApi.stats })
}

export function useProjectOptions() {
  return useQuery({ queryKey: [...PROJECTS_KEY, 'options'], queryFn: projectsApi.options, staleTime: 60_000 })
}

/** Lists, stats, options and the detail page all change together. */
export function useInvalidateProjects() {
  const qc = useQueryClient()
  return () => qc.invalidateQueries({ queryKey: PROJECTS_KEY })
}

export function useDeleteProject() {
  const invalidate = useInvalidateProjects()
  return useMutation({ mutationFn: (id: number) => projectsApi.remove(id), onSuccess: () => invalidate() })
}
