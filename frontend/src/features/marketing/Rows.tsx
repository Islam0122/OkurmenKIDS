import { CalendarDays, Check, Clock3, UserRound } from 'lucide-react'

import { Badge } from '@/components/ui/Badge'
import { useToast } from '@/components/ui/Toast'
import { useSaveTask } from '@/hooks/useMarketing'
import { extractErrorMessage } from '@/lib/apiError'
import type { ContentItem, MarketingTask } from '@/types/marketing'
import { cn } from '@/utils/cn'

import { CONTENT_BORDER, CONTENT_TONE, PRIORITY_TONE, TASK_TONE, hhmm, shortDate } from './shared'

/** Публикация в списке: тема, канал и формат, дата, ответственный, статус. */
export function ContentRow({ item, onOpen }: { item: ContentItem; onOpen: (item: ContentItem) => void }) {
  return (
    <li>
      <button
        type="button"
        onClick={() => onOpen(item)}
        className={cn('flex w-full min-w-0 flex-col gap-1.5 border-l-4 px-4 py-3 text-left transition-colors hover:bg-surface-hover sm:flex-row sm:items-start sm:gap-3 sm:px-5', CONTENT_BORDER[item.status])}
      >
        <div className="min-w-0 flex-1">
          <p className="line-clamp-2 font-medium text-ink sm:truncate">{item.title}</p>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-ink-secondary">
            <span>{item.channel_label} · {item.format_label}</span>
            <span className="inline-flex items-center gap-1">
              <CalendarDays className="size-3.5" aria-hidden />
              {item.publish_date ? `${shortDate(item.publish_date, true)}${item.publish_time ? `, ${hhmm(item.publish_time)}` : ''}` : 'Без даты'}
            </span>
            {item.responsible_info ? (
              <span className="inline-flex min-w-0 items-center gap-1"><UserRound className="size-3.5 shrink-0" aria-hidden /><span className="truncate">{item.responsible_info.full_name}</span></span>
            ) : null}
          </p>
        </div>
        <Badge tone={CONTENT_TONE[item.status]} className="shrink-0 self-start">{item.status_label}</Badge>
      </button>
    </li>
  )
}

/** Задача в списке: кружок «выполнено» (быстрое действие) и карточка, по
 * нажатию на которую открывается редактирование. */
export function TaskRow({ task, onOpen }: { task: MarketingTask; onOpen: (task: MarketingTask) => void }) {
  const save = useSaveTask()
  const { showToast } = useToast()
  const done = task.status === 'done'

  const toggle = () =>
    save.mutate({ id: task.id, body: { status: done ? 'todo' : 'done' } }, {
      onSuccess: () => showToast(done ? 'Задача снова открыта' : 'Задача выполнена', 'success'),
      onError: (e) => showToast(extractErrorMessage(e), 'error'),
    })

  return (
    <li className="flex min-w-0 items-start gap-1 px-2 sm:px-3">
      <button
        type="button"
        onClick={toggle}
        disabled={save.isPending}
        aria-label={done ? `Вернуть в работу: ${task.title}` : `Отметить выполненной: ${task.title}`}
        aria-pressed={done}
        className="flex size-11 shrink-0 items-center justify-center rounded-full disabled:opacity-50"
      >
        <span className={cn('flex size-6 items-center justify-center rounded-full border-2 transition-colors', done ? 'border-brand-500 bg-brand-500 text-white' : 'border-border-strong text-transparent hover:border-brand-500 hover:text-brand-500')}>
          <Check className="size-3.5" strokeWidth={3} aria-hidden />
        </span>
      </button>
      <button type="button" onClick={() => onOpen(task)} className="flex min-w-0 flex-1 flex-col gap-1.5 rounded-lg py-3 pr-2 text-left transition-colors hover:bg-surface-hover sm:flex-row sm:items-start sm:gap-3 sm:pr-3">
        <div className="min-w-0 flex-1 pl-1">
          <p className={cn('line-clamp-2 font-medium sm:truncate', done ? 'text-ink-muted line-through' : 'text-ink')}>{task.title}</p>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-ink-secondary">
            <span className={cn('inline-flex items-center gap-1', task.is_overdue && 'font-medium text-danger')}>
              <Clock3 className="size-3.5" aria-hidden />
              {task.due_date ? `${task.is_overdue ? 'Просрочено: ' : 'до '}${shortDate(task.due_date, true)}` : 'Без срока'}
            </span>
            {task.responsible_info ? (
              <span className="inline-flex min-w-0 items-center gap-1"><UserRound className="size-3.5 shrink-0" aria-hidden /><span className="truncate">{task.responsible_info.full_name}</span></span>
            ) : null}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-1 pl-1 sm:pl-0">
          {task.priority === 'high' && !done ? <Badge tone={PRIORITY_TONE.high}>{task.priority_label}</Badge> : null}
          <Badge tone={TASK_TONE[task.status]}>{task.status_label}</Badge>
        </div>
      </button>
    </li>
  )
}
