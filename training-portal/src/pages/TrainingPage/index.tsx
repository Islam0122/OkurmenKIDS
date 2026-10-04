import { useCallback, useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'

import type { Test, TrainingResult } from '@/types'

import { Button } from '@/components/Button'
import { Icon } from '@/components/Icon'
import { Loader } from '@/components/Loader'
import { Modal } from '@/components/Modal'
import { NameModal } from '@/components/NameModal'
import { ProgressBar } from '@/components/ProgressBar'
import { QuestionCard } from '@/components/QuestionCard'
import { QuestionNavigation } from '@/components/QuestionNavigation'
import { Timer } from '@/components/Timer'
import { useAsync } from '@/hooks/useAsync'
import { useTimer } from '@/hooks/useTimer'
import { useTraining } from '@/hooks/useTraining'
import { t } from '@/i18n'
import { formatClock } from '@/lib/format'
import { isAnswered } from '@/lib/grading'
import { contentService } from '@/services/contentService'
import { studentService } from '@/services/studentService'
import { trainingService } from '@/services/trainingService'
import { NotFoundPage } from '../NotFoundPage'
import './TrainingPage.css'

export function TrainingPage() {
  const { testId = '' } = useParams()
  const { data: test, loading } = useAsync(() => contentService.getTest(testId), [testId])
  if (loading) return <Loader />
  if (!test) return <NotFoundPage title={t.common.testNotFound} />
  return <TrainingRunner test={test} />
}

function TrainingIntro({ test, onStart, error }: { test: Test; onStart: () => void; error: string | null }) {
  return (
    <div className="container intro">
      <div>
        <span className="eyebrow"><Icon name="mortarboard" />{t.test.title} · {test.subject}</span>
        <h1 className="intro__title">{test.title}</h1>
        {test.description ? <p className="section-subtitle">{test.description}</p> : null}
        <ul className="intro__rules">
          <li><Icon name="check2-circle" />{t.training.intro}</li>
          <li><Icon name="clock" />{test.duration ? t.training.introTime(test.duration) : t.test.noLimit}</li>
          <li><Icon name="arrow-repeat" />{test.maxAttempts === null ? t.training.introRetake : `${t.test.attempts}: ${test.maxAttempts}`}</li>
          <li><Icon name="shield-lock" />{t.name.privacy}</li>
        </ul>
      </div>
      <aside className="intro__card">
        <dl className="intro__facts">
          <div><dt><Icon name="list-check" />{t.test.facts.questions}</dt><dd style={{ margin: 0 }}>{test.questions.length}</dd></div>
          <div><dt><Icon name="clock" />{t.test.facts.time}</dt><dd style={{ margin: 0 }}>{test.duration ? t.test.minutes(test.duration) : t.test.noLimit}</dd></div>
          <div><dt><Icon name="reception-3" />{t.test.facts.level}</dt><dd style={{ margin: 0 }}>{t.test.level[test.level]}</dd></div>
          <div><dt><Icon name="bookmarks" />{t.test.facts.topics}</dt><dd style={{ margin: 0 }}>{test.topics ?? test.subject}</dd></div>
        </dl>
        {error ? <p className="field-error" role="alert"><Icon name="exclamation-circle" />{error}</p> : null}
        <Button size="lg" block icon="play-circle" onClick={onStart}>{t.test.start}</Button>
        <p className="intro__note"><Icon name="info-circle" />{t.common.trainingOnly}</p>
      </aside>
    </div>
  )
}

function TrainingRunner({ test }: { test: Test }) {
  const navigate = useNavigate()
  const location = useLocation()
  const training = useTraining(test)
  const { progress } = training
  const [nameOpen, setNameOpen] = useState(false)
  const [startError, setStartError] = useState<string | null>(null)
  const [confirmFinish, setConfirmFinish] = useState(false)
  const [timeUp, setTimeUp] = useState<TrainingResult | null>(null)

  const begin = useCallback((name: string) => {
    if (test.maxAttempts !== null && trainingService.attemptsUsed(test.id, name) >= test.maxAttempts) {
      setStartError(t.training.limitReached)
      setNameOpen(false)
      return
    }
    studentService.setName(name)
    setNameOpen(false)
    training.start(name)
  }, [test, training])

  // «Тренировка баштоо» brings the student straight to the name; «Кайра
  // тапшыруу» starts again under the same name.
  useEffect(() => {
    if (progress) return
    const retake = (location.state as { retake?: boolean } | null)?.retake
    const saved = studentService.getName()
    if (retake && saved) begin(saved)
    else setNameOpen(true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [test.id])

  const onExpire = useCallback(() => {
    const result = training.finish(true)
    if (result) setTimeUp(result)
  }, [training])
  const secondsLeft = useTimer(timeUp ? null : progress?.deadline ?? null, onExpire)

  if (!progress) {
    return (
      <>
        <TrainingIntro test={test} error={startError} onStart={() => { setStartError(null); setNameOpen(true) }} />
        <NameModal open={nameOpen} initialName={studentService.getName()} onSubmit={begin} onClose={() => setNameOpen(false)} />
      </>
    )
  }

  const index = progress.currentIndex
  const question = test.questions[index]
  const answer = progress.answers[question.id]
  const revealed = Boolean(progress.checked[question.id])
  const last = index === test.questions.length - 1
  const canCheck = test.showExplanation && !revealed && isAnswered(answer)

  const finishNow = () => {
    const result = training.finish(false)
    if (result) navigate(`/result/${result.attemptId}`, { replace: true })
  }

  return (
    <div className="train">
      <div className="train__bar">
        <div className="container train__layout">
          <div className="train__bar-row">
            <div className="train__title">
              <strong>{test.title}</strong>
              <span className="train__student"><Icon name="person" />{progress.studentName}</span>
            </div>
            <Timer secondsLeft={secondsLeft} />
          </div>
          <ProgressBar value={index + 1} max={test.questions.length} label={t.training.progress(index + 1, test.questions.length)} />
        </div>
      </div>

      <div className="container train__layout">
        {training.resumed ? (
          <div className="train__notice">
            <span><Icon name="arrow-clockwise" />{t.training.resumed}</span>
            <Button variant="ghost" size="sm" onClick={training.restart}>{t.training.restart}</Button>
          </div>
        ) : null}

        <QuestionNavigation states={training.navStates} onSelect={training.goTo} />

        <div style={{ marginTop: 16 }}>
          <QuestionCard
            key={question.id}
            question={question}
            index={index}
            total={test.questions.length}
            answer={answer}
            revealed={revealed}
            showFeedback={test.showExplanation}
            onChange={(value) => training.setAnswer(question.id, value)}
          />
        </div>

        <div className="train__controls">
          <Button variant="outline" icon="arrow-left" disabled={index === 0} onClick={() => training.goTo(index - 1)}>{t.training.prev}</Button>
          <div className="train__controls-right">
            {canCheck ? <Button variant="navy" icon="check2-circle" onClick={() => training.check(question.id)}>{t.training.check}</Button> : null}
            {last
              ? <Button variant="primary" icon="flag" onClick={() => setConfirmFinish(true)}>{t.training.finish}</Button>
              : <Button variant={canCheck ? 'outline' : 'primary'} iconEnd="arrow-right" onClick={() => training.goTo(index + 1)}>{t.training.next}</Button>}
          </div>
        </div>

        <div className="train__exit">
          <Link className="link-arrow" to="/training"><Icon name="box-arrow-left" />{t.training.exit}</Link>
          {!last ? <> · <button type="button" className="link-arrow" style={{ border: 0, background: 'none', cursor: 'pointer' }} onClick={() => setConfirmFinish(true)}><Icon name="flag" />{t.training.finish}</button></> : null}
        </div>
      </div>

      <Modal
        open={confirmFinish}
        onClose={() => setConfirmFinish(false)}
        title={t.training.finishTitle}
        icon="flag"
        tone="amber"
        actions={<>
          <Button variant="ghost" onClick={() => setConfirmFinish(false)}>{t.training.keepGoing}</Button>
          <Button icon="flag-fill" onClick={finishNow}>{t.training.finish}</Button>
        </>}
      >
        <p className="modal__text">{t.training.finishText}</p>
        <dl className="finish-stats">
          <div><dt>{t.training.total}</dt><dd>{test.questions.length}</dd></div>
          <div><dt>{t.training.answered}</dt><dd>{training.answeredCount}</dd></div>
          <div><dt>{t.training.unanswered}</dt><dd>{test.questions.length - training.answeredCount}</dd></div>
          <div><dt>{t.training.timeLeft}</dt><dd>{secondsLeft === null ? '—' : formatClock(secondsLeft)}</dd></div>
        </dl>
      </Modal>

      <Modal
        open={Boolean(timeUp)}
        dismissible={false}
        title={t.training.timeUpTitle}
        icon="alarm"
        tone="red"
        actions={<Button icon="bar-chart" onClick={() => timeUp && navigate(`/result/${timeUp.attemptId}`, { replace: true })}>{t.training.seeResult}</Button>}
      >
        <p className="modal__text">{t.training.timeUpText}</p>
      </Modal>
    </div>
  )
}
