import { useMemo, useState } from 'react'
import { format, startOfMonth } from 'date-fns'
import { CalendarCheck2, CalendarX2, Layers, Plus, Users } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'

import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { DatePicker } from '@/components/ui/DatePicker'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { FilterBar, FilterField } from '@/components/ui/FilterBar'
import { LoadingState } from '@/components/ui/LoadingState'
import { Pagination } from '@/components/ui/Pagination'
import { Select } from '@/components/ui/Select'
import { StatCard } from '@/components/ui/StatCard'
import { StatGrid } from '@/components/ui/StatGrid'
import { useAuth } from '@/hooks/useAuth'
import { useParallelAnalytics, useParallelOptions, useParallelSessions } from '@/hooks/useParallelLessons'
import { extractErrorMessage } from '@/lib/apiError'
import { TrainerDot } from '@/features/scheduleBoard/LessonCard'
import type { SessionListParams, SessionStatus } from '@/types/parallelLessons'

import { SessionFormModal } from './SessionFormModal'
import { formatDay, hm, SessionStatusBadge, useParallelBase } from './shared'

const PAGE_SIZE = 20
const STATUS_OPTIONS = [
  { value: 'scheduled', label: 'Запланировано' },
  { value: 'in_progress', label: 'Идёт занятие' },
  { value: 'completed', label: 'Проведено' },
  { value: 'cancelled', label: 'Отменено' },
]

/**
 * «Параллельные занятия»: several groups study at the same time in one room
 * with one shared trainer. Admin / Assistant create and manage sessions,
 * a Team Lead reads all of them, a Trainer sees the sessions they give
 * (the backend scopes the list — apps.academy.parallel_session_views).
 */
