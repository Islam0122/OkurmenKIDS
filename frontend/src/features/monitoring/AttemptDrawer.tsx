import { useState } from 'react'
import { AlertTriangle, CheckCircle2, Info, XCircle } from 'lucide-react'

import { Drawer } from '@/components/ui/Drawer'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { formatDuration } from '@/features/exams/examUi'
import { useMonitoringAttempt } from '@/hooks/useMonitoring'
import type { MonitoringAttemptDetail, MonitoringEvent } from '@/types/monitoring'

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

          <dl className="grid grid-cols-1 gap-x-4 gap-y-1.5 text-sm sm:grid-cols-2">
            <div className="flex min-w-0 justify-between gap-2"><dt className="text-ink-muted">Тест</dt><dd className="truncate text-right text-ink" title={data.test.title}>{data.test.title}</dd></div>
            <div className="flex min-w-0 justify-between gap-2"><dt className="text-ink-muted">Предмет</dt><dd className="truncate text-right text-ink">{data.test.subject || '—'}</dd></div>
            <div className="flex min-w-0 justify-between gap-2"><dt className="text-ink-muted">Группа</dt><dd className="truncate text-right text-ink">{data.group?.name ?? '—'}</dd></div>
            <div className="flex min-w-0 justify-between gap-2"><dt className="text-ink-muted">Тренер</dt><dd className="truncate text-right text-ink">{data.teacher?.name ?? '—'}</dd></div>
            <div className="flex min-w-0 justify-between gap-2"><dt className="text-ink-muted">Завершён</dt><dd className="text-right text-ink">{formatTime(data.finished_at)}</dd></div>
            {data.attempt_no ? <div className="flex min-w-0 justify-between gap-2"><dt className="text-ink-muted">Попытка №</dt><dd className="text-right text-ink">{data.attempt_no}</dd></div> : null}
            {data.correct_count !== undefined ? (
              <div className="flex min-w-0 justify-between gap-2"><dt className="text-ink-muted">Правильно / неправильно</dt>
                <dd className="text-right"><span className="text-success">{data.correct_count}</span> / <span className="text-danger">{data.incorrect_count}</span> из {data.question_total}</dd></div>
            ) : null}
            <div className="flex min-w-0 justify-between gap-2"><dt className="text-ink-muted">Проходной балл</dt><dd className="text-right text-ink">{data.passing_score}%</dd></div>
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

          {data.questions.some((q) => q.selected !== undefined) ? <AnswersReview questions={data.questions} /> : null}

          {data.questions.length && !data.questions.some((q) => q.selected !== undefined) ? (
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

type ReviewQuestion = MonitoringAttemptDetail['questions'][number]
const QUESTION_STATUS: Record<string, { label: string; className: string }> = {
  correct: { label: 'Верно', className: 'text-success' },
  wrong: { label: 'Ошибка', className: 'text-danger' },
  skipped: { label: 'Без ответа', className: 'text-ink-muted' },
  pending: { label: 'На проверке', className: 'text-warning' },
}

/** Every question of a finished attempt: the student's answer, the correct
 * one and the status; «Только ошибки» narrows to the mistakes. */
function AnswersReview({ questions }: { questions: ReviewQuestion[] }) {
  const [mistakesOnly, setMistakesOnly] = useState(false)
  const mistakes = questions.filter((q) => q.status === 'wrong').length
  const shown = mistakesOnly ? questions.filter((q) => q.status === 'wrong') : questions
  return (
    <section>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 className="section-title">Ответы</h3>
        <label className="flex items-center gap-2 text-sm text-ink-secondary">
          <input type="checkbox" checked={mistakesOnly} onChange={(e) => setMistakesOnly(e.target.checked)} />
          Только ошибки ({mistakes})
        </label>
      </div>
      <ol className="space-y-3">
        {shown.map((q) => {
          const status = QUESTION_STATUS[q.status] ?? QUESTION_STATUS.skipped
          const given = q.selected?.length ? q.selected.join(', ') : q.answer_text || '—'
          return (
            <li key={q.question_id} className="min-w-0 rounded-lg border border-border p-3 text-sm">
              <div className="flex items-start justify-between gap-3">
                <p className="min-w-0 whitespace-pre-line font-medium text-ink [overflow-wrap:anywhere]">{q.number}. {q.full_text ?? q.text}</p>
                <span className={`shrink-0 text-xs font-semibold ${status.className}`}>{status.label}</span>
              </div>
              <dl className="mt-2 space-y-1">
                <div className="flex min-w-0 gap-2"><dt className="shrink-0 text-ink-muted">Ответ ученика:</dt><dd className={`min-w-0 [overflow-wrap:anywhere] ${q.status === 'wrong' ? 'text-danger' : 'text-ink'}`}>{given}</dd></div>
                {q.correct?.length ? <div className="flex min-w-0 gap-2"><dt className="shrink-0 text-ink-muted">Правильный:</dt><dd className="min-w-0 text-success [overflow-wrap:anywhere]">{q.correct.join(', ')}</dd></div> : null}
                {q.answered_at ? <div className="flex gap-2"><dt className="text-ink-muted">Время ответа:</dt><dd className="text-ink-secondary">{formatSeconds(q.answered_at)}</dd></div> : null}
              </dl>
            </li>
          )
        })}
      </ol>
    </section>
  )
}
