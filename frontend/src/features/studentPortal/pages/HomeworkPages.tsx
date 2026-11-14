import { useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import {
  ArrowLeft, BookOpen, CalendarClock, CalendarDays, ExternalLink, FileText, Hash, Info, MessageSquareQuote, PlayCircle, Users,
} from 'lucide-react'
import { Link, useParams, useSearchParams } from 'react-router-dom'

import { studentPortalApi } from '@/api/studentPortal'
import type { HomeworkFilter } from '@/api/studentPortal'
import { cn } from '@/utils/cn'
import type { PortalHomeworkDetail, PortalLesson } from '@/types/studentPortal'

import { LIVE_QUERY, PORTAL_KEY, usePortal } from '../context'
import { usePortalI18n } from '../i18n'
import { HomeworkMini } from './DashboardPage'
import { Empty, HomeworkBadge, HW_STYLE, LoadError, Loading, PCard, PageTitle } from '../ui'

/**
 * Homework in the Student & Parent Portal is READ-ONLY. The work is done
 * outside the LMS and checked offline by the trainer during the lesson; the
 * trainer records status, grade and comment in the existing grading form.
 * This page only shows what was saved there — no answer field, no link, no
 * upload, no «submit» — and refreshes itself so a newly saved result appears.
 *
 * The main view shows only the homework of the NEXT scheduled lesson (decided
 * by the backend from the real schedule — portal.services.data.next_lessons);
 * everything already given is under «История».
 */

type View = 'next' | 'history'
type FilterTab = Extract<HomeworkFilter, 'not_submitted' | 'done' | 'checked' | 'all'>
const FILTERS: FilterTab[] = ['all', 'not_submitted', 'done', 'checked']

/** Grade tile: the trainer's grade, or an honest «not graded yet». */
function GradeTile({ score }: { score: number | null }) {
  const { t } = usePortalI18n()
  return (
    <div className={cn('flex min-w-[5.5rem] flex-col items-center justify-center rounded-2xl px-3 py-2.5 text-center',
      score !== null ? 'bg-brand-600 text-white' : 'bg-surface-muted text-ink-muted ring-1 ring-border/70')} data-testid="hw-grade">
      {score !== null ? (
        <>
          <span className="text-2xl font-extrabold leading-none tabular-nums">{score}<span className="text-sm font-bold text-white/75">/10</span></span>
          <span className="mt-1 text-[11px] font-semibold text-white/85">{t('hw.grade')}</span>
        </>
      ) : (
        <span className="text-xs font-semibold leading-snug">{t('hw.notGraded')}</span>
      )}
    </div>
  )
}

/** One homework of the next lesson, shown in full: no click needed to read it. */
function NextHomeworkCard({ hw }: { hw: PortalHomeworkDetail }) {
  const { t, date } = usePortalI18n()
  const style = HW_STYLE[hw.state]
  return (
    <article className="sp-card sp-card-hover sp-rise relative overflow-hidden">
      <span className={cn('absolute inset-x-0 top-0 h-1', style.dot)} aria-hidden />
      <div className="p-5 sm:p-6">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="mb-2 flex flex-wrap items-center gap-1.5 text-xs font-semibold">
              {hw.lesson.lesson_number ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-brand-50 px-2.5 py-1 text-brand-700"><Hash className="size-3" aria-hidden />{t('hw.lessonNo', { n: hw.lesson.lesson_number })}</span>
              ) : null}
              {hw.subject ? <span className="inline-flex items-center gap-1 rounded-full bg-surface-muted px-2.5 py-1 text-ink-secondary"><BookOpen className="size-3" aria-hidden />{hw.subject.name}</span> : null}
              {hw.group ? <span className="inline-flex items-center gap-1 rounded-full bg-surface-muted px-2.5 py-1 text-ink-secondary"><Users className="size-3" aria-hidden />{hw.group.name}</span> : null}
            </div>
            <Link to={`/student/homework/${hw.id}`} className="text-lg font-extrabold tracking-tight text-ink hover:text-brand-700 sm:text-xl">{hw.title}</Link>
          </div>
          <GradeTile score={hw.score} />
        </div>

        {hw.description
          ? <p className="mt-3 whitespace-pre-line text-[15px] leading-relaxed text-ink">{hw.description}</p>
          : <p className="mt-3 text-sm text-ink-muted">{t('hw.noDescription')}</p>}

        {hw.feedback ? (
          <div className="mt-4 flex gap-3 rounded-2xl bg-brand-50/70 p-3.5">
            <MessageSquareQuote className="mt-0.5 size-4 shrink-0 text-brand-600" aria-hidden />
            <div className="min-w-0">
              <p className="text-xs font-semibold text-brand-700">{t('hw.feedback')}</p>
              <p className="text-sm text-ink" data-testid="hw-feedback">«{hw.feedback}»</p>
            </div>
          </div>
        ) : null}

        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-border/60 pt-4">
          <span className="inline-flex items-center gap-1.5 text-sm font-medium text-ink-secondary">
            <CalendarClock className="size-4 text-brand-600" aria-hidden />
            {hw.deadline ? t('hw.deadline', { date: date(hw.deadline, true) }) : t('hw.noDeadline')}
            {hw.state === 'awaiting' && hw.days_left !== null && hw.days_left >= 0
              ? <span className="text-ink-muted">· {hw.days_left === 0 ? t('hw.dueToday') : t('hw.daysLeft', { n: hw.days_left })}</span> : null}
          </span>
          <HomeworkBadge state={hw.state} />
        </div>
      </div>
    </article>
  )
}

