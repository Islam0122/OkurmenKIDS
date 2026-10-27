import { useEffect, useState } from 'react'
import { ArrowDown, ArrowUp, ArrowUpDown, CalendarCheck, Clock3, Download, Eye, LogIn, PencilLine, Plus, RefreshCw, TimerOff, UserX, Users } from 'lucide-react'
import { Navigate } from 'react-router-dom'

import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { DatePicker } from '@/components/ui/DatePicker'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { FilterBar, FilterField } from '@/components/ui/FilterBar'
import { LoadingState } from '@/components/ui/LoadingState'
import { Pagination } from '@/components/ui/Pagination'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import { StatCard } from '@/components/ui/StatCard'
import { StatGrid } from '@/components/ui/StatGrid'
import { useToast } from '@/components/ui/Toast'
import { useAttendanceMeta, useAttendanceOverview, useAttendanceRecords } from '@/hooks/useStaffAttendance'
import { staffAttendanceApi } from '@/api/staffAttendance'
import { extractErrorMessage, isForbidden } from '@/lib/apiError'
import type { DayRow, RecordsParams } from '@/types/staffAttendance'
import { cn } from '@/utils/cn'

import { AdjustModal, type AdjustTarget } from './AdjustModal'
import { EmployeeDrawer } from './EmployeeDrawer'
import { DEFAULT_TZ, formatDay, formatDuration, formatLate, formatTime } from './format'
import { Avatar } from './PersonalAttendancePage'
import { DAY_STATUS_TONE } from './statusUi'

const PAGE_SIZE = 20

type SortKey = 'name' | 'role' | 'check_in' | 'check_out' | 'duration' | 'late' | 'status'

function useDebounced<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(value), delay)
    return () => window.clearTimeout(id)
  }, [value, delay])
  return debounced
}

/** /admin/attendance (администраторы) и /attendance/management (руководство):
 * одна панель, возможности — по правам, которые вернул backend. */
export function AdminAttendancePage({ mode = 'admin' }: { mode?: 'admin' | 'management' }) {
  const meta = useAttendanceMeta()

  if (meta.isPending) return <LoadingState label="Проверяем доступ…" />
  if (meta.isError) {
    if (isForbidden(meta.error)) return <Navigate to="/attendance" replace />
    return <ErrorState message={extractErrorMessage(meta.error)} onRetry={() => void meta.refetch()} />
  }
  return <Dashboard mode={mode} />
}

