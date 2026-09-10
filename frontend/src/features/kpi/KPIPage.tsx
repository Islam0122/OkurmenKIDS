import { useMemo, useState } from 'react'
import { BarChart3, BookOpen, CalendarCheck, ClipboardCheck, Users } from 'lucide-react'

import { TrendChart } from '@/components/charts/TrendChart'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { StatCard } from '@/components/ui/StatCard'
import { useKPITeachers } from '@/hooks/useKPI'
import { formatDateShort } from '@/utils/format'

import { getKPIPeriods } from './periods'
import type { KPIPeriodKey } from './periods'

export function KPIPage() {
  const [periodKey, setPeriodKey] = useState<KPIPeriodKey>('this_month')
  const periods = useMemo(() => getKPIPeriods(), [])
  const period = periods.find((item) => item.key === periodKey) ?? periods[0]

  const periodSnapshots = useKPITeachers({ date_from: period.dateFrom, date_to: period.dateTo, ordering: 'date_to' })
  const latestOverall = useKPITeachers({ ordering: '-date_to' })

  if (periodSnapshots.isPending || latestOverall.isPending) return <LoadingState label="Считаем KPI…" />
  if (periodSnapshots.isError || latestOverall.isError) {
    return <ErrorState onRetry={() => { void periodSnapshots.refetch(); void latestOverall.refetch() }} />
  }

  const snapshotsInPeriod = periodSnapshots.data?.results ?? []
  const fallbackLatest = latestOverall.data?.results[0]
  const latest = snapshotsInPeriod.length > 0 ? snapshotsInPeriod[snapshotsInPeriod.length - 1] : fallbackLatest

  return (
    <div>
      <PageHeader title="KPI" description="Показатели рассчитываются на бэкенде — здесь только готовые снимки." />

      <div className="mb-6 flex flex-wrap gap-2">
        {periods.map((item) => (
          <Button
            key={item.key}
            variant={item.key === periodKey ? 'primary' : 'secondary'}
            size="sm"
            onClick={() => setPeriodKey(item.key)}
          >
            {item.label}
          </Button>
        ))}
      </div>

      {!latest ? (
        <EmptyState
          icon={BarChart3}
          title="KPI-снимков пока нет"
          description="Администратор ещё не запускал расчёт KPI для вас. Как только снимок появится, он отобразится здесь."
        />
      ) : (
        <>
          {snapshotsInPeriod.length === 0 ? (
            <p className="mb-4 text-sm text-ink-secondary">
              За выбранный период снимков нет. Показан последний доступный снимок: {formatDateShort(latest.date_from)}–
              {formatDateShort(latest.date_to)}.
            </p>
          ) : null}

          <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
            <StatCard icon={CalendarCheck} label="Посещаемость" value={`${latest.attendance_percent}%`} />
            <StatCard icon={ClipboardCheck} label="Выполнение ДЗ" value={`${latest.homework_completion_percent}%`} />
            <StatCard icon={BarChart3} label="Средний балл" value={`${latest.average_student_score}/10`} />
            <StatCard icon={BookOpen} label="Занятий" value={latest.total_lessons} hint={`${latest.completed_lessons} проведено`} />
            <StatCard icon={Users} label="Групп" value={latest.total_groups} />
          </div>

          {snapshotsInPeriod.length > 1 ? (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              <TrendChart
                title="Посещаемость, %"
                max={100}
                valueSuffix="%"
                points={snapshotsInPeriod.map((snapshot) => ({ label: formatDateShort(snapshot.date_to), value: snapshot.attendance_percent }))}
              />
              <TrendChart
                title="Выполнение ДЗ, %"
                max={100}
                valueSuffix="%"
                points={snapshotsInPeriod.map((snapshot) => ({ label: formatDateShort(snapshot.date_to), value: snapshot.homework_completion_percent }))}
              />
              <TrendChart
                title="Средний балл"
                max={10}
                points={snapshotsInPeriod.map((snapshot) => ({ label: formatDateShort(snapshot.date_to), value: snapshot.average_student_score }))}
              />
            </div>
          ) : null}
        </>
      )}
    </div>
  )
}
