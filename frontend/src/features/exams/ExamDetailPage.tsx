import { useState } from 'react'
import { CheckCircle2, CircleDashed, Clock, PlayCircle, Users } from 'lucide-react'
import { useParams } from 'react-router-dom'

import { BackLink } from '@/components/ui/BackLink'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Drawer } from '@/components/ui/Drawer'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { StatCard } from '@/components/ui/StatCard'
import { useExamParticipantResult, useExamParticipants } from '@/hooks/useExams'
import type { ExamParticipant, ExamSession } from '@/types/exams'

import {
  ParticipantStatusBadge,
  PhaseBadge,
  formatClock,
  formatDuration,
  formatSessionDate,
  formatSessionTime,
} from './examUi'

function Progress({ participant }: { participant: ExamParticipant }) {
  if (!participant.question_total) return <span className="text-ink-muted">0 / —</span>
  const midExam = participant.status === 'in_progress' || participant.status === 'disconnected' || participant.status === 'paused'
  return (
    <div className="min-w-32">
      <div className="flex items-baseline justify-between gap-2 text-sm text-ink">
        <span>
          {participant.answered_count} / {participant.question_total}
        </span>
        <span className="text-xs text-ink-muted">{participant.progress_percent}%</span>
      </div>
      <div
        className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-hover"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={participant.question_total}
        aria-valuenow={participant.answered_count}
        aria-label={`Отвечено ${participant.answered_count} из ${participant.question_total}`}
      >
        <div className="h-full rounded-full bg-brand-500" style={{ width: `${participant.progress_percent}%` }} />
      </div>
      {midExam ? <div className="mt-0.5 text-xs text-ink-muted">Вопрос {participant.current_question}</div> : null}
    </div>
  )
}

function Result({ participant, onOpen }: { participant: ExamParticipant; onOpen: () => void }) {
  if (participant.score === null) return <span className="text-ink-muted">—</span>
  return (
    <button type="button" onClick={onOpen} className="font-semibold text-brand-700 underline-offset-2 hover:underline">
      {Math.round(participant.score)}%
    </button>
  )
}

function ResultDrawer({ sessionId, participant, onClose }: { sessionId: string; participant: ExamParticipant | null; onClose: () => void }) {
  const { data, isPending, isError } = useExamParticipantResult(sessionId, participant?.id ?? null)
  const statusLabel = { correct: 'Верно', wrong: 'Неверно', pending: 'На проверке', skipped: 'Нет ответа' } as const
  const statusTone = { correct: 'success', wrong: 'danger', pending: 'warning', skipped: 'muted' } as const
  return (
    <Drawer isOpen={participant !== null} onClose={onClose} title={participant ? `Результат: ${participant.student.name}` : ''} side="right" size="lg">
      {isPending ? <LoadingState label="Загружаем результат…" /> : null}
      {isError ? <ErrorState title="Результат недоступен" /> : null}
      {data ? (
        <div className="space-y-4">
          <p className="text-sm text-ink-secondary">
            Балл: <strong className="text-ink">{data.score !== null ? `${Math.round(data.score)}%` : '—'}</strong> · проходной {data.passing_score}% ·
            время {formatDuration(data.duration_seconds)}
          </p>
          <ol className="space-y-3">
            {data.questions.map((q) => (
              <li key={q.number} className="rounded-lg border border-border p-3">
                <div className="flex items-start justify-between gap-3">
                  <p className="text-sm font-medium text-ink">
                    {q.number}. {q.text}
                  </p>
                  <Badge tone={statusTone[q.status]}>{statusLabel[q.status]}</Badge>
                </div>
                {q.image_url ? (
                  <img src={q.image_url} alt="" referrerPolicy="no-referrer" loading="lazy" className="mt-2 max-h-40 rounded-md" />
                ) : null}
                {q.selected.length ? (
                  <p className="mt-2 text-sm text-ink-secondary">Ответ: {q.selected.join(', ')}</p>
                ) : q.answer_text ? (
                  <pre className="mt-2 whitespace-pre-wrap rounded bg-surface-hover p-2 text-xs text-ink">{q.answer_text}</pre>
                ) : (
                  <p className="mt-2 text-sm text-ink-muted">Нет ответа</p>
                )}
                {q.status !== 'correct' && q.correct.length ? (
                  <p className="mt-1 text-sm text-brand-700">Правильно: {q.correct.join(', ')}</p>
                ) : null}
              </li>
            ))}
          </ol>
        </div>
      ) : null}
    </Drawer>
  )
}

