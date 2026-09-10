import { useQuery } from '@tanstack/react-query'

import { attendanceApi } from '@/api/attendance'
import { groupsApi } from '@/api/groups'
import { homeworkResultsApi } from '@/api/homework'
import { lessonsApi } from '@/api/lessons'
import { fetchAllPages } from '@/lib/fetchAllPages'
import type { Group, Lesson } from '@/types/academy'
import type { AttendanceRecord } from '@/types/attendance'

/** Local calendar date as `YYYY-MM-DD` — `toISOString()` alone would shift across midnight in timezones ahead of UTC. */
export function todayISO(): string {
  const now = new Date()
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 10)
}

export interface DashboardData {
  today: string
  lessonsToday: Lesson[]
  nextLesson: Lesson | null
  studentsToday: number
  attendancePercentToday: number | null
  pendingHomeworkCount: number
}

/** Every number here comes straight from real endpoints — nothing computed on invented data. */
export function useDashboardData() {
  const today = todayISO()

  return useQuery<DashboardData>({
    queryKey: ['dashboard', today],
    queryFn: async () => {
      const [lessonsTodayResponse, groups, attendanceToday, pendingHomework] = await Promise.all([
        lessonsApi.list({ date: today, ordering: 'start_time' }),
        fetchAllPages<Group>((page) => groupsApi.list({ page })),
        fetchAllPages<AttendanceRecord>((page) => attendanceApi.list({ date: today, page })),
        homeworkResultsApi.list({ status: 'submitted', page: 1 }),
      ])

      const lessonsToday = lessonsTodayResponse.results
      const groupIdsToday = new Set(lessonsToday.map((lesson) => lesson.group))
      const studentsToday = groups
        .filter((group) => groupIdsToday.has(group.id))
        .reduce((sum, group) => sum + group.students_count, 0)

      const attended = attendanceToday.filter(
        (record) => record.status === 'present' || record.status === 'late',
      ).length
      const attendancePercentToday =
        attendanceToday.length > 0 ? Math.round((attended / attendanceToday.length) * 1000) / 10 : null

      const now = new Date()
      const nowMinutes = now.getHours() * 60 + now.getMinutes()
      const nextLesson =
        lessonsToday.find((lesson) => {
          if (lesson.status === 'cancelled') return false
          const [hours, minutes] = lesson.start_time.split(':').map(Number)
          return hours * 60 + minutes >= nowMinutes
        }) ?? null

      return {
        today,
        lessonsToday,
        nextLesson,
        studentsToday,
        attendancePercentToday,
        pendingHomeworkCount: pendingHomework.count,
      }
    },
  })
}
