import { History } from 'lucide-react'

import { Badge } from '@/components/ui/Badge'
import { EmptyState } from '@/components/ui/EmptyState'
import type { AssistantLesson, HistoryRow } from '@/types/assistant'
import { formatDate, formatDateShort } from '@/utils/format'

/** History timeline and lesson list, shared by the group and student pages. */

export function HistoryList({ rows }: { rows: HistoryRow[] }) {
  if (rows.length === 0) return <EmptyState icon={History} title="История пока пуста" className="py-6" />
  return (
    <ol className="relative space-y-4 border-l border-border pl-5">
      {rows.map((row) => (
        <li key={row.id} className="relative">
          <span className="absolute top-1.5 -left-[25px] size-2.5 rounded-full border-2 border-surface bg-brand-500" aria-hidden />
          <p className="text-sm font-medium text-ink">{row.title}</p>
          {row.reason || row.comment ? (
            <p className="text-sm text-ink-secondary">{[row.reason, row.comment].filter(Boolean).join(' — ')}</p>
          ) : null}
          <p className="text-xs text-ink-muted">{formatDateShort(row.date)}{row.performed_by ? ` · ${row.performed_by}` : ''}</p>
        </li>
      ))}
    </ol>
  )
}

export function LessonList({ lessons, empty }: { lessons: AssistantLesson[]; empty: string }) {
  if (lessons.length === 0) return <p className="text-sm text-ink-secondary">{empty}</p>
  return (
    <ul className="divide-y divide-border">
      {lessons.map((lesson) => (
        <li key={lesson.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5 text-sm">
          <div className="min-w-0">
            <p className="font-medium text-ink">{formatDate(lesson.date, false)} · {lesson.start}–{lesson.end}</p>
            <p className="truncate text-ink-secondary">
              №{lesson.lesson_number} {lesson.topic || lesson.subject?.name || ''} · {lesson.teacher?.name ?? '—'}
            </p>
          </div>
          <Badge tone={lesson.status === 'completed' ? 'success' : lesson.status === 'cancelled' ? 'danger' : lesson.status === 'in_progress' ? 'info' : 'muted'}>
            {lesson.status_display}
          </Badge>
        </li>
      ))}
    </ul>
  )
}
