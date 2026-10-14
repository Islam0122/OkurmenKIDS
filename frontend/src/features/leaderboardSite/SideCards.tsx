import type { ReactNode } from 'react'
import { ArrowRight, BookOpenCheck, CalendarCheck, ClipboardCheck, Crown, Flame, HeartHandshake, Users } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'

import type { LeaderboardGroup, LeaderboardRules, LeaderboardStudent } from '@/types/leaderboard'

import { formatNumber } from './format'
import { MemberStack } from './GroupList'
import { Avatar, Panel, RankChangeBadge, RankNumber, RowsSkeleton } from './ui'
import { periodQuery } from './usePeriodParams'

function CardTitle({ icon, title, aside }: { icon: ReactNode; title: string; aside?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2 px-4 pb-2 pt-4">
      <h2 className="flex items-center gap-2 text-sm font-extrabold text-lb-deep">
        <span className="inline-flex size-7 items-center justify-center rounded-lg bg-lb-purple-50 text-lb-purple">{icon}</span>
        {title}
      </h2>
      {aside}
    </div>
  )
}

function FullLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link
      to={to}
      className="m-3 mt-1 flex h-10 items-center justify-center gap-1.5 rounded-xl bg-lb-purple-50 text-sm font-semibold text-lb-purple transition hover:bg-lb-purple hover:text-white focus-visible:outline-lb-purple"
    >
      {children}
      <ArrowRight className="size-4" aria-hidden />
    </Link>
  )
}

function usePeriodQuery() {
  return periodQuery(useLocation().search)
}

interface Loadable<T> {
  rows: T[] | undefined
  isError: boolean
}

export function TopGroupsCard({ rows, isError }: Loadable<LeaderboardGroup>) {
  const query = usePeriodQuery()
  return (
    <Panel aria-label="Топ групп">
      <CardTitle icon={<Users className="size-4" aria-hidden />} title="Топ групп" />
      {rows === undefined ? <RowsSkeleton rows={3} /> : isError ? (
        <p className="px-4 pb-4 text-sm text-lb-muted">Не удалось загрузить группы.</p>
      ) : rows.length === 0 ? (
        <p className="px-4 pb-4 text-sm text-lb-muted">За этот период у групп ещё нет баллов.</p>
      ) : (
        <ol className="space-y-0.5 px-2">
          {rows.map((group) => (
            <li key={group.key} className="flex items-center gap-2.5 rounded-xl px-2 py-2 transition-colors hover:bg-lb-bg">
              <RankNumber rank={group.rank} size="sm" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-bold text-lb-ink">{group.name}</p>
                <p className="truncate text-[11px] text-lb-muted">{group.course?.name ?? '—'}</p>
              </div>
              <MemberStack members={group.top_members} groupKey={group.key} max={3} />
              <div className="flex w-14 flex-col items-end">
                <span className="text-sm font-extrabold tabular-nums text-lb-deep">{formatNumber(group.average_xp)}</span>
                <RankChangeBadge change={group.change} className="h-5 px-1.5 text-[10px]" />
              </div>
            </li>
          ))}
        </ol>
      )}
      <FullLink to={`/leaderboard/groups${query}`}>Полный рейтинг групп</FullLink>
    </Panel>
  )
}

export function TopStudentsCard({ rows, isError }: Loadable<LeaderboardStudent>) {
  const query = usePeriodQuery()
  return (
    <Panel aria-label="Топ студентов">
      <CardTitle icon={<Crown className="size-4" aria-hidden />} title="Топ студентов" />
      {rows === undefined ? <RowsSkeleton rows={3} /> : isError ? (
        <p className="px-4 pb-4 text-sm text-lb-muted">Не удалось загрузить студентов.</p>
      ) : rows.length === 0 ? (
        <p className="px-4 pb-4 text-sm text-lb-muted">За этот период ещё нет баллов.</p>
      ) : (
        <ol className="space-y-0.5 px-2">
          {rows.map((row) => (
            <li key={row.key} className="flex items-center gap-2.5 rounded-xl px-2 py-2 transition-colors hover:bg-lb-bg">
              <RankNumber rank={row.rank} size="sm" />
              <Avatar initials={row.initials} seed={row.key} hidden={row.hidden} size="sm" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-bold text-lb-ink">{row.name}</p>
                <p className="truncate text-[11px] text-lb-muted">{row.group?.name ?? '—'}</p>
              </div>
              <span className="text-sm font-extrabold tabular-nums text-lb-deep">{formatNumber(row.xp)}</span>
            </li>
          ))}
        </ol>
      )}
      <FullLink to={`/leaderboard${query}`}>Полный рейтинг студентов</FullLink>
    </Panel>
  )
}

/** «Сила в команде» — the group methodology in one card, on a soft gold
 * background so it reads as a highlight, not as a settings panel. */
