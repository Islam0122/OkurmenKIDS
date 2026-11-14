import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight } from 'lucide-react'

import { studentPortalApi } from '@/api/studentPortal'
import { cn } from '@/utils/cn'
import type { PortalLesson } from '@/types/studentPortal'

import { PORTAL_KEY, usePortal } from '../context'
import { usePortalI18n } from '../i18n'
import { Empty, LessonRow, LoadError, Loading, PCard, PageTitle, isoDate } from '../ui'

type View = 'week' | 'month'

function mondayOf(d: Date) {
  const copy = new Date(d.getFullYear(), d.getMonth(), d.getDate())
  copy.setDate(copy.getDate() - ((copy.getDay() + 6) % 7))
  return copy
}

function addDays(d: Date, n: number) {
  const copy = new Date(d)
  copy.setDate(copy.getDate() + n)
  return copy
}

function range(view: View, anchor: Date): [Date, Date] {
  if (view === 'week') {
    const start = mondayOf(anchor)
    return [start, addDays(start, 6)]
  }
  // The month grid: Monday of the first week → Sunday of the last.
  const first = new Date(anchor.getFullYear(), anchor.getMonth(), 1)
  const last = new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0)
  return [mondayOf(first), addDays(mondayOf(last), 6)]
}

const DOT: Record<string, string> = {
  cancelled: 'bg-danger',
  completed: 'bg-ink-muted',
  scheduled: 'bg-brand-500',
  in_progress: 'bg-brand-500',
}

