import { useQuery } from '@tanstack/react-query'

import { kpiApi, type KPIListParams } from '@/api/kpi'

export function useKPIGroups(params: KPIListParams) {
  return useQuery({
    queryKey: ['kpi', 'groups', params],
    queryFn: () => kpiApi.groups(params),
  })
}

export function useKPITeachers(params: KPIListParams) {
  return useQuery({
    queryKey: ['kpi', 'teachers', params],
    queryFn: () => kpiApi.teachers(params),
  })
}

export function useKPIStudents(params: KPIListParams) {
  return useQuery({
    queryKey: ['kpi', 'students', params],
    queryFn: () => kpiApi.students(params),
  })
}
