import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'

import type { TrainingTest } from '@/types'

import { getTest } from '@/api/tests'
import { Button } from '@/components/Button'
import { Brand } from '@/components/Header'
import { ErrorState, errorText } from '@/components/ErrorState'
import { Icon } from '@/components/Icon'
import { Loader } from '@/components/Loader'
import { NameModal } from '@/components/NameModal'
import { TestScreen, useFinishFlow } from '@/components/TestScreen'
import { useAsync } from '@/hooks/useAsync'
import { requestFullscreen } from '@/hooks/useFullscreen'
import { useTraining } from '@/hooks/useTraining'
import { t } from '@/i18n'
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
  const flow = useFinishFlow((attemptId) => `/result/${attemptId}`)
  const training = useTraining(test.id, flow.onFinished)
  const [nameOpen, setNameOpen] = useState(false)

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

  return (
    <TestScreen
      mode="training"
      runner={training}
      flow={flow}
      security={test.security}
      onLeave={() => navigate('/training')}
      onRestart={training.restart}
    />
  )
}
