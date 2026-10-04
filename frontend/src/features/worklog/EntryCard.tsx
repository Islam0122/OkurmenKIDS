import { CalendarClock, Clock, Pencil, Trash2, UserRound } from 'lucide-react'

import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import type { WorkLogEntry } from '@/types/worklog'
import { formatDate } from '@/utils/format'

import { PRIORITY_TONE, STATUS_TONE } from './formUi'

function Row({ label, value }: { label: string; value: string }) {
  if (!value) return null
  return (
    <div className="grid gap-0.5 sm:grid-cols-[9rem_1fr] sm:gap-3">
      <dt className="text-xs font-medium text-ink-muted sm:text-sm">{label}</dt>
      <dd className="whitespace-pre-line text-sm text-ink">{value}</dd>
    </div>
  )
}

/** One journal record or task: the five answers and its follow-up. */
export function EntryCard({
  entry,
  onEdit,
  onDelete,
}: {
  entry: WorkLogEntry
  onEdit?: (entry: WorkLogEntry) => void
  onDelete?: (entry: WorkLogEntry) => void
}) {
  const isTask = entry.entry_kind === 'task'
  const who = [entry.group_detail?.name, entry.teacher_detail?.name, entry.student_detail?.name, entry.with_whom]
    .filter(Boolean)
    .join(', ')
  const hasFollowUp = Boolean(entry.next_action || entry.deadline || isTask)

  return (
    <article className="rounded-xl border border-border bg-surface p-4" aria-label={entry.title || entry.work_type_label}>
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink-secondary">
            <span className="inline-flex items-center gap-1">
              <CalendarClock className="size-4 text-ink-muted" aria-hidden />
              {formatDate(entry.date)}
            </span>
            {entry.time_from ? (
              <span className="inline-flex items-center gap-1">
                <Clock className="size-4 text-ink-muted" aria-hidden />
                {entry.time_from.slice(0, 5)}
                {entry.time_to ? `–${entry.time_to.slice(0, 5)}` : ''}
              </span>
            ) : null}
            <Badge tone="info">{entry.work_type_label}</Badge>
          </p>
          <h3 className="mt-1 font-medium text-ink">{isTask ? entry.title : who || entry.work_type_label}</h3>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {hasFollowUp ? <Badge tone={STATUS_TONE[entry.effective_status]}>{entry.effective_status_label}</Badge> : null}
          {isTask || entry.priority !== 'medium' ? (
            <Badge tone={PRIORITY_TONE[entry.priority]}>{entry.priority_label}</Badge>
          ) : null}
          {entry.can_edit && onEdit ? (
            <Button variant="ghost" size="sm" aria-label="Изменить" onClick={() => onEdit(entry)}>
              <Pencil className="size-4" aria-hidden />
            </Button>
          ) : null}
          {entry.can_edit && onDelete ? (
            <Button variant="ghost" size="sm" aria-label="Удалить" onClick={() => onDelete(entry)}>
              <Trash2 className="size-4" aria-hidden />
            </Button>
          ) : null}
        </div>
      </header>

      <dl className="mt-3 space-y-2">
        {isTask ? <Row label="Связано с" value={who} /> : null}
        <Row label="Цель" value={entry.goal} />
        <Row label="Что сделано" value={entry.description} />
        <Row label="Результат" value={entry.result} />
        <Row label="Проблема" value={entry.problem} />
        <Row label="Решение" value={entry.decision} />
        <Row label="Что дальше" value={entry.next_action} />
        <Row
          label="Ответственный"
          value={[entry.responsible, entry.deadline ? `до ${formatDate(entry.deadline)}` : ''].filter(Boolean).join(', ')}
        />
        <Row label="Комментарий" value={entry.comment} />
      </dl>

      <footer className="mt-3 flex items-center gap-1 text-xs text-ink-muted">
        <UserRound className="size-3.5" aria-hidden />
        {entry.author.name}
      </footer>
    </article>
  )
}
