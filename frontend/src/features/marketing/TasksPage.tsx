import { useState } from 'react'
import { ClipboardCheck, Plus } from 'lucide-react'

import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Pagination } from '@/components/ui/Pagination'
import { SearchInput } from '@/components/ui/SearchInput'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { Select } from '@/components/ui/Select'
import { useMarketingMeta, useMarketingTasks } from '@/hooks/useMarketing'
import { extractErrorMessage } from '@/lib/apiError'
import type { MarketingTask, TaskDueFilter, TaskPriority, TaskStatusFilter, TasksParams } from '@/types/marketing'
import { cn } from '@/utils/cn'

import { TaskDialog } from './Dialogs'
import { TaskRow } from './Rows'

const PAGE_SIZE = 30
type StatusTab = TaskStatusFilter | 'all'

const STATUS_TABS: { value: StatusTab; label: string }[] = [
  { value: 'open', label: 'Открытые' },
  { value: 'in_progress', label: 'В работе' },
  { value: 'overdue', label: 'Просроченные' },
  { value: 'done', label: 'Выполненные' },
  { value: 'all', label: 'Все' },
]

const DUE_OPTIONS: { value: TaskDueFilter; label: string }[] = [
  { value: 'today', label: 'Срок сегодня' },
  { value: 'week', label: 'Ближайшие 7 дней' },
  { value: 'overdue', label: 'Срок прошёл' },
  { value: 'none', label: 'Без срока' },
]

/** /marketing/tasks — задачи отдела: фильтры по статусу, сроку, приоритету и
 * ответственному, быстрая отметка «выполнено», создание и редактирование. */
export function MarketingTasksPage() {
  const meta = useMarketingMeta()
  const [status, setStatus] = useState<StatusTab>('open')
  const [due, setDue] = useState<TaskDueFilter | ''>('')
  const [priority, setPriority] = useState<TaskPriority | ''>('')
  const [mine, setMine] = useState(false)
  const [search, setSearch] = useState('')
  const scope = JSON.stringify([status, due, priority, mine, search])
  const [paging, setPaging] = useState({ scope, page: 1 })
  const page = paging.scope === scope ? paging.page : 1
  const [open, setOpen] = useState<MarketingTask | null | undefined>(undefined)

  const params: TasksParams = {
    status: status === 'all' ? undefined : status,
    due: due || undefined,
    priority: priority || undefined,
    mine: mine ? '1' : undefined,
    search: search || undefined,
    page,
    page_size: PAGE_SIZE,
  }
  const tasks = useMarketingTasks(params)
  const filtered = Boolean(due || priority || mine || search)

  return (
    <div className="space-y-4">
      <PageHeader
        title="Задачи"
        description="Задачи отдела маркетинга со сроками и ответственными"
        actions={<Button className="max-sm:h-11 max-sm:w-full" leftIcon={<Plus className="size-4" aria-hidden />} onClick={() => setOpen(null)}>Новая задача</Button>}
      />

      <div className="space-y-3">
        <SegmentedControl aria-label="Статус задач" value={status} onChange={setStatus} options={STATUS_TABS} />
        <div className="grid grid-cols-2 gap-2 md:flex md:items-center">
          <div className="col-span-2 min-w-0 md:w-72">
            <SearchInput value={search} onChange={setSearch} placeholder="Поиск по задачам" />
          </div>
          <div className="min-w-0 md:w-48">
            <Select aria-label="Срок" className="max-sm:h-11 max-sm:text-base" value={due} placeholder="Любой срок" options={DUE_OPTIONS} onChange={(e) => setDue(e.target.value as TaskDueFilter | '')} />
          </div>
          <div className="min-w-0 md:w-44">
            <Select aria-label="Приоритет" className="max-sm:h-11 max-sm:text-base" value={priority} placeholder="Любой приоритет" options={meta.data?.priorities ?? []} onChange={(e) => setPriority(e.target.value as TaskPriority | '')} />
          </div>
          <button
            type="button"
            aria-pressed={mine}
            onClick={() => setMine((v) => !v)}
            className={cn(
              'col-span-2 h-11 rounded-lg border px-4 text-sm font-medium transition-colors md:h-10',
              mine ? 'border-brand-500 bg-brand-50 text-brand-700' : 'border-border bg-surface text-ink-secondary hover:bg-surface-hover',
            )}
          >
            Только мои
          </button>
        </div>
      </div>

      <Card padding="none">
        {tasks.isPending ? (
          <LoadingState />
        ) : tasks.isError ? (
          <ErrorState message={extractErrorMessage(tasks.error)} onRetry={() => void tasks.refetch()} />
        ) : tasks.data.results.length === 0 ? (
          <EmptyState
            icon={ClipboardCheck}
            title={filtered || status !== 'open' ? 'Задач не найдено' : 'Открытых задач нет'}
            description={filtered ? 'Измените фильтры, чтобы увидеть другие задачи.' : 'Добавьте задачу — она появится здесь и на обзоре.'}
          />
        ) : (
          <>
            <ul className={cn('divide-y divide-border py-1 transition-opacity', tasks.isPlaceholderData && 'opacity-60')}>
              {tasks.data.results.map((task) => <TaskRow key={task.id} task={task} onOpen={setOpen} />)}
            </ul>
            {tasks.data.count > PAGE_SIZE ? <div className="px-4 pb-4 sm:px-5">
              <Pagination page={page} pageSize={PAGE_SIZE} totalCount={tasks.data.count} onPageChange={(next) => setPaging({ scope, page: next })} />
            </div> : null}
          </>
        )}
      </Card>

      <TaskDialog task={open} onClose={() => setOpen(undefined)} />
    </div>
  )
}
