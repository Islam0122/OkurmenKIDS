import { useParams } from 'react-router-dom'

import { getExamResult } from '@/api/exam'
import { ApiError } from '@/api/client'
import { Button } from '@/components/Button'
import { ErrorState } from '@/components/ErrorState'
import { Icon } from '@/components/Icon'
import { Loader } from '@/components/Loader'
import { useAsync } from '@/hooks/useAsync'
import { examToken } from '@/hooks/useExam'
import { t } from '@/i18n'
import { ResultView } from '../ResultPage'
import '../ResultPage/ResultPage.css'

/** The exam result — the training result view, with the exam's heading and
 * the way back to the student's cabinet (no retake, no leaderboard). */
export function ExamResultPage() {
  const { attemptId = '' } = useParams()
  const result = useAsync(() => {
    const token = examToken(attemptId)
    return token ? getExamResult(attemptId, token) : Promise.reject(new ApiError('', 403, 'forbidden'))
  }, [attemptId])

  if (result.loading) return <Loader />
  if (result.error || !result.data) {
    const denied = result.error?.status === 403 || result.error?.status === 404
    return (
      <div className="container result-page">
        {denied ? <div className="empty"><Icon name="shield-lock" /><p>{t.examMode.noAccess}</p></div>
          : <ErrorState error={result.error} onRetry={result.reload} />}
      </div>
    )
  }
  const data = result.data
  return (
    <div className="container result-page">
      <span className="eyebrow" style={{ marginBottom: 16 }}><Icon name="clipboard-check" />{t.examMode.doneTitle}</span>
      <ResultView
        data={data}
        hiddenText={t.examMode.hiddenResult}
        actions={<Button href={data.back_url} icon="house">{t.examMode.backToCabinet}</Button>}
      />
    </div>
  )
}