export function StudentSchedulePage() {
  const { student } = usePortal()
  const { t, month, weekday, date } = usePortalI18n()
  const [view, setView] = useState<View>('week')
  const [anchor, setAnchor] = useState(() => new Date())
  const [picked, setPicked] = useState<string | null>(null)
  const [start, end] = range(view, anchor)
  const startIso = isoDate(start)
  const endIso = isoDate(end)
  const todayIso = isoDate(new Date())

  const { data, isPending, isError, refetch } = useQuery({
    queryKey: [...PORTAL_KEY, 'schedule', student.id, startIso, endIso],
    queryFn: () => studentPortalApi.schedule(student.id, startIso, endIso),
  })
  const byDay = useMemo(() => {
    const map = new Map<string, PortalLesson[]>()
    for (const lesson of data?.lessons ?? []) map.set(lesson.date, [...(map.get(lesson.date) ?? []), lesson])
    return map
  }, [data])

  const shift = (direction: -1 | 1) => {
    setPicked(null)
    setAnchor((a) => (view === 'week' ? addDays(a, 7 * direction) : new Date(a.getFullYear(), a.getMonth() + direction, 1)))
  }
  const title = view === 'week'
    ? `${date(startIso)} – ${date(endIso, true)}`
    : `${month(anchor.getMonth() + 1)} ${anchor.getFullYear()}`
  const days = Array.from({ length: Math.round((end.getTime() - start.getTime()) / 86_400_000) + 1 }, (_, i) => addDays(start, i))

  return (
    <div>
      <PageTitle title={t('schedule.title')} subtitle={`${student.group?.name ?? ''}${student.branch ? ` · ${student.branch.name}` : ''}`} />
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="inline-flex rounded-xl bg-surface p-1 shadow-sm ring-1 ring-border/70" role="group">
          {(['week', 'month'] as View[]).map((v) => (
            <button key={v} type="button" onClick={() => { setView(v); setPicked(null) }} aria-pressed={view === v}
              className={cn('rounded-lg px-3.5 py-1.5 text-sm font-medium', view === v ? 'bg-brand-500 text-white' : 'text-ink-secondary hover:text-ink')}>
              {t(`schedule.${v}`)}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1">
          <button type="button" onClick={() => shift(-1)} aria-label={t('schedule.prev')} className="rounded-lg p-2 text-ink-secondary hover:bg-surface hover:text-ink"><ChevronLeft className="size-5" /></button>
          <span className="min-w-36 text-center text-sm font-semibold text-ink">{title}</span>
          <button type="button" onClick={() => shift(1)} aria-label={t('schedule.next')} className="rounded-lg p-2 text-ink-secondary hover:bg-surface hover:text-ink"><ChevronRight className="size-5" /></button>
          <button type="button" onClick={() => { setAnchor(new Date()); setPicked(null) }} className="ml-1 rounded-lg border border-brand-200 px-3 py-1.5 text-sm font-medium text-brand-700 hover:bg-brand-50">
            {t('schedule.current')}
          </button>
        </div>
      </div>

      {isPending ? <Loading /> : isError ? <LoadError onRetry={() => void refetch()} /> : view === 'week' ? (
        <div className="space-y-3">
          {data.lessons.length === 0 ? <Empty>{t('schedule.empty')}</Empty> : days.map((day, i) => {
            const iso = isoDate(day)
            const lessons = byDay.get(iso) ?? []
            if (!lessons.length) return null
            return (
              <PCard key={iso} title={
                <span className={cn(iso === todayIso && 'text-brand-700')}>
                  {weekday(i, true)}, {date(iso)}{iso === todayIso ? ` · ${t('common.today')}` : ''}
                </span>
              }>
                <div className="space-y-2">{lessons.map((l) => <LessonRow key={l.id} lesson={l} />)}</div>
              </PCard>
            )
          })}
        </div>
      ) : (
        <div className="grid gap-5 lg:grid-cols-[1fr_320px]">
          <PCard padded={false}>
            <div className="grid grid-cols-7 border-b border-border/70 px-2 pt-3 text-center text-xs font-medium text-ink-muted">
              {Array.from({ length: 7 }, (_, i) => <span key={i} className="pb-2">{weekday(i)}</span>)}
            </div>
            <div className="grid grid-cols-7 gap-1 p-2">
              {days.map((day) => {
                const iso = isoDate(day)
                const lessons = byDay.get(iso) ?? []
                const inMonth = day.getMonth() === anchor.getMonth()
                return (
                  <button key={iso} type="button" onClick={() => setPicked(iso)} aria-label={`${date(iso, true)}: ${lessons.length}`}
                    className={cn('flex min-h-14 flex-col items-center rounded-xl p-1.5 text-sm transition-colors sm:min-h-20 sm:items-start',
                      inMonth ? 'text-ink' : 'text-ink-muted/60', picked === iso ? 'bg-brand-50 ring-1 ring-brand-200' : 'hover:bg-surface-hover')}>
                    <span className={cn('flex size-7 items-center justify-center rounded-full tabular-nums', iso === todayIso && 'bg-brand-500 font-semibold text-white')}>{day.getDate()}</span>
                    <span className="mt-1 flex flex-wrap justify-center gap-1 sm:hidden">
                      {lessons.slice(0, 3).map((l) => <span key={l.id} className={cn('size-1.5 rounded-full', DOT[l.status])} />)}
                    </span>
                    <span className="mt-1 hidden w-full space-y-0.5 sm:block">
                      {lessons.slice(0, 2).map((l) => (
                        <span key={l.id} className={cn('block truncate rounded px-1 text-left text-[11px]',
                          l.status === 'cancelled' ? 'bg-danger-soft text-danger line-through' : 'bg-brand-50 text-brand-700')}>
                          {l.start} {l.subject?.name ?? ''}
                        </span>
                      ))}
                      {lessons.length > 2 ? <span className="block text-[11px] text-ink-muted">+{lessons.length - 2}</span> : null}
                    </span>
                  </button>
                )
              })}
            </div>
          </PCard>
          <PCard title={picked ? date(picked, true) : t('common.today')}>
            {(() => {
              const lessons = byDay.get(picked ?? todayIso) ?? []
              return lessons.length ? <div className="space-y-2">{lessons.map((l) => <LessonRow key={l.id} lesson={l} />)}</div> : <Empty>{t('schedule.empty')}</Empty>
            })()}
          </PCard>
        </div>
      )}
    </div>
  )
}
