import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  AlertTriangle,
  BookOpen,
  CalendarCheck,
  CalendarClock,
  ClipboardCheck,
  GraduationCap,
  Info,
  Minus,
  ShieldAlert,
  ShieldCheck,
  Star,
  TrendingDown,
  TrendingUp,
  Users,
  XCircle,
} from 'lucide-react'

import { subjectsApi } from '@/api/subjects'
import { TrendChart } from '@/components/charts/TrendChart'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import type { BadgeTone } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { FilterBar, FilterField } from '@/components/ui/FilterBar'
import { LoadingState } from '@/components/ui/LoadingState'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { Select } from '@/components/ui/Select'
import { StatCard } from '@/components/ui/StatCard'
import type { StatCardTrend } from '@/components/ui/StatCard'
import { StatGrid } from '@/components/ui/StatGrid'
import { useGroups } from '@/hooks/useGroups'
import { useAnalyticsDashboard } from '@/hooks/useKPI'
import { cn } from '@/utils/cn'
import { formatDateShort, formatRuPercent } from '@/utils/format'
import { KPI_STATUS_BADGE_TONE } from './kpiStatus'
import type { ComparisonMetric, InsightSeverity, KPIMetrics } from '@/types/kpi'

import { getKPIPeriods, KPI_COMPARE_OPTIONS } from './periods'
import type { KPICompareOption, KPIPeriod } from './periods'
import type { KPIPeriodKey } from '@/types/kpi'

function trendOf(metric: ComparisonMetric, goodDirection: 'up' | 'down' = 'up'): StatCardTrend {
  return { direction: metric.trend, changePercent: metric.change_percent, goodDirection }
}

const SEVERITY_TONE: Record<InsightSeverity, BadgeTone> = {
  high: 'danger',
  medium: 'warning',
  low: 'muted',
}

const SEVERITY_LABEL: Record<InsightSeverity, string> = {
  high: 'Критично',
  medium: 'Внимание',
  low: 'Инфо',
}

/** A long insight list is collapsed to the first few; the rest is one tap away. */
const INSIGHTS_PREVIEW_COUNT = 5

const SEVERITY_ICON: Record<InsightSeverity, typeof AlertTriangle> = {
  high: XCircle,
  medium: AlertTriangle,
  low: Info,
}

const METRIC_LABELS: Record<keyof KPIMetrics, string> = {
  attendance: 'Посещаемость',
  homework: 'Домашние задания',
  lesson_completion: 'Проведённые занятия',
  progress: 'Прогресс',
  retention: 'Удержание студентов',
  teacher_workload: 'Нагрузка тренеров',
  test_score: 'Средний результат тестов',
  test_pass_rate: 'Сдали тесты',
}

const METRIC_ORDER: (keyof KPIMetrics)[] = [
  'attendance',
  'homework',
  'lesson_completion',
  'progress',
  'retention',
  'teacher_workload',
  'test_score',
  'test_pass_rate',
]

