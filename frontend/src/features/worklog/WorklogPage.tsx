import { useState } from 'react'
import { AlertTriangle, CalendarCheck, FilePlus2, FileText, ListTodo, NotebookPen, Plus } from 'lucide-react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { DatePicker } from '@/components/ui/DatePicker'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { FilterBar, FilterField } from '@/components/ui/FilterBar'
import { LoadingState } from '@/components/ui/LoadingState'
import { Pagination } from '@/components/ui/Pagination'
import { SearchInput } from '@/components/ui/SearchInput'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { Select } from '@/components/ui/Select'
import { StatCard } from '@/components/ui/StatCard'
import { Tabs } from '@/components/ui/Tabs'
import { useToast } from '@/components/ui/Toast'
import {
  useDeleteEntry,
  useWorklogEntries,
  useWorklogOptions,
  useWorklogReports,
  useWorklogSummary,
} from '@/hooks/useWorklog'
import { extractErrorMessage } from '@/lib/apiError'
import type { EntryKind, WorkLogEntry, WorklogOptions } from '@/types/worklog'
import { formatDate } from '@/utils/format'

import { EntryCard } from './EntryCard'
import { EntryModal } from './EntryModal'
import { shiftDate, today } from './formUi'

type Tab = 'journal' | 'tasks' | 'reports'
type Scope = 'mine' | 'all'

const TABS: { key: Tab; label: string }[] = [
  { key: 'journal', label: 'Журнал' },
  { key: 'tasks', label: 'Задачи' },
  { key: 'reports', label: 'Отчёты' },
]

const SCOPES: { value: Scope; label: string }[] = [
  { value: 'mine', label: 'Мои' },
  { value: 'all', label: 'Все' },
]

const PAGE_SIZE = 20

/**
 * «Рабочий журнал» (Team Lead, read for Admin): the day-to-day record of
 * the Team Lead's work, the tasks that come out of it and the reports
 * (daily … monthly) that summarize it with figures from the LMS.
 */
export function WorklogPage() {
  const [params, setParams] = useSearchParams()
  const tab = (TABS.some((t) => t.key === params.get('tab')) ? params.get('tab') : 'journal') as Tab
  const options = useWorklogOptions()
  const summary = useWorklogSummary()
  const [modal, setModal] = useState<{ kind: EntryKind; entry?: WorkLogEntry } | null>(null)

  if (options.isPending) return <LoadingState label="Загружаем рабочий журнал…" />
  if (options.isError || !options.data) return <ErrorState onRetry={() => void options.refetch()} />

  return (
    <div>
      <PageHeader
        title="Рабочий журнал"
        description="Что сделано, когда, с кем, какой результат и что дальше"
        actions={
          <>
            <Button leftIcon={<Plus className="size-4" aria-hidden />} onClick={() => setModal({ kind: 'log' })}>
              Запись
            </Button>
            <Button variant="secondary" leftIcon={<ListTodo className="size-4" aria-hidden />} onClick={() => setModal({ kind: 'task' })}>
              Задача
            </Button>
          </>
        }
      />

      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Записей сегодня" value={summary.data?.today ?? '—'} icon={NotebookPen} />
        <StatCard label="Открытые дела" value={summary.data?.open ?? '—'} icon={ListTodo} />
        <StatCard label="Срок сегодня" value={summary.data?.due_today ?? '—'} icon={CalendarCheck} tone={summary.data?.due_today ? 'warning' : 'default'} />
        <StatCard label="Просрочено" value={summary.data?.overdue ?? '—'} icon={AlertTriangle} tone={summary.data?.overdue ? 'danger' : 'default'} />
      </div>

      <Tabs aria-label="Разделы рабочего журнала" items={TABS} value={tab} onChange={(next) => setParams({ tab: next }, { replace: true })} />

      {tab === 'journal' ? <EntriesTab key="log" kind="log" options={options.data} onEdit={(entry) => setModal({ kind: 'log', entry })} /> : null}
      {tab === 'tasks' ? <EntriesTab key="task" kind="task" options={options.data} onEdit={(entry) => setModal({ kind: 'task', entry })} /> : null}
      {tab === 'reports' ? <ReportsTab options={options.data} /> : null}

      {modal ? (
        <EntryModal
          key={modal.entry?.id ?? `new-${modal.kind}`}
          isOpen
          onClose={() => setModal(null)}
          options={options.data}
          kind={modal.kind}
          entry={modal.entry}
        />
      ) : null}
    </div>
  )
}

