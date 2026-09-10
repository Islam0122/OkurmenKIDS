import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { attendanceApi, type AttendanceListParams } from '@/api/attendance'
import { lessonsApi } from '@/api/lessons'
import type { BulkAttendanceItem } from '@/types/attendance'

export function useAttendanceRoster(lessonId: number | undefined) {
  return useQuery({
    queryKey: ['lessons', 'detail', lessonId, 'attendance'],
    queryFn: () => lessonsApi.getAttendanceRoster(lessonId as number),
    enabled: lessonId !== undefined,
  })
}

export function useAttendanceList(params: AttendanceListParams) {
  return useQuery({
    queryKey: ['attendance', 'list', params],
    queryFn: () => attendanceApi.list(params),
  })
}

export function useSaveAttendance(lessonId: number) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (items: BulkAttendanceItem[]) => lessonsApi.saveAttendance(lessonId, items),
    onSuccess: () => {
      // Attendance feeds the lesson card, the group/student stats and KPI —
      // invalidate everything downstream rather than trying to patch each cache by hand.
      void queryClient.invalidateQueries({ queryKey: ['lessons', 'detail', lessonId] })
      void queryClient.invalidateQueries({ queryKey: ['lessons', 'list'] })
      void queryClient.invalidateQueries({ queryKey: ['attendance'] })
      void queryClient.invalidateQueries({ queryKey: ['kpi'] })
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}
