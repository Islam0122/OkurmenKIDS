import { useMemo } from 'react'
import { useQueries } from '@tanstack/react-query'

import { homeworkApi } from '@/api/homework'
import { lessonsApi } from '@/api/lessons'

export interface LessonEnrichment {
  attendanceFilled: boolean
  homeworkCount: number
}

/**
 * Per-lesson "did the teacher actually finish this yet" status — attendance
 * marked + homework added — for a bounded set of already-happened lessons
 * (a day's worth, never a whole paginated list). Reuses the same query keys
 * as `useAttendanceRoster`/`useHomeworkList` so navigating into the lesson
 * itself hits a warm cache instead of refetching.
 */
export function useLessonEnrichment(lessonIds: number[]): Map<number, LessonEnrichment> {
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

  return useMemo(() => {
    const map = new Map<number, LessonEnrichment>()
    lessonIds.forEach((id, index) => {
      const roster = attendanceQueries[index]?.data
      const homework = homeworkQueries[index]?.data
      if (!roster || !homework) return
      map.set(id, {
        attendanceFilled: roster.length === 0 || roster.every((row) => row.status !== null),
        homeworkCount: homework.count,
      })
    })
    return map
  }, [lessonIds, attendanceQueries, homeworkQueries])
}
