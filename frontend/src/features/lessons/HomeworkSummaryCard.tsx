import { Eye } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import type { Lesson } from '@/types/academy'
import type { Homework } from '@/types/homework'
import { formatDate } from '@/utils/format'

export interface HomeworkSummaryCardProps {
  homework: Homework
  summary: Lesson['homework_summary']
  onView: () => void
}

/**
 * The one "Домашнее задание" card — shows the assignment itself plus its
 * real, backend-calculated grading progress (checked/pending, see
 * services.lesson_summary.homework_summary) and always offers its own way
 * in ("Посмотреть домашнее задание"), so results are reached through the
 * homework section itself rather than a separate action on the lesson
 * overview.
 */
export function HomeworkSummaryCard({ homework, summary, onView }: HomeworkSummaryCardProps) {
  return (
    <div className="rounded-xl border border-border bg-surface p-5">
      <p className="mb-2 text-sm font-medium text-ink-secondary">Домашнее задание</p>
      <p className="font-medium text-ink">{homework.title}</p>
      {homework.deadline ? <p className="mt-1 text-sm text-ink-secondary">Срок: {formatDate(homework.deadline)}</p> : null}
      <p className="mt-2 text-sm text-ink-secondary">
        {summary ? `${summary.results_total} результатов` : `${homework.results_count} результатов`}
        {summary ? ` · Проверено ${summary.checked} из ${summary.results_total}` : ''}
      </p>
      <div className="mt-3">
        <Button variant="secondary" size="sm" leftIcon={<Eye className="size-4" aria-hidden />} onClick={onView}>
          Посмотреть домашнее задание
        </Button>
      </div>
    </div>
  )
}
