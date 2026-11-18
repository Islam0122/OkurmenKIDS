import { Fragment } from 'react'
import { Check, Coffee, Sun } from 'lucide-react'

import { cn } from '@/utils/cn'
import type { PortalLesson } from '@/types/studentPortal'

import { usePortalI18n } from '../i18n'
import { Skeleton } from '../ui'
import { LessonCard } from './LessonCard'
import { SUBJECT_TONE, minutesOf, nowMinutes, subjectKind, uiStatus } from './model'

function NowLine({ now, next }: { now: Date; next: PortalLesson | null }) {
  const { t } = usePortalI18n()
  const time = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`
  const start = minutesOf(next?.start)
  const diff = start !== null ? start - nowMinutes(now) : null
  const left = diff !== null && diff > 0
    ? diff < 60 ? t('schedule.startsIn', { n: diff }) : t('schedule.startsInH', { h: Math.floor(diff / 60), m: diff % 60 })
    : null
  return (
    <li className="relative flex items-center gap-2 py-1 pl-8" aria-label={t('schedule.now', { time })}>
      <span className="absolute left-[7px] top-1/2 size-3 -translate-y-1/2 rounded-full border-2 border-white bg-danger shadow ring-2 ring-danger/25" aria-hidden />
      <span className="h-px flex-1 bg-danger/50" aria-hidden />
      <span className="shrink-0 rounded-full bg-danger px-2 py-0.5 text-[11px] font-bold tabular-nums text-white">{t('schedule.now', { time })}</span>
      {left ? <span className="shrink-0 text-[11px] font-semibold text-danger">{left}</span> : null}
    </li>
  )
}

/**
 * Today's lessons on a vertical timeline. Dots: filled check = held, pulsing
 * = going on now (the lesson's own status), hollow = still ahead. The red
 * «now» line sits between the lessons by the device clock, and only while
 * the school day is not over.
 */
export function TodayTimeline({ lessons, loading, now }: { lessons: PortalLesson[]; loading: boolean; now: Date }) {
  const { t, weekday, dayMonth } = usePortalI18n()
  const todayIso = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
  const nowMin = nowMinutes(now)
  const active = lessons.filter((l) => l.status !== 'cancelled')
  const lastEnd = Math.max(-1, ...active.map((l) => minutesOf(l.end) ?? minutesOf(l.start) ?? -1))
  const dayOver = active.length > 0 && nowMin >= lastEnd
  // The «now» line goes before the first lesson that has not started yet.
  const nowIndex = active.length && !dayOver
    ? (() => {
        const i = lessons.findIndex((l) => (minutesOf(l.start) ?? 0) > nowMin)
        return i === -1 ? lessons.length : i
      })()
    : -1
  const done = active.filter((l) => l.status === 'completed').length

  return (
    <section className="sp-card sp-rise overflow-hidden" aria-labelledby="sp-today-title">
      <header className="flex items-center justify-between gap-3 border-b border-border/60 bg-gradient-to-br from-brand-50/80 to-transparent px-5 py-4">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-brand-500 text-white shadow-sm shadow-brand-500/30"><Sun className="size-5" aria-hidden /></span>
          <div className="min-w-0">
            <h2 id="sp-today-title" className="text-[15px] font-bold tracking-tight text-ink">{t('schedule.today')}</h2>
            <p className="text-xs text-ink-secondary">{weekday((now.getDay() + 6) % 7, true)}, {dayMonth(todayIso)}</p>
          </div>
        </div>
        {active.length ? (
          <span className="shrink-0 rounded-full bg-surface px-2.5 py-1 text-xs font-bold tabular-nums text-brand-700 ring-1 ring-brand-200">
            {done}/{active.length}
          </span>
        ) : null}
      </header>

      <div className="p-4 sm:p-5">
        {loading ? (
          <div className="space-y-3" aria-hidden><Skeleton className="h-28" /><Skeleton className="h-28" /></div>
        ) : lessons.length === 0 ? (
          <div className="flex flex-col items-center px-4 py-8 text-center">
            <span className="mb-3 flex size-14 items-center justify-center rounded-2xl bg-brand-50 text-brand-600"><Coffee className="size-7" aria-hidden /></span>
            <p className="font-bold text-ink">{t('schedule.todayEmpty')}</p>
            <p className="mt-1 max-w-xs text-sm text-ink-secondary">{t('schedule.todayEmptyHint')}</p>
          </div>
        ) : (
          <>
            <ol className="relative space-y-3 before:absolute before:bottom-3 before:left-[12px] before:top-3 before:w-0.5 before:rounded-full before:bg-border" >
              {lessons.map((lesson, i) => {
                const status = uiStatus(lesson)
                const held = status === 'completed' || status === 'missed'
                const live = status === 'in_progress'
                const tone = SUBJECT_TONE[subjectKind(lesson)]
                return (
                  <Fragment key={lesson.id}>
                    {i === nowIndex ? <NowLine now={now} next={lesson} /> : null}
                    <li className={cn('relative pl-8', held && 'opacity-75 transition-opacity hover:opacity-100')}>
                      <span className={cn('absolute left-0 top-4 flex size-[26px] items-center justify-center rounded-full border-2 border-white shadow-sm',
                        status === 'cancelled' ? 'bg-border-strong' : held ? tone.bar : live ? 'bg-brand-500' : 'bg-surface ring-2 ring-inset ring-brand-200')} aria-hidden>
                        {held ? <Check className="size-3.5 text-white" strokeWidth={3} /> : null}
                        {live ? <span className="size-2.5 animate-pulse rounded-full bg-white motion-reduce:animate-none" /> : null}
                      </span>
                      <LessonCard lesson={lesson} compact />
                    </li>
                  </Fragment>
                )
              })}
              {nowIndex === lessons.length ? <NowLine now={now} next={null} /> : null}
            </ol>
            {dayOver ? (
              <p className="mt-4 flex items-center justify-center gap-1.5 rounded-xl bg-brand-50 px-3 py-2 text-xs font-semibold text-brand-700">
                <Check className="size-3.5" aria-hidden />{t('schedule.dayDone')}
              </p>
            ) : null}
          </>
        )}
      </div>
    </section>
  )
}
