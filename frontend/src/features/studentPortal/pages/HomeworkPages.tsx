import { useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { ArrowLeft, CalendarDays, ExternalLink, FileText, Info, MessageSquareQuote, PlayCircle } from 'lucide-react'
import { Link, useParams, useSearchParams } from 'react-router-dom'

import { studentPortalApi } from '@/api/studentPortal'
import type { HomeworkFilter } from '@/api/studentPortal'
import type { PortalHomeworkDetail } from '@/types/studentPortal'
import { cn } from '@/utils/cn'

import { LIVE_QUERY, PORTAL_KEY, usePortal } from '../context'
import { usePortalI18n } from '../i18n'
import { HomeworkMini } from './DashboardPage'
import { Empty, HomeworkBadge, LoadError, Loading, PCard, PageTitle } from '../ui'

/**
 * Homework in the Student & Parent Portal is READ-ONLY. The work is done
 * outside the LMS and checked offline by the trainer during the lesson; the
 * trainer records status, grade and comment in the existing grading form.
 * This page only shows what was saved there — no answer field, no link, no
 * «submit» — and refreshes itself so a newly saved result appears at once.
 *
 * The list shows only the homework of the NEXT scheduled lesson (decided by
 * the backend from the real schedule — portal.services.data.next_lessons);
 * everything already given is under «История».
 */

type View = 'next' | 'history'
type FilterTab = Extract<HomeworkFilter, 'not_submitted' | 'done' | 'checked' | 'all'>
const FILTERS: FilterTab[] = ['all', 'not_submitted', 'done', 'checked']

/** One homework of the next lesson, shown in full: no click needed to read it. */
function NextHomeworkCard({ hw }: { hw: PortalHomeworkDetail }) {
  const { t, date } = usePortalI18n()
  return (
    <article className="rounded-xl border border-border/70 p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <Link to={`/student/homework/${hw.id}`} className="min-w-0 text-base font-semibold text-ink hover:text-brand-700">{hw.title}</Link>
        <HomeworkBadge state={hw.state} />
      </div>
      {hw.description
        ? <p className="mt-2 whitespace-pre-line text-sm leading-relaxed text-ink">{hw.description}</p>
        : <p className="mt-2 text-sm text-ink-muted">{t('hw.noDescription')}</p>}
      <dl className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-ink-secondary">
        <div>{hw.deadline ? t('hw.deadline', { date: date(hw.deadline, true) }) : t('hw.noDeadline')}</div>
        <div>{t('hw.grade')}: {hw.score !== null ? <b className="text-brand-700">{hw.score}/10</b> : t('hw.notGraded')}</div>
      </dl>
      {hw.feedback ? <p className="mt-2 rounded-lg bg-brand-50/60 px-3 py-2 text-sm text-ink">«{hw.feedback}»</p> : null}
    </article>
  )
}

function NextLessonHomework() {
  const { student } = usePortal()
  const { t, date, weekday } = usePortalI18n()
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: [...PORTAL_KEY, 'homework-next', student.id],
    queryFn: () => studentPortalApi.nextHomework(student.id),
    ...LIVE_QUERY,
  })
  if (isPending) return <Loading />
  if (isError || !data) return <LoadError onRetry={() => void refetch()} />
  if (!data.lessons.length) return <Empty>{data.has_group ? t('hw.noNextLesson') : t('hw.noGroup')}</Empty>
  return (
    <div className="space-y-4">
      {data.lessons.map(({ lesson, homework }) => {
        const day = (new Date(`${lesson.date}T00:00:00`).getDay() + 6) % 7
        return (
          <PCard key={lesson.id} title={
            <span className="flex flex-wrap items-center gap-x-2">
              <CalendarDays className="size-4 text-brand-600" aria-hidden />
              {lesson.lesson_number ? t('hw.nextLesson', { n: lesson.lesson_number }) : t('hw.relatedLesson')}
              <span className="font-normal text-ink-secondary">
                · {weekday(day, true)}, {date(lesson.date, true)}{lesson.start ? ` · ${lesson.start}` : ''}{lesson.subject ? ` · ${lesson.subject.name}` : ''}
              </span>
            </span>
          }>
            {lesson.topic ? <p className="-mt-1 mb-3 text-sm text-ink-secondary">{lesson.topic}</p> : null}
            {homework.length
              ? <div className="space-y-3">{homework.map((hw) => <NextHomeworkCard key={hw.id} hw={hw} />)}</div>
              : <Empty>{t('hw.notAssigned')}</Empty>}
          </PCard>
        )
      })}
    </div>
  )
}

function HomeworkHistory() {
  const { student } = usePortal()
  const { t } = usePortalI18n()
  const [filter, setFilter] = useState<FilterTab>('all')
  const [page, setPage] = useState(1)
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: [...PORTAL_KEY, 'homework', student.id, filter, page],
    queryFn: () => studentPortalApi.homework(student.id, filter, page),
    placeholderData: keepPreviousData,
    ...LIVE_QUERY,
  })
  const label = (f: FilterTab) => (f === 'all' ? t('common.all') : t(`hw.filter.${f}`))
  return (
    <>
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
        <Empty>{filter === 'all' ? t('hw.historyEmpty') : t('hw.empty')}</Empty>
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
    </>
  )
}

