import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'

import type { TrainingTest } from '@/types'

import { getTest } from '@/api/tests'
import { Button } from '@/components/Button'
import { Brand } from '@/components/Header'
import { ErrorState, errorText } from '@/components/ErrorState'
import { Icon } from '@/components/Icon'
import { Loader } from '@/components/Loader'
import { Modal } from '@/components/Modal'
import { NameModal } from '@/components/NameModal'
import { ProgressBar } from '@/components/ProgressBar'
import { QuestionCard } from '@/components/QuestionCard'
import { QuestionNavigation } from '@/components/QuestionNavigation'
import { SaveIndicator } from '@/components/SaveIndicator'
import { Timer } from '@/components/Timer'
import { useAsync } from '@/hooks/useAsync'
import { useExamGuard, type BlockedAction } from '@/hooks/useExamGuard'
import { requestFullscreen } from '@/hooks/useFullscreen'
import { useTimer } from '@/hooks/useTimer'
import { isAnswered, useTraining } from '@/hooks/useTraining'
import { t } from '@/i18n'
import { formatClock } from '@/lib/format'
import { storageService } from '@/services/storageService'
import { NotFoundPage } from '../NotFoundPage'
import './TrainingPage.css'

export function TrainingPage() {
  const { testId = '' } = useParams()
  const test = useAsync(() => getTest(testId), [testId])
  if (test.loading) return <Loader />
  if (test.error?.status === 404) return <NotFoundPage title={t.common.testNotFound} />
  if (test.error || !test.data) return <div className="container"><ErrorState error={test.error} onRetry={test.reload} /></div>
  return <TrainingRunner key={test.data.id} test={test.data} />
}

function TrainingIntro({ test, onStart, busy }: { test: TrainingTest; onStart: () => void; busy: boolean }) {
  return (
    <>
    <div className="container exam-topline">
      <Brand />
      <Link className="link-arrow" to="/training"><Icon name="chevron-left" />{t.home.testsTitle}</Link>
    </div>
    <div className="container intro">
      <div>
        <span className="eyebrow"><Icon name="mortarboard" />{t.test.title}{test.subject ? ` · ${test.subject}` : ''}</span>
        <h1 className="intro__title">{test.title}</h1>
        {test.description ? <p className="section-subtitle">{test.description}</p> : null}
        <ul className="intro__rules">
          {test.show_explanation ? <li><Icon name="check2-circle" />{t.training.intro}</li> : null}
          <li><Icon name="clock" />{test.duration ? t.training.introTime(test.duration) : t.test.noLimit}</li>
          <li><Icon name="arrow-repeat" />{test.max_attempts === null ? t.training.introRetake : `${t.test.attempts}: ${test.max_attempts}`}</li>
          <li><Icon name="shield-lock" />{t.name.privacy}</li>
          {test.security.track_tab_switches ? <li><Icon name="window-stack" />{t.guard.introTabs}</li> : null}
          {test.security.block_copy_paste ? <li><Icon name="clipboard-x" />{t.guard.introCopy}</li> : null}
        </ul>
      </div>
      <aside className="intro__card">
        <dl className="intro__facts">
          <div><dt><Icon name="list-check" />{t.test.facts.questions}</dt><dd style={{ margin: 0 }}>{test.questions_count}</dd></div>
          <div><dt><Icon name="clock" />{t.test.facts.time}</dt><dd style={{ margin: 0 }}>{test.duration ? t.test.minutes(test.duration) : t.test.noLimit}</dd></div>
          <div><dt><Icon name="reception-3" />{t.test.facts.level}</dt><dd style={{ margin: 0 }}>{test.level_display}</dd></div>
          <div><dt><Icon name="trophy" />{t.test.facts.passing}</dt><dd style={{ margin: 0 }}>{test.passing_score}%</dd></div>
        </dl>
        <Button size="lg" block icon="play-circle" onClick={onStart} disabled={busy}>{t.test.start}</Button>
        {test.security.require_fullscreen ? <p className="intro__note"><Icon name="fullscreen" />{t.guard.introFullscreen}</p> : null}
        <p className="intro__note"><Icon name="info-circle" />{t.common.trainingOnly}</p>
      </aside>
    </div>
    </>
  )
}

