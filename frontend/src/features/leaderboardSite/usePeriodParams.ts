import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'

import type { PeriodParams } from '@/api/publicLeaderboard'
import type { LeaderboardMeta, LeaderboardPeriodType } from '@/types/leaderboard'

import { addDays } from './format'

const TYPES: LeaderboardPeriodType[] = ['year', 'month', 'week']
const PERIOD_KEYS = ['period', 'year', 'month', 'week']

/** `?period=…&year=…` of the current URL without the page's own filters —
 * the selected period travels between the tabs, the filters do not. */
export function periodQuery(search: string): string {
  const params = new URLSearchParams(search)
  for (const name of [...params.keys()]) if (!PERIOD_KEYS.includes(name)) params.delete(name)
  const query = params.toString()
  return query ? `?${query}` : ''
}

/**
 * The selected period lives in the URL (?period=month&year=2026&month=10,
 * ?period=week&week=2026-10-12), so a link opens the same leaderboard and
 * both tabs share it. Missing parts fall back to the current period from
 * the server (its calendar, not the browser's).
 */
export function usePeriodParams(meta: LeaderboardMeta | undefined) {
  const [search, setSearch] = useSearchParams()

  const params = useMemo<PeriodParams>(() => {
    const raw = search.get('period') as LeaderboardPeriodType | null
    const period: LeaderboardPeriodType = raw && TYPES.includes(raw) ? raw : 'month'
    const current = meta?.current
    const year = Number(search.get('year')) || current?.year
    if (period === 'year') return { period, year }
    if (period === 'month') return { period, year, month: Number(search.get('month')) || current?.month }
    return { period, week_start: search.get('week') || current?.week_start }
  }, [search, meta])

  const update = useCallback(
    (next: Partial<PeriodParams>) => {
      setSearch((previous) => {
        const merged = new URLSearchParams(previous)
        const values: Record<string, string | number | undefined> = {
          period: next.period, year: next.year, month: next.month, week: next.week_start,
        }
        for (const [name, value] of Object.entries(values)) {
          if (value === undefined) continue
          merged.set(name, String(value))
        }
        return merged
      }, { replace: true })
    },
    [setSearch],
  )

  const setPeriodType = useCallback(
    (period: LeaderboardPeriodType) => {
      const current = meta?.current
      if (period === 'week') update({ period, week_start: params.week_start ?? current?.week_start })
      else update({ period, year: params.year ?? current?.year, month: params.month ?? current?.month })
    },
    [meta, params, update],
  )

  const shiftWeek = useCallback(
    (weeks: number) => {
      const start = params.week_start ?? meta?.current.week_start
      if (start) update({ period: 'week', week_start: addDays(start, weeks * 7) })
    },
    [meta, params.week_start, update],
  )

  /** Ready once the server's current period is known (or the URL is complete). */
  const ready = params.period === 'week' ? Boolean(params.week_start) : Boolean(params.year)

  return { params, ready, update, setPeriodType, shiftWeek }
}
