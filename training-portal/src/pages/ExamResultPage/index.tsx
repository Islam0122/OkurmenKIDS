import { useParams } from 'react-router-dom'

import { getExamResult } from '@/api/exam'
import { ApiError } from '@/api/client'
import { ErrorState } from '@/components/ErrorState'
import { TestHeader } from '@/components/TestHeader'
import { EXAM_MODE } from '@/components/TestScreen/modes'
import { Icon } from '@/components/Icon'
import { Loader } from '@/components/Loader'
import { useAsync } from '@/hooks/useAsync'
import { examToken } from '@/hooks/useExam'
import { t } from '@/i18n'
import { ResultView } from '../ResultPage'
import '../ResultPage/ResultPage.css'

/** The exam result — the training result view with the exam's heading. The
 * last screen of an exam: no retake, no leaderboard, nowhere else to go. */
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
    <>
    {/* The same header as the exam itself (no timer): the result is part of it. */}
    <TestHeader config={EXAM_MODE} title={data.test_title} student={data.student_name} />
    <div className="container result-page">
      <p className="visually-hidden" role="status">{t.examMode.doneTitle}</p>
      <ResultView
        data={data}
        hiddenText={t.examMode.hiddenResult}
      />
      <p className="result-final"><Icon name="check2-circle" />{t.examMode.closePage}</p>
    </div>
    </>
  )
}
