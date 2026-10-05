import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import type { SecuritySettings } from '@/types'

import { Button } from '@/components/Button'
import { ConfirmSubmitModal } from '@/components/ConfirmSubmitModal'
import { errorText } from '@/components/ErrorState'
import { Icon } from '@/components/Icon'
import { Modal } from '@/components/Modal'
import { QuestionCard } from '@/components/QuestionCard'
import { QuestionNavigation } from '@/components/QuestionNavigation'
import { SaveIndicator } from '@/components/SaveIndicator'
import { TestHeader } from '@/components/TestHeader'
import { TestProgress } from '@/components/TestProgress'
import { isAnswered, type AttemptRunner } from '@/hooks/useAttemptRunner'
import { useExamGuard, type BlockedAction } from '@/hooks/useExamGuard'
import { useTimer } from '@/hooks/useTimer'
import { t } from '@/i18n'
import '@/pages/TrainingPage/TrainingPage.css'

import { TEST_MODES, type TestMode, type TestModeConfig } from './modes'

export { EXAM_MODE, TEST_MODES, TRAINING_MODE, type TestMode, type TestModeConfig } from './modes'

/**
 * What happens when an attempt ends: straight to the result, or — when the
 * time ran out — first the «time is up» notice. Created before the runner
 * (the runner calls `onFinished`), handed to <TestScreen> with it.
 */
export function useFinishFlow(resultPath: (attemptId: string) => string) {
  const navigate = useNavigate()
  const [timeUp, setTimeUp] = useState(false)
  const timeUpRef = useRef(false)
  const resultTarget = useRef<string | null>(null)
  const pathRef = useRef(resultPath)
  pathRef.current = resultPath
  const onFinished = useCallback((attemptId: string) => {
    if (timeUpRef.current) { setTimeUp(true); resultTarget.current = attemptId; return }
    navigate(pathRef.current(attemptId), { replace: true })
  }, [navigate])
  const openResult = useCallback(() => {
    if (resultTarget.current) navigate(pathRef.current(resultTarget.current), { replace: true })
  }, [navigate])
  return { onFinished, timeUp, timeUpRef, openResult }
}

export type FinishFlow = ReturnType<typeof useFinishFlow>

/**
 * The one test screen of the portal — Training and Exam alike: the bar
 * (title, timer), progress, question numbers, the question card, navigation,
 * the guard (fullscreen / tab switches / copy) and the finish dialogs. What
 * differs between kinds of test comes from their TestModeConfig (./modes) —
 * no mode checks here.
 */
