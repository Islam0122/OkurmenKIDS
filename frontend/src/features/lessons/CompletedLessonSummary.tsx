import { AlarmClock, BookOpen, CheckCircle2, CheckCircle, Percent, Users, XCircle } from 'lucide-react'

import { StatCard } from '@/components/ui/StatCard'
import type { Lesson } from '@/types/academy'
import { ATTENDANCE_SUMMARY_LABELS } from '@/types/attendance'
import { formatDate } from '@/utils/format'

/**
 * The exact, required wording for a completed lesson — never "Завершено"
 * or an English "Completed" anywhere in this notice, so the terminology
 * never drifts from the status badge ("Проведено"). Kept to one compact
 * line (plus an optional "Провёл" fragment) rather than a tall banner —
 * this is a status line, not a section of its own.
 */
export function CompletedLessonNotice({ lesson }: { lesson: Lesson }) {
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-xl bg-brand-50 px-4 py-2.5 text-sm text-brand-700">
      <CheckCircle className="size-4 shrink-0" aria-hidden />
      <p className="font-medium">Занятие проведено и закрыто. Все данные сохранены. Редактирование недоступно.</p>
      {lesson.completed_by_name || lesson.completed_at ? (
        <p className="text-brand-600">
          Провёл{lesson.completed_by_name ? `: ${lesson.completed_by_name}` : ''}
          {lesson.completed_at ? ` · ${formatDate(lesson.completed_at)}` : ''}
        </p>
      ) : null}
    </div>
  )
}

/**
 * "Результаты занятия" — one balanced, real, backend-calculated KPI grid
 * (see services.lesson_summary on the backend, exposed as
 * `attendance_summary`/`homework_summary` on LessonSerializer). Always
 * exactly six tiles — attendance's excused breakdown and homework's
 * checked/pending/average detail live in their own section cards below,
 * not as extra tiles here — so the grid divides evenly at every
 * breakpoint (6/6/3/2 students-wide) and nothing ever wraps alone.
 */
export function CompletedLessonKpis({ lesson }: { lesson: Lesson }) {
  const attendance = lesson.attendance_summary
  const homework = lesson.homework_summary

  const homeworkValue = homework
    ? `${homework.checked}/${homework.results_total}`
    : lesson.homework_not_required
      ? 'Не требуется'
      : 'Не добавлено'

  const homeworkHint = homework
    ? homework.average_score !== null
      ? `Средний балл ${homework.average_score}`
      : homework.pending > 0
        ? `${homework.pending} на проверке`
        : 'Все проверены'
    : undefined

  return (
    <div>
      <p className="mb-3 text-sm font-medium text-ink-secondary">Результаты занятия</p>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <StatCard label="Студентов" value={attendance.total_students} icon={Users} />
        <StatCard label={ATTENDANCE_SUMMARY_LABELS.present} value={attendance.present} icon={CheckCircle2} />
        <StatCard label={ATTENDANCE_SUMMARY_LABELS.absent} value={attendance.absent} icon={XCircle} tone="danger" />
        <StatCard label={ATTENDANCE_SUMMARY_LABELS.late} value={attendance.late} icon={AlarmClock} tone="warning" />
        <StatCard
          label="Посещаемость"
          value={attendance.attendance_rate !== null ? `${attendance.attendance_rate}%` : '—'}
          icon={Percent}
        />
        <StatCard label="Домашнее задание" value={homeworkValue} hint={homeworkHint} icon={BookOpen} />
      </div>
    </div>
  )
}
