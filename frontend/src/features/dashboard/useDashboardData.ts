import { useQuery } from '@tanstack/react-query'

import { attendanceApi } from '@/api/attendance'
import { groupsApi } from '@/api/groups'
import { homeworkResultsApi } from '@/api/homework'
import { lessonsApi } from '@/api/lessons'
import { hasLessonPassed, tomorrowISO, upcomingWindow } from '@/features/lessons/lessonViews'
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
  /** Up to 5, for the dashboard's "Завтра" section — the full day lives at `/app/lessons?view=tomorrow`. */
  tomorrowLessons: Lesson[]
  /** Up to 5 nearest lessons from now on (today's remaining + future days) — the rest live at `/app/lessons?view=upcoming`. */
  upcomingLessons: Lesson[]
  studentsToday: number
  attendancePercentToday: number | null
  pendingHomeworkCount: number
}

const DASHBOARD_PREVIEW_COUNT = 5

/** Every number here comes straight from real endpoints — nothing computed on invented data. */
export function useDashboardData() {
  const today = todayISO()

  return useQuery<DashboardData>({
    queryKey: ['dashboard', today],
    queryFn: async () => {
      const [lessonsTodayResponse, tomorrowResponse, upcomingLessonsRaw, groups, attendanceToday, pendingHomework] =
        await Promise.all([
          lessonsApi.list({ date: today, ordering: 'start_time' }),
          lessonsApi.list({ date: tomorrowISO(), ordering: 'start_time' }),
          fetchAllPages<Lesson>((page) =>
            lessonsApi.list({ date_from: today, date_to: upcomingWindow().to, ordering: 'date,start_time', page }),
          ),
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

      const upcomingLessons = upcomingLessonsRaw
        .filter((lesson) => lesson.status !== 'cancelled' && !hasLessonPassed(lesson, now))
        .slice(0, DASHBOARD_PREVIEW_COUNT)

      return {
        today,
        lessonsToday,
        nextLesson,
        tomorrowLessons: tomorrowResponse.results.slice(0, DASHBOARD_PREVIEW_COUNT),
        upcomingLessons,
        studentsToday,
        attendancePercentToday,
        pendingHomeworkCount: pendingHomework.count,
      }
    },
  })
}
