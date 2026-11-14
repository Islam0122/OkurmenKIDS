import { useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, ExternalLink, FileText, PlayCircle, Send } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'

import { studentPortalApi } from '@/api/studentPortal'
import type { HomeworkFilter } from '@/api/studentPortal'
import { extractErrorMessage } from '@/lib/apiError'
import { cn } from '@/utils/cn'

import { PORTAL_KEY, usePortal } from '../context'
import { usePortalI18n } from '../i18n'
import { HomeworkMini } from './DashboardPage'
import { Empty, HomeworkBadge, LoadError, Loading, PCard, PageTitle } from '../ui'

type FilterTab = Extract<HomeworkFilter, 'open' | 'overdue' | 'done' | 'checked' | 'all'>
const FILTERS: FilterTab[] = ['open', 'overdue', 'done', 'checked', 'all']

export function StudentHomeworkPage() {
  const { student } = usePortal()
  const { t } = usePortalI18n()
  const [filter, setFilter] = useState<FilterTab>('open')
  const [page, setPage] = useState(1)
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: [...PORTAL_KEY, 'homework', student.id, filter, page],
    queryFn: () => studentPortalApi.homework(student.id, filter, page),
    placeholderData: keepPreviousData,
  })
  const label = (f: FilterTab) => (f === 'all' ? t('common.all') : t(`hw.filter.${f}`))
  return (
    <div>
      <PageTitle title={t('hw.title')} />
      <div className="-mx-4 mb-4 flex gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:px-0">
        {FILTERS.map((f) => (
          <button key={f} type="button" onClick={() => { setFilter(f); setPage(1) }} aria-pressed={filter === f}
            className={cn('shrink-0 rounded-full px-3.5 py-1.5 text-sm font-medium ring-1',
              filter === f ? 'bg-brand-500 text-white ring-brand-500' : 'bg-surface text-ink-secondary ring-border hover:text-ink')}>
            {label(f)}
          </button>
        ))}
      </div>
      {isPending ? <Loading /> : isError || !data ? <LoadError onRetry={() => void refetch()} /> : data.results.length === 0 ? (
        <Empty>{t('hw.empty')}</Empty>
      ) : (
        <>
          <div className="grid gap-2 md:grid-cols-2">{data.results.map((hw) => <HomeworkMini key={hw.id} hw={hw} />)}</div>
          {data.next || data.previous ? (
            <div className="mt-4 flex justify-center gap-2">
              <button type="button" disabled={!data.previous} onClick={() => setPage((p) => p - 1)} className="rounded-lg border border-border px-3 py-1.5 text-sm disabled:opacity-40">←</button>
              <span className="px-2 py-1.5 text-sm text-ink-secondary">{page}</span>
              <button type="button" disabled={!data.next} onClick={() => setPage((p) => p + 1)} className="rounded-lg border border-border px-3 py-1.5 text-sm disabled:opacity-40">→</button>
            </div>
          ) : null}
        </>
      )}
    </div>
  )
}