function SessionHeader({ session }: { session: ExamSession }) {
  const date = formatSessionDate(session)
  const time = formatSessionTime(session)
  return (
    <div className="mb-6">
      <BackLink to="/app/exams">Экзамены</BackLink>
      <div className="mt-3 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold text-ink">{session.title}</h1>
          <p className="mt-1 text-sm text-ink-secondary">
            Группа: {session.group?.name ?? '—'}
            {date ? ` · ${date}` : ''}
            {time ? ` · ${time}` : ''}
            {session.time_limit_minutes ? ` · ${session.time_limit_minutes} мин на прохождение` : ''}
          </p>
        </div>
        <PhaseBadge session={session} />
      </div>
    </div>
  )
}

export function ExamDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { data, isPending, isError, refetch, dataUpdatedAt } = useExamParticipants(id)
  const [openResult, setOpenResult] = useState<ExamParticipant | null>(null)

  if (isPending) return <LoadingState label="Загружаем экзамен…" />
  if (isError || !data) return <ErrorState title="Экзамен не найден" onRetry={() => void refetch()} />

  const { session, participants } = data
  const { counts } = session

  return (
    <div>
      <SessionHeader session={session} />

      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
        <StatCard label="Всего студентов" value={counts.total} icon={Users} />
        <StatCard label="Начали" value={counts.started} icon={PlayCircle} />
        <StatCard
          label="Проходят сейчас"
          value={counts.in_progress}
          icon={Clock}
          hint={counts.disconnected ? `нет соединения: ${counts.disconnected}` : undefined}
          tone={counts.disconnected ? 'warning' : 'default'}
        />
        <StatCard
          label="Завершили"
          value={counts.completed}
          icon={CheckCircle2}
          hint={counts.average_score !== null ? `средний балл ${Math.round(counts.average_score)}%` : undefined}
        />
        <StatCard label="Не начали" value={counts.not_started} icon={CircleDashed} />
      </div>

      <section className="card">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-3">
          <h2 className="section-title">Студенты</h2>
          {session.is_live ? (
            <span className="text-xs text-ink-muted" aria-live="polite">
              Обновляется автоматически · {new Date(dataUpdatedAt).toLocaleTimeString('ru-RU')}
            </span>
          ) : null}
        </div>

        {participants.length === 0 ? (
          <EmptyState icon={Users} title="Нет участников" description="В этой сессии нет списка студентов." className="m-4" />
        ) : (
          <>
            {/* Desktop table */}
            <div className="hidden overflow-x-auto md:block">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs uppercase tracking-wide text-ink-muted">
                    <th className="px-4 py-2 font-medium">Студент</th>
                    <th className="px-4 py-2 font-medium">Статус</th>
                    <th className="px-4 py-2 font-medium">Прогресс</th>
                    <th className="px-4 py-2 font-medium">Время</th>
                    <th className="px-4 py-2 font-medium">Результат</th>
                    <th className="px-4 py-2 font-medium">Последняя активность</th>
                  </tr>
                </thead>
                <tbody>
                  {participants.map((p) => (
                    <tr key={p.id} className="border-t border-border">
                      <td className="px-4 py-3 font-medium text-ink">{p.student.name}</td>
                      <td className="px-4 py-3">
                        <ParticipantStatusBadge status={p.status} />
                      </td>
                      <td className="px-4 py-3">
                        <Progress participant={p} />
                      </td>
                      <td className="px-4 py-3 font-mono text-ink">{formatDuration(p.duration_seconds)}</td>
                      <td className="px-4 py-3">
                        <Result participant={p} onOpen={() => setOpenResult(p)} />
                      </td>
                      <td className="px-4 py-3 text-ink-secondary">{formatClock(p.last_seen_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Phone cards */}
            <ul className="divide-y divide-border md:hidden">
              {participants.map((p) => (
                <li key={p.id} className="space-y-2 px-4 py-3">
                  <div className="flex items-start justify-between gap-2">
                    <span className="font-medium text-ink">{p.student.name}</span>
                    <ParticipantStatusBadge status={p.status} />
                  </div>
                  <Progress participant={p} />
                  <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-secondary">
                    <span>Время: {formatDuration(p.duration_seconds)}</span>
                    <span>Активность: {formatClock(p.last_seen_at)}</span>
                    {p.score !== null ? (
                      <Button variant="ghost" size="sm" onClick={() => setOpenResult(p)}>
                        Результат {Math.round(p.score)}%
                      </Button>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      {id ? <ResultDrawer sessionId={id} participant={openResult} onClose={() => setOpenResult(null)} /> : null}
    </div>
  )
}
