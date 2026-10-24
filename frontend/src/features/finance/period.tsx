import { useSyncExternalStore } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CalendarRange } from 'lucide-react'

import { financeApi } from '@/api/finance'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import type { FinancePeriod, PeriodsResponse } from '@/types/finance'
import { cn } from '@/utils/cn'

import { FINANCE_KEY, today } from './ui'

const MONTHS = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']
const STORAGE_KEY = 'finance.period'
const RANGE = 'range'

export function currentMonth(): string {
  return today().slice(0, 7)
}

/** `2026-09` → 1 и 30 сентября. */
export function monthBounds(month: string): { date_from: string; date_to: string } {
  const [year, m] = month.split('-').map(Number)
  const last = new Date(year, m, 0).getDate()
  return { date_from: `${month}-01`, date_to: `${month}-${String(last).padStart(2, '0')}` }
}

export function monthLabel(month: string): string {
  const [year, m] = month.split('-').map(Number)
  return `${MONTHS[m - 1]} ${year}`
}

/** Месяц даты: `2026-09-20` → «Сентябрь 2026». */
export function periodMonth(date: string): string {
  return monthLabel(date.slice(0, 7))
}

function read(): FinancePeriod {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY)
    const parsed = raw ? (JSON.parse(raw) as FinancePeriod) : null
    if (parsed?.kind === 'month' && /^\d{4}-\d{2}$/.test(parsed.month)) return parsed
    if (parsed?.kind === 'range' && parsed.date_from && parsed.date_to) return parsed
  } catch {
    // хранилище недоступно — текущий месяц
  }
  return { kind: 'month', month: currentMonth() }
}

let state: FinancePeriod = read()
const listeners = new Set<() => void>()

export function setFinancePeriod(next: FinancePeriod) {
  state = next
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next))
  } catch {
    // выбор действует до перезагрузки страницы
  }
  listeners.forEach((listener) => listener())
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export interface PeriodRange {
  period: FinancePeriod
  date_from: string
  date_to: string
  label: string
  /** Период закончился раньше сегодняшнего дня (бухгалтер работает с прошлым месяцем). */
  isPast: boolean
  /** Параметры запроса к API: `month` или `date_from` + `date_to`. */
  params: Record<string, string>
}

export function rangeOf(period: FinancePeriod): PeriodRange {
  if (period.kind === 'month') {
    const bounds = monthBounds(period.month)
    return { period, ...bounds, label: monthLabel(period.month), isPast: bounds.date_to < today(),
      params: { month: period.month } }
  }
  const fmt = (d: string) => d.split('-').reverse().join('.')
  return { period, date_from: period.date_from, date_to: period.date_to,
    label: `${fmt(period.date_from)} — ${fmt(period.date_to)}`, isPast: period.date_to < today(),
    params: { date_from: period.date_from, date_to: period.date_to } }
}

/** Выбранный период финансового раздела — общий для всех страниц (Dashboard,
 * платежи, аналитика, добавление платежа); переживает переходы между ними. */
export function useFinancePeriod(): PeriodRange & { setPeriod: (next: FinancePeriod) => void } {
  const period = useSyncExternalStore(subscribe, () => state, () => state)
  return { ...rangeOf(period), setPeriod: setFinancePeriod }
}

export function usePeriods() {
  return useQuery({ queryKey: [...FINANCE_KEY, 'periods'], queryFn: financeApi.periods, staleTime: 10 * 60 * 1000 })
}

function monthOptions(data: PeriodsResponse | undefined, selected: string | null) {
  const months = data?.months.map((m) => ({ value: m.value, label: m.is_current ? `${m.label} (текущий)` : m.label })) ?? []
  // Выбранный месяц есть в списке, даже если данных за него ещё нет.
  if (selected && !months.some((m) => m.value === selected)) months.unshift({ value: selected, label: monthLabel(selected) })
  return [...months, { value: RANGE, label: 'Произвольный период…' }]
}

/** Переключатель периода: месяцы (Сентябрь 2026, Октябрь 2026, Ноябрь 2026…) и произвольный диапазон. */
export function PeriodSwitcher({ className }: { className?: string }) {
  const { period, setPeriod, date_from, date_to, isPast } = useFinancePeriod()
  const periods = usePeriods()
  const selected = period.kind === 'month' ? period.month : RANGE
  return (
    <div className={cn('flex flex-wrap items-center gap-2', className)}>
      <CalendarRange className={cn('size-4 shrink-0', isPast ? 'text-warning' : 'text-ink-secondary')} aria-hidden />
      <div className="w-48">
        <Select aria-label="Финансовый период" value={selected}
          options={monthOptions(periods.data, period.kind === 'month' ? period.month : null)}
          onChange={(e) => setPeriod(e.target.value === RANGE
            ? { kind: 'range', date_from, date_to }
            : { kind: 'month', month: e.target.value })} />
      </div>
      {period.kind === 'range' ? (
        <>
          <Input type="date" aria-label="Начало периода" className="w-40" value={period.date_from} max={period.date_to}
            onChange={(e) => e.target.value && setPeriod({ ...period, date_from: e.target.value })} />
          <Input type="date" aria-label="Конец периода" className="w-40" value={period.date_to} min={period.date_from}
            onChange={(e) => e.target.value && setPeriod({ ...period, date_to: e.target.value })} />
        </>
      ) : null}
      {isPast ? <span className="rounded-full bg-warning-soft px-2 py-0.5 text-xs font-medium text-warning">прошлый период</span> : null}
    </div>
  )
}
