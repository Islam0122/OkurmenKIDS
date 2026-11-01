import { useQuery } from '@tanstack/react-query'
import type { QueryKey } from '@tanstack/react-query'

import { reportsApi } from '@/api/reports'
import type { ReportParams } from '@/types/reports'

function samePeriod(a: ReportParams | undefined, b: ReportParams): boolean {
  return !!a && a.period === b.period && a.start_date === b.start_date && a.end_date === b.end_date
}

/**
 * Keep the previous page on screen while the next one loads — but only for
 * the same report (same key prefix: endpoint, trainer/group id) and the same
 * period, i.e. paging, search, sorting. After a period switch the old
 * figures must never stay up as if they were the new month's (regression:
 * September showed October's numbers); the page shows its loading state
 * until the selected period arrives.
 */
export function keepWithinPeriod<T>(key: QueryKey) {
  const params = key[key.length - 1] as ReportParams
  const prefix = JSON.stringify(key.slice(0, -1))
  return (previousData: T | undefined, previousQuery?: { queryKey: QueryKey }): T | undefined => {
    const previousKey = previousQuery?.queryKey
    if (!previousKey || JSON.stringify(previousKey.slice(0, -1)) !== prefix) return undefined
    return samePeriod(previousKey[previousKey.length - 1] as ReportParams | undefined, params) ? previousData : undefined
  }
}

function reportQuery<T>(key: QueryKey, queryFn: () => Promise<T>, enabled = true) {
  return { queryKey: key, queryFn, placeholderData: keepWithinPeriod<T>(key), enabled }
}

export function useReportFilters() {
  return useQuery({ queryKey: ['reports', 'filters'], queryFn: () => reportsApi.filters(), staleTime: 5 * 60_000 })
}

export function useReportOverview(params: ReportParams) {
  return useQuery(reportQuery(['reports', 'overview', params], () => reportsApi.overview(params)))
}

export function useReportTeachers(params: ReportParams) {
  return useQuery(reportQuery(['reports', 'teachers', params], () => reportsApi.teachers(params)))
}

export function useReportTeacher(id: number, params: ReportParams) {
  return useQuery(reportQuery(['reports', 'teacher', id, params], () => reportsApi.teacher(id, params), Number.isFinite(id)))
}

export function useReportGroups(params: ReportParams) {
  return useQuery(reportQuery(['reports', 'groups', params], () => reportsApi.groups(params)))
}

export function useReportGroup(id: number, params: ReportParams, enabled = true) {
  return useQuery(
    reportQuery(['reports', 'group', id, params], () => reportsApi.group(id, params), enabled && Number.isFinite(id)),
  )
}

export function useReportSubjects(params: ReportParams) {
  return useQuery(reportQuery(['reports', 'subjects', params], () => reportsApi.subjects(params)))
}

export function useReportStudents(params: ReportParams) {
  return useQuery(reportQuery(['reports', 'students', params], () => reportsApi.students(params)))
}
