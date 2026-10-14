import type { LeaderboardStudent } from '@/types/leaderboard'
import { cn } from '@/utils/cn'

import { formatNumber } from './format'
import { Avatar, RankChangeBadge, RankNumber } from './ui'

function breakdownHint(row: LeaderboardStudent): string {
  const { attendance, homework, tests } = row.breakdown
  return `Посещаемость ${attendance} · ДЗ ${homework} · Тесты ${tests}`
}

/** A thin medal-colored edge on the top-3 rows. */
const TOP_EDGE: Record<number, string> = {
  1: 'shadow-[inset_3px_0_0_#f6b82f] bg-lb-gold-soft/40',
  2: 'shadow-[inset_3px_0_0_#a9b2c6]',
  3: 'shadow-[inset_3px_0_0_#cd8346]',
}

function Name({ row }: { row: LeaderboardStudent }) {
  return (
    <span className={cn('block truncate font-semibold', row.hidden ? 'italic text-lb-muted' : 'text-lb-ink')}>
      {row.name}
    </span>
  )
}

function Xp({ value, hint }: { value: number; hint: string }) {
  return (
    <span className="inline-flex items-baseline gap-1 whitespace-nowrap" title={hint}>
      <span className="text-base font-extrabold tabular-nums text-lb-deep">{formatNumber(value)}</span>
      <span className="text-[11px] font-bold text-lb-gold-dark">XP</span>
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
          <tr className="whitespace-nowrap bg-lb-bg/70 text-left text-[11px] font-bold uppercase tracking-wider text-lb-muted">
            <th scope="col" className="w-[4.75rem] px-4 py-2.5">Место</th>
            <th scope="col" className="w-[40%] px-2 py-2.5 xl:w-[32%]">Студент</th>
            <th scope="col" className="px-2 py-2.5">Группа</th>
            <th scope="col" className="hidden px-2 py-2.5 xl:table-cell">Направление</th>
            <th scope="col" className="w-24 px-2 py-2.5 text-right">XP</th>
            <th scope="col" className="w-[6.5rem] px-4 py-2.5 text-right">Динамика</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-lb-line">
          {rows.map((row) => (
            <tr key={row.key} className={cn('transition-colors duration-150 hover:bg-lb-purple-50/60', TOP_EDGE[row.rank])}>
              <td className="px-4 py-2.5"><RankNumber rank={row.rank} /></td>
              <td className="px-2 py-2.5">
                <div className="flex min-w-0 items-center gap-3">
                  <Avatar initials={row.initials} seed={row.key} hidden={row.hidden} />
                  <Name row={row} />
                </div>
              </td>
              <td className="truncate px-2 py-2.5 font-medium text-lb-ink/80">{row.group?.name ?? '—'}</td>
              <td className="hidden truncate px-2 py-2.5 text-lb-muted xl:table-cell">{row.course?.name ?? '—'}</td>
              <td className="px-2 py-2.5 text-right"><Xp value={row.xp} hint={breakdownHint(row)} /></td>
              <td className="px-4 py-2.5 text-right"><RankChangeBadge change={row.change} /></td>
            </tr>
          ))}
        </tbody>
      </table>

      <ol className="divide-y divide-lb-line md:hidden" aria-label={caption}>
        {rows.map((row) => (
          <li key={row.key} className={cn('flex items-center gap-3 px-4 py-3', TOP_EDGE[row.rank])}>
            <RankNumber rank={row.rank} />
            <Avatar initials={row.initials} seed={row.key} hidden={row.hidden} />
            <div className="min-w-0 flex-1">
              <Name row={row} />
              <span className="block truncate text-xs text-lb-muted">
                {[row.group?.name, row.course?.name].filter(Boolean).join(' · ') || '—'}
              </span>
            </div>
            <div className="flex shrink-0 flex-col items-end gap-1">
              <Xp value={row.xp} hint={breakdownHint(row)} />
              <RankChangeBadge change={row.change} />
            </div>
          </li>
        ))}
      </ol>
    </>
  )
}
