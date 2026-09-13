import { useMemo } from 'react'
import { useQueries } from '@tanstack/react-query'

import { homeworkApi } from '@/api/homework'
import { lessonsApi } from '@/api/lessons'

/**
 * A completed Lesson's `status` field only says the class happened — it says
 * nothing about whether the teacher actually finished their side of it. This
 * is that real, derived state, for a bounded page of completed lessons.
 */
export type LessonOperationalStatus = 'complete' | 'attendance_missing' | 'homework_missing' | 'checking_pending'

export const OPERATIONAL_STATUS_LABELS: Record<LessonOperationalStatus, string> = {
  complete: 'Полностью выполнено',
  attendance_missing: 'Не отмечена посещаемость',
  homework_missing: 'Не добавлено ДЗ',
  checking_pending: 'Требуется проверка ДЗ',
}

export function useLessonOperationalStatus(lessonIds: number[]): Map<number, LessonOperationalStatus> {
  const attendanceQueries = useQueries({
    queries: lessonIds.map((id) => ({
      queryKey: ['lessons', 'detail', id, 'attendance'],
      queryFn: () => lessonsApi.getAttendanceRoster(id),
    })),
  })

  const homeworkQueries = useQueries({
    queries: lessonIds.map((id) => ({
      queryKey: ['homework', 'list', { lesson: id }],
      queryFn: () => homeworkApi.list({ lesson: id }),
    })),
  })

  const homeworkIds = lessonIds.map((_, index) => homeworkQueries[index]?.data?.results[0]?.id ?? null)

  const homeworkResultQueries = useQueries({
    queries: homeworkIds.map((homeworkId) => ({
      queryKey: ['homework', 'detail', homeworkId, 'results'],
      queryFn: () => homeworkApi.getResultsRoster(homeworkId as number),
      enabled: homeworkId !== null,
    })),
  })

  return useMemo(() => {
    const map = new Map<number, LessonOperationalStatus>()
    lessonIds.forEach((id, index) => {
      const roster = attendanceQueries[index]?.data
      const homework = homeworkQueries[index]?.data
      if (!roster || !homework) return

      const attendanceFilled = roster.length === 0 || roster.every((row) => row.status !== null)
      if (!attendanceFilled) {
        map.set(id, 'attendance_missing')
        return
      }
      if (homework.count === 0) {
        map.set(id, 'homework_missing')
        return
      }
      const resultsRoster = homeworkResultQueries[index]?.data
      if (!resultsRoster) return
      const pendingChecks = resultsRoster.filter((row) => row.status === 'submitted' || row.status === 'late').length
      map.set(id, pendingChecks > 0 ? 'checking_pending' : 'complete')
    })
    return map
  }, [lessonIds, attendanceQueries, homeworkQueries, homeworkResultQueries])
}
