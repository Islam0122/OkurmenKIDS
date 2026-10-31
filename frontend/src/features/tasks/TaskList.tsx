import { CheckSquare, Repeat } from 'lucide-react'
import { Link } from 'react-router-dom'

import { EmptyState } from '@/components/ui/EmptyState'
import type { TaskListItem } from '@/types/operations'
import { cn } from '@/utils/cn'

import { PriorityBadge, TaskStatusBadge, dateTime } from '../operations/shared'

/** Компактный список задач: одна строка — название, исполнитель, дедлайн,
 * чек-лист, приоритет и статус. */
export function TaskList({ tasks, empty = 'Задач нет', showAssignee = true }: { tasks: TaskListItem[]; empty?: string; showAssignee?: boolean }) {
  if (!tasks.length) return <EmptyState title={empty} className="py-6" />
  return (
    <ul className="divide-y divide-border">
      {tasks.map((t) => (
        <li key={t.id}>
          <Link to={`/tasks/${t.id}`} className="flex flex-col gap-1 px-4 py-3 hover:bg-surface-hover sm:flex-row sm:items-center sm:justify-between sm:px-5">
            <span className="min-w-0">
              <span className="flex items-center gap-1.5 text-sm font-medium text-ink">
                {t.is_recurring ? <Repeat className="size-3.5 shrink-0 text-ink-muted" aria-label="Повторяющаяся" /> : null}
                <span className="truncate">{t.title}</span>
              </span>
              <span className="block truncate text-xs text-ink-secondary">
                {showAssignee ? `${t.assignee?.full_name ?? `Отдел: ${t.department_label}`} · ` : ''}
                <span className={cn(t.status === 'overdue' && 'font-medium text-danger')}>{t.deadline ? `до ${dateTime(t.deadline)}` : 'без срока'}</span>
                {t.checklist_total ? <span className="ml-2 inline-flex items-center gap-0.5"><CheckSquare className="size-3" aria-hidden />{t.checklist_done}/{t.checklist_total}</span> : null}
              </span>
            </span>
            <span className="flex shrink-0 items-center gap-1.5">
              <PriorityBadge priority={t.priority} label={t.priority_label} />
              <TaskStatusBadge status={t.status} label={t.status_label} />
            </span>
          </Link>
        </li>
      ))}
    </ul>
  )
}