function Dashboard({ mode }: { mode: 'admin' | 'management' }) {
  const { showToast } = useToast()
  const meta = useAttendanceMeta().data!
  const tz = meta.timezone || DEFAULT_TZ
  const [date, setDate] = useState(meta.today)
  const [search, setSearch] = useState('')
  const [role, setRole] = useState('')
  const [location, setLocation] = useState('')
  const [status, setStatus] = useState('')
  const [ordering, setOrdering] = useState<string>('name')
  const [page, setPage] = useState(1)
  const [employeeId, setEmployeeId] = useState<number | null>(null)
  const [adjustTarget, setAdjustTarget] = useState<AdjustTarget | null>(null)
  const [exporting, setExporting] = useState(false)
  const debouncedSearch = useDebounced(search.trim())

  const filters: RecordsParams = { date, search: debouncedSearch || undefined, role: role || undefined, location: location || undefined }
  const params: RecordsParams = { ...filters, status: status || undefined, ordering, page, page_size: PAGE_SIZE }
  const overview = useAttendanceOverview(filters)
  const records = useAttendanceRecords(params)

  const reset = <T,>(setter: (v: T) => void) => (value: T) => {
    setter(value)
    setPage(1)
  }

  const toggleSort = (key: SortKey) => {
    setOrdering((current) => (current === key ? `-${key}` : key))
    setPage(1)
  }

  const refresh = () => {
    void overview.refetch()
    void records.refetch()
  }

  const exportCsv = async () => {
    setExporting(true)
    try {
      const name = await staffAttendanceApi.exportCsv({ ...filters, status: status || undefined, ordering })
      showToast(`Файл ${name} сохранён`, 'success')
    } catch (error) {
      showToast(extractErrorMessage(error, 'Не удалось выгрузить отчёт'), 'error')
    } finally {
      setExporting(false)
    }
  }

  const o = overview.data
  const canAdjust = meta.access.can_adjust

  return (
    <div className="space-y-5">
      <PageHeader
        title={mode === 'management' ? 'Отчёты посещаемости' : 'Учёт посещаемости'}
        description="Приход, уход и рабочее время сотрудников"
        badge={meta.access.scope === 'teachers' ? <Badge tone="info">Только тренеры</Badge> : undefined}
        actions={
          <>
            <Button variant="secondary" leftIcon={<Download className="size-4" aria-hidden />} isLoading={exporting} onClick={() => void exportCsv()}>
              Экспорт CSV
            </Button>
            <Button variant="ghost" leftIcon={<RefreshCw className={cn('size-4', (records.isFetching || overview.isFetching) && 'animate-spin')} aria-hidden />} onClick={refresh}>
              Обновить
            </Button>
          </>
        }
      />

      <FilterBar>
        <FilterField label="Дата" htmlFor="att-date">
          <DatePicker id="att-date" value={date} onChange={(e) => e.target.value && reset(setDate)(e.target.value)} />
        </FilterField>
        <FilterField size="lg" label="Поиск">
          <SearchInput aria-label="Поиск по имени" value={search} onChange={reset(setSearch)} placeholder="Имя, логин или email" />
        </FilterField>
        <FilterField label="Роль" htmlFor="att-role">
          <Select id="att-role" value={role} onChange={(e) => reset(setRole)(e.target.value)} placeholder="Все роли" options={meta.roles.map((r) => ({ value: r.value, label: r.label }))} />
        </FilterField>
        <FilterField label="Офис" htmlFor="att-office">
          <Select id="att-office" value={location} onChange={(e) => reset(setLocation)(e.target.value)} placeholder="Все офисы" options={meta.locations.map((l) => ({ value: String(l.id), label: l.is_active ? l.name : `${l.name} (отключён)` }))} />
        </FilterField>
        <FilterField label="Статус" htmlFor="att-status">
          <Select id="att-status" value={status} onChange={(e) => reset(setStatus)(e.target.value)} placeholder="Все статусы" options={meta.statuses.map((s) => ({ value: s.value, label: s.label }))} />
        </FilterField>
      </FilterBar>

      {overview.isError ? (
        <ErrorState title="Статистика недоступна" message={extractErrorMessage(overview.error)} onRetry={() => void overview.refetch()} />
      ) : (
        <StatGrid columns={3} className="xl:grid-cols-6">
          <StatCard label="Активных сотрудников" value={o?.total_employees ?? '…'} icon={Users} />
          <StatCard label="Пришли" value={o?.arrived ?? '…'} icon={LogIn} />
          <StatCard label="Сейчас на работе" value={o?.at_work ?? '…'} icon={Clock3} />
          <StatCard label="Опоздали" value={o?.late ?? '…'} icon={TimerOff} tone={o && o.late > 0 ? 'warning' : 'default'} />
          <StatCard label="Завершили день" value={o?.finished ?? '…'} icon={CalendarCheck} />
          <StatCard
            label="Нет отметки прихода"
            value={o ? o.not_arrived + o.no_check_in : '…'}
            icon={UserX}
            tone={o && o.no_check_in > 0 ? 'danger' : 'default'}
            hint={o ? `После конца рабочего дня: ${o.no_check_in}; выходной: ${o.day_off}` : undefined}
          />
        </StatGrid>
      )}

      <section className="card min-w-0 overflow-hidden" aria-label="Таблица посещаемости">
        {records.isPending ? (
          <LoadingState />
        ) : records.isError ? (
          <ErrorState message={extractErrorMessage(records.error)} onRetry={() => void records.refetch()} />
        ) : records.data.results.length === 0 ? (
          <EmptyState title="Записей не найдено" description="Измените дату или фильтры." />
        ) : (
          <>
            <RecordsTable
              rows={records.data.results}
              timeZone={tz}
              ordering={ordering}
              onSort={toggleSort}
              canAdjust={canAdjust}
              onView={(row) => setEmployeeId(row.employee.id)}
              onAdjust={(row) => {
                const last = row.sessions[row.sessions.length - 1]
                setAdjustTarget(last ? { mode: 'edit', employee: row.employee, session: last } : { mode: 'create', employee: row.employee, date: row.date })
              }}
            />
            <div className="border-t border-border px-4 py-3">
              <Pagination page={page} pageSize={PAGE_SIZE} totalCount={records.data.count} onPageChange={setPage} />
            </div>
          </>
        )}
      </section>

      <p className="text-xs text-ink-muted">
        Время — по часовому поясу офиса ({tz}). Продолжительность — время между приходом и уходом, не оплачиваемые часы.
        Геолокация браузера и постоянный QR-код не дают абсолютной защиты от подмены — спорные записи проверяйте по журналу событий.
      </p>

      <EmployeeDrawer
        key={employeeId ?? 'none'}
        employeeId={employeeId}
        today={meta.today}
        timeZone={tz}
        canAdjust={canAdjust}
        onClose={() => setEmployeeId(null)}
        onAdjust={(employee, session) => setAdjustTarget({ mode: 'edit', employee, session })}
      />
      <AdjustModal target={adjustTarget} timeZone={tz} locations={meta.locations} onClose={() => setAdjustTarget(null)} />
    </div>
  )
}