export function KPIPage() {
  const [periodKey, setPeriodKey] = useState<KPIPeriodKey>('this_month')
  const [groupId, setGroupId] = useState('')
  const [subjectId, setSubjectId] = useState('')
  const [compareKey, setCompareKey] = useState<KPICompareOption['key']>('off')
  const [showAllInsights, setShowAllInsights] = useState(false)

  const periods = useMemo(() => getKPIPeriods(), [])
  const period: KPIPeriod = periods.find((item) => item.key === periodKey) ?? periods[0]

  const { data: groupsData } = useGroups({})
  const { data: subjectsData } = useQuery({
    queryKey: ['subjects', 'list'],
    queryFn: () => subjectsApi.list({ is_active: true }),
  })

  const { data, isPending, isError, refetch } = useAnalyticsDashboard({
    period: periodKey,
    start_date: period.dateFrom,
    end_date: period.dateTo,
    ...(compareKey !== 'off' ? { compare: compareKey } : {}),
    ...(groupId ? { group: Number(groupId) } : {}),
    ...(subjectId ? { subject: Number(subjectId) } : {}),
  })

  const insights = data?.insights ?? []
  const visibleInsights = showAllInsights ? insights : insights.slice(0, INSIGHTS_PREVIEW_COUNT)
  const hiddenInsightsCount = insights.length - visibleInsights.length

  return (
    <div>
      <PageHeader
        title="Аналитика"
        description="Считается прямо сейчас по реальным данным — посещаемости, занятиям и домашним заданиям."
      />

      <div className="mb-6 space-y-3">
        <SegmentedControl<KPIPeriodKey>
          aria-label="Период"
          value={periodKey}
          onChange={setPeriodKey}
          options={periods.map((item) => ({ value: item.key, label: item.label }))}
        />
        <FilterBar className="mb-0">
          <FilterField>
            <Select
              aria-label="Сравнение"
              value={compareKey}
              onChange={(event) => setCompareKey(event.target.value as KPICompareOption['key'])}
              options={KPI_COMPARE_OPTIONS.map((option) => ({ value: option.key, label: option.label }))}
            />
          </FilterField>
          <FilterField>
            <Select
              aria-label="Группа"
              placeholder="Все группы"
              value={groupId}
              onChange={(event) => setGroupId(event.target.value)}
              options={(groupsData?.results ?? []).map((group) => ({ value: String(group.id), label: group.name }))}
            />
          </FilterField>
          <FilterField>
            <Select
              aria-label="Предмет"
              placeholder="Все предметы"
              value={subjectId}
              onChange={(event) => setSubjectId(event.target.value)}
              options={(subjectsData?.results ?? []).map((subject) => ({ value: String(subject.id), label: subject.name }))}
            />
          </FilterField>
        </FilterBar>
      </div>

      {isPending ? <LoadingState label="Считаем аналитику…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}

      {data ? (
        <div className="space-y-6">
          {/* 1. Total KPI — computed by the backend KPI engine; display only. */}
          <Card as="section">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
              <div>
                <p className="text-sm text-ink-secondary">Общий KPI</p>
                <p className="text-3xl font-bold text-ink tabular-nums sm:text-4xl">{formatRuPercent(data.kpi.total)}</p>
              </div>
              <Badge tone={KPI_STATUS_BADGE_TONE[data.kpi.status]}>{data.kpi.status_label}</Badge>
            </div>
            <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 border-t border-border pt-4 sm:grid-cols-3 xl:grid-cols-6">
              {METRIC_ORDER.map((key) => {
                const inKpi = data.kpi.weights.some((weight) => weight.key === key)
                return (
                  <div key={key} className="min-w-0">
                    <dt className="field-label">
                      {METRIC_LABELS[key]}
                      {inKpi ? null : <span className="block text-ink-muted">не входит в KPI</span>}
                    </dt>
                    <dd className="mt-0.5 text-base font-semibold text-ink tabular-nums">{formatRuPercent(data.metrics[key])}</dd>
                  </div>
                )
              })}
            </dl>
          </Card>

          <StatGrid>
            <StatCard
              icon={Users}
              label="Группы"
              value={data.groups.total_groups.value}
              trend={trendOf(data.groups.total_groups)}
            />
            <StatCard
              icon={GraduationCap}
              label="Студенты"
              value={data.students.total_students.value}
              trend={trendOf(data.students.total_students)}
            />
            <StatCard
              icon={BookOpen}
              label="Занятия"
              value={data.lessons.lessons_scheduled.value}
              hint={`сегодня: ${data.lessons.lessons_today.value}`}
              trend={trendOf(data.lessons.lessons_scheduled)}
            />
            <StatCard
              icon={CalendarCheck}
              label="Посещаемость"
              value={`${data.attendance.attendance_rate.value}%`}
              trend={trendOf(data.attendance.attendance_rate)}
            />
            <StatCard
              icon={ClipboardCheck}
              label="Сдача ДЗ"
              value={`${data.homework.submission_rate.value}%`}
              trend={trendOf(data.homework.submission_rate)}
            />
            <StatCard
              icon={Star}
              label="Средний балл"
              value={`${data.homework.average_score.value}/10`}
              trend={trendOf(data.homework.average_score)}
            />
            <StatCard
              icon={CalendarClock}
              label="Отменено занятий"
              value={data.lessons.lessons_cancelled.value}
              trend={trendOf(data.lessons.lessons_cancelled, 'down')}
            />
          </StatGrid>

          {/* 2. Students / Groups */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card as="section" title="Студенты">
              <div className="grid grid-cols-2 gap-3 text-sm">
                <Metric label="Активных" metric={data.students.active_students} />
                <Metric label="Неактивных" metric={data.students.inactive_students} goodDirection="down" />
                <Metric label="Новых за период" metric={data.students.new_students} />
                <Metric label="Выбыло за период" metric={data.students.students_left} goodDirection="down" />
              </div>
            </Card>
            <Card as="section" title="Группы">
              <div className="grid grid-cols-2 gap-3 text-sm">
                <Metric label="Активных" metric={data.groups.active_groups} />
                <Metric label="Приостановлено" metric={data.groups.paused_groups} goodDirection="down" />
                <Metric label="Близки к заполнению" metric={data.groups.groups_near_capacity} />
                <Metric label="Ср. студентов/группа" metric={data.groups.average_students_per_group} />
              </div>
            </Card>
          </div>

          {/* 3. Attendance trend */}
          {data.attendance.attendance_trend.length > 1 || data.homework.homework_completion_trend.length > 1 ? (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              {data.attendance.attendance_trend.length > 1 ? (
                <TrendChart
                  title="Посещаемость, %"
                  max={100}
                  valueSuffix="%"
                  points={data.attendance.attendance_trend.map((point) => ({
                    label: formatDateShort(point.date),
                    value: point.percent,
                  }))}
                />
              ) : null}
              {data.homework.homework_completion_trend.length > 1 ? (
                <TrendChart
                  title="Сдача ДЗ, %"
                  max={100}
                  valueSuffix="%"
                  points={data.homework.homework_completion_trend.map((point) => ({
                    label: formatDateShort(point.date),
                    value: point.percent,
                  }))}
                />
              ) : null}
            </div>
          ) : null}

          {/* 4. Lessons */}
          <Card as="section" title="Занятия">
            <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
              <Metric label="Запланировано" metric={data.lessons.lessons_scheduled} />
              <Metric label="Проведено" metric={data.lessons.lessons_completed} />
              <Metric label="Отменено" metric={data.lessons.lessons_cancelled} goodDirection="down" />
              <Metric label="% проведения" metric={data.lessons.lesson_completion_rate} suffix="%" />
            </div>
            {data.lessons.lessons_by_teacher.length > 0 ? (
              <div className="mt-4 space-y-1.5">
                {data.lessons.lessons_by_teacher.slice(0, 6).map((row) => (
                  <WorkloadBar
                    key={row.teacher_id}
                    label={row.teacher_name}
                    value={row.lessons}
                    max={Math.max(...data.lessons.lessons_by_teacher.map((r) => r.lessons))}
                  />
                ))}
              </div>
            ) : null}
          </Card>

          {/* 5. Homework */}
          <Card as="section" title="Домашние задания">
            <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
              <Metric label="Всего" metric={data.homework.homework_count} />
              <Metric label="Проверено" metric={data.homework.checked_count} />
              <Metric label="Не сдано" metric={data.homework.not_submitted_count} goodDirection="down" />
              <Metric label="Сдача" metric={data.homework.submission_rate} suffix="%" />
            </div>
          </Card>

          {/* 6. Test results (Test KPI) — reported alongside, not part of the total */}
          <Card as="section" title="Тесты" description="Результаты тестов студентов за период. Не входят в итоговый KPI.">
            <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-5">
              <Metric label="Средний результат" metric={data.tests.average_score} suffix="%" />
              <Metric label="Сдали" metric={data.tests.pass_rate} suffix="%" />
              <Metric label="Протестировано" metric={data.tests.students_tested} />
              <Metric label="Ниже порога" metric={data.tests.students_below_passing} goodDirection="down" />
              <Metric label="Попыток" metric={data.tests.attempts} />
            </div>
            {data.tests.average_score_trend.length > 1 ? (
              <div className="mt-4">
                <TrendChart
                  title="Средний результат тестов, %"
                  max={100}
                  valueSuffix="%"
                  points={data.tests.average_score_trend.map((point) => ({ label: formatDateShort(point.date), value: point.percent }))}
                />
              </div>
            ) : null}
          </Card>

          {/* 7. Insights / Attention Required */}
          <section>
            <h2 className="section-title mb-4 flex items-center gap-2">
              <ShieldAlert className="size-5 text-ink-secondary" aria-hidden /> Требует внимания
            </h2>
            {data.insights.length === 0 ? (
              <EmptyState icon={ShieldCheck} title="Ничего не требует внимания за выбранный период." />
            ) : (
              <div className="space-y-2">
                {visibleInsights.map((insight, index) => {
                  const Icon = SEVERITY_ICON[insight.severity]
                  return (
                    <div key={`${insight.metric}-${index}`} className="card card-body flex items-start gap-3">
                      <Icon
                        className={
                          insight.severity === 'high'
                            ? 'mt-0.5 size-4 shrink-0 text-danger'
                            : insight.severity === 'medium'
                              ? 'mt-0.5 size-4 shrink-0 text-warning'
                              : 'mt-0.5 size-4 shrink-0 text-ink-muted'
                        }
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="text-sm font-medium text-ink">{insight.title}</p>
                          <Badge tone={SEVERITY_TONE[insight.severity]}>{SEVERITY_LABEL[insight.severity]}</Badge>
                        </div>
                        <p className="mt-0.5 text-sm text-ink-secondary">{insight.message}</p>
                      </div>
                    </div>
                  )
                })}
                {hiddenInsightsCount > 0 ? (
                  <Button variant="secondary" className="w-full" onClick={() => setShowAllInsights(true)}>
                    Показать ещё {hiddenInsightsCount}
                  </Button>
                ) : null}
              </div>
            )}
          </section>
        </div>
      ) : null}
    </div>
  )
}

function Metric({
  label,
  metric,
  goodDirection = 'up',
  suffix = '',
}: {
  label: string
  metric: ComparisonMetric
  goodDirection?: 'up' | 'down'
  suffix?: string
}) {
  const trend = trendOf(metric, goodDirection)
  const isGood = trend.direction !== 'stable' && trend.direction === goodDirection
  const TrendIcon = trend.direction === 'up' ? TrendingUp : trend.direction === 'down' ? TrendingDown : Minus
  return (
    <div className="min-w-0">
      <p className="field-label">{label}</p>
      <p className="text-base font-semibold text-ink tabular-nums">
        {metric.value}
        {suffix}
      </p>
      {metric.change_percent !== null ? (
        <p
          className={cn(
            'inline-flex items-center gap-0.5 text-xs font-medium',
            isGood ? 'text-brand-600' : trend.direction === 'stable' ? 'text-ink-muted' : 'text-danger',
          )}
        >
          <TrendIcon className="size-3" aria-hidden />
          {metric.change_percent}%
        </p>
      ) : null}
    </div>
  )
}

function WorkloadBar({ label, value, max }: { label: string; value: number; max: number }) {
  const width = max > 0 ? Math.max(4, Math.round((value / max) * 100)) : 0
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="w-28 shrink-0 truncate text-ink-secondary sm:w-40">{label}</span>
      <div className="h-2 flex-1 rounded-full bg-surface-hover">
        <div className="h-2 rounded-full bg-brand-500" style={{ width: `${width}%` }} />
      </div>
      <span className="w-6 shrink-0 text-right text-ink-muted">{value}</span>
    </div>
  )
}
