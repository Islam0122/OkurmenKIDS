import { Link } from 'react-router-dom'

import type { Homework } from '@/types/homework'
import { formatDate } from '@/utils/format'

export interface HomeworkCardProps {
  homework: Homework
  submitted?: number
  checked?: number
  pending?: number
  totalStudents?: number
}

export function HomeworkCard({ homework, submitted, checked, pending, totalStudents }: HomeworkCardProps) {
  return (
    <Link
      to={`/app/homework/${homework.id}`}
      className="block rounded-lg border border-border bg-surface p-4 transition-colors hover:border-brand-200 hover:bg-brand-50/40"
    >
      <p className="font-medium text-ink">{homework.title}</p>
      <p className="mt-1 text-sm text-ink-secondary">
        {homework.group_name} · {formatDate(homework.lesson_date, false)}
      </p>
      {homework.deadline ? <p className="mt-1 text-xs text-ink-muted">Срок сдачи: {formatDate(homework.deadline)}</p> : null}

      {totalStudents !== undefined ? (
        <div className="mt-3 flex flex-wrap gap-x-3 gap-y-1 text-xs">
          <span className="text-brand-700">Сдано: {submitted ?? 0}</span>
          <span className="text-ink-secondary">Проверено: {checked ?? 0}</span>
          <span className="text-warning">Ожидают: {pending ?? 0}</span>
        </div>
      ) : (
        <p className="mt-3 text-xs text-ink-muted">{homework.results_count} результатов</p>
      )}
    </Link>
  )
}
