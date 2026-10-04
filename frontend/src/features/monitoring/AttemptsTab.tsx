import { useState } from 'react'
import { Activity, BarChart3, CheckCircle2, ListChecks, PlayCircle, ShieldAlert, Users, XCircle } from 'lucide-react'

import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { FilterBar, FilterField } from '@/components/ui/FilterBar'
import { Input } from '@/components/ui/Input'
import { LoadingState } from '@/components/ui/LoadingState'
import { Pagination } from '@/components/ui/Pagination'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import { StatCard } from '@/components/ui/StatCard'
import { StatGrid } from '@/components/ui/StatGrid'
import { formatDuration } from '@/features/exams/examUi'
import { useMonitoringAttempts, useMonitoringFilterOptions, useMonitoringOverview } from '@/hooks/useMonitoring'
import type { MonitoringFilters } from '@/types/monitoring'

import { AttemptDrawer } from './AttemptDrawer'
import { STATUS_LABEL, SeverityBadge, StatusBadge, formatTime, percent } from './monitoringUi'

const PAGE_SIZE = 25

export function AttemptsTab({ filters, setFilters }: { filters: MonitoringFilters; setFilters: (f: MonitoringFilters) => void }) {
  const overview = useMonitoringOverview({ ...filters, page: undefined })
  const attempts = useMonitoringAttempts(filters)
  const options = useMonitoringFilterOptions()
  const [openId, setOpenId] = useState<string | null>(null)
  const set = (patch: MonitoringFilters) => setFilters({ ...filters, ...patch, page: 1 })
  const o = overview.data

  return (
    <>
      <StatGrid className="mb-6">
        <StatCard label="Активные экзамены" value={o?.active_exams ?? '—'} icon={PlayCircle} hint={o ? `тренажёров: ${o.active_trainers}` : undefined} />
        <StatCard label="Проходят сейчас" value={o?.active_students ?? '—'} icon={Users} />
        <StatCard label="Завершено" value={o?.completed ?? '—'} icon={ListChecks} />
        <StatCard label="Средний балл" value={percent(o?.average_score)} icon={BarChart3} />
        <StatCard label="Сдали" value={o?.passed ?? '—'} icon={CheckCircle2} />
        <StatCard label="Не сдали" value={o?.failed ?? '—'} icon={XCircle} tone={o && o.failed ? 'warning' : 'default'} />
        <StatCard label="Нарушения" value={o?.violations ?? '—'} icon={ShieldAlert} tone={o && o.violations ? 'danger' : 'default'} hint={o ? `попыток с нарушениями: ${o.flagged_attempts}` : undefined} />
        <StatCard label="Прервано системой" value={o?.terminated ?? '—'} icon={Activity} tone={o && o.terminated ? 'danger' : 'default'} />
      </StatGrid>

      <FilterBar>
        <FilterField size="lg"><SearchInput value={filters.q ?? ''} onChange={(q) => set({ q })} placeholder="Имя студента…" /></FilterField>
        <FilterField label="Группа" htmlFor="mf-group">
          <Select id="mf-group" value={filters.group ?? ''} onChange={(e) => set({ group: e.target.value })}
            options={[{ value: '', label: 'Все группы' }, ...(options.data?.groups ?? []).map((g) => ({ value: String(g.id), label: g.name }))]} />
        </FilterField>
        {options.data?.team_view ? (
          <FilterField label="Тренер" htmlFor="mf-teacher">
            <Select id="mf-teacher" value={filters.teacher ?? ''} onChange={(e) => set({ teacher: e.target.value })}
              options={[{ value: '', label: 'Все тренеры' }, ...options.data.teachers.map((t) => ({ value: String(t.id), label: t.name }))]} />
          </FilterField>
        ) : null}
        <FilterField label="Предмет" htmlFor="mf-subject">
          <Select id="mf-subject" value={filters.subject ?? ''} onChange={(e) => set({ subject: e.target.value })}
            options={[{ value: '', label: 'Все предметы' }, ...(options.data?.subjects ?? []).map((s) => ({ value: String(s.id), label: s.name }))]} />
        </FilterField>
        <FilterField label="Тренажёр / экзамен" htmlFor="mf-session">
          <Select id="mf-session" value={filters.session ?? ''} onChange={(e) => set({ session: e.target.value })}
            options={[{ value: '', label: 'Все' }, ...(options.data?.sessions ?? []).map((s) => ({ value: s.id, label: `${s.mode === 'exam' ? 'Экзамен' : 'Тренажёр'}: ${s.title}` }))]} />
        </FilterField>
        <FilterField label="Режим" htmlFor="mf-mode">
          <Select id="mf-mode" value={filters.mode ?? ''} onChange={(e) => set({ mode: e.target.value })}
            options={[{ value: '', label: 'Экзамены и тренажёры' }, { value: 'exam', label: 'Экзамены' }, { value: 'training', label: 'Тренажёры' }]} />
        </FilterField>
        <FilterField label="Статус" htmlFor="mf-status">
          <Select id="mf-status" value={filters.status ?? ''} onChange={(e) => set({ status: e.target.value })}
            options={[{ value: '', label: 'Все статусы' }, ...Object.entries(STATUS_LABEL).map(([value, label]) => ({ value, label }))]} />
        </FilterField>
        <FilterField label="С даты" htmlFor="mf-from"><Input id="mf-from" type="date" value={filters.date_from ?? ''} onChange={(e) => set({ date_from: e.target.value })} /></FilterField>
        <FilterField label="По дату" htmlFor="mf-to"><Input id="mf-to" type="date" value={filters.date_to ?? ''} onChange={(e) => set({ date_to: e.target.value })} /></FilterField>
        <FilterField label="Нарушения" htmlFor="mf-viol">
          <Select id="mf-viol" value={filters.violations ?? ''} onChange={(e) => set({ violations: e.target.value })}
            options={[{ value: '', label: 'Все попытки' }, { value: '1', label: 'Только с нарушениями' }]} />
        </FilterField>
      </FilterBar>

      {attempts.isLoading ? <LoadingState /> : attempts.isError ? <ErrorState onRetry={() => attempts.refetch()} /> : !attempts.data?.results.length ? (
        <EmptyState title="Попыток нет" description="Здесь появятся попытки студентов ваших групп — экзамены и тренажёры." />
      ) : (
        <div className="card overflow-hidden">
          <div className="scroll-x">
            <table className="w-full min-w-[960px] text-left text-sm">
              <thead className="bg-surface-hover text-xs uppercase tracking-wide text-ink-muted">
                <tr>
                  <th className="px-4 py-2 font-medium">Студент</th>
                  <th className="px-4 py-2 font-medium">Группа</th>
                  <th className="px-4 py-2 font-medium">Тренажёр / экзамен</th>
                  <th className="px-4 py-2 font-medium">Начало</th>
                  <th className="px-4 py-2 font-medium">Время</th>
                  <th className="px-4 py-2 font-medium">Прогресс</th>
                  <th className="px-4 py-2 font-medium">Статус</th>
                  <th className="px-4 py-2 font-medium">Балл</th>
                  <th className="px-4 py-2 font-medium">Нарушения</th>
                </tr>
              </thead>
              <tbody>
                {attempts.data.results.map((a) => (
                  <tr key={a.id} className="cursor-pointer border-t border-border hover:bg-surface-hover" onClick={() => setOpenId(a.id)}>
                    <td className="px-4 py-3 font-medium text-ink">
                      <button type="button" className="text-left hover:underline" onClick={(e) => { e.stopPropagation(); setOpenId(a.id) }}>{a.student_name}</button>
                    </td>
                    <td className="px-4 py-3 text-ink-secondary">{a.group?.name ?? '—'}</td>
                    <td className="px-4 py-3 text-ink-secondary">{a.session.title}<div className="text-xs text-ink-muted">{a.mode === 'exam' ? 'Экзамен' : 'Тренажёр'}</div></td>
                    <td className="px-4 py-3 text-ink-secondary">{formatTime(a.started_at)}</td>
                    <td className="px-4 py-3 font-mono text-ink">{a.status === 'in_progress' ? <span title="Осталось">{formatDuration(a.remaining_seconds)}</span> : formatDuration(a.duration_seconds)}</td>
                    <td className="px-4 py-3 text-ink">{a.answered} / {a.question_total}</td>
                    <td className="px-4 py-3"><StatusBadge status={a.status} /></td>
                    <td className="px-4 py-3 text-ink">{percent(a.score)}</td>
                    <td className="px-4 py-3">
                      <SeverityBadge severity={a.severity} />
                      <div className="mt-1 text-xs text-ink-muted">вкладки {a.tab_switch_count}{a.max_tab_switches !== null ? `/${a.max_tab_switches}` : ''} · экран {a.fullscreen_exits}</div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="px-4 pb-3">
            <Pagination page={filters.page ?? 1} pageSize={PAGE_SIZE} totalCount={attempts.data.count} onPageChange={(page) => setFilters({ ...filters, page })} />
          </div>
        </div>
      )}
      <AttemptDrawer attemptId={openId} onClose={() => setOpenId(null)} />
    </>
  )
}
