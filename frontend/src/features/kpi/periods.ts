import { endOfMonth, format, startOfMonth, subMonths } from 'date-fns'

export type KPIPeriodKey = 'this_month' | 'last_month' | 'last_3_months'

export interface KPIPeriod {
  key: KPIPeriodKey
  label: string
  dateFrom: string
  dateTo: string
}

function toISODate(date: Date): string {
  return format(date, 'yyyy-MM-dd')
}

/** Preset date ranges used to filter existing KPITeacher snapshots — never a computed range of our own. */
export function getKPIPeriods(now = new Date()): KPIPeriod[] {
  const thisMonthStart = startOfMonth(now)
  const lastMonthStart = startOfMonth(subMonths(now, 1))
  const lastMonthEnd = endOfMonth(subMonths(now, 1))
  const threeMonthsAgoStart = startOfMonth(subMonths(now, 2))

  return [
    { key: 'this_month', label: 'Этот месяц', dateFrom: toISODate(thisMonthStart), dateTo: toISODate(now) },
    { key: 'last_month', label: 'Прошлый месяц', dateFrom: toISODate(lastMonthStart), dateTo: toISODate(lastMonthEnd) },
    {
      key: 'last_3_months',
      label: 'Последние 3 месяца',
      dateFrom: toISODate(threeMonthsAgoStart),
      dateTo: toISODate(now),
    },
  ]
}
