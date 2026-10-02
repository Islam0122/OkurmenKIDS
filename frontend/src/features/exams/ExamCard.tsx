import { CalendarDays, Clock, Users } from 'lucide-react'
import { Link } from 'react-router-dom'

import type { ExamSession } from '@/types/exams'
import { cn } from '@/utils/cn'
import { pluralize } from '@/utils/format'

import { PhaseBadge, StatusDot, formatSessionDate, formatSessionTime } from './examUi'

export function ExamCard({ session }: { session: ExamSession }) {
  const { counts } = session
  const date = formatSessionDate(session)
  const time = formatSessionTime(session)
  const started = session.phase !== 'draft' && session.phase !== 'scheduled'

  return (
    <article
      className={cn(
        'card card-body flex h-full flex-col gap-3',
        session.is_live && !session.is_paused && 'border-l-4 border-l-danger',
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-base font-semibold text-ink">{session.title}</h3>
          {session.title !== session.test.title ? <p className="text-sm text-ink-secondary">{session.test.title}</p> : null}
        </div>
        <PhaseBadge session={session} />
      </div>

      <dl className="grid grid-cols-1 gap-1.5 text-sm text-ink-secondary sm:grid-cols-2">
        <div className="flex items-center gap-2">
          <Users className="size-4 text-ink-muted" aria-hidden />
          <dt className="sr-only">Группа</dt>
          <dd>{session.group?.name ?? '—'}</dd>
        </div>
        <div className="flex items-center gap-2">
          <CalendarDays className="size-4 text-ink-muted" aria-hidden />
          <dt className="sr-only">Дата</dt>
          <dd>{date ?? 'Дата не назначена'}</dd>
        </div>
        {time ? (
          <div className="flex items-center gap-2">
            <Clock className="size-4 text-ink-muted" aria-hidden />
            <dt className="sr-only">Время</dt>
            <dd>{time}</dd>
          </div>
        ) : null}
        <div className="flex items-center gap-2">
          <dt className="sr-only">Студентов</dt>
          <dd>
            {counts.total} {pluralize(counts.total, 'студент', 'студента', 'студентов')}
          </dd>
        </div>
      </dl>

      {started && counts.total > 0 ? (
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-ink" aria-label="Прогресс группы">
          <li className="flex items-center gap-1.5">
            <StatusDot status="completed" />
            {counts.completed} завершили
          </li>
          <li className="flex items-center gap-1.5">
            <StatusDot status="in_progress" />
            {counts.in_progress} проходят
          </li>
          <li className="flex items-center gap-1.5">
            <StatusDot status="not_started" />
            {counts.not_started} не начали
          </li>
        </ul>
      ) : null}

      <div className="mt-auto pt-1">
        <Link
          to={`/app/exams/${session.id}`}
          className="inline-flex h-9 items-center justify-center rounded-lg bg-brand-500 px-4 text-sm font-medium text-white hover:bg-brand-600"
        >
          Открыть
        </Link>
      </div>
    </article>
  )
}
