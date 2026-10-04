import { useState } from 'react'
import { BarChart3, CheckCircle2, ClipboardList, TrendingDown, TrendingUp, Users, XCircle } from 'lucide-react'

import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { FilterBar, FilterField } from '@/components/ui/FilterBar'
import { Input } from '@/components/ui/Input'
import { LoadingState } from '@/components/ui/LoadingState'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import { StatCard } from '@/components/ui/StatCard'
import { StatGrid } from '@/components/ui/StatGrid'
import { percent } from '@/features/monitoring/monitoringUi'
import { useMonitoringFilterOptions } from '@/hooks/useMonitoring'
import { useResultsSummary } from '@/hooks/useResults'
import type { MonitoringFilters } from '@/types/monitoring'

import { NO_RESULTS, ResultsBreakdown, ResultsDynamics, ResultsTable } from './resultsUi'

/** «Test Performance» report: filters (period, teacher, group, subject, test,
 * student search), totals, progress, breakdowns and the results table with
 * Excel export. Every number comes from /monitoring/results/* (backend scope). */
export function TestPerformanceReport() {
  const [filters, setFilters] = useState<MonitoringFilters>({})
  const options = useMonitoringFilterOptions()
  const summary = useResultsSummary(filters)
  const set = (patch: MonitoringFilters) => setFilters((current) => ({ ...current, ...patch }))
  const s = summary.data
  const dyn = s?.dynamics.filter((p) => p.average_score !== null) ?? []
  const progress = dyn.length > 1 ? Math.round(((dyn[dyn.length - 1].average_score ?? 0) - (dyn[0].average_score ?? 0)) * 10) / 10 : null

  return (
    <div className="space-y-6">
      <FilterBar>
        <FilterField label="С даты" htmlFor="tp-from"><Input id="tp-from" type="date" value={filters.date_from ?? ''} onChange={(e) => set({ date_from: e.target.value })} /></FilterField>
        <FilterField label="По дату" htmlFor="tp-to"><Input id="tp-to" type="date" value={filters.date_to ?? ''} onChange={(e) => set({ date_to: e.target.value })} /></FilterField>
        <FilterField label="Тренер" htmlFor="tp-teacher">
          <Select id="tp-teacher" value={filters.teacher ?? ''} onChange={(e) => set({ teacher: e.target.value })}
            options={[{ value: '', label: 'Все тренеры' }, ...(options.data?.teachers ?? []).map((t) => ({ value: String(t.id), label: t.name }))]} />
        </FilterField>
        <FilterField label="Группа" htmlFor="tp-group">
          <Select id="tp-group" value={filters.group ?? ''} onChange={(e) => set({ group: e.target.value })}
            options={[{ value: '', label: 'Все группы' }, ...(options.data?.groups ?? []).map((g) => ({ value: String(g.id), label: g.name }))]} />
        </FilterField>
        <FilterField label="Предмет" htmlFor="tp-subject">
          <Select id="tp-subject" value={filters.subject ?? ''} onChange={(e) => set({ subject: e.target.value })}
            options={[{ value: '', label: 'Все предметы' }, ...(options.data?.subjects ?? []).map((x) => ({ value: String(x.id), label: x.name }))]} />
        </FilterField>
        <FilterField label="Тест / сессия" htmlFor="tp-session">
          <Select id="tp-session" value={filters.session ?? ''} onChange={(e) => set({ session: e.target.value })}
            options={[{ value: '', label: 'Все' }, ...(options.data?.sessions ?? []).map((x) => ({ value: x.id, label: x.title }))]} />
        </FilterField>
        <FilterField size="lg" label="Студент / тест / группа"><SearchInput value={filters.q ?? ''} onChange={(q) => set({ q })} /></FilterField>
      </FilterBar>

      {summary.isLoading ? <LoadingState /> : summary.isError || !s ? <ErrorState onRetry={() => void summary.refetch()} /> : !s.attempts ? (
        <EmptyState icon={ClipboardList} title={NO_RESULTS} description="Измените фильтры или дождитесь результатов студентов." />
      ) : (
        <>
          <StatGrid>
            <StatCard label="Попыток" value={s.attempts} icon={ClipboardList} />
            <StatCard label="Студентов" value={s.students_tested} icon={Users} />
            <StatCard label="Средний результат" value={percent(s.average_score)} icon={BarChart3} />
            <StatCard label="Сдали" value={percent(s.pass_rate)} icon={CheckCircle2} hint={`не сдали ${percent(s.failed_rate)}`} />
            <StatCard label="Лучший результат" value={percent(s.best_score)} icon={TrendingUp} />
            <StatCard label="Минимальный" value={percent(s.lowest_score)} icon={TrendingDown} />
            <StatCard label="Не сдали" value={s.failed} icon={XCircle} tone={s.failed ? 'warning' : 'default'} />
            <StatCard label="Прогресс" value={progress === null ? '—' : `${progress > 0 ? '+' : ''}${progress}%`} icon={TrendingUp}
              hint="первый день периода → последний" />
          </StatGrid>
          <ResultsDynamics summary={s} />
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <ResultsBreakdown filters={filters} by="group" />
            <ResultsBreakdown filters={filters} by="subject" />
            {options.data?.team_view ? <ResultsBreakdown filters={filters} by="teacher" /> : <ResultsBreakdown filters={filters} by="test" />}
          </div>
          <ResultsTable filters={filters} exportable title="Результаты" />
        </>
      )}
    </div>
  )
}