export function StudentHomeworkDetailPage() {
  const { id } = useParams()
  const homeworkId = Number(id)
  const { student } = usePortal()
  const { t, date } = usePortalI18n()
  const queryClient = useQueryClient()
  const key = [...PORTAL_KEY, 'homework-detail', student.id, homeworkId]
  const { data, isPending, isError, refetch } = useQuery({ queryKey: key, queryFn: () => studentPortalApi.homeworkDetail(student.id, homeworkId) })
  const [text, setText] = useState<string | null>(null)
  const [link, setLink] = useState<string | null>(null)
  const [sent, setSent] = useState(false)
  const submit = useMutation({
    mutationFn: () => studentPortalApi.submitHomework(student.id, homeworkId, { text: (text ?? data?.submission?.text ?? '').trim(), link: (link ?? data?.submission?.link ?? '').trim() }),
    onSuccess: async (result) => {
      queryClient.setQueryData(key, result)
      setSent(true)
      await queryClient.invalidateQueries({ queryKey: PORTAL_KEY })
    },
  })

  if (isPending) return <Loading />
  if (isError || !data) return <LoadError onRetry={() => void refetch()} />
  const answer = text ?? data.submission?.text ?? ''
  const url = link ?? data.submission?.link ?? ''

  return (
    <div className="mx-auto max-w-3xl">
      <Link to="/student/homework" className="mb-3 inline-flex items-center gap-1 text-sm text-ink-secondary hover:text-ink"><ArrowLeft className="size-4" aria-hidden />{t('common.back')}</Link>
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-xl font-bold text-ink sm:text-2xl">{data.title}</h1>
          <p className="mt-1 text-sm text-ink-secondary">
            {[data.subject?.name, data.teacher?.name, t('hw.lesson', { date: date(data.lesson.date, true) })].filter(Boolean).join(' · ')}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <HomeworkBadge state={data.state} />
          <span className="text-xs text-ink-muted">{data.deadline ? t('hw.deadline', { date: date(data.deadline, true) }) : t('hw.noDeadline')}</span>
        </div>
      </div>
      <div className="space-y-4">
        <PCard title={t('hw.description')}>
          {data.description ? <p className="whitespace-pre-line text-sm leading-relaxed text-ink">{data.description}</p> : <p className="text-sm text-ink-muted">{t('hw.noDescription')}</p>}
          {data.lesson.topic ? <p className="mt-3 text-xs text-ink-muted">{data.lesson.topic}</p> : null}
        </PCard>
        {data.attachments.length ? (
          <PCard title={t('hw.attachments')}>
            <ul className="space-y-2">
              {data.attachments.map((item) => (
                <li key={item.url}>
                  <a href={item.url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-3 rounded-xl border border-border/70 p-3 text-sm hover:border-brand-200 hover:bg-brand-50/40">
                    {item.kind === 'video' ? <PlayCircle className="size-5 text-danger" aria-hidden /> : <FileText className="size-5 text-info" aria-hidden />}
                    <span className="flex-1 font-medium text-ink">{t(item.kind === 'video' ? 'hw.video' : 'hw.presentation')}</span>
                    <ExternalLink className="size-4 text-ink-muted" aria-hidden />
                  </a>
                </li>
              ))}
            </ul>
          </PCard>
        ) : null}
        {data.feedback || data.score !== null ? (
          <PCard title={t('hw.feedback')} className="border-brand-200 bg-brand-50/40">
            {data.score !== null ? <p className="mb-1 text-lg font-bold text-brand-700">{t('hw.score', { score: data.score })}</p> : null}
            {data.feedback ? <p className="text-sm text-ink">«{data.feedback}»</p> : null}
          </PCard>
        ) : null}
        <PCard title={t('hw.yourWork')}>
          {data.can_submit ? (
            <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); setSent(false); submit.mutate() }}>
              {data.state === 'overdue' ? <p className="rounded-lg bg-warning-soft px-3 py-2 text-sm text-warning">{t('hw.lateWarning')}</p> : null}
              <label className="block text-sm font-medium text-ink" htmlFor="hw-answer">{t('hw.answer')}</label>
              <textarea id="hw-answer" rows={5} maxLength={4000} value={answer} onChange={(e) => setText(e.target.value)} placeholder={t('hw.answerPlaceholder')}
                className="w-full rounded-xl border border-border bg-surface px-3 py-2 text-sm text-ink focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100" />
              <label className="block text-sm font-medium text-ink" htmlFor="hw-link">{t('hw.link')}</label>
              <input id="hw-link" type="url" maxLength={500} value={url} onChange={(e) => setLink(e.target.value)} placeholder={t('hw.linkPlaceholder')}
                className="h-10 w-full rounded-xl border border-border bg-surface px-3 text-sm text-ink focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100" />
              {submit.error ? <p className="text-sm text-danger">{extractErrorMessage(submit.error)}</p> : null}
              {sent ? <p className="text-sm font-medium text-brand-700">{t('hw.submitted')}</p> : null}
              <button type="submit" disabled={submit.isPending || (!answer.trim() && !url.trim())}
                className="inline-flex h-10 items-center gap-2 rounded-xl bg-brand-500 px-4 text-sm font-semibold text-white hover:bg-brand-600 disabled:opacity-50">
                <Send className="size-4" aria-hidden />{data.submission ? t('hw.resubmit') : t('hw.submit')}
              </button>
            </form>
          ) : (
            <div className="space-y-2 text-sm">
              {data.submission?.text ? <p className="whitespace-pre-line text-ink">{data.submission.text}</p> : null}
              {data.submission?.link ? <a href={data.submission.link} target="_blank" rel="noopener noreferrer" className="break-all text-brand-700 underline">{data.submission.link}</a> : null}
              <p className="text-ink-muted">{t('hw.locked')}</p>
            </div>
          )}
        </PCard>
      </div>
    </div>
  )
}
