import { CalendarDays, ChevronLeft, ChevronRight, Trophy, Zap } from 'lucide-react'

import type { PeriodParams } from '@/api/publicLeaderboard'
import type { LeaderboardMeta, LeaderboardPeriodType } from '@/types/leaderboard'
import { cn } from '@/utils/cn'

import { MONTHS, weekRangeLabel } from './format'

const TYPES: { value: LeaderboardPeriodType; label: string; icon: typeof Trophy }[] = [
  { value: 'year', label: 'Год', icon: Trophy },
  { value: 'month', label: 'Месяц', icon: CalendarDays },
  { value: 'week', label: 'Неделя', icon: Zap },
]

export const selectClass =
  'h-10 min-w-0 appearance-none rounded-xl border-0 bg-white pl-3.5 pr-9 text-sm font-semibold text-lb-ink shadow-[0_0_0_1px_rgba(41,16,100,0.08)] transition ' +
  'bg-[url("data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 width=%2716%27 height=%2716%27 fill=%27none%27 stroke=%27%23777b91%27 stroke-width=%272%27%3E%3Cpath d=%27m4 6 4 4 4-4%27/%3E%3C/svg%3E")] ' +
  'bg-[length:16px] bg-[right_0.75rem_center] bg-no-repeat hover:shadow-[0_0_0_1px_rgba(59,22,141,0.3)] focus-visible:outline-lb-purple'

const arrowClass =
  'inline-flex size-10 items-center justify-center rounded-xl bg-white text-lb-muted shadow-[0_0_0_1px_rgba(41,16,100,0.08)] transition ' +
  'hover:text-lb-purple hover:shadow-[0_0_0_1px_rgba(59,22,141,0.3)] disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-lb-purple'

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
      <div
        role="radiogroup"
        aria-label="Период рейтинга"
        className="inline-flex h-11 items-center gap-1 rounded-2xl bg-white p-1 shadow-[0_0_0_1px_rgba(41,16,100,0.08),0_4px_12px_-8px_rgba(41,16,100,0.25)]"
      >
        {TYPES.map(({ value, label, icon: Icon }) => {
          const active = params.period === value
          return (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => onType(value)}
              className={cn(
                'inline-flex h-full items-center gap-1.5 rounded-xl px-3 text-sm font-semibold transition-all duration-200 focus-visible:outline-lb-purple sm:px-4',
                active
                  ? 'bg-lb-purple text-white shadow-[0_6px_14px_-6px_rgba(59,22,141,0.7)]'
                  : 'text-lb-muted hover:bg-lb-purple-50 hover:text-lb-purple',
              )}
            >
              <Icon className={cn('size-4', active ? 'text-lb-gold' : '')} aria-hidden />
              {label}
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
          <span
            className="inline-flex h-10 min-w-[11rem] items-center justify-center rounded-xl bg-white px-3 text-sm font-semibold tabular-nums text-lb-ink shadow-[0_0_0_1px_rgba(41,16,100,0.08)]"
            aria-live="polite"
          >
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