export function TeamCard({ link = true }: { link?: boolean }) {
  const query = usePeriodQuery()
  return (
    <Panel aria-label="Сила в команде" className="overflow-hidden">
      <div className="relative bg-gradient-to-br from-lb-gold-soft via-[#fff8e6] to-white px-4 py-4">
        <HeartHandshake aria-hidden className="absolute -right-3 -top-3 size-24 text-lb-gold/20" />
        <h2 className="relative flex items-center gap-2 text-sm font-extrabold text-lb-deep">
          <span className="inline-flex size-7 items-center justify-center rounded-lg bg-white/80 text-lb-gold-dark">
            <HeartHandshake className="size-4" aria-hidden />
          </span>
          Сила в команде
        </h2>
        <p className="relative mt-2 text-sm leading-relaxed text-lb-ink/80">
          Каждый XP идёт и в личный рейтинг, и в зачёт группы. Группы сравниваются по <b className="text-lb-deep">среднему XP на студента</b>, поэтому
          важен вклад каждого, а не размер группы.
        </p>
        {link ? (
          <Link
            to={`/leaderboard/groups${query}`}
            className="relative mt-3 inline-flex items-center gap-1 rounded text-sm font-bold text-lb-purple hover:underline focus-visible:outline-lb-purple"
          >
            Смотреть топ групп <ArrowRight className="size-4" aria-hidden />
          </Link>
        ) : null}
      </div>
    </Panel>
  )
}

/** Highlights of the period — every value comes from the loaded ranking. */
export function HighlightsCard({ leader, climber, group }: {
  leader: { name: string; detail: string; value: string } | null
  climber: { name: string; detail: string; value: number } | null
  group: { name: string; value: string } | null
}) {
  const items = [
    leader && { icon: <Crown className="size-4" aria-hidden />, tone: 'bg-lb-gold-soft text-lb-gold-dark', label: 'Лидер периода', title: leader.name, detail: leader.detail, value: leader.value },
    climber && { icon: <Flame className="size-4" aria-hidden />, tone: 'bg-[#e3f7ee] text-lb-success', label: 'Рывок периода', title: climber.name, detail: climber.detail, value: `+${climber.value} мест` },
    group && { icon: <Users className="size-4" aria-hidden />, tone: 'bg-lb-purple-50 text-lb-purple', label: 'Лучшая группа', title: group.name, detail: 'средний XP на студента', value: group.value },
  ].filter(Boolean) as { icon: ReactNode; tone: string; label: string; title: string; detail: string; value: string }[]
  if (!items.length) return null
  return (
    <Panel aria-label="Герои периода">
      <CardTitle icon={<Flame className="size-4" aria-hidden />} title="Герои периода" />
      <ul className="space-y-1 px-2 pb-3">
        {items.map((item) => (
          <li key={item.label} className="flex items-center gap-3 rounded-xl px-2 py-2">
            <span className={`inline-flex size-9 shrink-0 items-center justify-center rounded-xl ${item.tone}`}>{item.icon}</span>
            <span className="min-w-0 flex-1">
              <span className="block text-[11px] font-semibold uppercase tracking-wide text-lb-muted">{item.label}</span>
              <span className="block truncate text-sm font-bold text-lb-ink">{item.title}</span>
              <span className="block truncate text-[11px] text-lb-muted">{item.detail}</span>
            </span>
            <span className="shrink-0 text-sm font-extrabold tabular-nums text-lb-deep">{item.value}</span>
          </li>
        ))}
      </ul>
    </Panel>
  )
}

/** How XP is earned — the server's own numbers, not a copy of its logic. */
export function RulesCard({ rules }: { rules: LeaderboardRules | undefined }) {
  if (!rules) return null
  const items = [
    { icon: CalendarCheck, title: 'Занятие', text: `${rules.attendance_present} XP · опоздание ${rules.attendance_late}` },
    { icon: BookOpenCheck, title: 'Домашнее задание', text: `${rules.homework_done} XP + оценка до ${rules.homework_grade_max} · с опозданием ${rules.homework_late}` },
    { icon: ClipboardCheck, title: 'Тест', text: `до ${rules.test_max} XP по лучшей попытке` },
  ]
  return (
    <Panel aria-label="Как начисляются XP">
      <CardTitle icon={<ClipboardCheck className="size-4" aria-hidden />} title="Как начисляются XP" />
      <ul className="space-y-2 px-4 pb-4">
        {items.map(({ icon: Icon, title, text }) => (
          <li key={title} className="flex items-center gap-3 text-sm">
            <Icon className="size-4 shrink-0 text-lb-gold-dark" aria-hidden />
            <span className="min-w-0">
              <span className="font-semibold text-lb-ink">{title}</span>
              <span className="text-lb-muted"> — {text}</span>
            </span>
          </li>
        ))}
        <li className="pt-1 text-[11px] leading-relaxed text-lb-muted">
          Только реальные записи журнала за период; исправленная оценка сразу пересчитывает рейтинг. Неделя — пн–вс, время {rules.timezone}.
        </li>
      </ul>
    </Panel>
  )
}
