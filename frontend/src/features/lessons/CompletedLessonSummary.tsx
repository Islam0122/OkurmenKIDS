import { AlarmClock, Award, BookOpen, CheckCircle2, Hourglass, Percent, ShieldQuestion, Users, XCircle } from 'lucide-react'

import { StatCard } from '@/components/ui/StatCard'
import type { Lesson } from '@/types/academy'
import { ATTENDANCE_SUMMARY_LABELS } from '@/types/attendance'
import { formatDate } from '@/utils/format'

/**
 * The exact, required wording for a completed lesson — never "Завершено"
 * or an English "Completed" anywhere in this notice, so the terminology
 * never drifts from the status badge ("Проведено").
 */
export function CompletedLessonNotice({ lesson }: { lesson: Lesson }) {
  return (
    <div className="mb-6 rounded-lg bg-brand-50 px-4 py-3 text-sm text-brand-700">
      <p className="font-medium">Занятие проведено и закрыто. Все данные сохранены. Редактирование недоступно.</p>
      {lesson.completed_by_name || lesson.completed_at ? (
        <p className="mt-1 text-brand-600">
          Провёл{lesson.completed_by_name ? `: ${lesson.completed_by_name}` : ''}
          {lesson.completed_at ? ` · ${formatDate(lesson.completed_at)}` : ''}
        </p>
      ) : null}
    </div>
  )
}

/**
 * "Итоги занятия" — a real, backend-calculated KPI grid (see
 * services.lesson_summary on the backend, exposed as `attendance_summary`/
 * `homework_summary` on LessonSerializer). Every tile is either a plain
 * copy of an API number or a trivial ratio of two API numbers ("3 из 3") —
 * nothing here is estimated or invented on the frontend.
 */
export function CompletedLessonKpis({ lesson }: { lesson: Lesson }) {
  const attendance = lesson.attendance_summary
  const homework = lesson.homework_summary

  const homeworkStatusLabel = homework
    ? 'ДЗ выдано'
    : lesson.homework_not_required
      ? 'ДЗ не требуется'
      : 'ДЗ не добавлено'

  return (
    <div className="mb-6">
      <p className="mb-3 text-sm font-medium text-ink-secondary">Итоги занятия</p>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">
        <StatCard label="Студентов" value={attendance.total_students} icon={Users} />
        <StatCard label={ATTENDANCE_SUMMARY_LABELS.present} value={attendance.present} icon={CheckCircle2} />
        <StatCard label={ATTENDANCE_SUMMARY_LABELS.absent} value={attendance.absent} icon={XCircle} tone="danger" />
        <StatCard label={ATTENDANCE_SUMMARY_LABELS.late} value={attendance.late} icon={AlarmClock} tone="warning" />
        <StatCard label={ATTENDANCE_SUMMARY_LABELS.excused} value={attendance.excused} icon={ShieldQuestion} />
        <StatCard
          label="Посещаемость"
          value={attendance.attendance_rate !== null ? `${attendance.attendance_rate}%` : '—'}
          icon={Percent}
        />
        <StatCard label="Домашнее задание" value={homeworkStatusLabel} icon={BookOpen} />
        {homework ? (
          <>
            <StatCard label="Результатов сдано" value={homework.results_total} icon={BookOpen} />
            <StatCard label="Проверено" value={`${homework.checked} из ${homework.results_total}`} icon={CheckCircle2} />
            {homework.pending > 0 ? (
              <StatCard label="Ожидают проверки" value={homework.pending} icon={Hourglass} tone="warning" />
            ) : null}
            {homework.average_score !== null ? (
              <StatCard label="Средний балл" value={`${homework.average_score} / 10`} icon={Award} />
            ) : null}
          </>
        ) : null}
      </div>
    </div>
  )
}
