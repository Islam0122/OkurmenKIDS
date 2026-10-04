import { useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import type { Answer, Question, QuestionOutcome } from '@/types'

import { Button } from '@/components/Button'
import { ExamButton } from '@/components/Button/ExamButton'
import { Icon } from '@/components/Icon'
import { ResultCard } from '@/components/ResultCard'
import { useAsync } from '@/hooks/useAsync'
import { t } from '@/i18n'
import { correctAnswerText } from '@/lib/grading'
import { contentService } from '@/services/contentService'
import { leaderboardService } from '@/services/leaderboardService'
import { trainingService } from '@/services/trainingService'
import './ResultPage.css'

const OUTCOME: Record<QuestionOutcome, { label: string; icon: string }> = {
  correct: { label: t.result.correct, icon: 'check-circle-fill' },
  incorrect: { label: t.result.incorrect, icon: 'x-circle-fill' },
  skipped: { label: t.result.skipped, icon: 'dash-circle-fill' },
  ungraded: { label: t.result.ungraded, icon: 'eye' },
}

function answerText(question: Question, answer: Answer | undefined): string {
  if (!answer) return ''
  if (question.type === 'single' || question.type === 'multiple') {
    return (question.options ?? []).filter((o) => answer.options?.includes(o.id)).map((o) => o.text).join(', ')
  }
  return answer.text ?? ''
}

export function ResultPage() {
  const { attemptId = '' } = useParams()
  const navigate = useNavigate()
  const result = useMemo(() => trainingService.getResult(attemptId), [attemptId])
  const test = useAsync(() => (result ? contentService.getTest(result.testId) : Promise.resolve(null)), [result?.testId])
  const board = useAsync(() => (result ? leaderboardService.getLeaderboard(result.testId) : Promise.resolve([])), [result?.testId])
  const [showReview, setShowReview] = useState(false)

  if (!result) {
    return (
      <div className="container result-page">
        <div className="empty">
          <Icon name="clipboard-x" />
          <h1 className="section-title" style={{ marginBottom: 8 }}>{t.result.notFound}</h1>
          <p>{t.result.notFoundText}</p>
          <div style={{ marginTop: 20 }}><Button to="/training" icon="play-circle">{t.test.start}</Button></div>
        </div>
      </div>
    )
  }

  const rank = (board.data ?? []).findIndex((e) => e.name.toLocaleLowerCase() === result.studentName.toLocaleLowerCase())

  return (
    <div className="container result-page">
      <ResultCard result={result} />
      {result.timedOut ? <p className="result-note"><Icon name="alarm" />{t.result.timedOut}</p> : null}

      <div className="result-actions">
        <Button icon="arrow-repeat" onClick={() => navigate(`/training/${result.testId}`, { state: { retake: true } })}>{t.result.retake}</Button>
        <Button variant="outline" icon={showReview ? 'eye-slash' : 'list-check'} onClick={() => setShowReview((v) => !v)}>
          {showReview ? t.result.hideReview : t.result.review}
        </Button>
        <Button variant="outline" to="/leaderboard" icon="trophy">{t.result.leaders}</Button>
        <Button variant="outline" to="/materials" icon="journal-bookmark">{t.result.materials}</Button>
        <ExamButton label={t.result.exam} />
      </div>

      {rank >= 0 ? (
        <div className="result-rank">
          <span className="result-rank__icon"><Icon name="trophy-fill" /></span>
          <p><strong>{String(rank + 1).padStart(2, '0')}</strong> — {t.leaderboard.title.toLowerCase()} тизмесиндеги ордуңуз ({result.testTitle}).</p>
        </div>
      ) : null}

      {showReview && test.data ? (
        <section className="review" aria-label={t.result.reviewTitle}>
          <h2 className="section-title">{t.result.reviewTitle}</h2>
          {test.data.questions.map((question, i) => {
            const outcome = result.outcomes[question.id] ?? 'skipped'
            const given = answerText(question, result.answers[question.id])
            return (
              <article key={question.id} className={`review__item review__item--${outcome}`}>
                <div className="review__head">
                  <span className="review__num">{t.training.question} {i + 1}</span>
                  <span className={`review__badge review__badge--${outcome}`}><Icon name={OUTCOME[outcome].icon} />{OUTCOME[outcome].label}</span>
                </div>
                <p className="review__q">{question.question}</p>
                <div className="review__row">
                  <strong>{t.result.yourAnswer}</strong>
                  {given ? (question.type === 'code' ? <pre>{given}</pre> : given) : <span className="muted">{t.result.noAnswer}</span>}
                </div>
                {outcome !== 'correct' && question.correctAnswer ? (
                  <div className="review__row">
                    <strong>{question.type === 'code' ? t.training.sample : t.training.correctAnswer}</strong>
                    {question.type === 'code' ? <pre>{correctAnswerText(question)}</pre> : correctAnswerText(question)}
                  </div>
                ) : null}
                {question.explanation ? <div className="review__row"><strong>{t.training.explanation}</strong>{question.explanation}</div> : null}
              </article>
            )
          })}
        </section>
      ) : null}
    </div>
  )
}
