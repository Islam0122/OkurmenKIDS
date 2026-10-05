import { useParams } from 'react-router-dom'

import { ErrorState } from '@/components/ErrorState'
import { Icon } from '@/components/Icon'
import { Loader } from '@/components/Loader'
import { TestScreen, useFinishFlow } from '@/components/TestScreen'
import { useExam } from '@/hooks/useExam'
import { t } from '@/i18n'

const NO_SECURITY = { require_fullscreen: false, track_tab_switches: true, max_tab_switches: null, block_copy_paste: true }

/**
 * The exam — the same test screen as a training, with Exam Mode's rules:
 * the attempt comes from the session-key page (never started here), a reload
 * restores it (answers, timer from the server), no answer checking, no way
 * back to the site until it is finished.
 */
export function ExamAttemptPage() {
  const { attemptId = '' } = useParams()
  const flow = useFinishFlow((id) => `/exam/${id}/result`)
  const exam = useExam(attemptId, flow.onFinished)

  if (exam.phase === 'loading') return <Loader />
  if (exam.phase === 'error' || !exam.attempt) {
    const denied = exam.error?.status === 403 || exam.error?.status === 404
    return (
      <div className="container" style={{ paddingTop: 48 }}>
        {denied ? (
          <div className="empty">
            <Icon name="shield-lock" />
            <h1 className="section-title" style={{ marginBottom: 8 }}>{t.examMode.badge}</h1>
            <p>{t.examMode.noAccess}</p>
          </div>
        ) : <ErrorState error={exam.error} onRetry={() => window.location.reload()} />}
      </div>
    )
  }
  return <TestScreen mode="exam" runner={exam} flow={flow} security={exam.attempt.security ?? NO_SECURITY} />
}
