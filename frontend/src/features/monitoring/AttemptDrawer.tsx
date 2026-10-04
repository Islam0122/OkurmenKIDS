import { AlertTriangle, CheckCircle2, Info, XCircle } from 'lucide-react'

import { Drawer } from '@/components/ui/Drawer'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { formatDuration } from '@/features/exams/examUi'
import { useMonitoringAttempt } from '@/hooks/useMonitoring'
import type { MonitoringEvent } from '@/types/monitoring'

import { SeverityBadge, StatusBadge, VIOLATION_LABEL, formatSeconds, formatTime, percent } from './monitoringUi'

const EVENT_ICON = { danger: XCircle, warning: AlertTriangle, info: Info } as const
const EVENT_COLOR = { danger: 'text-danger', warning: 'text-warning', info: 'text-ink-muted' } as const

function Timeline({ events }: { events: MonitoringEvent[] }) {
  if (!events.length) return <p className="text-sm text-ink-muted">Событий пока нет.</p>
  return (
    <ol className="space-y-2" aria-label="Журнал событий">
      {events.map((event) => {
        const Icon = EVENT_ICON[event.severity]
        return (
          <li key={event.id} className="flex items-start gap-3 text-sm">
            <span className="w-16 shrink-0 font-mono text-xs text-ink-muted">{formatSeconds(event.timestamp)}</span>
            <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${EVENT_COLOR[event.severity]}`} aria-hidden="true" />
            <span className="min-w-0 text-ink">
              {event.label}
              {event.question ? <span className="text-ink-muted"> · вопрос {event.question}</span> : null}
              {event.detail ? <span className="text-ink-muted"> · {event.detail}</span> : null}
            </span>
          </li>
        )
      })}
    </ol>
  )
}

export function AttemptDrawer({ attemptId, onClose }: { attemptId: string | null; onClose: () => void }) {
  const { data, isLoading, isError, refetch } = useMonitoringAttempt(attemptId)
  return (
    <Drawer isOpen={attemptId !== null} onClose={onClose} title={data?.student_name ?? 'Попытка'} side="right" size="lg">
      {isLoading ? <LoadingState /> : isError || !data ? <ErrorState onRetry={() => refetch()} /> : (
        <div className="space-y-6">
          <div>
            <p className="text-sm text-ink-secondary">{data.session.title}{data.group ? ` · ${data.group.name}` : ''}</p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <StatusBadge status={data.status} />
              <SeverityBadge severity={data.severity} />
              <span className="text-xs text-ink-muted">{data.mode === 'exam' ? 'Экзамен' : 'Тренажёр'}</span>
            </div>
          </div>

          <dl className="grid grid-cols-2 gap-3 text-sm">
            <div className="rounded-lg bg-surface-hover p-3"><dt className="text-ink-muted">Прогресс</dt><dd className="mt-1 text-lg font-semibold text-ink">{data.answered} / {data.question_total}</dd></div>
            <div className="rounded-lg bg-surface-hover p-3"><dt className="text-ink-muted">Балл</dt><dd className="mt-1 text-lg font-semibold text-ink">{percent(data.score)}{data.passed === true ? ' · сдал' : data.passed === false ? ' · не сдал' : ''}</dd></div>
            <div className="rounded-lg bg-surface-hover p-3"><dt className="text-ink-muted">Начало</dt><dd className="mt-1 font-medium text-ink">{formatTime(data.started_at)}</dd></div>
            <div className="rounded-lg bg-surface-hover p-3"><dt className="text-ink-muted">{data.status === 'in_progress' ? 'Осталось' : 'Время'}</dt><dd className="mt-1 font-mono font-medium text-ink">{formatDuration(data.status === 'in_progress' ? data.remaining_seconds : data.duration_seconds)}</dd></div>
          </dl>

          <section>
            <h3 className="section-title mb-3">Нарушения</h3>
            <dl className="grid grid-cols-2 gap-2 text-sm">
              {Object.entries(data.violations).map(([type, count]) => (
                <div key={type} className="flex items-center justify-between gap-2 rounded-lg border border-border px-3 py-2">
                  <dt className="text-ink-secondary">{VIOLATION_LABEL[type] ?? type}</dt>
                  <dd className={count ? 'font-semibold text-danger' : 'text-ink-muted'}>{count}</dd>
                </div>
              ))}
            </dl>
          </section>

          <section>
            <h3 className="section-title mb-3">Журнал событий</h3>
            <Timeline events={data.events} />
          </section>

          {data.questions.length ? (
            <section>
              <h3 className="section-title mb-3">Вопросы</h3>
              <ul className="flex flex-wrap gap-1.5" aria-label="Вопросы">
                {data.questions.map((q) => {
                  const ok = q.status === 'correct'
                  const bad = q.status === 'wrong'
                  return (
                    <li key={q.question_id} title={q.text ?? ''} className={`flex h-8 w-8 items-center justify-center rounded-md border text-xs font-semibold ${ok ? 'border-brand-200 bg-brand-50 text-brand-700' : bad ? 'border-danger/30 bg-danger-soft text-danger' : q.status === 'answered' ? 'border-info/30 bg-info-soft text-info' : 'border-border text-ink-muted'}`}>
                      {ok ? <CheckCircle2 className="h-3.5 w-3.5" aria-label={`${q.number}: верно`} /> : q.number}
                    </li>
                  )
                })}
              </ul>
            </section>
          ) : null}
        </div>
      )}
    </Drawer>
  )
}
