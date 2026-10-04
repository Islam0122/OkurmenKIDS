import { useState } from 'react'
import { PenLine } from 'lucide-react'

import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { useToast } from '@/components/ui/Toast'
import { useMyAttempts, useTakeExamSession } from '@/hooks/useExams'
import { extractErrorMessage } from '@/lib/apiError'
import type { MyAttempt } from '@/types/exams'

/** Leaves the LMS for the test pages — the very same ones students use
 * (questions, Назад / Далее, timer, autosave, result). The link is a
 * short-lived signed handoff to the user's *own* attempt (backend:
 * services.handoff). Kept in one place so tests can stub it. */
export const testPage = {
  open(url: string) {
    window.location.assign(url)
  },
}

/** «Пройти тест»: start (or continue) the user's own attempt. */
export function TakeTestButton({ sessionId }: { sessionId: string }) {
  const { showToast } = useToast()
  const mutation = useTakeExamSession()

  async function handleTake() {
    try {
      const attempt = await mutation.mutateAsync(sessionId)
      const url = attempt.take_url ?? attempt.result_url
      if (url) testPage.open(url)
    } catch (error) {
      showToast(extractErrorMessage(error, 'Не удалось открыть тест'), 'error')
    }
  }

  return (
    <Button leftIcon={<PenLine className="size-4" aria-hidden />} onClick={() => void handleTake()} isLoading={mutation.isPending}>
      Пройти как студент
    </Button>
  )
}

const STATUS_TONE = { active: 'warning', finished: 'success', expired: 'muted' } as const

function formatDate(value: string) {
  return new Date(value).toLocaleDateString('ru-RU')
}

/** «Мои результаты»: only the user's own attempts — never a student's. */
export function MyResults({ sessionId, title = 'Мои результаты' }: { sessionId?: string; title?: string }) {
  const { data, isPending, isError, refetch } = useMyAttempts(sessionId)
  const [opening, setOpening] = useState<string | null>(null)

  if (isPending) return <LoadingState label="Загружаем ваши результаты…" />
  if (isError) return <ErrorState onRetry={() => void refetch()} />
  if (!data || data.length === 0) return null

  return (
    <section className="card card-body" aria-label={title}>
      <h2 className="section-title mb-3">{title}</h2>
      <ul className="divide-y divide-border">
        {data.map((attempt) => (
          <MyAttemptRow
            key={attempt.id}
            attempt={attempt}
            isOpening={opening === attempt.id}
            onOpen={() => {
              // Links are short-lived (5 min): fetch a fresh one on click.
              setOpening(attempt.id)
              void refetch().then((fresh) => {
                const current = fresh.data?.find((item) => item.id === attempt.id)
                const url = current?.result_url ?? current?.take_url
                if (url) testPage.open(url)
                else setOpening(null)
              })
            }}
          />
        ))}
      </ul>
    </section>
  )
}

function MyAttemptRow({ attempt, isOpening, onOpen }: { attempt: MyAttempt; isOpening: boolean; onOpen: () => void }) {
  const { score } = attempt
  const url = attempt.result_url ?? attempt.take_url
  return (
    <li className="flex flex-wrap items-center justify-between gap-3 py-3">
      <div className="min-w-0">
        <p className="font-medium text-ink">{attempt.test.title}</p>
        <p className="text-sm text-ink-secondary">
          {attempt.session.group?.name ?? attempt.session.title} · {formatDate(attempt.finished_at ?? attempt.started_at)}
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        {score ? (
          <span className="text-sm text-ink" data-testid="my-score">
            <strong>
              {score.earned} / {score.possible}
            </strong>{' '}
            — {Math.round(score.percent)}% · верно {score.correct}, ошибок {score.wrong}
            {score.pending ? `, на проверке ${score.pending}` : ''}
          </span>
        ) : null}
        <Badge tone={STATUS_TONE[attempt.status]}>{attempt.status === 'finished' ? 'Завершён' : attempt.status_label}</Badge>
        {url ? (
          <Button variant="secondary" size="sm" isLoading={isOpening} onClick={onOpen}>
            {attempt.status === 'active' ? 'Продолжить' : 'Подробнее'}
          </Button>
        ) : null}
      </div>
    </li>
  )
}
