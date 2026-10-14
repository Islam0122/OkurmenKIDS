import { useState } from 'react'
import { ChevronDown, Users } from 'lucide-react'

import type { PeriodParams } from '@/api/publicLeaderboard'
import { useStudentBoard } from '@/hooks/usePublicLeaderboard'
import type { LeaderboardGroup, LeaderboardGroupMember } from '@/types/leaderboard'
import { cn } from '@/utils/cn'

import { formatNumber, plural } from './format'
import { Avatar, ErrorState, RankChangeBadge, RankNumber, RowsSkeleton } from './ui'

export function MemberStack({ members, groupKey, size = 'sm', max = 4 }: {
  members: LeaderboardGroupMember[]
  groupKey: string
  size?: 'sm' | 'md'
  max?: number
}) {
  if (!members.length) return null
  return (
    <span className="flex -space-x-2" aria-label={`Лидеры группы: ${members.map((m) => m.name).join(', ')}`}>
      {members.slice(0, max).map((member) => (
        <Avatar
          key={member.name}
          initials={size === 'sm' ? member.initials.slice(0, 1) : member.initials}
          seed={`${groupKey}:${member.name}`}
          size={size}
          className="ring-2 ring-white"
        />
      ))}
    </span>
  )
}

/** The group's own ranking for the same period — the students endpoint
 * filtered by the group's public key (places stay academy-wide). */
function GroupMembers({ group, period }: { group: LeaderboardGroup; period: PeriodParams }) {
  const query = useStudentBoard({ ...period, group: group.key, page_size: 50 })
  if (query.isPending) return <RowsSkeleton rows={3} />
  if (query.isError) return <ErrorState onRetry={() => void query.refetch()} />
  const rows = query.data.pages.flatMap((page) => page.results)
  if (!rows.length) return <p className="px-5 py-4 text-sm text-lb-muted">В этом периоде у группы нет участников с XP.</p>
  return (
    <ol className="grid gap-x-6 px-3 py-2 sm:grid-cols-2 sm:px-5" aria-label={`Студенты группы ${group.name}`}>
      {rows.map((row) => (
        <li key={row.key} className="flex items-center gap-3 rounded-lg px-2 py-1.5 hover:bg-white">
          <span className="w-10 shrink-0 text-xs font-semibold tabular-nums text-lb-muted">#{row.rank}</span>
          <Avatar initials={row.initials} seed={row.key} hidden={row.hidden} size="sm" />
          <span className={cn('min-w-0 flex-1 truncate text-sm', row.hidden ? 'italic text-lb-muted' : 'font-medium text-lb-ink')}>{row.name}</span>
          <span className="text-sm font-bold tabular-nums text-lb-deep">{formatNumber(row.xp)} <span className="text-[11px] text-lb-gold-dark">XP</span></span>
        </li>
      ))}
    </ol>
  )
}

function GroupRow({ group, period }: { group: LeaderboardGroup; period: PeriodParams }) {
  const [open, setOpen] = useState(false)
  const panelId = `group-${group.key}`
  return (
    <li className={cn('transition-colors', open && 'bg-lb-bg/60')}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors duration-150 hover:bg-lb-purple-50/60 focus-visible:outline-lb-purple sm:gap-4 sm:px-5"
      >
        <RankNumber rank={group.rank} />
        <span className="min-w-0 flex-1">
          <span className="block truncate font-bold text-lb-ink">{group.name}</span>
          <span className="flex items-center gap-1.5 text-xs text-lb-muted">
            <span className="min-w-0 truncate">{group.course?.name ?? '—'}</span>
            <span aria-hidden>·</span>
            <Users className="size-3 shrink-0" aria-hidden />
            <span className="whitespace-nowrap">
              {group.active_students} из {group.members} {plural(group.members, ['студента', 'студентов', 'студентов'])}
            </span>
          </span>
        </span>
        <span className="hidden lg:block"><MemberStack members={group.top_members} groupKey={group.key} /></span>
        <span className="flex shrink-0 flex-col items-end">
          <span className="inline-flex items-baseline gap-1 whitespace-nowrap" title="Средний XP на студента">
            <span className="text-base font-extrabold tabular-nums text-lb-deep">{formatNumber(group.average_xp)}</span>
            <span className="text-[11px] font-bold text-lb-gold-dark">XP/чел.</span>
          </span>
          <span className="text-[11px] tabular-nums text-lb-muted" title="Сумма XP группы">Σ {formatNumber(group.total_xp)} XP</span>
        </span>
        <span className="hidden w-16 justify-end sm:flex"><RankChangeBadge change={group.change} /></span>
        <ChevronDown className={cn('size-4 shrink-0 text-lb-muted transition-transform duration-200', open && 'rotate-180 text-lb-purple')} aria-hidden />
      </button>
      {open ? (
        <div id={panelId} className="lb-rise border-t border-lb-line">
          <GroupMembers group={group} period={period} />
        </div>
      ) : null}
    </li>
  )
}

export function GroupList({ rows, period, caption }: { rows: LeaderboardGroup[]; period: PeriodParams; caption: string }) {
  return (
    <ol className="divide-y divide-lb-line" aria-label={caption}>
      {rows.map((group) => <GroupRow key={group.key} group={group} period={period} />)}
    </ol>
  )
}
