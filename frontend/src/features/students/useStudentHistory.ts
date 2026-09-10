import { useQuery } from '@tanstack/react-query'

import { attendanceApi } from '@/api/attendance'
import { homeworkApi, homeworkResultsApi } from '@/api/homework'
import { lessonsApi } from '@/api/lessons'
import { fetchAllPages } from '@/lib/fetchAllPages'
import type { Lesson } from '@/types/academy'
import type { AttendanceRecord } from '@/types/attendance'
import type { Homework, HomeworkResult } from '@/types/homework'

export interface StudentHistoryRow {
  lesson: Lesson
  attendance: AttendanceRecord | undefined
  homework: Homework | undefined
  result: HomeworkResult | undefined
}

export interface StudentHistory {
  rows: StudentHistoryRow[]
  attendanceTotal: number
  attendancePercent: number | null
  homeworkAssigned: number
  homeworkCompleted: number
  homeworkCompletionPercent: number | null
  averageScore: number | null
}

/**
 * Everything here is a real join across already-scoped endpoints — lessons
 * for the student's group, homeworks for those lessons, and this student's
 * own attendance/results — never invented numbers.
 */
export function useStudentHistory(studentId: number | undefined, groupId: number | null | undefined) {
  return useQuery<StudentHistory>({
    queryKey: ['student-history', studentId, groupId],
    queryFn: async () => {
      const [lessons, homeworks, attendance, results] = await Promise.all([
        groupId
          ? fetchAllPages<Lesson>((page) => lessonsApi.list({ group: groupId, ordering: '-date', page }))
          : Promise.resolve([]),
        groupId ? fetchAllPages<Homework>((page) => homeworkApi.list({ group: groupId, page })) : Promise.resolve([]),
        fetchAllPages<AttendanceRecord>((page) => attendanceApi.list({ student: studentId, page })),
        fetchAllPages<HomeworkResult>((page) => homeworkResultsApi.list({ student: studentId, page })),
      ])

      const attendanceByLesson = new Map(attendance.map((record) => [record.lesson, record]))
      const homeworkByLesson = new Map(homeworks.map((homework) => [homework.lesson, homework]))
      const resultByHomework = new Map(results.map((result) => [result.homework, result]))

      const rows: StudentHistoryRow[] = lessons.map((lesson) => {
        const homework = homeworkByLesson.get(lesson.id)
        return {
          lesson,
          attendance: attendanceByLesson.get(lesson.id),
          homework,
          result: homework ? resultByHomework.get(homework.id) : undefined,
        }
      })

      const attended = attendance.filter((record) => record.status === 'present' || record.status === 'late').length
      const attendancePercent = attendance.length > 0 ? Math.round((attended / attendance.length) * 1000) / 10 : null

      const completed = results.filter((result) => result.status !== 'not_submitted').length
      const homeworkCompletionPercent = homeworks.length > 0 ? Math.round((completed / homeworks.length) * 1000) / 10 : null

      const scored = results.filter((result): result is HomeworkResult & { score: number } => result.score !== null)
      const averageScore =
        scored.length > 0 ? Math.round((scored.reduce((sum, result) => sum + result.score, 0) / scored.length) * 10) / 10 : null

      return {
        rows,
        attendanceTotal: attendance.length,
        attendancePercent,
        homeworkAssigned: homeworks.length,
        homeworkCompleted: completed,
        homeworkCompletionPercent,
        averageScore,
      }
    },
    enabled: studentId !== undefined,
  })
}
