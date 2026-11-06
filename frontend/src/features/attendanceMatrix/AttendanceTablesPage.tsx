import { useMemo, useState } from 'react'
import { ArrowLeft, BarChart3, CalendarDays, ChevronLeft, ChevronRight, Download, Users } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'

import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Select } from '@/components/ui/Select'
import { useToast } from '@/components/ui/Toast'
import { attendanceMatrixApi } from '@/api/attendanceMatrix'
import { useMatrixMeta, useMatrixOverview } from '@/hooks/useAttendanceMatrix'
import { extractErrorMessage } from '@/lib/apiError'
import type { OverviewGroup } from '@/types/attendanceMatrix'
import { cn } from '@/utils/cn'

import { AttendanceMatrix } from './AttendanceMatrix'
import { MONTH_NAMES, pct, percentTone, todayIso } from './ui'

function shiftMonth(month: string, delta: number): string {
  const [y, m] = month.split('-').map(Number)
  const d = new Date(y, m - 1 + delta, 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

/**
 * «Посещаемость групп» — one page for the Assistant, the Team Lead and the
 * Operations director: [предмет] [группа] [тренер] [месяц] → the group's
 * full attendance table (the same AttendanceMatrix every role uses). Only
 * the groups and subjects on offer differ — the server scopes them
 * (backend: apps.attendance_matrix.access).
 */
export function AttendanceTablesPage({ title = 'Посещаемость групп', summaryPath }: { title?: string; summaryPath?: string }) {
  const [params, setParams] = useSearchParams()
  const subject = params.get('subject') ?? ''
  const group = params.get('group') ?? ''
  const teacher = params.get('teacher') ?? ''
  const month = /^\d{4}-\d{2}$/.test(params.get('month') ?? '') ? (params.get('month') as string) : todayIso().slice(0, 7)
  const [exporting, setExporting] = useState(false)
  const { showToast } = useToast()

  const set = (patch: Record<string, string>) => {
    const next = new URLSearchParams(params)
    for (const [key, value] of Object.entries(patch)) {
      if (value) next.set(key, value)
      else next.delete(key)
    }
    setParams(next, { replace: true })
  }

  const meta = useMatrixMeta()
  const overviewParams = {
    date: `${month}-01`,
    subject: subject && subject !== 'none' ? Number(subject) : undefined,
    teacher: teacher ? Number(teacher) : undefined,
  }
  const overview = useMatrixOverview(overviewParams, !group)

  // Groups on offer: the user's groups (server-scoped), narrowed by subject and trainer.
  const groups = useMemo(() => (meta.data?.groups ?? []).filter((g) =>
    (!subject || subject === 'none' || g.subject_ids.includes(Number(subject))) && (!teacher || g.teacher_ids.includes(Number(teacher)))),
  [meta.data, subject, teacher])

  const onExport = async () => {
    setExporting(true)
    try {
      await attendanceMatrixApi.exportOverview(overviewParams)
    } catch (error) {
      showToast(extractErrorMessage(error, 'Не удалось сформировать Excel'), 'error')
    } finally {
      setExporting(false)
    }
  }

  const [year, mon] = month.split('-').map(Number)
  const selected = meta.data?.groups.find((g) => String(g.id) === group)

  return (
    <div className="space-y-5">
      <PageHeader
        title={title}
        description="Таблица посещаемости и домашних заданий по датам занятий — вся история групп"
        actions={
          <div className="flex flex-wrap gap-2">
            {summaryPath ? (
              <Link to={summaryPath} className="inline-flex h-10 items-center gap-2 rounded-lg px-4 text-sm font-medium text-ink-secondary hover:bg-surface-hover">
                <BarChart3 className="size-4" aria-hidden />Сводка
              </Link>
            ) : null}
            {!group ? (
              <Button variant="secondary" leftIcon={<Download className="size-4" aria-hidden />} isLoading={exporting} onClick={() => void onExport()}>
                Экспорт
              </Button>
            ) : null}
          </div>
        }
      />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Select aria-label="Предмет" placeholder="Все предметы" value={subject} onChange={(e) => set({ subject: e.target.value })}
          options={(meta.data?.subjects ?? []).map((s) => ({ value: String(s.id), label: s.name }))} />
        <Select aria-label="Группа" placeholder="Все группы" value={group} onChange={(e) => set({ group: e.target.value })}
          options={(selected && !groups.includes(selected) ? [selected, ...groups] : groups).map((g) => ({ value: String(g.id), label: g.name }))} />
        <Select aria-label="Тренер" placeholder="Все тренеры" value={teacher} onChange={(e) => set({ teacher: e.target.value })}
          options={(meta.data?.teachers ?? []).map((t) => ({ value: String(t.id), label: t.name }))} />
        <div className="flex min-w-0 gap-2">
          <label className="relative flex h-10 min-w-0 flex-1 items-center gap-2 rounded-lg border border-border bg-surface px-3 text-sm font-medium text-ink">
            <CalendarDays className="size-4 shrink-0 text-ink-muted" aria-hidden />
            <span className="truncate">{MONTH_NAMES[mon - 1]} {year}</span>
            <input aria-label="Месяц" type="month" value={month} onChange={(e) => e.target.value && set({ month: e.target.value })} className="absolute inset-0 cursor-pointer opacity-0" />
          </label>
          <div className="flex h-10 items-center rounded-lg border border-border bg-surface">
            <button type="button" aria-label="Предыдущий месяц" onClick={() => set({ month: shiftMonth(month, -1) })} className="flex h-full w-10 items-center justify-center text-ink-secondary hover:bg-surface-hover">
              <ChevronLeft className="size-4" aria-hidden />
            </button>
            <button type="button" aria-label="Следующий месяц" onClick={() => set({ month: shiftMonth(month, 1) })} className="flex h-full w-10 items-center justify-center border-l border-border text-ink-secondary hover:bg-surface-hover">
              <ChevronRight className="size-4" aria-hidden />
            </button>
          </div>
        </div>
      </div>

      {meta.isPending ? <LoadingState label="Загружаем группы…" /> : null}
      {meta.isError ? <ErrorState onRetry={() => void meta.refetch()} /> : null}

      {group ? (
        <div className="space-y-4">
          <button type="button" onClick={() => set({ group: '' })} className="inline-flex items-center gap-1.5 text-sm font-medium text-brand-700 hover:underline">
            <ArrowLeft className="size-4" aria-hidden />Все группы
          </button>
          <AttendanceMatrix
            key={group}
            groupId={Number(group)}
            date={`${month}-01`}
            onDateChange={(d) => set({ month: d.slice(0, 7) })}
            subject={subject}
            onSubjectChange={(value) => set({ subject: value })}
            teacher={teacher ? Number(teacher) : undefined}
          />
        </div>
      ) : meta.data ? (
        <GroupPicker groups={groups} stats={overview.data?.groups ?? []} loading={overview.isFetching} onOpen={(id) => set({ group: String(id) })} />
      ) : null}
    </div>
  )
}

function GroupPicker({ groups, stats, loading, onOpen }: {
  groups: { id: number; name: string; status: string; course: string }[]
  stats: OverviewGroup[]
  loading: boolean
  onOpen: (id: number) => void
}) {
  if (groups.length === 0) return <EmptyState icon={Users} title="Нет групп по выбранным фильтрам" />
  const byId = new Map(stats.map((g) => [g.id, g]))
  // Groups with lessons this month first, by attendance; the rest after, by name.
  const sorted = [...groups].sort((a, b) => Number(byId.has(b.id)) - Number(byId.has(a.id)) || a.name.localeCompare(b.name, 'ru'))
  const TH = 'px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-ink-muted'
  const TD = 'border-t border-border px-3 py-2.5'
  return (
    <div className={cn('card overflow-x-auto transition-opacity', loading && 'opacity-60')}>
      <table className="w-full min-w-[760px] text-sm">
        <thead className="bg-surface-muted">
          <tr>{['Группа', 'Тренеры', 'Студ.', 'Занятий', 'Посещаемость', 'ДЗ', 'Пропуски', ''].map((h, i) => <th key={i} className={TH}>{h}</th>)}</tr>
        </thead>
        <tbody>
          {sorted.map((g) => {
            const s = byId.get(g.id)
            return (
              <tr key={g.id} className="cursor-pointer hover:bg-surface-hover" onClick={() => onOpen(g.id)}>
                <td className={TD}>
                  <button type="button" className="text-left font-medium text-brand-700 hover:underline" onClick={(e) => { e.stopPropagation(); onOpen(g.id) }}>{g.name}</button>
                  <p className="text-xs text-ink-muted">{g.course}</p>
                </td>
                <td className={cn(TD, 'max-w-48 truncate text-ink-secondary')}>{s?.trainers.join(', ') || '—'}</td>
                <td className={TD}>{s?.students ?? '—'}</td>
                <td className={TD}>{s ? s.lessons : <span className="text-ink-muted">нет занятий</span>}</td>
                <td className={cn(TD, 'font-semibold', percentTone(s?.percent))}>{pct(s?.percent)}</td>
                <td className={cn(TD, percentTone(s?.hw_percent))}>{pct(s?.hw_percent)}</td>
                <td className={cn(TD, s?.absent ? 'text-danger' : '')}>{s?.absent ?? '—'}</td>
                <td className={cn(TD, 'text-right text-brand-700')}>Открыть таблицу</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