const COLUMNS: { key: string; label: string; sort?: SortKey; className?: string }[] = [
  { key: 'employee', label: 'Сотрудник', sort: 'name' },
  { key: 'role', label: 'Роль', sort: 'role' },
  { key: 'date', label: 'Дата' },
  { key: 'in', label: 'Приход', sort: 'check_in' },
  { key: 'out', label: 'Уход', sort: 'check_out' },
  { key: 'duration', label: 'Продолжительность', sort: 'duration' },
  { key: 'late', label: 'Опоздание', sort: 'late' },
  { key: 'status', label: 'Статус', sort: 'status' },
  { key: 'actions', label: 'Действия', className: 'text-right' },
]

interface TableProps {
  rows: DayRow[]
  timeZone: string
  ordering: string
  canAdjust: boolean
  onSort: (key: SortKey) => void
  onView: (row: DayRow) => void
  onAdjust: (row: DayRow) => void
}

function SortIcon({ active, desc }: { active: boolean; desc: boolean }) {
  if (!active) return <ArrowUpDown className="size-3.5 text-ink-muted" aria-hidden />
  return desc ? <ArrowDown className="size-3.5" aria-hidden /> : <ArrowUp className="size-3.5" aria-hidden />
}

function StatusBadges({ row }: { row: DayRow }) {
  return (
    <div className="flex flex-wrap gap-1">
      <Badge tone={DAY_STATUS_TONE[row.status]} className="whitespace-nowrap">{row.status_label}</Badge>
      {row.is_late ? <Badge tone="warning" className="whitespace-nowrap">Опоздание</Badge> : null}
      {row.is_adjusted ? <Badge tone="info" className="whitespace-nowrap">Исправлена запись</Badge> : null}
    </div>
  )
}

function RowActions({ row, canAdjust, onView, onAdjust }: { row: DayRow; canAdjust: boolean; onView: () => void; onAdjust: () => void }) {
  return (
    <div className="flex justify-end gap-1">
      <Button size="sm" variant="ghost" onClick={onView} aria-label={`Открыть: ${row.employee.full_name}`}>
        <Eye className="size-4" aria-hidden />
      </Button>
      {canAdjust && row.status !== 'day_off' ? (
        <Button size="sm" variant="ghost" onClick={onAdjust} aria-label={row.sessions.length ? 'Исправить запись' : 'Добавить запись'}>
          {row.sessions.length ? <PencilLine className="size-4" aria-hidden /> : <Plus className="size-4" aria-hidden />}
        </Button>
      ) : null}
    </div>
  )
}