function EntriesTab({ kind, options, onEdit }: { kind: EntryKind; options: WorklogOptions; onEdit: (entry: WorkLogEntry) => void }) {
  const isTask = kind === 'task'
  const [scope, setScope] = useState<Scope>('mine')
  const [dateFrom, setDateFrom] = useState(isTask ? '' : shiftDate(today(), -6))
  const [dateTo, setDateTo] = useState('')
  const [workType, setWorkType] = useState('')
  const [status, setStatus] = useState('')
  const [priority, setPriority] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [deleting, setDeleting] = useState<WorkLogEntry | null>(null)
  const remove = useDeleteEntry()
  const { showToast } = useToast()

  const reset = <T,>(setter: (value: T) => void) => (value: T) => {
    setter(value)
    setPage(1)
  }

  const { data, isPending, isError, refetch } = useWorklogEntries({
    entry_kind: kind,
    mine: scope === 'mine' ? '1' : undefined,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
    work_type: workType || undefined,
    status: status || undefined,
    priority: priority || undefined,
    search: search.trim() || undefined,
    ordering: isTask ? 'deadline' : undefined,
    page,
  })

  return (
    <section aria-label={isTask ? 'Задачи' : 'Журнал'}>
      <FilterBar>
        <FilterField size="lg">
          <SearchInput value={search} onChange={reset(setSearch)} placeholder={isTask ? 'Поиск по задачам' : 'Поиск по записям'} />
        </FilterField>
        <FilterField>
          <SegmentedControl aria-label="Чьи записи" options={SCOPES} value={scope} onChange={reset(setScope)} />
        </FilterField>
        <FilterField label="С" htmlFor={`${kind}-from`}>
          <DatePicker id={`${kind}-from`} value={dateFrom} onChange={(e) => reset(setDateFrom)(e.target.value)} />
        </FilterField>
        <FilterField label="По" htmlFor={`${kind}-to`}>
          <DatePicker id={`${kind}-to`} value={dateTo} onChange={(e) => reset(setDateTo)(e.target.value)} />
        </FilterField>
        <FilterField>
          <Select aria-label="Вид работы" value={workType} onChange={(e) => reset(setWorkType)(e.target.value)} placeholder="Все виды работ" options={options.work_types} />
        </FilterField>
        <FilterField>
          <Select aria-label="Статус" value={status} onChange={(e) => reset(setStatus)(e.target.value)} placeholder="Все статусы" options={options.statuses} />
        </FilterField>
        {isTask ? (
          <FilterField>
            <Select aria-label="Приоритет" value={priority} onChange={(e) => reset(setPriority)(e.target.value)} placeholder="Любой приоритет" options={options.priorities} />
          </FilterField>
        ) : null}
      </FilterBar>

      {isPending ? (
        <LoadingState />
      ) : isError || !data ? (
        <ErrorState onRetry={() => void refetch()} />
      ) : data.results.length === 0 ? (
        <EmptyState
          icon={isTask ? ListTodo : NotebookPen}
          title={isTask ? 'Задач нет' : 'Записей нет'}
          description={isTask ? 'Задачи с ответственным и сроком появятся здесь.' : 'Добавьте запись о выполненной работе.'}
        />
      ) : (
        <div className="space-y-3">
          {data.results.map((entry) => (
            <EntryCard key={entry.id} entry={entry} onEdit={onEdit} onDelete={setDeleting} />
          ))}
          <Pagination page={page} pageSize={PAGE_SIZE} totalCount={data.count} onPageChange={setPage} />
        </div>
      )}

      <ConfirmDialog
        isOpen={deleting !== null}
        title={isTask ? 'Удалить задачу?' : 'Удалить запись?'}
        message="Это действие нельзя отменить."
        confirmLabel="Удалить"
        tone="danger"
        isLoading={remove.isPending}
        onCancel={() => setDeleting(null)}
        onConfirm={() =>
          deleting &&
          remove.mutate(deleting.id, {
            onSuccess: () => {
              setDeleting(null)
              showToast('Удалено', 'success')
            },
            onError: (error) => showToast(extractErrorMessage(error), 'error'),
          })
        }
      />
    </section>
  )
}

