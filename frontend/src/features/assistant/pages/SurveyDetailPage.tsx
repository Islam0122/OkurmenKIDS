import { Copy, Lock, MessageSquareText, Send, Unlock } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'

import { surveysApi } from '@/api/assistant'
import { PageHeader } from '@/components/layout/PageHeader'
import { BackLink } from '@/components/ui/BackLink'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { StatCard } from '@/components/ui/StatCard'
import { useToast } from '@/components/ui/Toast'
import { useAssistantMutation, useAssistantOptions, useSurvey, useSurveyAnalytics } from '@/hooks/useAssistant'
import { isNotFound } from '@/lib/apiError'

import { SURVEY_STATUS } from './SurveysPage'

/** A survey: its link, publish / close, questions, and simple results (responses, response rate, per-question counts). */
export function AssistantSurveyDetailPage() {
  const { id } = useParams()
  const surveyId = Number(id)
  const { showToast } = useToast()
  const { data: survey, isPending, isError, error, refetch } = useSurvey(Number.isFinite(surveyId) ? surveyId : undefined)
  const { data: analytics } = useSurveyAnalytics(surveyId, Boolean(survey && survey.status !== 'draft'))
  const { data: options } = useAssistantOptions()
  const publish = useAssistantMutation(() => surveysApi.publish(surveyId), 'Опрос опубликован')
  const close = useAssistantMutation(() => surveysApi.close(surveyId), 'Опрос закрыт')
  const reopen = useAssistantMutation(() => surveysApi.reopen(surveyId), 'Опрос снова принимает ответы')

  if (isPending) return <LoadingState label="Загружаем опрос…" />
  if (isError || !survey) {
    return isNotFound(error)
      ? <EmptyState icon={MessageSquareText} title="Опрос не найден" action={<Link to="/assistant/surveys" className="text-sm font-medium text-brand-700">К опросам</Link>} />
      : <ErrorState onRetry={() => void refetch()} />
  }

  const group = options?.groups.find((g) => g.id === survey.group)
  const rate = group?.students_count ? Math.round((survey.response_count / group.students_count) * 100) : null
  const copy = async () => {
    if (!survey.public_url) return
    try {
      await navigator.clipboard.writeText(survey.public_url)
      showToast('Ссылка скопирована', 'success')
    } catch {
      showToast('Не удалось скопировать — выделите ссылку вручную', 'error')
    }
  }

  return (
    <div>
      <BackLink to="/assistant/surveys">Все опросы</BackLink>
      <PageHeader
        title={survey.title}
        badge={<Badge tone={SURVEY_STATUS[survey.status].tone}>{SURVEY_STATUS[survey.status].label}</Badge>}
        description={`${group?.name ?? (survey.group ? `Группа #${survey.group}` : 'Вся академия')} · ${survey.audience === 'parent' ? 'родители' : 'студенты'}`}
        actions={
          <>
            {survey.status === 'draft' ? <Button leftIcon={<Send className="size-4" aria-hidden />} isLoading={publish.isPending} disabled={publish.isPending || survey.questions.length === 0} onClick={() => publish.mutate(undefined)}>Опубликовать</Button> : null}
            {survey.status === 'published' ? <Button variant="secondary" leftIcon={<Lock className="size-4" aria-hidden />} isLoading={close.isPending} disabled={close.isPending} onClick={() => close.mutate(undefined)}>Закрыть</Button> : null}
            {survey.status === 'closed' ? <Button variant="secondary" leftIcon={<Unlock className="size-4" aria-hidden />} isLoading={reopen.isPending} disabled={reopen.isPending} onClick={() => reopen.mutate(undefined)}>Открыть снова</Button> : null}
          </>
        }
      />

      {survey.status === 'published' && survey.public_url ? (
        <Card className="mb-6" title="Ссылка для ответа" description="Отправьте её в чат группы или родителям.">
          <div className="flex flex-col gap-2 sm:flex-row">
            <input readOnly value={survey.public_url} className="form-control font-mono text-xs" onFocus={(e) => e.target.select()} aria-label="Ссылка на опрос" />
            <Button variant="secondary" leftIcon={<Copy className="size-4" aria-hidden />} onClick={() => void copy()}>Копировать</Button>
          </div>
        </Card>
      ) : null}

      <div className="mb-6 grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-3">
        <StatCard label="Ответов" value={survey.response_count} />
        <StatCard label="Отклик" value={rate !== null ? `${rate}%` : '—'} hint={group ? `из ${group.students_count} студентов` : 'без группы'} />
        <StatCard label="Вопросов" value={survey.questions.length} className="col-span-2 lg:col-span-1" />
      </div>

      <Card title="Результаты">
        {survey.status === 'draft' ? (
          <ol className="list-decimal space-y-2 pl-5 text-sm text-ink">
            {survey.questions.map((q) => <li key={q.id}>{q.text}{q.options.length ? <span className="text-ink-secondary"> — {q.options.map((o) => o.text).join(', ')}</span> : null}</li>)}
          </ol>
        ) : !analytics ? <LoadingState label="Считаем ответы…" /> : analytics.response_count === 0 ? (
          <p className="text-sm text-ink-secondary">Ответов пока нет.</p>
        ) : (
          <div className="space-y-6">
            {analytics.questions.map((q) => (
              <div key={q.id}>
                <p className="text-sm font-medium text-ink">{q.index}. {q.text}</p>
                <p className="mb-2 text-xs text-ink-muted">Ответили: {q.answered}</p>
                {q.options ? (
                  <ul className="space-y-1.5">
                    {q.options.map((o) => (
                      <li key={o.id} className="text-sm">
                        <div className="flex justify-between gap-3"><span className="text-ink">{o.text}</span><span className="tabular-nums text-ink-secondary">{o.count} · {o.pct}%</span></div>
                        <div className="mt-1 h-2 rounded-full bg-surface-hover"><div className="h-2 rounded-full bg-brand-500" style={{ width: `${Math.min(o.pct, 100)}%` }} /></div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <ul className="max-h-60 space-y-1.5 overflow-y-auto">
                    {(q.texts ?? []).map((t, i) => <li key={i} className="rounded-lg bg-surface-muted px-3 py-2 text-sm text-ink">{t.text}</li>)}
                  </ul>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
