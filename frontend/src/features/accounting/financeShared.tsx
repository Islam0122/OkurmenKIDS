import { useState } from 'react'

import { Badge } from '@/components/ui/Badge'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import type { FinanceRange, MetricChange } from '@/types/accounting'

import { formatDate, som, today } from './shared'

export type RangeChoice = { kind: 'month'; month: string } | { kind: 'range'; date_from: string; date_to: string }

export const SHORT_MONTHS = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']

export function currentMonthKey(): string {
  return today().slice(0, 7)
}

export function rangeParams(choice: RangeChoice): FinanceRange {
  return choice.kind === 'month' ? { month: choice.month } : { date_from: choice.date_from, date_to: choice.date_to }
}

/** Период финансовых страниц: по умолчанию текущий месяц. */
export function useFinanceRange(initial?: RangeChoice) {
  const [choice, setChoice] = useState<RangeChoice>(initial ?? { kind: 'month', month: currentMonthKey() })
  return { choice, setChoice, params: rangeParams(choice) }
}

/** Месяц или произвольный диапазон дат. */
export function RangePicker({ value, onChange }: { value: RangeChoice; onChange: (next: RangeChoice) => void }) {
  return (
    <div className="flex flex-wrap items-end gap-2">
      <Select aria-label="Тип периода" className="w-40" value={value.kind}
        options={[{ value: 'month', label: 'Месяц' }, { value: 'range', label: 'Период' }]}
        onChange={(e) => onChange(e.target.value === 'month'
          ? { kind: 'month', month: currentMonthKey() }
          : { kind: 'range', date_from: `${currentMonthKey()}-01`, date_to: today() })} />
      {value.kind === 'month' ? (
        <Input aria-label="Месяц" type="month" className="w-44" value={value.month}
          onChange={(e) => e.target.value && onChange({ kind: 'month', month: e.target.value })} />
      ) : (
        <>
          <Input aria-label="С даты" type="date" className="w-40" value={value.date_from}
            onChange={(e) => e.target.value && onChange({ ...value, date_from: e.target.value })} />
          <Input aria-label="По дату" type="date" className="w-40" value={value.date_to}
            onChange={(e) => e.target.value && onChange({ ...value, date_to: e.target.value })} />
        </>
      )}
    </div>
  )
}

export function rangeLabel(dateFrom: string, dateTo: string): string {
  return `${formatDate(dateFrom)} – ${formatDate(dateTo)}`
}

/** Изменение к предыдущему периоду. `goodDirection` — какой рост считать хорошим
 * (больше расходов — не хорошо), поэтому цвет не выводится из знака. */
export function ChangeBadge({ change, goodDirection = 'up' }: { change: MetricChange; goodDirection?: 'up' | 'down' }) {
  const delta = Number(change.delta)
  if (!delta) return <Badge tone="muted">без изменений</Badge>
  const good = (delta > 0) === (goodDirection === 'up')
  const sign = delta > 0 ? '+' : ''
  return (
    <Badge tone={good ? 'success' : 'danger'}>
      {sign}{som(change.delta)}{change.percent !== null ? ` (${sign}${Number(change.percent)}%)` : ''}
    </Badge>
  )
}

export const METHOD_FILTER = [
  { value: 'cash', label: 'Наличные' },
  { value: 'bank', label: 'Банковский перевод' },
  { value: 'card', label: 'Карта / QR' },
  { value: 'other', label: 'Другое' },
]
