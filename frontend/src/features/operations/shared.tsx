import type { ReactNode } from 'react'
import type { UseQueryResult } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'

import { Badge, type BadgeTone } from '@/components/ui/Badge'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { Select } from '@/components/ui/Select'
import { useOpsMeta } from '@/hooks/useOperations'
import { extractErrorMessage } from '@/lib/apiError'
import type { OpsFiltersParams, OpsPeriod, Priority, TaskStatus } from '@/types/operations'
import { cn } from '@/utils/cn'
import { formatRuPercent } from '@/utils/format'

const PERIOD_OPTIONS: { value: OpsPeriod; label: string }[] = [
  { value: 'today', label: 'Сегодня' },
  { value: 'yesterday', label: 'Вчера' },
  { value: 'this_week', label: 'Неделя' },
  { value: 'this_month', label: 'Месяц' },
  { value: 'last_month', label: 'Прошлый месяц' },
  { value: 'custom', label: 'Период' },
]

/** Фильтры страницы живут в адресе: ссылка открывает тот же срез данных. */
export function useOpsFilters(defaultPeriod: OpsPeriod = 'this_month') {
  const [search, setSearch] = useSearchParams()
  const period = (search.get('period') as OpsPeriod | null) ?? defaultPeriod
  const params: OpsFiltersParams & Record<string, string | undefined> = { period }
  for (const key of ['start_date', 'end_date', 'department', 'role', 'employee', 'subject', 'group', 'kpi_level', 'journal_status', 'warning', 'q', 'status', 'kind']) {
    const value = search.get(key)
    if (value) params[key] = value
  }
  if (period === 'custom' && !(params.start_date && params.end_date)) params.period = defaultPeriod
  const set = (patch: Record<string, string | undefined>) => {
    const next = new URLSearchParams(search)
    for (const [key, value] of Object.entries(patch)) {
      if (value) next.set(key, value)
      else next.delete(key)
    }
    setSearch(next, { replace: true })
  }
  return { params, period, set, raw: search }
}

export interface FiltersProps {
  filters: ReturnType<typeof useOpsFilters>
  show?: ('department' | 'role' | 'employee')[]
  periods?: OpsPeriod[]
  children?: ReactNode
}

export function OpsFilters({ filters, show = [], periods, children }: FiltersProps) {
  const meta = useOpsMeta()
  const { period, set, raw } = filters
  const options = periods ? PERIOD_OPTIONS.filter((p) => periods.includes(p.value)) : PERIOD_OPTIONS
  const department = raw.get('department') ?? ''
  return (
    <div className="space-y-2 print:hidden">
      <SegmentedControl aria-label="Период" value={period} onChange={(value) => set({ period: value })} options={options} />
      <div className="grid grid-cols-2 gap-2 md:flex md:flex-wrap md:items-center">
        {period === 'custom' ? (
          <>
            <input type="date" aria-label="Начало периода" className="form-control md:w-40" value={raw.get('start_date') ?? ''}
              onChange={(e) => set({ start_date: e.target.value, period: 'custom' })} />
            <input type="date" aria-label="Конец периода" className="form-control md:w-40" value={raw.get('end_date') ?? ''}
              onChange={(e) => set({ end_date: e.target.value, period: 'custom' })} />
          </>
        ) : null}
        {show.includes('department') ? (
          <div className="md:w-48">
            <Select aria-label="Отдел" placeholder="Все отделы" value={department}
              options={(meta.data?.departments ?? []).map((d) => ({ value: d.value, label: d.label }))}
              onChange={(e) => set({ department: e.target.value, role: undefined, employee: undefined })} />
          </div>
        ) : null}
        {show.includes('role') ? (
          <div className="md:w-52">
            <Select aria-label="Должность" placeholder="Все должности" value={raw.get('role') ?? ''}
              options={(meta.data?.roles ?? []).filter((r) => !department || r.department === department).map((r) => ({ value: r.value, label: r.label }))}
              onChange={(e) => set({ role: e.target.value })} />
          </div>
        ) : null}
        {show.includes('employee') ? (
          <div className="col-span-2 md:w-56">
            <Select aria-label="Сотрудник" placeholder="Все сотрудники" value={raw.get('employee') ?? ''}
              options={(meta.data?.employees ?? []).filter((e) => !department || e.department === department).map((e) => ({ value: String(e.id), label: e.full_name }))}
              onChange={(e) => set({ employee: e.target.value })} />
          </div>
        ) : null}
        {children}
      </div>
    </div>
  )
}

/** Состояния загрузки/ошибки одинаково на каждой странице. */
export function QueryView<T>({ query, children, label }: { query: UseQueryResult<T>; children: (data: T) => ReactNode; label?: string }) {
  if (query.isPending) return <LoadingState label={label ?? 'Загрузка данных…'} />
  if (query.isError) return <ErrorState message={extractErrorMessage(query.error)} onRetry={() => void query.refetch()} />
  return <div className={cn(query.isFetching && 'opacity-70 transition-opacity')}>{children(query.data)}</div>
}

export function pct(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : formatRuPercent(value)
}

