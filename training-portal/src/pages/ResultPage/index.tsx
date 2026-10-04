import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import type { ReviewRow } from '@/types'

import { getResult } from '@/api/attempts'
import { getTest } from '@/api/tests'
import { getLeaderboard } from '@/api/leaderboard'
import { Button } from '@/components/Button'
import { ExamButton } from '@/components/Button/ExamButton'
import { ErrorState } from '@/components/ErrorState'
import { Icon } from '@/components/Icon'
import { Loader } from '@/components/Loader'
import { ResultCard } from '@/components/ResultCard'
import { useAsync } from '@/hooks/useAsync'
import { t } from '@/i18n'
import './ResultPage.css'

const OUTCOME: Record<ReviewRow['status'], { label: string; icon: string; css: string }> = {
  correct: { label: t.result.correct, icon: 'check-circle-fill', css: 'correct' },
  wrong: { label: t.result.incorrect, icon: 'x-circle-fill', css: 'incorrect' },
  skipped: { label: t.result.skipped, icon: 'dash-circle-fill', css: 'skipped' },
  pending: { label: t.result.pending, icon: 'hourglass-split', css: 'ungraded' },
}

export function ResultPage() {
  const { attemptId = '' } = useParams()
  const navigate = useNavigate()
  const result = useAsync(() => getResult(attemptId), [attemptId])
  const board = useAsync(
    () => (result.data ? getLeaderboard(result.data.test_id) : Promise.resolve([])),
    [result.data?.test_id],
  )
  const trainer = useAsync(() => (result.data ? getTest(result.data.test_id) : Promise.resolve(null)), [result.data?.test_id])
  const [showReview, setShowReview] = useState(false)

  if (result.loading) return <Loader />
  if (result.error || !result.data) {
    return (
      <div className="container result-page">
        {result.error?.status === 404 ? (
          <div className="empty">
            <Icon name="clipboard-x" />
            <h1 className="section-title" style={{ marginBottom: 8 }}>{t.result.notFound}</h1>
            <p>{t.result.notFoundText}</p>
            <div style={{ marginTop: 20 }}><Button to="/training" icon="play-circle">{t.test.start}</Button></div>
          </div>
        ) : <ErrorState error={result.error} onRetry={result.reload} />}
      </div>
    )
  }

  const data = result.data
  const rank = (board.data ?? []).find((e) => e.student_name.toLocaleLowerCase() === data.student_name.toLocaleLowerCase())?.rank
  const review = data.review ?? []

  return (
    <div className="container result-page">
      {data.show_result && data.percentage !== undefined ? (
        <ResultCard result={data} />
      ) : (
        <div className="empty"><Icon name="send-check" /><h1 className="section-title" style={{ marginBottom: 8 }}>{t.result.title}</h1><p>{t.result.hidden}</p></div>
      )}
      {data.finish_reason === 'time_expired' ? <p className="result-note"><Icon name="alarm" />{t.result.timedOut}</p> : null}
      {data.finish_reason === 'violations' ? <p className="result-note"><Icon name="shield-exclamation" />{t.guard.terminated}</p> : null}
      {data.pending ? <p className="result-note result-note--wait"><Icon name="hourglass-split" />{t.result.pendingNote(data.pending)}</p> : null}

      <div className="result-actions">
        {trainer.data?.allow_retry === false ? null : (
          <Button icon="arrow-repeat" onClick={() => navigate(`/training/${data.test_id}`, { state: { retake: true } })}>{t.result.retake}</Button>
        )}
        {review.length ? (
          <Button variant="outline" icon={showReview ? 'eye-slash' : 'list-check'} onClick={() => setShowReview((v) => !v)}>
            {showReview ? t.result.hideReview : t.result.review}
          </Button>
        ) : null}
        <Button variant="outline" to="/leaderboard" icon="trophy">{t.result.leaders}</Button>
        <Button variant="outline" to="/materials" icon="journal-bookmark">{t.result.materials}</Button>
        <ExamButton url={trainer.data?.exam_url} />
      </div>

      {rank ? (
        <div className="result-rank">
          <span className="result-rank__icon"><Icon name="trophy-fill" /></span>
          <p><strong>{String(rank).padStart(2, '0')}</strong> — {t.result.rankText(data.test_title)}</p>
        </div>
      ) : null}

      {showReview ? (
        <section className="review" aria-label={t.result.reviewTitle}>
          <h2 className="section-title">{t.result.reviewTitle}</h2>
          {review.map((row) => {
            const outcome = OUTCOME[row.status]
            const given = row.selected.length ? row.selected.join(', ') : row.answer_text
            return (
              <article key={row.question_id} className={`review__item review__item--${outcome.css}`}>
                <div className="review__head">
                  <span className="review__num">{t.training.question} {row.number}</span>
                  <span className={`review__badge review__badge--${outcome.css}`}><Icon name={outcome.icon} />{outcome.label}</span>
                </div>
                <p className="review__q">{row.text}</p>
                <div className="review__row">
                  <strong>{t.result.yourAnswer}</strong>
                  {given ? (row.type === 'code' ? <pre>{given}</pre> : given) : <span className="muted">{t.result.noAnswer}</span>}
                </div>
                {row.status !== 'correct' && row.correct.length && row.type !== 'code' ? (
                  <div className="review__row"><strong>{t.training.correctAnswer}</strong>{row.correct.join(', ')}</div>
                ) : null}
                {row.explanation ? <div className="review__row"><strong>{t.training.explanation}</strong>{row.explanation}</div> : null}
              </article>
            )
          })}
        </section>
      ) : null}
    </div>
  )
}
