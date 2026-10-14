import { ArrowRight, BookOpenCheck, CalendarCheck, ClipboardCheck, Scale, Sparkles } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'

import type { PeriodParams } from '@/api/publicLeaderboard'
import { useGroupBoard, useStudentBoard } from '@/hooks/usePublicLeaderboard'
import type { LeaderboardRules } from '@/types/leaderboard'

import { formatNumber } from './format'
import { MemberStack } from './GroupList'
import { Avatar, Panel, RankChangeBadge, RankNumber, RowsSkeleton } from './ui'
import { periodQuery } from './usePeriodParams'

function CardHeader({ title, link }: { title: string; link?: { to: string; label: string } }) {
  return (
    <div className="flex items-center justify-between gap-2 border-b border-lb-line px-4 py-3">
      <h2 className="text-sm font-bold text-lb-deep">{title}</h2>
      {link ? (
        <Link to={link.to} className="inline-flex items-center gap-1 rounded text-xs font-semibold text-lb-purple hover:underline focus-visible:outline-lb-purple">
          {link.label}
          <ArrowRight className="size-3.5" aria-hidden />
        </Link>
      ) : null}
    </div>
  )
}

function usePeriodQuery() {
  return periodQuery(useLocation().search)
}

export function TopGroupsCard({ period }: { period: PeriodParams }) {
  const query = useGroupBoard({ ...period, page_size: 5 })
  const groups = query.data?.pages[0]?.results ?? []
  return (
    <Panel aria-label="Топ групп">
      <CardHeader title="Топ групп" link={{ to: `/leaderboard/groups${usePeriodQuery()}`, label: 'Все группы' }} />
      {query.isPending ? <RowsSkeleton rows={4} /> : query.isError ? (
        <p className="px-4 py-4 text-sm text-ink-secondary">Не удалось загрузить группы.</p>
      ) : groups.length === 0 ? (
        <p className="px-4 py-4 text-sm text-ink-secondary">За этот период у групп ещё нет баллов.</p>
      ) : (
        <ol className="divide-y divide-lb-line">
          {groups.map((group) => (
            <li key={group.key} className="flex items-center gap-3 px-4 py-2.5">
              <RankNumber rank={group.rank} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold text-ink">{group.name}</p>
                <p className="truncate text-xs text-ink-secondary">{group.course?.name ?? '—'}</p>
              </div>
              <MemberStack members={group.top_members} groupKey={group.key} max={3} />
              <div className="flex flex-col items-end">
                <span className="text-sm font-bold tabular-nums text-lb-deep">{formatNumber(group.average_xp)}</span>
                <RankChangeBadge change={group.change} />
              </div>
            </li>
          ))}
        </ol>
      )}
    </Panel>
  )
}

export function TopStudentsCard({ period }: { period: PeriodParams }) {
  const query = useStudentBoard({ ...period, page_size: 5 })
  const rows = query.data?.pages[0]?.results ?? []
  return (
    <Panel aria-label="Топ студентов">
      <CardHeader title="Топ студентов" link={{ to: `/leaderboard${usePeriodQuery()}`, label: 'Весь рейтинг' }} />
      {query.isPending ? <RowsSkeleton rows={4} /> : query.isError ? (
        <p className="px-4 py-4 text-sm text-ink-secondary">Не удалось загрузить студентов.</p>
      ) : rows.length === 0 ? (
        <p className="px-4 py-4 text-sm text-ink-secondary">За этот период ещё нет баллов.</p>
      ) : (
        <ol className="divide-y divide-lb-line">
          {rows.map((row) => (
            <li key={row.key} className="flex items-center gap-3 px-4 py-2.5">
              <RankNumber rank={row.rank} />
              <Avatar initials={row.initials} seed={row.key} hidden={row.hidden} size="sm" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold text-ink">{row.name}</p>
                <p className="truncate text-xs text-ink-secondary">{row.group?.name ?? '—'}</p>
              </div>
              <span className="text-sm font-bold tabular-nums text-lb-deep">{formatNumber(row.xp)}</span>
            </li>
          ))}
        </ol>
      )}
    </Panel>
  )
}

/** How XP is earned — the server's own numbers, not a copy of its logic. */
export function RulesCard({ rules }: { rules: LeaderboardRules | undefined }) {
  const items = rules
    ? [
        { icon: CalendarCheck, title: 'Посещаемость', text: `${rules.attendance_present} XP за занятие, ${rules.attendance_late} XP при опоздании` },
        { icon: BookOpenCheck, title: 'Домашние задания', text: `${rules.homework_done} XP за сданное ДЗ (${rules.homework_late} XP с опозданием) + оценка тренера до ${rules.homework_grade_max}` },
        { icon: ClipboardCheck, title: 'Тесты', text: `до ${rules.test_max} XP за тест — по лучшей попытке, пересдача не начисляет повторно` },
      ]
    : []
  return (
    <Panel aria-label="Как начисляются XP">
      <CardHeader title="Как начисляются XP" />
      <ul className="space-y-3 px-4 py-4">
        {items.map(({ icon: Icon, title, text }) => (
          <li key={title} className="flex gap-3">
            <span className="mt-0.5 inline-flex size-8 shrink-0 items-center justify-center rounded-lg bg-lb-purple-50 text-lb-purple">
              <Icon className="size-4" aria-hidden />
            </span>
            <span className="text-sm">
              <span className="block font-semibold text-ink">{title}</span>
              <span className="text-ink-secondary">{text}</span>
            </span>
          </li>
        ))}
        <li className="flex gap-3 rounded-xl bg-lb-gold-soft/70 p-3 text-xs text-[#6b4a00]">
          <Sparkles className="size-4 shrink-0" aria-hidden />
          <span>
            Учитываются только реальные записи журнала за выбранный период. Исправленная отметка или оценка сразу
            пересчитывает рейтинг. Неделя — с понедельника по воскресенье, время — {rules?.timezone ?? 'Asia/Bishkek'}.
          </span>
        </li>
      </ul>
    </Panel>
  )
}

export function GroupMethodCard() {
  return (
    <Panel aria-label="Как считается рейтинг групп">
      <CardHeader title="Как считается рейтинг групп" />
      <div className="flex gap-3 px-4 py-4 text-sm text-ink-secondary">
        <span className="mt-0.5 inline-flex size-8 shrink-0 items-center justify-center rounded-lg bg-lb-purple-50 text-lb-purple">
          <Scale className="size-4" aria-hidden />
        </span>
        <p>
          Группы сравниваются по <b className="text-ink">среднему XP на студента</b>: сумма XP всех текущих студентов
          группы за период, делённая на их число (включая тех, кто пока без баллов). Так большая группа не побеждает
          только за счёт размера. Сумма XP показана рядом для справки.
        </p>
      </div>
    </Panel>
  )
}