function RecordsTable({ rows, timeZone, ordering, canAdjust, onSort, onView, onAdjust }: TableProps) {
  const desc = ordering.startsWith('-')
  const activeKey = ordering.replace(/^-/, '')
  return (
    <>
      {/* Телефон: карточки */}
      <ul className="divide-y divide-border md:hidden">
        {rows.map((row) => (
          <li key={row.key} className="space-y-2 px-4 py-3">
            <div className="flex items-center justify-between gap-2">
              <button type="button" className="flex min-w-0 items-center gap-2 text-left" onClick={() => onView(row)}>
                <Avatar employee={row.employee} size="md" />
                <span className="min-w-0">
                  <span className="block truncate font-medium text-ink">{row.employee.full_name}</span>
                  <span className="block text-xs text-ink-secondary">{row.employee.role_label} · {formatDay(row.date, false)}</span>
                </span>
              </button>
              <RowActions row={row} canAdjust={canAdjust} onView={() => onView(row)} onAdjust={() => onAdjust(row)} />
            </div>
            <p className="text-sm tabular-nums text-ink-secondary">
              {formatTime(row.check_in, timeZone)} — {formatTime(row.check_out, timeZone)} · {formatDuration(row.duration_seconds)}
              {row.is_late ? ` · опоздание ${formatLate(row.late_minutes)}` : ''}
            </p>
            <StatusBadges row={row} />
          </li>
        ))}
      </ul>

      {/* Планшет и компьютер: таблица */}
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full min-w-[960px] text-sm">
          <thead className="bg-surface-muted text-left text-xs font-medium uppercase tracking-wide text-ink-secondary">
            <tr>
              {COLUMNS.map((col) => (
                <th key={col.key} scope="col" className={cn('px-4 py-3', col.className)} aria-sort={col.sort && activeKey === col.sort ? (desc ? 'descending' : 'ascending') : undefined}>
                  {col.sort ? (
                    <button type="button" className="inline-flex items-center gap-1 uppercase hover:text-ink" onClick={() => onSort(col.sort!)}>
                      {col.label}
                      <SortIcon active={activeKey === col.sort} desc={desc} />
                    </button>
                  ) : (
                    col.label
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {rows.map((row) => (
              <tr key={row.key} className={cn('hover:bg-surface-hover', row.status === 'no_check_in' && 'bg-danger-soft/30')}>
                <td className="px-4 py-3">
                  <button type="button" className="flex items-center gap-2 text-left" onClick={() => onView(row)}>
                    <Avatar employee={row.employee} size="md" />
                    <span className="font-medium text-ink hover:text-brand-700">{row.employee.full_name}</span>
                  </button>
                </td>
                <td className="px-4 py-3 text-ink-secondary">{row.employee.role_label}</td>
                <td className="whitespace-nowrap px-4 py-3 text-ink-secondary">{formatDay(row.date, false)}</td>
                <td className="px-4 py-3 font-medium tabular-nums text-ink">{formatTime(row.check_in, timeZone)}</td>
                <td className="px-4 py-3 font-medium tabular-nums text-ink">{formatTime(row.check_out, timeZone)}</td>
                <td className="whitespace-nowrap px-4 py-3 tabular-nums text-ink">{formatDuration(row.duration_seconds)}</td>
                <td className={cn('whitespace-nowrap px-4 py-3 tabular-nums', row.is_late ? 'font-medium text-warning' : 'text-ink-muted')}>{formatLate(row.late_minutes)}</td>
                <td className="px-4 py-3"><StatusBadges row={row} /></td>
                <td className="px-4 py-3"><RowActions row={row} canAdjust={canAdjust} onView={() => onView(row)} onAdjust={() => onAdjust(row)} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

/** /attendance/management — та же панель для руководства и HR. */
export function ManagementAttendancePage() {
  return <AdminAttendancePage mode="management" />
}
