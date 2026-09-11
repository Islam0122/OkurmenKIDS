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
  ShieldAlert,
  Star,
  Users,
  XCircle,
} from 'lucide-react'

import { subjectsApi } from '@/api/subjects'
import { TrendChart } from '@/components/charts/TrendChart'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import type { BadgeTone } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Select } from '@/components/ui/Select'
import { StatCard } from '@/components/ui/StatCard'
import type { StatCardTrend } from '@/components/ui/StatCard'
import { useGroups } from '@/hooks/useGroups'
import { useAnalyticsDashboard } from '@/hooks/useKPI'
import { formatDateShort } from '@/utils/format'
import type { AnalyticsHealthLevel, ComparisonMetric, InsightSeverity } from '@/types/kpi'

import { getKPIPeriods, KPI_COMPARE_OPTIONS } from './periods'
import type { KPICompareOption, KPIPeriod } from './periods'
import type { KPIPeriodKey } from '@/types/kpi'

function trendOf(metric: ComparisonMetric, goodDirection: 'up' | 'down' = 'up'): StatCardTrend {
  return { direction: metric.trend, changePercent: metric.change_percent, goodDirection }
}

const HEALTH_TONE: Record<AnalyticsHealthLevel, BadgeTone> = {
  excellent: 'success',
  good: 'success',
  fair: 'warning',
  poor: 'danger',
}

const HEALTH_LABEL: Record<AnalyticsHealthLevel, string> = {
  excellent: 'Отлично',
  good: 'Хорошо',
  fair: 'Средне',
  poor: 'Требует внимания',
}

const SEVERITY_TONE: Record<InsightSeverity, BadgeTone> = {
  high: 'danger',
  medium: 'warning',
  low: 'muted',
}

const SEVERITY_ICON: Record<InsightSeverity, typeof AlertTriangle> = {
  high: XCircle,
  medium: AlertTriangle,
  low: Info,
}

const HEALTH_COMPONENT_LABELS: Record<string, string> = {
  attendance: 'Посещаемость',
  homework: 'Домашние задания',
  lesson_completion: 'Проведение занятий',
  retention: 'Удержание студентов',
  teacher_workload: 'Загрузка тренеров',
}

