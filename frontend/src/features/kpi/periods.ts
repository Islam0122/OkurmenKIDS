import { endOfWeek, format, startOfMonth, startOfWeek, startOfYear, subMonths } from 'date-fns'

export type KPIPeriodKey = 'today' | 'this_week' | 'this_month' | 'last_month' | 'this_year'

export interface KPIPeriod {
  key: KPIPeriodKey
  label: string
  dateFrom: string
  dateTo: string
}

function toISODate(date: Date): string {
  return format(date, 'yyyy-MM-dd')
}

/** The Analytics Dashboard's quick period presets — mirrors the Django Admin dashboard's own. */
export function getKPIPeriods(now = new Date()): KPIPeriod[] {
  const today = toISODate(now)
  const weekStart = startOfWeek(now, { weekStartsOn: 1 })
  const weekEnd = endOfWeek(now, { weekStartsOn: 1 })
  const monthStart = startOfMonth(now)
  const lastMonthStart = startOfMonth(subMonths(now, 1))
  const lastMonthEnd = new Date(monthStart.getTime() - 1)
  const yearStart = startOfYear(now)

  return [
    { key: 'today', label: 'Сегодня', dateFrom: today, dateTo: today },
    { key: 'this_week', label: 'Эта неделя', dateFrom: toISODate(weekStart), dateTo: toISODate(weekEnd) },
    { key: 'this_month', label: 'Этот месяц', dateFrom: toISODate(monthStart), dateTo: today },
    { key: 'last_month', label: 'Прошлый месяц', dateFrom: toISODate(lastMonthStart), dateTo: toISODate(lastMonthEnd) },
    { key: 'this_year', label: 'Этот год', dateFrom: toISODate(yearStart), dateTo: today },
  ]
}
