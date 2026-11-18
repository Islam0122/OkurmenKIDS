import { useMemo, useRef, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { AnimatePresence, MotionConfig, motion } from 'framer-motion'
import { ArrowRight, CalendarRange, RotateCcw } from 'lucide-react'

import { studentPortalApi } from '@/api/studentPortal'
import { cn } from '@/utils/cn'
import type { PortalLesson } from '@/types/studentPortal'

import { PORTAL_KEY, usePortal } from '../context'
import { usePortalI18n } from '../i18n'
import { LoadError, Skeleton, isoDate } from '../ui'
import { LessonCard } from '../schedule/LessonCard'
import {
  EmptyState, GHOST_BTN, MonthGrid, PRIMARY_BTN, ScheduleHeader, ScheduleToolbar, StatCards, StatCardsSkeleton, WeekStrip,
} from '../schedule/ScheduleParts'
import { TodayTimeline } from '../schedule/TodayTimeline'
import {
  addDays, byStart, daysBetween, groupByDay, minutesOf, mondayOf, nowMinutes, range, stats, useNow, type View,
} from '../schedule/model'

/**
 * «Моё расписание» (/student/schedule). One request per visible period —
 * GET /portal/students/:id/schedule/?start&end (apps.portal ScheduleView,
 * scoped to the family's own children by apps.portal.access) — plus the
 * current week for the header and «Сегодняшние занятия» (the same cached
 * query whenever the current week is on screen). Statistics are counted from
 * those lessons; nothing is invented.
 */

function scheduleQuery(studentId: number, start: Date, end: Date) {
  const startIso = isoDate(start)
  const endIso = isoDate(end)
  return {
    queryKey: [...PORTAL_KEY, 'schedule', studentId, startIso, endIso],
    queryFn: () => studentPortalApi.schedule(studentId, startIso, endIso),
  }
}

export function StudentSchedulePage() {
  const { student } = usePortal()
  const { t, month, weekday, dayMonth } = usePortalI18n()
  const now = useNow()
  const todayIso = isoDate(now)

  const [view, setView] = useState<View>('week')
  const [anchor, setAnchor] = useState(() => new Date())
  const [picked, setPicked] = useState<string | null>(null)
  const direction = useRef<1 | -1>(1)

  const [start, end] = range(view, anchor)
  const startIso = isoDate(start)
  const endIso = isoDate(end)
  const [weekStart, weekEnd] = range('week', now)

  const period = useQuery({ ...scheduleQuery(student.id, start, end), placeholderData: keepPreviousData })
  const week = useQuery(scheduleQuery(student.id, weekStart, weekEnd))

  const lessons = useMemo(() => period.data?.lessons ?? [], [period.data])
  const byDay = useMemo(() => groupByDay(lessons), [lessons])
  const inPeriod = useMemo(
    () => (view === 'month' ? lessons.filter((l) => Number(l.date.slice(5, 7)) === anchor.getMonth() + 1) : lessons),
    [lessons, view, anchor],
  )
  const periodStats = useMemo(() => stats(inPeriod), [inPeriod])

  const weekLessons = useMemo(() => [...(week.data?.lessons ?? [])].sort(byStart), [week.data])
  const weekStats = useMemo(() => (week.data ? stats(weekLessons) : null), [week.data, weekLessons])
  const todayLessons = weekLessons.filter((l) => l.date === todayIso)
  const live = todayLessons.find((l) => l.status === 'in_progress') ?? null
  const next = weekLessons.find((l) => l.status === 'scheduled'
    && (l.date > todayIso || (l.date === todayIso && (minutesOf(l.start) ?? 0) > nowMinutes(now)))) ?? null

  const isCurrent = view === 'week'
    ? startIso === isoDate(mondayOf(now))
    : anchor.getFullYear() === now.getFullYear() && anchor.getMonth() === now.getMonth()

  const changeView = (v: View) => {
    if (v === view) return
    setView(v)
    setPicked(null)
  }
  const shift = (d: -1 | 1) => {
    direction.current = d
    setPicked(null)
    setAnchor((a) => (view === 'week' ? addDays(a, 7 * d) : new Date(a.getFullYear(), a.getMonth() + d, 1)))
  }
  const goToday = () => {
    direction.current = anchor < now ? 1 : -1
    setAnchor(new Date())
    setPicked(view === 'month' ? todayIso : null)
  }

  const sameMonth = startIso.slice(0, 7) === endIso.slice(0, 7)
  const title = view === 'week'
    ? `${sameMonth ? Number(startIso.slice(8)) : dayMonth(startIso)} – ${dayMonth(endIso)}`
    : `${month(anchor.getMonth() + 1)} ${anchor.getFullYear()}`
  const periodHint = view === 'week'
    ? t(isCurrent ? 'schedule.hint.week' : 'schedule.hint.otherWeek')
    : t('schedule.hint.month', { month: month(anchor.getMonth() + 1).toLowerCase() })
  const days = daysBetween(start, end)

  /** The nearest day of the period with lessons, looking forward from `from` first. */
  const nearest = (from: string) => {
    const withLessons = days.map(isoDate).filter((iso) => (byDay.get(iso)?.length ?? 0) > 0)
    return withLessons.find((iso) => iso > from) ?? [...withLessons].reverse().find((iso) => iso < from) ?? null
  }

  const groupLine = [student.group?.name, student.course?.name, student.branch?.name].filter(Boolean).join(' · ')
  const contentKey = `${view}:${period.data?.start ?? startIso}`

  const periodEmpty = (
    <EmptyState illustration
      title={view === 'week' ? t('schedule.weekEmpty') : t('schedule.monthEmpty')}
      hint={t('schedule.periodEmptyHint')}
      actions={(
        <>
          <button type="button" onClick={() => shift(1)} className={PRIMARY_BTN}>
            {view === 'week' ? t('schedule.nextWeek') : t('schedule.nextMonth')}<ArrowRight className="size-4" aria-hidden />
          </button>
          {!isCurrent ? <button type="button" onClick={goToday} className={GHOST_BTN}><RotateCcw className="size-4" aria-hidden />{t('schedule.current')}</button> : null}
        </>
      )} />
  )

  const dayEmpty = (iso: string, onShowAll?: () => void) => {
    const target = nearest(iso)
    return (
      <EmptyState title={t('schedule.dayEmpty')} hint={t('schedule.dayEmptyHint')}
        actions={(
          <>
            {target ? (
              <button type="button" onClick={() => setPicked(target)} className={PRIMARY_BTN}>
                {t('schedule.goNearest')}<ArrowRight className="size-4" aria-hidden />
              </button>
            ) : null}
            {onShowAll ? <button type="button" onClick={onShowAll} className={GHOST_BTN}><CalendarRange className="size-4" aria-hidden />{t('schedule.showWeek')}</button> : null}
          </>
        )} />
    )
  }

  const dayHeading = (iso: string, count: number) => {
    const d = (new Date(`${iso}T00:00:00`).getDay() + 6) % 7
    const today = iso === todayIso
    return (
      <h3 className="mb-2.5 flex items-center gap-2 px-1 text-sm font-bold text-ink">
        <span className={cn(today && 'text-brand-700')}>{weekday(d, true)}</span>
        <span className="font-semibold text-ink-muted">{dayMonth(iso)}</span>
        {today ? <span className="rounded-full bg-brand-500 px-2 py-0.5 text-[11px] font-bold text-white">{t('common.today')}</span> : null}
        <span className="ml-auto shrink-0 text-xs font-semibold text-ink-muted">{t('common.lessonsCount', { n: count })}</span>
      </h3>
    )
  }

  const renderList = (list: PortalLesson[]) => (
    <div className="grid gap-3 xl:grid-cols-2">
      {list.map((l, i) => (
        <motion.div key={l.id} className="min-w-0" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25, delay: Math.min(i, 6) * 0.03 }}>
          <LessonCard lesson={l} />
        </motion.div>
      ))}
    </div>
  )

  const weekContent = () => {
    if (lessons.length === 0) return periodEmpty
    if (picked) {
      const list = byDay.get(picked) ?? []
      return list.length ? <div>{dayHeading(picked, list.length)}{renderList(list)}</div> : dayEmpty(picked, () => setPicked(null))
    }
    return (
      <div className="space-y-6">
        {days.map((day) => {
          const iso = isoDate(day)
          const list = byDay.get(iso) ?? []
          return list.length ? <section key={iso}>{dayHeading(iso, list.length)}{renderList(list)}</section> : null
        })}
      </div>
    )
  }

  const anchorMonth = anchor.getMonth() + 1
  const monthPicked = picked
    ?? (Number(todayIso.slice(5, 7)) === anchorMonth && Number(todayIso.slice(0, 4)) === anchor.getFullYear() ? todayIso : null)
    ?? days.map(isoDate).find((iso) => Number(iso.slice(5, 7)) === anchorMonth && byDay.has(iso))
    ?? isoDate(new Date(anchor.getFullYear(), anchor.getMonth(), 1))

  const monthContent = () => {
    const list = byDay.get(monthPicked) ?? []
    return (
      <div className="space-y-5">
        <MonthGrid days={days} byDay={byDay} picked={monthPicked} onPick={setPicked} todayIso={todayIso} month={anchor.getMonth()} />
        {inPeriod.length === 0 ? periodEmpty : list.length ? (
          <div>{dayHeading(monthPicked, list.length)}{renderList(list)}</div>
        ) : dayEmpty(monthPicked)}
      </div>
    )
  }

  return (
    <MotionConfig reducedMotion="user">
      <ScheduleHeader now={now} week={weekStats} next={next} live={live} loading={week.isPending} groupLine={groupLine} />

      {period.isPending ? <StatCardsSkeleton /> : period.isError ? null : <StatCards stats={periodStats} periodHint={periodHint} />}

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_340px] xl:grid-cols-[minmax(0,1fr)_380px]">
        <aside className="min-w-0 lg:order-last">
          <div className="lg:sticky lg:top-6">
            {week.isError ? <LoadError onRetry={() => void week.refetch()} /> : (
              <TodayTimeline lessons={todayLessons} loading={week.isPending} now={now} />
            )}
          </div>
        </aside>

        <div className="min-w-0">
          <ScheduleToolbar view={view} onView={changeView} title={title} onShift={shift} onToday={goToday} isCurrent={isCurrent} />
          {view === 'week' && !period.isError ? (
            <WeekStrip days={days} byDay={byDay} picked={picked} onPick={setPicked} todayIso={todayIso} />
          ) : null}

          {period.isPending ? (
            <div className="space-y-3" role="status" aria-label={t('common.loading')}>
              <span className="sr-only">{t('common.loading')}</span>
              <Skeleton className="h-5 w-48" />
              <div className="grid gap-3 xl:grid-cols-2"><Skeleton className="h-44 rounded-[18px]" /><Skeleton className="h-44 rounded-[18px]" /></div>
              <Skeleton className="mt-4 h-5 w-40" />
              <Skeleton className="h-44 rounded-[18px]" />
            </div>
          ) : period.isError ? <LoadError onRetry={() => void period.refetch()} /> : (
            <div className={cn('overflow-x-clip transition-opacity duration-200', period.isPlaceholderData && 'pointer-events-none opacity-60')} aria-busy={period.isPlaceholderData}>
              <AnimatePresence mode="wait" initial={false} custom={direction.current}>
                <motion.div key={contentKey} custom={direction.current}
                  variants={{
                    enter: (d: number) => ({ opacity: 0, x: 24 * d }),
                    center: { opacity: 1, x: 0 },
                    exit: (d: number) => ({ opacity: 0, x: -24 * d }),
                  }}
                  initial="enter" animate="center" exit="exit" transition={{ duration: 0.22, ease: [0.2, 0.7, 0.2, 1] }}>
                  {view === 'week' ? weekContent() : monthContent()}
                </motion.div>
              </AnimatePresence>
            </div>
          )}
        </div>
      </div>
    </MotionConfig>
  )
}