export function TestScreen({ mode, runner, flow, security, onLeave, onRestart }: {
  /** a known mode, or a config of a new kind of test */
  mode: TestMode | TestModeConfig
  runner: AttemptRunner
  flow: FinishFlow
  security: SecuritySettings
  /** Training: «Артка» back to the list (the attempt stays resumable). */
  onLeave?: () => void
  /** Training: «Башынан баштоо» after a resume. */
  onRestart?: () => void
}) {
  const config = typeof mode === 'string' ? TEST_MODES[mode] : mode
  const { text } = config
  const [confirmFinish, setConfirmFinish] = useState(false)
  const [confirmLeave, setConfirmLeave] = useState(false)
  const [blocked, setBlocked] = useState<BlockedAction | null>(null)
  useEffect(() => {
    if (!blocked) return
    const id = window.setTimeout(() => setBlocked(null), 2200)
    return () => window.clearTimeout(id)
  }, [blocked])

  const { timeUp, timeUpRef } = flow
  const guard = useExamGuard({
    active: runner.phase === 'running' && !timeUp,
    security: runner.attempt?.security ?? security,
    onEvent: runner.reportEvent,
    onBlocked: setBlocked,
  })
  const { submit } = runner
  const onExpire = useCallback(() => {
    timeUpRef.current = true
    void submit(true)  // the backend checks the deadline itself and grades the saved answers
  }, [submit, timeUpRef])
  const secondsLeft = useTimer(runner.phase === 'running' && !timeUp ? runner.deadline : null, onExpire)

  const attempt = runner.attempt
  if (!attempt) return null
  const { index } = runner
  const total = attempt.questions.length
  const question = attempt.questions[index]
  const answer = runner.answers[question.id]
  const fb = runner.feedback[question.id]
  const locked = Boolean(fb)
  const last = index === total - 1
  const showOutcome = config.allowCheck && attempt.show_explanation
  const canCheck = showOutcome && !locked && isAnswered(answer)

  return (
    <div className="train">
      <TestHeader
        config={config}
        title={attempt.test_title}
        student={attempt.student_name}
        secondsLeft={secondsLeft}
        onLeave={onLeave ? () => setConfirmLeave(true) : undefined}
      />

      <div className="train__layout">
        <TestProgress index={index} total={total} answered={runner.answeredCount} counts={config.counts} />
        {runner.resumed ? (
          <div className="train__notice" role="status">
            <span><Icon name="arrow-clockwise" />{text.resumed}</span>
            {config.allowRestart && onRestart ? <Button variant="ghost" size="sm" onClick={onRestart}>{t.training.restart}</Button> : null}
          </div>
        ) : null}
        {runner.error ? (
          <div className="train__notice train__notice--error" role="alert">
            <span><Icon name="exclamation-triangle" />{errorText(runner.error)}</span>
            <Button variant="ghost" size="sm" onClick={runner.clearError}>OK</Button>
          </div>
        ) : null}

        <QuestionNavigation states={runner.navStates} onSelect={runner.goTo} showOutcome={showOutcome} />

        <div className="train__question">
          <QuestionCard
            key={question.id}
            question={question}
            index={index}
            total={total}
            answer={answer}
            locked={locked}
            feedback={fb && fb !== true ? fb : null}
            onChange={(value) => runner.setAnswer(question.id, value)}
          />
        </div>

        <div className="train__controls">
          <Button className="train__prev" variant="outline" icon="arrow-left" disabled={index === 0} onClick={() => runner.goTo(index - 1)}>{t.training.prev}</Button>
          <div className="train__save"><SaveIndicator state={runner.saveState} /></div>
          <div className="train__controls-right">
            {canCheck ? <Button variant="navy" icon="check2-circle" disabled={runner.busy} onClick={() => { void runner.check(question.id) }}>{t.training.check}</Button> : null}
            {last
              ? <Button variant="primary" icon="flag" onClick={() => setConfirmFinish(true)}>{text.finish}</Button>
              : <Button variant={canCheck ? 'outline' : 'primary'} iconEnd="arrow-right" onClick={() => runner.goTo(index + 1)}>{t.training.next}</Button>}
          </div>
        </div>

        <div className="train__exit">
          {!last ? (
            <button type="button" className="link-arrow train__finish-link" onClick={() => setConfirmFinish(true)}>
              <Icon name="flag" />{text.finish}
            </button>
          ) : null}
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
        tone="warning"
        actions={<Button onClick={guard.dismissLeftPage}>{t.guard.continue}</Button>}
      >
        <p className="modal__text">{t.guard.leftText}</p>
        {attempt.security.max_tab_switches !== null ? (
          <p className="modal__text"><strong>{text.leftCount(runner.tabSwitches, attempt.security.max_tab_switches)}</strong></p>
        ) : null}
      </Modal>

      {blocked ? <div className="exam-toast" role="status"><Icon name="lock" />{t.guard.blocked[blocked]}</div> : null}

      {onLeave ? (
        <Modal
          open={confirmLeave}
          onClose={() => setConfirmLeave(false)}
          title={t.training.leaveTitle}
          icon="box-arrow-left"
          actions={<>
            <Button variant="outline" onClick={() => setConfirmLeave(false)}>{t.training.leaveStay}</Button>
            <Button variant="outline" icon="box-arrow-left" onClick={onLeave}>{t.training.leaveConfirm}</Button>
          </>}
        >
          <p className="modal__text">{t.training.leaveText}</p>
        </Modal>
      ) : null}

      <ConfirmSubmitModal
        open={confirmFinish}
        config={config}
        total={total}
        answered={runner.answeredCount}
        secondsLeft={secondsLeft}
        busy={runner.busy}
        onCancel={() => setConfirmFinish(false)}
        onConfirm={() => { setConfirmFinish(false); void runner.submit() }}
      />

      <Modal
        open={timeUp}
        dismissible={false}
        title={text.timeUpTitle}
        icon="alarm"
        tone="warning"
        actions={<Button icon="bar-chart" onClick={flow.openResult}>{text.seeResult}</Button>}
      >
        <p className="modal__text">{text.timeUpText}</p>
      </Modal>
    </div>
  )
}