export function KPIPage() {
  const [periodKey, setPeriodKey] = useState<KPIPeriodKey>('this_month')
  const [groupId, setGroupId] = useState('')
  const [subjectId, setSubjectId] = useState('')
  const [compareKey, setCompareKey] = useState<KPICompareOption['key']>('off')

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

  return (
    <div>
      <PageHeader
        title="Аналитика"
        description="Считается прямо сейчас по реальным данным — посещаемости, занятиям и домашним заданиям."
      />

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
        <div className="flex flex-wrap gap-2">
          <div className="w-44">
            <Select
              aria-label="Сравнение"
              value={compareKey}
              onChange={(event) => setCompareKey(event.target.value as KPICompareOption['key'])}
              options={KPI_COMPARE_OPTIONS.map((option) => ({ value: option.key, label: option.label }))}
            />
          </div>
          <div className="w-44">
            <Select
              aria-label="Группа"
              placeholder="Все группы"
              value={groupId}
              onChange={(event) => setGroupId(event.target.value)}
              options={(groupsData?.results ?? []).map((group) => ({ value: String(group.id), label: group.name }))}
            />
          </div>
          <div className="w-44">
            <Select
              aria-label="Предмет"
              placeholder="Все предметы"
              value={subjectId}
              onChange={(event) => setSubjectId(event.target.value)}
              options={(subjectsData?.results ?? []).map((subject) => ({ value: String(subject.id), label: subject.name }))}
            />
          </div>
        </div>
      </div>

      {isPending ? <LoadingState label="Считаем аналитику…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}

      {data ? (
        <>
          {/* 1. Academy Health + main KPIs */}
          <section className="mb-6 rounded-xl border border-border bg-surface p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-4">
                <div>
                  <p className="text-sm text-ink-secondary">Academy Health</p>
                  <p className="text-4xl font-bold text-ink">{data.health.score}</p>
                </div>
                <Badge tone={HEALTH_TONE[data.health.level]}>{HEALTH_LABEL[data.health.level]}</Badge>
              </div>
              <div className="flex flex-wrap gap-x-6 gap-y-2">
                {Object.entries(data.health.components).map(([key, value]) => (
                  <div key={key} className="text-right">
                    <p className="text-xs uppercase tracking-wide text-ink-muted">
                      {HEALTH_COMPONENT_LABELS[key] ?? key}
                    </p>
                    <p className="text-sm font-semibold text-ink">{value}</p>
                  </div>
                ))}
              </div>
            </div>
          </section>

          <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">
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
          </div>

          {/* 2. Students / Groups */}
          <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
            <section className="rounded-xl border border-border bg-surface p-4">
              <h2 className="mb-3 text-sm font-semibold text-ink">Студенты</h2>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <Metric label="Активных" metric={data.students.active_students} />
                <Metric label="Неактивных" metric={data.students.inactive_students} goodDirection="down" />
                <Metric label="Новых за период" metric={data.students.new_students} />
                <Metric label="Выбыло за период" metric={data.students.students_left} goodDirection="down" />
              </div>
            </section>
            <section className="rounded-xl border border-border bg-surface p-4">
              <h2 className="mb-3 text-sm font-semibold text-ink">Группы</h2>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <Metric label="Активных" metric={data.groups.active_groups} />
                <Metric label="Приостановлено" metric={data.groups.paused_groups} goodDirection="down" />
                <Metric label="Близки к заполнению" metric={data.groups.groups_near_capacity} />
                <Metric label="Ср. студентов/группа" metric={data.groups.average_students_per_group} />
              </div>
            </section>
          </div>

          {/* 3. Attendance trend */}
          {data.attendance.attendance_trend.length > 1 || data.homework.homework_completion_trend.length > 1 ? (
            <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-2">
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
          <section className="mb-6 rounded-xl border border-border bg-surface p-4">
            <h2 className="mb-3 text-sm font-semibold text-ink">Занятия</h2>
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
          </section>

          {/* 5. Homework */}
          <section className="mb-6 rounded-xl border border-border bg-surface p-4">
            <h2 className="mb-3 text-sm font-semibold text-ink">Домашние задания</h2>
            <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
              <Metric label="Всего" metric={data.homework.homework_count} />
              <Metric label="Проверено" metric={data.homework.checked_count} />
              <Metric label="Не сдано" metric={data.homework.not_submitted_count} goodDirection="down" />
              <Metric label="Сдача" metric={data.homework.submission_rate} suffix="%" />
            </div>
          </section>

          {/* 6. Insights / Attention Required */}
          <section className="mb-6">
            <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink">
              <ShieldAlert className="size-4" /> Требует внимания
            </h2>
            {data.insights.length === 0 ? (
              <p className="rounded-xl border border-border bg-surface p-4 text-sm text-ink-secondary">
                Ничего не требует внимания за выбранный период.
              </p>
            ) : (
              <div className="space-y-2">
                {data.insights.map((insight, index) => {
                  const Icon = SEVERITY_ICON[insight.severity]
                  return (
                    <div
                      key={`${insight.metric}-${index}`}
                      className="flex items-start gap-3 rounded-xl border border-border bg-surface p-3"
                    >
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
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-medium text-ink">{insight.title}</p>
                          <Badge tone={SEVERITY_TONE[insight.severity]}>{insight.severity}</Badge>
                        </div>
                        <p className="text-sm text-ink-secondary">{insight.message}</p>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </section>
        </>
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
  return (
    <div>
      <p className="text-xs text-ink-muted">{label}</p>
      <p className="text-base font-semibold text-ink">
        {metric.value}
        {suffix}
      </p>
      {metric.change_percent !== null ? (
        <p className={isGood ? 'text-xs text-brand-600' : trend.direction === 'stable' ? 'text-xs text-ink-muted' : 'text-xs text-danger'}>
          {trend.direction === 'up' ? '▲' : trend.direction === 'down' ? '▼' : '·'} {metric.change_percent}%
        </p>
      ) : null}
    </div>
  )
}

function WorkloadBar({ label, value, max }: { label: string; value: number; max: number }) {
  const width = max > 0 ? Math.max(4, Math.round((value / max) * 100)) : 0
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="w-28 shrink-0 truncate text-ink-secondary">{label}</span>
      <div className="h-2 flex-1 rounded-full bg-surface-hover">
        <div className="h-2 rounded-full bg-brand-500" style={{ width: `${width}%` }} />
      </div>
      <span className="w-6 shrink-0 text-right text-ink-muted">{value}</span>
    </div>
  )
}