export function num(value: number | string | null | undefined, unit = ''): string {
  if (value === null || value === undefined || value === '') return '—'
  const n = typeof value === 'string' ? Number(value) : value
  return `${n.toLocaleString('ru-RU', { maximumFractionDigits: 2 })}${unit ? ` ${unit}` : ''}`
}

export function dateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const d = new Date(value)
  return `${d.toLocaleDateString('ru-RU')} ${d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}`
}

export function shortDate(value: string | null | undefined): string {
  return value ? new Date(value.length === 10 ? `${value}T00:00:00` : value).toLocaleDateString('ru-RU') : '—'
}

export function time(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }) : '—'
}

const TASK_TONE: Record<TaskStatus, BadgeTone> = {
  pending: 'muted', in_progress: 'info', review: 'warning', completed: 'success', rejected: 'danger', overdue: 'danger', cancelled: 'muted',
}

export function TaskStatusBadge({ status, label }: { status: TaskStatus; label: string }) {
  return <Badge tone={TASK_TONE[status]}>{label}</Badge>
}

const PRIORITY_TONE: Record<Priority, BadgeTone> = { low: 'muted', medium: 'info', high: 'warning', critical: 'danger' }

export function PriorityBadge({ priority, label }: { priority: Priority; label: string }) {
  return <Badge tone={PRIORITY_TONE[priority]}>{label}</Badge>
}

const LEVEL_TONE: Record<string, BadgeTone> = {
  good: 'success', ok: 'success', attention: 'warning', low: 'danger', problem: 'danger', no_data: 'muted', upcoming: 'muted',
  present: 'success', late: 'warning', absent: 'danger', not_checked_out: 'warning', not_arrived: 'muted', day_off: 'muted', not_tracked: 'muted',
  normal: 'success', risk: 'danger', open: 'danger', in_progress: 'info', resolved: 'success', dismissed: 'muted',
  submitted: 'success', missing: 'danger', pending: 'muted', accepted: 'success', returned: 'warning', draft: 'muted',
}

export function LevelBadge({ level, label }: { level: string; label: string }) {
  return <Badge tone={LEVEL_TONE[level] ?? 'muted'}>{label}</Badge>
}

const KPI_LABEL: Record<string, string> = { good: 'Хороший', attention: 'Требует внимания', low: 'Низкий', no_data: 'Нет данных' }

export function KpiValue({ value, level }: { value: number | null; level: string }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className="font-semibold tabular-nums">{pct(value)}</span>
      {value !== null ? <LevelBadge level={level} label={KPI_LABEL[level] ?? level} /> : null}
    </span>
  )
}

/** Доля в виде полосы. null — серая пустая полоса и «—». */
export function Progress({ value, tone }: { value: number | null | undefined; tone?: 'auto' | 'brand' }) {
  const v = value ?? null
  const color = v === null ? 'bg-border' : tone === 'brand' ? 'bg-brand-500' : v >= 90 ? 'bg-brand-500' : v >= 70 ? 'bg-warning' : 'bg-danger'
  return (
    <div className="flex min-w-24 items-center gap-2">
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-hover">
        <div className={cn('h-full rounded-full', color)} style={{ width: `${Math.min(100, Math.max(0, v ?? 0))}%` }} />
      </div>
      <span className="w-12 text-right text-xs tabular-nums text-ink-secondary">{pct(v)}</span>
    </div>
  )
}

export function Section({ title, actions, children, className, padding = true }: { title: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; padding?: boolean }) {
  return (
    <section className={cn('card min-w-0', className)}>
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-3 sm:px-5">
        <h2 className="section-title">{title}</h2>
        {actions}
      </header>
      <div className={cn(padding && 'card-body')}>{children}</div>
    </section>
  )
}

export function PersonLink({ id, name, sub }: { id: number; name: string; sub?: string }) {
  return (
    <Link to={`/operations/employees/${id}`} className="block min-w-0 hover:text-brand-700">
      <span className="block truncate font-medium">{name}</span>
      {sub ? <span className="block truncate text-xs text-ink-secondary">{sub}</span> : null}
    </Link>
  )
}

export function Counter({ value, tone = 'default' }: { value: number; tone?: 'default' | 'danger' | 'warning' }) {
  return (
    <span className={cn('tabular-nums', value > 0 && tone === 'danger' && 'font-semibold text-danger', value > 0 && tone === 'warning' && 'font-semibold text-warning')}>
      {value}
    </span>
  )
}

export function Table({ headers, children, empty }: { headers: string[]; children: ReactNode; empty?: boolean }) {
  return (
    <div className="overflow-x-auto">
      <table className="data-table">
        <thead>
          <tr>{headers.map((h) => <th key={h}>{h}</th>)}</tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
      {empty ? <p className="px-4 py-6 text-center text-sm text-ink-muted">Нет данных за выбранный период</p> : null}
    </div>
  )
}

export function Note({ children }: { children: ReactNode }) {
  return <p className="rounded-lg border border-border bg-surface-muted px-3 py-2 text-xs text-ink-secondary">{children}</p>
}

export function saveBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = name
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
