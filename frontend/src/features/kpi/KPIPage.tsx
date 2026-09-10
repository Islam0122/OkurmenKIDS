import { useMemo, useState } from 'react'
import { BarChart3, BookOpen, CalendarCheck, ClipboardCheck, GraduationCap, Star, Users } from 'lucide-react'

import { TrendChart } from '@/components/charts/TrendChart'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Select } from '@/components/ui/Select'
import { StatCard } from '@/components/ui/StatCard'
import { useGroups } from '@/hooks/useGroups'
import { useAnalyticsDashboard } from '@/hooks/useKPI'
import { formatDateShort } from '@/utils/format'

import { getKPIPeriods } from './periods'
import type { KPIPeriodKey } from './periods'

export function KPIPage() {
  const [periodKey, setPeriodKey] = useState<KPIPeriodKey>('this_month')
  const [groupId, setGroupId] = useState('')
  const periods = useMemo(() => getKPIPeriods(), [])
  const period = periods.find((item) => item.key === periodKey) ?? periods[0]

  const { data: groupsData } = useGroups({})
  const { data, isPending, isError, refetch } = useAnalyticsDashboard({
    date_from: period.dateFrom,
    date_to: period.dateTo,
    ...(groupId ? { group: Number(groupId) } : {}),
  })

  return (
    <div>
      <PageHeader title="KPI" description="Считается прямо сейчас по реальным данным — посещаемости, занятиям и домашним заданиям." />

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-2">
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
        <div className="w-48">
          <Select
            aria-label="Группа"
            placeholder="Все группы"
            value={groupId}
            onChange={(event) => setGroupId(event.target.value)}
            options={(groupsData?.results ?? []).map((group) => ({ value: String(group.id), label: group.name }))}
          />
        </div>
      </div>

      {isPending ? <LoadingState label="Считаем KPI…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}

      {data ? (
        <>
          <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">
            <StatCard icon={Users} label="Группы" value={data.overview.groups} />
            <StatCard icon={GraduationCap} label="Студенты" value={data.overview.students} />
            <StatCard icon={BookOpen} label="Занятия" value={data.overview.lessons} />
            <StatCard icon={CalendarCheck} label="Посещаемость" value={`${data.overview.attendance_percent}%`} />
            <StatCard icon={ClipboardCheck} label="Выполнение ДЗ" value={`${data.overview.homework_completion_percent}%`} />
            <StatCard icon={Star} label="Средний балл" value={`${data.overview.average_score}/10`} />
            <StatCard icon={BarChart3} label="Проведено занятий" value={data.lessons.completed} hint={`из ${data.lessons.total}`} />
          </div>

          {data.attendance.total === 0 && data.homework.total_results === 0 ? (
            <p className="mb-4 text-sm text-ink-secondary">Нет данных за выбранный период.</p>
          ) : (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              {data.attendance.by_date.length > 1 ? (
                <TrendChart
                  title="Посещаемость, %"
                  max={100}
                  valueSuffix="%"
                  points={data.attendance.by_date.map((point) => ({ label: formatDateShort(point.date), value: point.percent }))}
                />
              ) : null}
              {data.homework.by_date.length > 1 ? (
                <TrendChart
                  title="Выполнение ДЗ, %"
                  max={100}
                  valueSuffix="%"
                  points={data.homework.by_date.map((point) => ({ label: formatDateShort(point.date), value: point.percent }))}
                />
              ) : null}
            </div>
          )}
        </>
      ) : null}
    </div>
  )
}
