import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { reportsApi } from '@/api/reports'
import type { ReportParams } from '@/types/reports'

export function useReportFilters() {
  return useQuery({ queryKey: ['reports', 'filters'], queryFn: () => reportsApi.filters(), staleTime: 5 * 60_000 })
}

export function useReportOverview(params: ReportParams) {
  return useQuery({ queryKey: ['reports', 'overview', params], queryFn: () => reportsApi.overview(params), placeholderData: keepPreviousData })
}

export function useReportTeachers(params: ReportParams) {
  return useQuery({ queryKey: ['reports', 'teachers', params], queryFn: () => reportsApi.teachers(params), placeholderData: keepPreviousData })
}

export function useReportTeacher(id: number, params: ReportParams) {
  return useQuery({
    queryKey: ['reports', 'teacher', id, params],
    queryFn: () => reportsApi.teacher(id, params),
    enabled: Number.isFinite(id),
    placeholderData: keepPreviousData,
  })
}

export function useReportGroups(params: ReportParams) {
  return useQuery({ queryKey: ['reports', 'groups', params], queryFn: () => reportsApi.groups(params), placeholderData: keepPreviousData })
}

export function useReportGroup(id: number, params: ReportParams, enabled = true) {
  return useQuery({
    queryKey: ['reports', 'group', id, params],
    queryFn: () => reportsApi.group(id, params),
    enabled: enabled && Number.isFinite(id),
    placeholderData: keepPreviousData,
  })
}

export function useReportSubjects(params: ReportParams) {
  return useQuery({ queryKey: ['reports', 'subjects', params], queryFn: () => reportsApi.subjects(params), placeholderData: keepPreviousData })
}

export function useReportStudents(params: ReportParams) {
  return useQuery({ queryKey: ['reports', 'students', params], queryFn: () => reportsApi.students(params), placeholderData: keepPreviousData })
}
