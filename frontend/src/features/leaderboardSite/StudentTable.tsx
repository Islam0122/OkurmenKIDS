import type { LeaderboardStudent } from '@/types/leaderboard'
import { cn } from '@/utils/cn'

import { formatNumber } from './format'
import { Avatar, RankChangeBadge, RankNumber } from './ui'

function breakdownHint(row: LeaderboardStudent): string {
  const { attendance, homework, tests } = row.breakdown
  return `Посещаемость ${attendance} · ДЗ ${homework} · Тесты ${tests}`
}

function Name({ row }: { row: LeaderboardStudent }) {
  return (
    <span className={cn('block truncate font-medium', row.hidden ? 'italic text-ink-secondary' : 'text-ink')}>
      {row.name}
    </span>
  )
}

/**
 * The ranking below the podium: a real table from `md` up, a compact card
 * list on phones (no horizontal page scroll). The rank shown is always the
 * global place in the period, even when a filter is on.
 */
export function StudentTable({ rows, caption }: { rows: LeaderboardStudent[]; caption: string }) {
  return (
    <>
      <table className="hidden w-full table-fixed text-sm md:table">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="border-b border-lb-line text-left text-xs font-medium text-ink-secondary">
            <th scope="col" className="w-20 px-4 py-2.5">Место</th>
            <th scope="col" className="w-[42%] px-2 py-2.5 lg:w-[34%]">Студент</th>
            <th scope="col" className="px-2 py-2.5">Группа</th>
            <th scope="col" className="hidden px-2 py-2.5 lg:table-cell">Направление</th>
            <th scope="col" className="w-20 px-2 py-2.5 text-right">XP</th>
            <th scope="col" className="w-28 px-4 py-2.5 text-right">Динамика</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-lb-line">
          {rows.map((row) => (
            <tr key={row.key} className="transition-colors hover:bg-lb-purple-50/50">
              <td className="px-4 py-2.5"><RankNumber rank={row.rank} /></td>
              <td className="px-2 py-2.5">
                <div className="flex min-w-0 items-center gap-3">
                  <Avatar initials={row.initials} seed={row.key} hidden={row.hidden} />
                  <Name row={row} />
                </div>
              </td>
              <td className="truncate px-2 py-2.5 text-ink-secondary">{row.group?.name ?? '—'}</td>
              <td className="hidden truncate px-2 py-2.5 text-ink-secondary lg:table-cell">{row.course?.name ?? '—'}</td>
              <td className="px-2 py-2.5 text-right font-bold tabular-nums text-lb-deep" title={breakdownHint(row)}>
                {formatNumber(row.xp)}
              </td>
              <td className="px-4 py-2.5 text-right"><RankChangeBadge change={row.change} /></td>
            </tr>
          ))}
        </tbody>
      </table>

      <ol className="divide-y divide-lb-line md:hidden" aria-label={caption}>
        {rows.map((row) => (
          <li key={row.key} className="flex items-center gap-3 px-4 py-3">
            <RankNumber rank={row.rank} />
            <Avatar initials={row.initials} seed={row.key} hidden={row.hidden} />
            <div className="min-w-0 flex-1">
              <Name row={row} />
              <span className="block truncate text-xs text-ink-secondary">
                {[row.group?.name, row.course?.name].filter(Boolean).join(' · ') || '—'}
              </span>
            </div>
            <div className="flex shrink-0 flex-col items-end gap-0.5">
              <span className="text-sm font-bold tabular-nums text-lb-deep" title={breakdownHint(row)}>{formatNumber(row.xp)} XP</span>
              <RankChangeBadge change={row.change} />
            </div>
          </li>
        ))}
      </ol>
    </>
  )
}
