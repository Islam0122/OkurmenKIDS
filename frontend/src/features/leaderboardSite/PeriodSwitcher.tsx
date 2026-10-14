import { ChevronLeft, ChevronRight } from 'lucide-react'

import type { PeriodParams } from '@/api/publicLeaderboard'
import type { LeaderboardMeta, LeaderboardPeriodType } from '@/types/leaderboard'
import { cn } from '@/utils/cn'

import { MONTHS, weekRangeLabel } from './format'

const TYPES: { value: LeaderboardPeriodType; label: string }[] = [
  { value: 'year', label: 'Год' },
  { value: 'month', label: 'Месяц' },
  { value: 'week', label: 'Неделя' },
]

const selectClass =
  'h-9 min-w-0 appearance-none rounded-lg border border-lb-line bg-white pl-3 pr-8 text-sm font-medium text-ink ' +
  'bg-[url("data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 width=%2716%27 height=%2716%27 fill=%27none%27 stroke=%27%2368736c%27 stroke-width=%272%27%3E%3Cpath d=%27m4 6 4 4 4-4%27/%3E%3C/svg%3E")] ' +
  'bg-[length:16px] bg-[right_0.5rem_center] bg-no-repeat hover:border-lb-purple-100 focus-visible:outline-lb-purple'

const arrowClass =
  'inline-flex size-9 items-center justify-center rounded-lg border border-lb-line bg-white text-ink-secondary transition-colors ' +
  'hover:border-lb-purple-100 hover:text-lb-purple disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-lb-purple'

/** Год / Месяц / Неделя plus the concrete year, month or week. Never offers
 * a period that has not started yet (the server refuses those anyway). */
export function PeriodSwitcher({ meta, params, onType, onChange, onShiftWeek }: {
  meta: LeaderboardMeta | undefined
  params: PeriodParams
  onType: (type: LeaderboardPeriodType) => void
  onChange: (next: Partial<PeriodParams>) => void
  onShiftWeek: (weeks: number) => void
}) {
  const current = meta?.current
  const years = meta?.years.length ? meta.years : current ? [current.year] : []
  const maxMonth = current && params.year === current.year ? current.month : 12
  const weekStart = params.week_start
  const isCurrentWeek = Boolean(weekStart && current && weekStart >= current.week_start)
  const isFirstWeek = Boolean(weekStart && meta?.first_date && weekStart <= meta.first_date)

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div role="radiogroup" aria-label="Период рейтинга" className="inline-flex h-10 items-center gap-1 rounded-xl border border-lb-line bg-white p-1">
        {TYPES.map((type) => {
          const active = params.period === type.value
          return (
            <button
              key={type.value}
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => onType(type.value)}
              className={cn(
                'h-full rounded-lg px-3.5 text-sm font-semibold transition-colors focus-visible:outline-lb-purple',
                active ? 'bg-lb-purple text-white shadow-sm' : 'text-ink-secondary hover:bg-lb-purple-50 hover:text-lb-purple',
              )}
            >
              {type.label}
            </button>
          )
        })}
      </div>

      {params.period !== 'week' ? (
        <div className="flex items-center gap-2">
          {params.period === 'month' ? (
            <select
              aria-label="Месяц"
              className={selectClass}
              value={params.month ?? ''}
              onChange={(e) => onChange({ period: 'month', month: Number(e.target.value) })}
            >
              {MONTHS.map((name, index) => (
                <option key={name} value={index + 1} disabled={index + 1 > maxMonth}>
                  {name}
                </option>
              ))}
            </select>
          ) : null}
          <select
            aria-label="Год"
            className={selectClass}
            value={params.year ?? ''}
            onChange={(e) => {
              const year = Number(e.target.value)
              const month = params.period === 'month' && current && year === current.year && (params.month ?? 1) > current.month
                ? current.month
                : params.month
              onChange({ period: params.period, year, month })
            }}
          >
            {years.map((year) => (
              <option key={year} value={year}>{year}</option>
            ))}
          </select>
        </div>
      ) : (
        <div className="flex items-center gap-1.5">
          <button type="button" className={arrowClass} onClick={() => onShiftWeek(-1)} disabled={isFirstWeek} aria-label="Предыдущая неделя">
            <ChevronLeft className="size-4" aria-hidden />
          </button>
          <span className="min-w-[10.5rem] text-center text-sm font-medium tabular-nums text-ink" aria-live="polite">
            {weekStart ? weekRangeLabel(weekStart) : '…'}
          </span>
          <button type="button" className={arrowClass} onClick={() => onShiftWeek(1)} disabled={isCurrentWeek} aria-label="Следующая неделя">
            <ChevronRight className="size-4" aria-hidden />
          </button>
        </div>
      )}
    </div>
  )
}
