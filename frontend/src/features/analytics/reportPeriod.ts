import { useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'

import type { ReportParams, ReportPeriodKey } from '@/types/reports'

/**
 * The period of the Team Lead / Admin analytics pages: a relative preset
 * («Этот месяц», «Прошлый месяц», …) or one concrete calendar month
 * (`YYYY-MM`, e.g. `2026-09`). A month is sent to the backend as an explicit
 * `period=custom&start_date=…&end_date=…` range, so «Сентябрь 2026» always
 * means 1–30 September, whatever today is — never «this month» re-anchored
 * on the current date.
 *
 * The choice lives in the URL (`?period=2026-09`): a page refresh, a shared
 * link or a click through to a trainer/group keeps the same month.
 */
export type ReportPresetKey = Extract<ReportPeriodKey, 'this_week' | 'this_month' | 'last_month' | 'this_quarter'>
export type ReportPeriodChoice = ReportPresetKey | `${number}-${number}`

export const DEFAULT_REPORT_PERIOD: ReportPeriodChoice = 'this_month'
export const PERIOD_SEARCH_PARAM = 'period'

const PRESETS: ReportPresetKey[] = ['this_week', 'this_month', 'last_month', 'this_quarter']
const MONTH_RE = /^(\d{4})-(0[1-9]|1[0-2])$/
/** How many past calendar months the select offers, besides the presets. */
const MONTHS_BACK = 12

const MONTH_NAMES = [
  'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
  'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
]

function pad(value: number): string {
  return String(value).padStart(2, '0')
}

function monthKey(year: number, month: number): ReportPeriodChoice {
  return `${year}-${pad(month)}` as ReportPeriodChoice
}

function monthLabel(year: number, month: number): string {
  return `${MONTH_NAMES[month - 1]} ${year}`
}

/** `null` for anything that isn't a known preset or a valid `YYYY-MM`. */
export function parseReportPeriod(value: string | null | undefined): ReportPeriodChoice | null {
  if (!value) return null
  if ((PRESETS as string[]).includes(value)) return value as ReportPresetKey
  return MONTH_RE.test(value) ? (value as ReportPeriodChoice) : null
}

/** The API params of a choice: a preset as is, a month as its exact range. */
export function reportPeriodParams(choice: ReportPeriodChoice): Pick<ReportParams, 'period' | 'start_date' | 'end_date'> {
  const match = MONTH_RE.exec(choice)
  if (!match) return { period: choice as ReportPresetKey }
  const year = Number(match[1])
  const month = Number(match[2])
  // Day 0 of the next month = the last day of this one (28–31, leap years included).
  const lastDay = new Date(year, month, 0).getDate()
  return { period: 'custom', start_date: `${year}-${pad(month)}-01`, end_date: `${year}-${pad(month)}-${pad(lastDay)}` }
}

/** Select options: the presets (the two month presets name their month),
 * then the concrete calendar months from last month back, newest first. A month picked from a
 * link that is older than the list is still shown, so the select never
 * silently displays another period than the one the numbers are for. */
export function reportPeriodOptions(now: Date = new Date(), selected?: ReportPeriodChoice): { value: ReportPeriodChoice; label: string }[] {
  const year = now.getFullYear()
  const month = now.getMonth() + 1
  const last = month === 1 ? { year: year - 1, month: 12 } : { year, month: month - 1 }
  const quarter = Math.floor((month - 1) / 3) + 1

  const options: { value: ReportPeriodChoice; label: string }[] = [
    { value: 'this_week', label: 'Эта неделя' },
    { value: 'this_month', label: `Этот месяц (${monthLabel(year, month)})` },
    { value: 'last_month', label: `Прошлый месяц (${monthLabel(last.year, last.month)})` },
    { value: 'this_quarter', label: `${quarter} квартал ${year}` },
  ]
  // Concrete months, from last month back: MONTHS_BACK of them.
  for (let back = 1; back <= MONTHS_BACK; back += 1) {
    const date = new Date(year, month - 1 - back, 1)
    options.push({ value: monthKey(date.getFullYear(), date.getMonth() + 1), label: monthLabel(date.getFullYear(), date.getMonth() + 1) })
  }
  if (selected && !options.some((option) => option.value === selected)) {
    const match = MONTH_RE.exec(selected)
    if (match) options.push({ value: selected, label: monthLabel(Number(match[1]), Number(match[2])) })
  }
  return options
}

/** Path with the period carried over (`?period=…`), unless it's the default. */
export function withReportPeriod(path: string, choice: ReportPeriodChoice): string {
  if (choice === DEFAULT_REPORT_PERIOD) return path
  const separator = path.includes('?') ? '&' : '?'
  return `${path}${separator}${PERIOD_SEARCH_PARAM}=${encodeURIComponent(choice)}`
}

/** The page's period, read from and written to `?period=` (other search
 * params, e.g. the active tab, are kept). */
export function useReportPeriod(): [ReportPeriodChoice, (next: ReportPeriodChoice) => void] {
  const [searchParams, setSearchParams] = useSearchParams()
  const choice = parseReportPeriod(searchParams.get(PERIOD_SEARCH_PARAM)) ?? DEFAULT_REPORT_PERIOD

  const setChoice = useCallback(
    (next: ReportPeriodChoice) => {
      setSearchParams(
        (prev) => {
          const params = new URLSearchParams(prev)
          if (next === DEFAULT_REPORT_PERIOD) params.delete(PERIOD_SEARCH_PARAM)
          else params.set(PERIOD_SEARCH_PARAM, next)
          return params
        },
        { replace: true },
      )
    },
    [setSearchParams],
  )

  return [choice, setChoice]
}