function ReportsTab({ options }: { options: WorklogOptions }) {
  const navigate = useNavigate()
  const [scope, setScope] = useState<Scope>('mine')
  // The report kind lives in the URL (?tab=reports&kind=daily) so the menu's
  // «Ежедневные / Еженедельные / Ежемесячные» open the list already filtered.
  const [params, setParams] = useSearchParams()
  const kind = options.report_kinds.some((k) => k.kind === params.get('kind')) ? (params.get('kind') as string) : ''
  const setKind = (value: string) => setParams(value ? { tab: 'reports', kind: value } : { tab: 'reports' }, { replace: true })
  const [newKind, setNewKind] = useState('daily')
  const [page, setPage] = useState(1)
  const { data, isPending, isError, refetch } = useWorklogReports({
    kind: kind || undefined,
    mine: scope === 'mine' ? '1' : undefined,
    page,
  })
  const kindOptions = options.report_kinds.map((k) => ({ value: k.kind, label: k.label }))

  return (
    <section aria-label="Отчёты">
      <FilterBar>
        <FilterField>
          <SegmentedControl aria-label="Чьи отчёты" options={SCOPES} value={scope} onChange={(v) => { setScope(v); setPage(1) }} />
        </FilterField>
        <FilterField>
          <Select aria-label="Вид отчёта" value={kind} onChange={(e) => { setKind(e.target.value); setPage(1) }} placeholder="Все отчёты" options={kindOptions} />
        </FilterField>
        <FilterField size="lg" className="flex gap-2">
          <Select aria-label="Новый отчёт" value={newKind} onChange={(e) => setNewKind(e.target.value)} options={kindOptions} />
          <Button leftIcon={<FilePlus2 className="size-4" aria-hidden />} onClick={() => navigate(`/app/worklog/reports/new?kind=${newKind}`)}>
            Создать
          </Button>
        </FilterField>
      </FilterBar>

      {isPending ? (
        <LoadingState />
      ) : isError || !data ? (
        <ErrorState onRetry={() => void refetch()} />
      ) : data.results.length === 0 ? (
        <EmptyState icon={FileText} title="Отчётов нет" description="Выберите вид отчёта и нажмите «Создать»." />
      ) : (
        <div className="space-y-2">
          <ul className="divide-y divide-border rounded-xl border border-border bg-surface">
            {data.results.map((report) => (
              <li key={report.id}>
                <Link to={`/app/worklog/reports/${report.id}`} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 hover:bg-surface-hover">
                  <span className="min-w-0">
                    <span className="block font-medium text-ink">{report.title}</span>
                    <span className="block text-xs text-ink-muted">
                      {report.author.name}, изменён {formatDate(report.updated_at.slice(0, 10))}
                    </span>
                  </span>
                  <Badge tone={report.status === 'draft' ? 'muted' : 'success'}>{report.status_label}</Badge>
                </Link>
              </li>
            ))}
          </ul>
          <Pagination page={page} pageSize={PAGE_SIZE} totalCount={data.count} onPageChange={setPage} />
        </div>
      )}
    </section>
  )
}
