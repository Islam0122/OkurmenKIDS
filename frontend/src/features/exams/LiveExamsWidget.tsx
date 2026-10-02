import { Link } from 'react-router-dom'

import { useExamList } from '@/hooks/useExams'
import { pluralize } from '@/utils/format'

import { LiveIndicator, StatusDot, formatSessionTime } from './examUi'

/** Dashboard block: exams of the teacher's groups running right now, live.
 * Renders nothing when no exam is running. */
export function LiveExamsWidget() {
  const { data } = useExamList({ status: 'live' })
  const live = data?.results ?? []
  if (live.length === 0) return null

  return (
    <section className="card card-body" aria-labelledby="live-exams-title">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 id="live-exams-title" className="section-title flex items-center gap-3">
          <LiveIndicator label={false} />
          <span>
            {live.length} {pluralize(live.length, 'экзамен идёт', 'экзамена идут', 'экзаменов идут')} сейчас
          </span>
        </h2>
        <Link to="/app/exams" className="text-sm font-medium text-brand-700 hover:underline">
          Все экзамены
        </Link>
      </div>
      <ul className="space-y-3">
        {live.map((session) => (
          <li key={session.id} className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-lg border border-border px-4 py-3">
            <div className="min-w-0 flex-1">
              <div className="font-medium text-ink">{session.group?.name ?? session.title}</div>
              <div className="text-xs text-ink-secondary">
                {session.title}
                {formatSessionTime(session) ? ` · ${formatSessionTime(session)}` : ''}
              </div>
            </div>
            <ul className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-ink">
              <li className="flex items-center gap-1.5">
                <StatusDot status="completed" />
                {session.counts.completed} / {session.counts.total} завершили
              </li>
              <li className="flex items-center gap-1.5">
                <StatusDot status="in_progress" />
                {session.counts.in_progress} проходят
              </li>
              <li className="flex items-center gap-1.5">
                <StatusDot status="not_started" />
                {session.counts.not_started} не начали
              </li>
            </ul>
            <Link
              to={`/app/exams/${session.id}`}
              className="inline-flex h-9 items-center justify-center rounded-lg bg-brand-500 px-4 text-sm font-medium text-white hover:bg-brand-600"
            >
              Открыть
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}
