import { endOfWeek, format, startOfMonth, startOfWeek, subDays, subMonths, subWeeks } from 'date-fns'

import type { KPIPeriodKey } from '@/types/kpi'

export interface KPIPeriod {
  key: KPIPeriodKey
  label: string
  dateFrom: string
  dateTo: string
}

function toISODate(date: Date): string {
  return format(date, 'yyyy-MM-dd')
}

/** The Analytics Dashboard's quick period presets (spec §2) — mirrors
 * `apps.academy.services.analytics.period.resolve_period` exactly, so a
 * period picked here and one picked on the Django admin dashboard mean the
 * same date range. `custom` has no fixed range — the caller supplies its
 * own start/end via the date pickers. */
export function getKPIPeriods(now = new Date()): KPIPeriod[] {
  const today = toISODate(now)
  const yesterday = toISODate(subDays(now, 1))
  const last7Start = toISODate(subDays(now, 6))
  const weekStart = startOfWeek(now, { weekStartsOn: 1 })
  const weekEnd = endOfWeek(now, { weekStartsOn: 1 })
  const lastWeekStart = startOfWeek(subWeeks(now, 1), { weekStartsOn: 1 })
  const lastWeekEnd = endOfWeek(subWeeks(now, 1), { weekStartsOn: 1 })
  const monthStart = startOfMonth(now)
  const lastMonthStart = startOfMonth(subMonths(now, 1))
  const lastMonthEnd = new Date(monthStart.getTime() - 1)

  return [
    { key: 'today', label: 'Сегодня', dateFrom: today, dateTo: today },
    { key: 'yesterday', label: 'Вчера', dateFrom: yesterday, dateTo: yesterday },
    { key: 'last_7_days', label: 'Последние 7 дней', dateFrom: last7Start, dateTo: today },
    { key: 'this_week', label: 'Эта неделя', dateFrom: toISODate(weekStart), dateTo: toISODate(weekEnd) },
    { key: 'last_week', label: 'Прошлая неделя', dateFrom: toISODate(lastWeekStart), dateTo: toISODate(lastWeekEnd) },
    { key: 'this_month', label: 'Этот месяц', dateFrom: toISODate(monthStart), dateTo: today },
    { key: 'last_month', label: 'Прошлый месяц', dateFrom: toISODate(lastMonthStart), dateTo: toISODate(lastMonthEnd) },
  ]
}

export interface KPICompareOption {
  key: 'off' | 'previous_period' | 'previous_month' | 'previous_week'
  label: string
}

/** Spec §2's comparison choices ("Custom comparison period" is handled
 * separately, via explicit compare_start_date/compare_end_date pickers,
 * not as a quick option here). */
export const KPI_COMPARE_OPTIONS: KPICompareOption[] = [
  { key: 'off', label: 'Без сравнения' },
  { key: 'previous_period', label: 'С предыдущим периодом' },
  { key: 'previous_week', label: 'С прошлой неделей' },
  { key: 'previous_month', label: 'С прошлым месяцем' },
]