function LessonHeader({ lesson }: { lesson: PortalLesson }) {
  const { t, date, weekday } = usePortalI18n()
  const day = (new Date(`${lesson.date}T00:00:00`).getDay() + 6) % 7
  return (
    <div className="sp-rise mb-3 flex flex-wrap items-center gap-3">
      <span className="flex size-11 items-center justify-center rounded-2xl bg-brand-600 text-white shadow-sm"><CalendarDays className="size-5" aria-hidden /></span>
      <div className="min-w-0">
        <p className="text-base font-extrabold tracking-tight text-ink">
          {lesson.lesson_number ? t('hw.nextLesson', { n: lesson.lesson_number }) : t('hw.relatedLesson')}
          {lesson.topic ? <span className="font-semibold text-ink-secondary"> · {lesson.topic}</span> : null}
        </p>
        <p className="text-sm text-ink-secondary">
          {weekday(day, true)}, {date(lesson.date, true)}{lesson.start ? ` · ${lesson.start}` : ''}{lesson.subject ? ` · ${lesson.subject.name}` : ''}
        </p>
      </div>
    </div>
  )
}

function NextLessonHomework() {
  const { student } = usePortal()
  const { t } = usePortalI18n()
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: [...PORTAL_KEY, 'homework-next', student.id],
    queryFn: () => studentPortalApi.nextHomework(student.id),
    ...LIVE_QUERY,
  })
  if (isPending) return <Loading variant="list" />
  if (isError || !data) return <LoadError onRetry={() => void refetch()} />
  if (!data.lessons.length) {
    return (
      <div className="sp-card sp-rise">
        <Empty illustration title={t('hw.emptyNext')}>{data.has_group ? t('hw.noNextLesson') : t('hw.noGroup')}</Empty>
      </div>
    )
  }
  return (
    <div className="space-y-8">
      {data.lessons.map(({ lesson, homework }) => (
        <section key={lesson.id}>
          <LessonHeader lesson={lesson} />
          {homework.length ? (
            <div className="grid gap-4">{homework.map((hw) => <NextHomeworkCard key={hw.id} hw={hw} />)}</div>
          ) : (
            <div className="sp-card sp-rise">
              <Empty illustration title={t('hw.emptyNext')}>{t('hw.emptyNextHint')}</Empty>
            </div>
          )}
        </section>
      ))}
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
            className={cn('sp-press shrink-0 rounded-full px-4 py-2 text-sm font-semibold ring-1',
              filter === f ? 'bg-ink text-white ring-ink' : 'bg-surface text-ink-secondary ring-border hover:text-ink')}>
            {label(f)}
          </button>
        ))}
      </div>
      {isPending ? <Loading variant="list" /> : isError || !data ? <LoadError onRetry={() => void refetch()} /> : data.results.length === 0 ? (
        <div className="sp-card"><Empty illustration title={filter === 'all' ? t('hw.historyEmpty') : t('hw.empty')} /></div>
      ) : (
        <>
          <div className="grid gap-2.5 md:grid-cols-2">{data.results.map((hw) => <HomeworkMini key={hw.id} hw={hw} />)}</div>
          {data.next || data.previous ? (
            <div className="mt-5 flex items-center justify-center gap-2">
              <button type="button" disabled={!data.previous} onClick={() => setPage((p) => p - 1)} className="sp-press rounded-xl border border-border bg-surface px-4 py-2 text-sm font-semibold disabled:opacity-40" aria-label={t('schedule.prev')}>←</button>
              <span className="min-w-8 text-center text-sm font-semibold text-ink-secondary">{page}</span>
              <button type="button" disabled={!data.next} onClick={() => setPage((p) => p + 1)} className="sp-press rounded-xl border border-border bg-surface px-4 py-2 text-sm font-semibold disabled:opacity-40" aria-label={t('schedule.next')}>→</button>
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
      <div className="mb-6 inline-flex w-full rounded-2xl bg-surface p-1 shadow-sm ring-1 ring-border/70 sm:w-auto" role="tablist">
        {(['next', 'history'] as View[]).map((v) => (
          <button key={v} type="button" role="tab" aria-selected={view === v}
            onClick={() => setParams(v === 'next' ? {} : { view: v }, { replace: true })}
            className={cn('sp-press flex-1 rounded-xl px-5 py-2.5 text-sm font-bold sm:flex-none',
              view === v ? 'bg-brand-600 text-white shadow-sm' : 'text-ink-secondary hover:text-ink')}>
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

  if (isPending) return <Loading variant="list" />
  if (isError || !data) return <LoadError onRetry={() => void refetch()} />
  const evaluated = data.state !== 'awaiting'
  const style = HW_STYLE[data.state]

  return (
    <div className="mx-auto max-w-3xl">
      <Link to="/student/homework" className="sp-press mb-4 inline-flex items-center gap-1.5 rounded-xl px-2 py-1 text-sm font-semibold text-ink-secondary hover:bg-surface hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden />{t('common.back')}
      </Link>

      <article className="sp-card sp-rise relative overflow-hidden">
        <span className={cn('absolute inset-x-0 top-0 h-1.5', style.dot)} aria-hidden />
        <div className="p-5 sm:p-7">
          <div className="mb-2 flex flex-wrap gap-1.5 text-xs font-semibold">
            {data.lesson.lesson_number ? <span className="rounded-full bg-brand-50 px-2.5 py-1 text-brand-700">{t('hw.lessonNo', { n: data.lesson.lesson_number })}</span> : null}
            {data.subject ? <span className="rounded-full bg-surface-muted px-2.5 py-1 text-ink-secondary">{data.subject.name}</span> : null}
            {data.group ? <span className="rounded-full bg-surface-muted px-2.5 py-1 text-ink-secondary">{data.group.name}</span> : null}
          </div>
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <h1 className="text-2xl font-extrabold tracking-tight text-ink sm:text-[28px]">{data.title}</h1>
              {data.teacher ? <p className="mt-1 text-sm text-ink-secondary">{data.teacher.name}</p> : null}
            </div>
            <GradeTile score={data.score} />
          </div>

          <dl className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3">
            <div className="rounded-2xl bg-surface-muted p-3">
              <dt className="text-xs font-medium text-ink-secondary">{t('hw.status')}</dt>
              <dd className="mt-1.5"><HomeworkBadge state={data.state} /></dd>
            </div>
            <div className="rounded-2xl bg-surface-muted p-3">
              <dt className="text-xs font-medium text-ink-secondary">{t('hw.assignedLabel')}</dt>
              <dd className="mt-1 text-sm font-bold text-ink">{date(data.assigned_date, true)}</dd>
            </div>
            <div className="col-span-2 rounded-2xl bg-surface-muted p-3 sm:col-span-1">
              <dt className="text-xs font-medium text-ink-secondary">{t('hw.deadlineLabel')}</dt>
              <dd className="mt-1 text-sm font-bold text-ink">{data.deadline ? date(data.deadline, true) : t('hw.noDeadline')}</dd>
            </div>
          </dl>
          {evaluated && data.evaluated_at ? (
            <p className="mt-3 text-xs text-ink-muted">{t('hw.evaluated', { date: date(data.evaluated_at, true) })}</p>
          ) : (
            <p className="mt-4 flex items-start gap-2 rounded-2xl bg-info-soft/60 px-3.5 py-2.5 text-xs leading-relaxed text-info">
              <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden />{t('hw.offline')}
            </p>
          )}
        </div>
      </article>

      <div className="mt-4 space-y-4">
        {data.feedback ? (
          <PCard title={t('hw.feedback')} icon={<MessageSquareQuote className="size-4" aria-hidden />} className="border-brand-200 bg-brand-50/40">
            <p className="text-[15px] leading-relaxed text-ink" data-testid="hw-feedback">«{data.feedback}»</p>
          </PCard>
        ) : null}

        <PCard title={t('hw.description')} icon={<FileText className="size-4" aria-hidden />}>
          {data.description
            ? <p className="whitespace-pre-line text-[15px] leading-relaxed text-ink">{data.description}</p>
            : <p className="text-sm text-ink-muted">{t('hw.noDescription')}</p>}
        </PCard>

        <PCard title={t('hw.relatedLesson')} icon={<CalendarDays className="size-4" aria-hidden />}>
          <p className="text-sm font-bold text-ink">
            {t('hw.lesson', { date: date(data.lesson.date, true) })}
            {data.lesson.lesson_number ? <span className="font-medium text-ink-muted"> · №{data.lesson.lesson_number}</span> : null}
          </p>
          {data.lesson.topic ? <p className="mt-1 text-sm text-ink-secondary">{data.lesson.topic}</p> : null}
          {data.lesson.description ? <p className="mt-2 whitespace-pre-line text-sm text-ink-secondary">{data.lesson.description}</p> : null}
          {data.attachments.length ? (
            <>
              <h3 className="mb-2 mt-5 text-xs font-bold uppercase tracking-[0.08em] text-ink-muted">{t('hw.attachments')}</h3>
              <ul className="grid gap-2 sm:grid-cols-2">
                {data.attachments.map((item) => (
                  <li key={item.url}>
                    <a href={item.url} target="_blank" rel="noopener noreferrer"
                      className="sp-press flex items-center gap-3 rounded-2xl border border-border/70 p-3 text-sm hover:border-brand-200 hover:bg-brand-50/40">
                      <span className={cn('flex size-9 items-center justify-center rounded-xl', item.kind === 'video' ? 'bg-danger-soft text-danger' : 'bg-info-soft text-info')}>
                        {item.kind === 'video' ? <PlayCircle className="size-5" aria-hidden /> : <FileText className="size-5" aria-hidden />}
                      </span>
                      <span className="flex-1 font-semibold text-ink">{t(item.kind === 'video' ? 'hw.video' : 'hw.presentation')}</span>
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