function TrainingRunner({ test }: { test: TrainingTest }) {
  const navigate = useNavigate()
  const location = useLocation()
  const [timeUp, setTimeUp] = useState(false)
  const timeUpRef = useRef(false)
  const resultTarget = useRef<string | null>(null)
  const onFinished = useCallback((attemptId: string) => {
    if (timeUpRef.current) { setTimeUp(true); resultTarget.current = attemptId; return }
    navigate(`/result/${attemptId}`, { replace: true })
  }, [navigate])
  const training = useTraining(test.id, onFinished)
  const [nameOpen, setNameOpen] = useState(false)
  const [confirmFinish, setConfirmFinish] = useState(false)
  const [confirmLeave, setConfirmLeave] = useState(false)

  // From «Тренировка баштоо» straight to the name; «Кайра тапшыруу» starts
  // again under the same name.
  const autoStarted = useRef(false)
  useEffect(() => {
    if (training.phase !== 'intro' || autoStarted.current) return
    autoStarted.current = true
    const retake = (location.state as { retake?: boolean } | null)?.retake
    const saved = storageService.getStudentName()
    if (retake && saved) void training.start(saved)
    else setNameOpen(true)
  }, [training.phase, training, location.state])

  const [blocked, setBlocked] = useState<BlockedAction | null>(null)
  useEffect(() => {
    if (!blocked) return
    const id = window.setTimeout(() => setBlocked(null), 2200)
    return () => window.clearTimeout(id)
  }, [blocked])
  const guard = useExamGuard({
    active: training.phase === 'running' && !timeUp,
    security: training.attempt?.security ?? test.security,
    onEvent: training.reportEvent,
    onBlocked: setBlocked,
  })

  const onExpire = useCallback(() => {
    timeUpRef.current = true
    void training.submit()  // the backend closes it as «time expired» and grades the saved answers
  }, [training])
  const secondsLeft = useTimer(training.phase === 'running' && !timeUp ? training.deadline : null, onExpire)

  if (training.phase === 'loading') return <Loader />
  if (training.phase === 'error') return <div className="container"><ErrorState error={training.error} onRetry={() => window.location.reload()} /></div>

  if (training.phase === 'intro' || !training.attempt) {
    return (
      <>
        <TrainingIntro test={test} busy={training.busy} onStart={() => { training.clearError(); setNameOpen(true) }} />
        <NameModal
          open={nameOpen}
          busy={training.busy}
          serverError={training.error ? errorText(training.error) : null}
          initialName={storageService.getStudentName()}
          onSubmit={(name) => {
            // Fullscreen is a per-trainer setting; it must be requested inside the click.
            if (test.security.require_fullscreen) requestFullscreen()
            void training.start(name)
          }}
          onClose={() => setNameOpen(false)}
        />
      </>
    )
  }

  const { attempt, index } = training
  const total = attempt.questions.length
  const question = attempt.questions[index]
  const answer = training.answers[question.id]
  const fb = training.feedback[question.id]
  const locked = Boolean(fb)
  const last = index === total - 1
  const canCheck = attempt.show_explanation && !locked && isAnswered(answer)

  return (
    <div className="train">
      <header className="train__bar">
        <div className="train__bar-inner">
          <button type="button" className="train__back" aria-label={t.training.leave} onClick={() => setConfirmLeave(true)}>
            <Icon name="chevron-left" /><span>{t.training.leave}</span>
          </button>
          <div className="train__title">
            <strong title={attempt.test_title}>{attempt.test_title}</strong>
            <span className="train__student"><Icon name="person" /><span>{attempt.student_name}</span></span>
          </div>
          <Timer secondsLeft={secondsLeft} />
        </div>
      </header>

      <div className="train__layout">
        <div className="train__progress">
          <ProgressBar value={index + 1} max={total} label={t.training.progress(index + 1, total)} />
        </div>
        {training.resumed ? (
          <div className="train__notice">
            <span><Icon name="arrow-clockwise" />{t.training.resumed}</span>
            <Button variant="ghost" size="sm" onClick={training.restart}>{t.training.restart}</Button>
          </div>
        ) : null}
        {training.error ? (
          <div className="train__notice train__notice--error" role="alert">
            <span><Icon name="exclamation-triangle" />{errorText(training.error)}</span>
            <Button variant="ghost" size="sm" onClick={training.clearError}>OK</Button>
          </div>
        ) : null}

        <QuestionNavigation states={training.navStates} onSelect={training.goTo} />

        <div className="train__question">
          <QuestionCard
            key={question.id}
            question={question}
            index={index}
            total={total}
            answer={answer}
            locked={locked}
            feedback={fb && fb !== true ? fb : null}
            onChange={(value) => training.setAnswer(question.id, value)}
          />
        </div>

        <div className="train__save"><SaveIndicator state={training.saveState} /></div>

        <div className="train__controls">
          <Button className="train__prev" variant="outline" icon="arrow-left" disabled={index === 0} onClick={() => training.goTo(index - 1)}>{t.training.prev}</Button>
          <div className="train__controls-right">
            {canCheck ? <Button variant="navy" icon="check2-circle" disabled={training.busy} onClick={() => { void training.check(question.id) }}>{t.training.check}</Button> : null}
            {last
              ? <Button variant="primary" icon="flag" onClick={() => setConfirmFinish(true)}>{t.training.finish}</Button>
              : <Button variant={canCheck ? 'outline' : 'primary'} iconEnd="arrow-right" onClick={() => training.goTo(index + 1)}>{t.training.next}</Button>}
          </div>
        </div>

        <div className="train__exit">
          {!last ? <><button type="button" className="link-arrow" style={{ border: 0, background: 'none', cursor: 'pointer' }} onClick={() => setConfirmFinish(true)}><Icon name="flag" />{t.training.finish}</button></> : null}
        </div>
      </div>

      {guard.locked ? (
        <div className="lock-overlay" role="alertdialog" aria-modal="true" aria-labelledby="lock-title">
          <div className="lock-overlay__box">
            <span className="lock-overlay__icon"><Icon name="fullscreen" /></span>
            <h2 id="lock-title">{t.guard.lockTitle}</h2>
            <p>{t.guard.lockText}</p>
            <Button size="lg" icon="fullscreen" onClick={guard.requestFullscreen}>{t.guard.lockButton}</Button>
            <p className="lock-overlay__note">{t.guard.lockNote}</p>
          </div>
        </div>
      ) : null}

      <Modal
        open={guard.leftPage && !guard.locked && !timeUp}
        onClose={guard.dismissLeftPage}
        title={t.guard.leftTitle}
        icon="exclamation-triangle"
        tone="amber"
        actions={<Button onClick={guard.dismissLeftPage}>{t.guard.continue}</Button>}
      >
        <p className="modal__text">{t.guard.leftText}</p>
        {attempt.security.max_tab_switches !== null ? (
          <p className="modal__text"><strong>{t.guard.leftCount(training.tabSwitches, attempt.security.max_tab_switches)}</strong></p>
        ) : null}
      </Modal>

      {blocked ? <div className="exam-toast" role="status"><Icon name="lock" />{t.guard.blocked[blocked]}</div> : null}

      <Modal
        open={confirmLeave}
        onClose={() => setConfirmLeave(false)}
        title={t.training.leaveTitle}
        icon="box-arrow-left"
        tone="amber"
        actions={<>
          <Button variant="ghost" onClick={() => setConfirmLeave(false)}>{t.training.leaveStay}</Button>
          <Button variant="outline" icon="box-arrow-left" onClick={() => navigate('/training')}>{t.training.leaveConfirm}</Button>
        </>}
      >
        <p className="modal__text">{t.training.leaveText}</p>
      </Modal>

      <Modal
        open={confirmFinish}
        onClose={() => setConfirmFinish(false)}
        title={t.training.finishTitle}
        icon="flag"
        tone="amber"
        actions={<>
          <Button variant="ghost" onClick={() => setConfirmFinish(false)}>{t.training.keepGoing}</Button>
          <Button icon="flag-fill" disabled={training.busy} onClick={() => { setConfirmFinish(false); void training.submit() }}>{t.training.finish}</Button>
        </>}
      >
        <p className="modal__text">{t.training.finishText}</p>
        <dl className="finish-stats">
          <div><dt>{t.training.total}</dt><dd>{total}</dd></div>
          <div><dt>{t.training.answered}</dt><dd>{training.answeredCount}</dd></div>
          <div><dt>{t.training.unanswered}</dt><dd>{total - training.answeredCount}</dd></div>
          <div><dt>{t.training.timeLeft}</dt><dd>{secondsLeft === null ? '—' : formatClock(secondsLeft)}</dd></div>
        </dl>
      </Modal>

      <Modal
        open={timeUp}
        dismissible={false}
        title={t.training.timeUpTitle}
        icon="alarm"
        tone="red"
        actions={<Button icon="bar-chart" onClick={() => resultTarget.current && navigate(`/result/${resultTarget.current}`, { replace: true })}>{t.training.seeResult}</Button>}
      >
        <p className="modal__text">{t.training.timeUpText}</p>
      </Modal>
    </div>
  )
}
