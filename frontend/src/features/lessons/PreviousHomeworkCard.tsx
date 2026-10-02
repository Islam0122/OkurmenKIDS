import { ClipboardCheck } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import type { Lesson } from '@/types/academy'
import { formatDate } from '@/utils/format'

export interface PreviousHomeworkCardProps {
  lesson: Lesson
  onCheck: (homeworkId: number) => void
}

/**
 * "Проверка ДЗ прошлого занятия" — homework N-1 is set in lesson N-1 and
 * checked during lesson N. Homework stays attached to the lesson it was set
 * in (see LessonSerializer.homework_to_check); this card only gives lesson N
 * a way into the existing homework grading page. Hidden on the program's
 * first lesson (no `previous_lesson`).
 */
export function PreviousHomeworkCard({ lesson, onCheck }: PreviousHomeworkCardProps) {
  const previous = lesson.previous_lesson
  if (!previous) return null
  const homework = lesson.homework_to_check

  return (
    <div className="card card-body" data-testid="previous-homework-card">
      <h2 className="section-title mb-3">📝 Проверка ДЗ прошлого занятия</h2>
      <p className="text-sm text-ink-secondary">
        Урок №{previous.lesson_number}
        {previous.date ? ` · ${formatDate(previous.date)}` : ''}
      </p>
      {previous.topic ? <p className="mt-0.5 text-sm font-medium text-ink">{previous.topic}</p> : null}

      {homework ? (
        <>
          <div className="mt-3 border-t border-border pt-3">
            <p className="font-medium text-ink">{homework.title}</p>
            {homework.description ? <p className="mt-1 text-sm text-ink-secondary">{homework.description}</p> : null}
            {homework.deadline ? <p className="mt-1 text-sm text-ink-secondary">Срок: {formatDate(homework.deadline)}</p> : null}
            <p className="mt-2 text-sm text-ink-secondary">
              {homework.results_summary.results_total} результатов · проверено {homework.results_summary.checked}, ожидает{' '}
              {homework.results_summary.pending}
            </p>
          </div>
          {homework.can_check ? (
            <div className="pt-3">
              <Button
                variant="secondary"
                size="sm"
                leftIcon={<ClipboardCheck className="size-4" aria-hidden />}
                onClick={() => onCheck(homework.id)}
              >
                Проверить ДЗ
              </Button>
            </div>
          ) : (
            <p className="mt-3 text-xs text-ink-secondary">Это ДЗ проверяет тренер, который вёл прошлое занятие.</p>
          )}
        </>
      ) : (
        <p className="mt-3 text-sm text-ink-secondary">На предыдущем занятии домашнее задание не задавалось.</p>
      )}
    </div>
  )
}