export function ParallelLessonsPage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const base = useParallelBase()
  const role = user?.role
  const canCreate = role === 'admin' || role === 'assistant'
  const seesAll = canCreate || role === 'team_lead'

  const [filters, setFilters] = useState<SessionListParams>({})
  const [page, setPage] = useState(1)
  const [creating, setCreating] = useState(false)
  const params = useMemo(() => ({ ...filters, page }), [filters, page])
  const list = useParallelSessions(params)
  const options = useParallelOptions(seesAll)

  const today = new Date()
  const period = { start: format(startOfMonth(today), 'yyyy-MM-dd'), end: format(today, 'yyyy-MM-dd') }
  const analytics = useParallelAnalytics(period)

  const set = (patch: SessionListParams) => {
    setPage(1)
    setFilters((current) => ({ ...current, ...patch }))
  }
  const num = (value: string) => (value ? Number(value) : undefined)

  return (
    <div className="space-y-6">
      <PageHeader
        title="Параллельные занятия"
        description="Несколько групп одновременно в одной аудитории с одним тренером — одно общее занятие. Посещаемость и ДЗ у каждой группы свои."
        actions={canCreate ? <Button leftIcon={<Plus className="size-4" aria-hidden />} onClick={() => setCreating(true)}>Создать занятие</Button> : null}
      />

      {analytics.data ? (
        <StatGrid>
          <StatCard label="Занятий в этом месяце" value={analytics.data.totals.sessions} icon={Layers} />
          <StatCard label="Проведено" value={analytics.data.totals.completed} icon={CalendarCheck2} />
          <StatCard label="Отменено" value={analytics.data.totals.cancelled} icon={CalendarX2} tone={analytics.data.totals.cancelled ? 'warning' : 'default'} />
          <StatCard label="Групп / студентов" value={`${analytics.data.totals.groups} / ${analytics.data.totals.students}`} icon={Users}
            hint={`${analytics.data.totals.group_participations} участий групп`} />
        </StatGrid>
      ) : null}

      <FilterBar>
        <FilterField label="Дата" htmlFor="pl-date">
          <DatePicker id="pl-date" value={filters.date ?? ''} onChange={(e) => set({ date: e.target.value || undefined })} />
        </FilterField>
        {seesAll ? (
          <FilterField label="Тренер" htmlFor="pl-teacher">
            <Select id="pl-teacher" placeholder="Все тренеры" value={String(filters.teacher ?? '')}
              options={(options.data?.teachers ?? []).map((t) => ({ value: String(t.id), label: t.name }))}
              onChange={(e) => set({ teacher: num(e.target.value) })} />
          </FilterField>
        ) : null}
        {seesAll ? (
          <FilterField label="Аудитория" htmlFor="pl-room">
            <Select id="pl-room" placeholder="Все аудитории" value={String(filters.room ?? '')}
              options={(options.data?.rooms ?? []).map((r) => ({ value: String(r.id), label: r.name }))}
              onChange={(e) => set({ room: num(e.target.value) })} />
          </FilterField>
        ) : null}
        {seesAll ? (
          <FilterField label="Группа" htmlFor="pl-group">
            <Select id="pl-group" placeholder="Все группы" value={String(filters.group ?? '')}
              options={(options.data?.groups ?? []).map((g) => ({ value: String(g.id), label: g.name }))}
              onChange={(e) => set({ group: num(e.target.value) })} />
          </FilterField>
        ) : null}
        <FilterField label="Статус" htmlFor="pl-status">
          <Select id="pl-status" placeholder="Все статусы" value={filters.status ?? ''} options={STATUS_OPTIONS}
            onChange={(e) => set({ status: (e.target.value || undefined) as SessionStatus | undefined })} />
        </FilterField>
      </FilterBar>

      {list.isLoading ? <LoadingState label="Загрузка занятий…" /> : list.isError ? (
        <ErrorState message={extractErrorMessage(list.error)} onRetry={() => void list.refetch()} />
      ) : !list.data?.results.length ? (
        <EmptyState icon={Layers} title="Параллельных занятий нет"
          description={canCreate ? 'Создайте общее занятие для нескольких групп — тренер, аудитория и время будут проверены на занятость.' : 'Здесь появятся общие занятия нескольких групп.'} />
      ) : (
        <Card padding="none">
          <ul className="divide-y divide-border" aria-label="Параллельные занятия">
            {list.data.results.map((session) => (
              <li key={session.id}>
                <Link to={`${base}/${session.id}`} className="flex flex-col gap-2 px-4 py-3 hover:bg-surface-hover sm:flex-row sm:items-center sm:gap-4">
                  <div className="min-w-36">
                    <p className="font-semibold text-ink first-letter:uppercase">{formatDay(session.date, 'd MMM, EEEEEE')}</p>
                    <p className="text-sm tabular-nums text-ink-secondary">{hm(session.start_time)}–{hm(session.end_time)}</p>
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium text-ink">{session.topic || 'Без темы'}</p>
                    <p className="flex flex-wrap items-center gap-x-2 text-sm text-ink-secondary">
                      <span className="inline-flex items-center gap-1.5"><TrainerDot color={session.teacher.color} />{session.teacher.name}</span>
                      <span>· {session.room.name}</span>
                      <span>· {session.students_count} студ.</span>
                    </p>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {session.groups.filter((p) => p.status === 'active').map((p) => <Badge key={p.id}>{p.group.name}</Badge>)}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 sm:flex-col sm:items-end">
                    <SessionStatusBadge status={session.status} label={session.status_display} />
                    <span className="text-xs text-ink-muted">{session.groups_count} групп</span>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
          <div className="border-t border-border px-4 py-3">
            <Pagination page={page} pageSize={PAGE_SIZE} totalCount={list.data.count} onPageChange={setPage} />
          </div>
        </Card>
      )}

      {seesAll && analytics.data?.workload.length ? (
        <Card title="Нагрузка тренеров" description="Одно параллельное занятие — одно проведённое занятие тренера, сколько бы групп в нём ни было.">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-ink-secondary"><th className="py-2 pr-4 font-medium">Тренер</th><th className="py-2 pr-4 font-medium">Занятий</th><th className="py-2 pr-4 font-medium">Проведено</th><th className="py-2 pr-4 font-medium">Участий групп</th><th className="py-2 font-medium">Часов</th></tr></thead>
              <tbody className="divide-y divide-border">
                {analytics.data.workload.map((row) => (
                  <tr key={row.teacher.id}><td className="py-2 pr-4 text-ink">{row.teacher.name}</td><td className="py-2 pr-4 tabular-nums">{row.sessions}</td><td className="py-2 pr-4 tabular-nums">{row.completed}</td><td className="py-2 pr-4 tabular-nums">{row.groups}</td><td className="py-2 tabular-nums">{(row.minutes / 60).toFixed(1)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ) : null}

      {creating ? <SessionFormModal onClose={() => setCreating(false)} onSaved={(session) => navigate(`${base}/${session.id}`)} /> : null}
    </div>
  )
}