export function StudentHomeworkPage() {
  const { t } = usePortalI18n()
  const [params, setParams] = useSearchParams()
  const view: View = params.get('view') === 'history' ? 'history' : 'next'
  return (
    <div>
      <PageTitle title={t('hw.title')} subtitle={view === 'next' ? t('hw.nextSubtitle') : t('hw.offline')} />
      <div className="mb-5 inline-flex rounded-xl bg-surface p-1 shadow-sm ring-1 ring-border/70" role="tablist">
        {(['next', 'history'] as View[]).map((v) => (
          <button key={v} type="button" role="tab" aria-selected={view === v}
            onClick={() => setParams(v === 'next' ? {} : { view: v }, { replace: true })}
            className={cn('rounded-lg px-4 py-1.5 text-sm font-medium', view === v ? 'bg-brand-500 text-white' : 'text-ink-secondary hover:text-ink')}>
            {t(`hw.tab.${v}`)}
          </button>
        ))}
      </div>
      {view === 'next' ? <NextLessonHomework /> : <HomeworkHistory />}
    </div>
  )
}

export function StudentHomeworkDetailPage() {
  const { id } = useParams()
  const homeworkId = Number(id)
  const { student } = usePortal()
  const { t, date } = usePortalI18n()
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: [...PORTAL_KEY, 'homework-detail', student.id, homeworkId],
    queryFn: () => studentPortalApi.homeworkDetail(student.id, homeworkId),
    ...LIVE_QUERY,
  })

  if (isPending) return <Loading />
  if (isError || !data) return <LoadError onRetry={() => void refetch()} />
  const evaluated = data.state !== 'awaiting'

  return (
    <div className="mx-auto max-w-3xl">
      <Link to="/student/homework" className="mb-3 inline-flex items-center gap-1 text-sm text-ink-secondary hover:text-ink"><ArrowLeft className="size-4" aria-hidden />{t('common.back')}</Link>
      <div className="mb-5">
        <h1 className="text-xl font-bold text-ink sm:text-2xl">{data.title}</h1>
        <p className="mt-1 text-sm text-ink-secondary">{[data.subject?.name, data.teacher?.name].filter(Boolean).join(' · ')}</p>
      </div>

      <div className="space-y-4">
        {/* Status · grade · dates — exactly what the trainer saved. */}
        <PCard>
          <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div>
              <dt className="text-xs text-ink-secondary">{t('hw.status')}</dt>
              <dd className="mt-1"><HomeworkBadge state={data.state} /></dd>
            </div>
            <div>
              <dt className="text-xs text-ink-secondary">{t('hw.grade')}</dt>
              <dd className="mt-0.5" data-testid="hw-grade">
                {data.score !== null
                  ? <span className="text-xl font-bold tabular-nums text-brand-700">{data.score}<span className="text-sm font-semibold text-ink-muted"> / 10</span></span>
                  : <span className="text-sm text-ink-muted">{t('hw.notGraded')}</span>}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-ink-secondary">{t('hw.assignedLabel')}</dt>
              <dd className="mt-0.5 text-sm font-medium text-ink">{date(data.assigned_date, true)}</dd>
            </div>
            <div>
              <dt className="text-xs text-ink-secondary">{t('hw.deadlineLabel')}</dt>
              <dd className="mt-0.5 text-sm font-medium text-ink">{data.deadline ? date(data.deadline, true) : t('hw.noDeadline')}</dd>
            </div>
          </dl>
          {evaluated && data.evaluated_at ? (
            <p className="mt-3 text-xs text-ink-muted">{t('hw.evaluated', { date: date(data.evaluated_at, true) })}</p>
          ) : (
            <p className="mt-3 flex items-start gap-2 rounded-lg bg-surface-muted px-3 py-2 text-xs text-ink-secondary">
              <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden />{t('hw.offline')}
            </p>
          )}
        </PCard>

        {data.feedback ? (
          <PCard title={<span className="inline-flex items-center gap-2"><MessageSquareQuote className="size-4 text-brand-600" aria-hidden />{t('hw.feedback')}</span>}
            className="border-brand-200 bg-brand-50/40">
            <p className="text-sm text-ink" data-testid="hw-feedback">«{data.feedback}»</p>
          </PCard>
        ) : null}

        <PCard title={t('hw.description')}>
          {data.description
            ? <p className="whitespace-pre-line text-sm leading-relaxed text-ink">{data.description}</p>
            : <p className="text-sm text-ink-muted">{t('hw.noDescription')}</p>}
        </PCard>

        <PCard title={t('hw.relatedLesson')}>
          <p className="flex items-center gap-2 text-sm font-medium text-ink">
            <CalendarDays className="size-4 text-brand-600" aria-hidden />
            {t('hw.lesson', { date: date(data.lesson.date, true) })}
            {data.lesson.lesson_number ? <span className="text-ink-muted">· №{data.lesson.lesson_number}</span> : null}
          </p>
          {data.lesson.topic ? <p className="mt-1 text-sm text-ink-secondary">{data.lesson.topic}</p> : null}
          {data.lesson.description ? <p className="mt-2 whitespace-pre-line text-sm text-ink-secondary">{data.lesson.description}</p> : null}
          {data.attachments.length ? (
            <>
              <h3 className="mb-2 mt-4 text-xs font-semibold uppercase tracking-wide text-ink-muted">{t('hw.attachments')}</h3>
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
            </>
          ) : null}
        </PCard>
      </div>
    </div>
  )
}
