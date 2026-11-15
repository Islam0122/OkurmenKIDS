import { useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import { keepPreviousData, useInfiniteQuery, useQuery } from '@tanstack/react-query'
import {
  BarChart3, CalendarCheck2, CalendarClock, CalendarDays, CalendarX, CheckCircle2, ChevronLeft, ChevronRight, CircleDashed,
  Clock, Flame, History, Info, MapPin, ShieldCheck, User, X, XCircle,
} from 'lucide-react'

import { studentPortalApi } from '@/api/studentPortal'
import { cn } from '@/utils/cn'
import type { AttendanceHistoryRow, AttendanceMark, AttendanceOverview, CalendarLesson, LessonState } from '@/types/studentPortal'

import { LIVE_QUERY, PORTAL_KEY, usePortal } from '../context'
import { usePortalI18n } from '../i18n'
import { Empty, LoadError, PageTitle, PCard, ProgressRing, Skeleton, isoDate } from '../ui'

/**
 * «Катышуу» — read-only attendance dashboard (backend:
 * portal.services.attendance). Every number is the trainer's own marks, by the
 * KPI's rules — attended = present + late, missed = absent + excused, percent
 * over marked lessons; an unmarked lesson is not a miss and cancelled lessons
 * count for nothing. The rules are shown on the page.
 */

/** Status colours as specified: present green, absent red, late orange, excused blue, future/none gray. */
export const STATE_STYLE: Record<LessonState, { dot: string; soft: string; text: string; icon: typeof CheckCircle2 }> = {
  present: { dot: 'bg-[#2f8f5b]', soft: 'bg-brand-50', text: 'text-brand-700', icon: CheckCircle2 },
  absent: { dot: 'bg-[#c7402e]', soft: 'bg-danger-soft', text: 'text-danger', icon: XCircle },
  late: { dot: 'bg-[#d97706]', soft: 'bg-[#fdf0dc]', text: 'text-[#9a5800]', icon: Clock },
  excused: { dot: 'bg-[#2563a8]', soft: 'bg-info-soft', text: 'text-info', icon: ShieldCheck },
  unmarked: { dot: 'bg-[#b8c2bc]', soft: 'bg-surface-muted', text: 'text-ink-secondary', icon: CircleDashed },
  future: { dot: 'bg-[#d5ddd8]', soft: 'bg-surface-muted', text: 'text-ink-muted', icon: CalendarClock },
  cancelled: { dot: 'bg-[#d5ddd8]', soft: 'bg-surface-muted', text: 'text-ink-muted line-through', icon: CalendarX },
}
const LEGEND: LessonState[] = ['present', 'late', 'absent', 'excused', 'unmarked', 'future']
const FILTERS: ('all' | AttendanceMark)[] = ['all', 'present', 'absent', 'late', 'excused']

export function MonthSwitcher({ year, month, onChange, allowFuture = false }: {
  year: number; month: number; onChange: (y: number, m: number) => void; allowFuture?: boolean
}) {
  const { t, month: monthName } = usePortalI18n()
  const now = new Date()
  const isCurrent = year === now.getFullYear() && month === now.getMonth() + 1
  const ahead = (year * 12 + month) - (now.getFullYear() * 12 + now.getMonth() + 1)
  const go = (delta: number) => {
    const index = year * 12 + (month - 1) + delta
    onChange(Math.floor(index / 12), (index % 12) + 1)
  }
  return (
    <div className="flex items-center gap-1 rounded-xl bg-surface p-1 shadow-sm ring-1 ring-border/70">
      <button type="button" onClick={() => go(-1)} aria-label={t('atd.prev')} className="sp-press rounded-lg p-1.5 text-ink-secondary hover:bg-surface-hover"><ChevronLeft className="size-5" /></button>
      <span className="min-w-32 text-center text-sm font-bold text-ink">
        {monthName(month)} {year}
        {isCurrent ? <span className="ml-1.5 inline-block size-1.5 -translate-y-0.5 rounded-full bg-brand-500 align-middle" aria-label={t('atd.thisMonth')} /> : null}
      </span>
      <button type="button" onClick={() => go(1)} disabled={allowFuture ? ahead >= 1 : isCurrent} aria-label={t('atd.next')}
        className="sp-press rounded-lg p-1.5 text-ink-secondary hover:bg-surface-hover disabled:opacity-30"><ChevronRight className="size-5" /></button>
    </div>
  )
}

function StateBadge({ state }: { state: LessonState }) {
  const { t } = usePortalI18n()
  const s = STATE_STYLE[state]
  return (
    <span className={cn('inline-flex items-center gap-1.5 whitespace-nowrap rounded-full py-1 pl-2 pr-2.5 text-xs font-bold', s.soft, s.text.replace('line-through', ''))}>
      <s.icon className="size-3.5" aria-hidden />{t(`atd.state.${state}`)}
    </span>
  )
}

const pct = (v: number | null) => (v === null ? '—' : `${Math.round(v)}%`)
const dow = (iso: string) => (new Date(`${iso}T00:00:00`).getDay() + 6) % 7

// ---------------------------------------------------------------------------
// Overview
// ---------------------------------------------------------------------------

function Overview({ data }: { data: AttendanceOverview }) {
  const { t, date } = usePortalI18n()
  const s = data.summary
  const cards = [
    { key: 'held', label: t('atd.held'), value: s.held, icon: CalendarDays, tone: 'bg-surface-muted text-ink-secondary' },
    { key: 'attended', label: t('atd.attended'), value: s.attended, icon: CheckCircle2, tone: 'bg-brand-50 text-brand-700' },
    { key: 'absent', label: t('atd.absent'), value: s.absent, icon: XCircle, tone: 'bg-danger-soft text-danger' },
    { key: 'late', label: t('atd.late'), value: s.late, icon: Clock, tone: 'bg-[#fdf0dc] text-[#9a5800]' },
    { key: 'excused', label: t('atd.excused'), value: s.excused, icon: ShieldCheck, tone: 'bg-info-soft text-info' },
  ]
  return (
    <section className="sp-card sp-rise p-5 sm:p-7">
      <div className="flex flex-col gap-6">
        <div className="flex items-center gap-5">
          <ProgressRing value={s.percent} size={128} stroke={12} label={t('atd.overall')} />
          <div className="min-w-0">
            <p className="text-xs font-bold uppercase tracking-[0.1em] text-brand-600">{t('atd.overall')}</p>
            <p className="text-sm font-semibold text-ink">{t('atd.ofMarked', { a: s.attended, m: s.marked })}</p>
            <p className="text-xs text-ink-muted">{t('atd.since', { date: date(data.since, true) })}</p>
            {s.unmarked ? <p className="mt-1 text-xs text-ink-muted">{t('atd.unmarked', { n: s.unmarked })}</p> : null}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-5 sm:gap-3">
          {cards.map(({ key, label, value, icon: Icon, tone }, i) => (
            <div key={key} className="sp-rise rounded-2xl bg-surface-muted/70 p-3 ring-1 ring-border/50" style={{ animationDelay: `${i * 40}ms` }}>
              <p className="flex items-center gap-1.5 text-[11px] font-semibold leading-tight text-ink-secondary sm:text-xs">
                <span className={cn('flex size-6 shrink-0 items-center justify-center rounded-lg', tone)}><Icon className="size-3.5" aria-hidden /></span>
                {label}
              </p>
              <p className="mt-1.5 text-2xl font-extrabold tabular-nums tracking-tight text-ink">{value}</p>
            </div>
          ))}
        </div>
      </div>
      <p className="mt-5 flex items-start gap-2 rounded-2xl bg-surface-muted px-3.5 py-2.5 text-xs leading-relaxed text-ink-secondary">
        <Info className="mt-0.5 size-3.5 shrink-0 text-brand-600" aria-hidden />{t('atd.rules')}
      </p>
    </section>
  )
}

function StreakCard({ data }: { data: AttendanceOverview }) {
  const { t } = usePortalI18n()
  const { current, best } = data.streak
  return (
    <PCard title={t('atd.streak')} icon={<Flame className="size-4" aria-hidden />}>
      <div className="flex items-center gap-4">
        <span className={cn('flex size-14 items-center justify-center rounded-2xl', current ? 'bg-gradient-to-br from-[#f6c453] to-[#d97706] text-white shadow-sm' : 'bg-surface-muted text-ink-muted')}>
          <Flame className="size-7" aria-hidden />
        </span>
        <div>
          <p className="text-3xl font-extrabold tabular-nums tracking-tight text-ink">{current ? t('atd.streakDays', { n: current }) : '0'}</p>
          <p className="text-xs font-semibold text-ink-muted">{current ? t('atd.bestStreak', { n: best }) : t('atd.streakNone')}</p>
        </div>
      </div>
    </PCard>
  )
}

// ---------------------------------------------------------------------------
// Calendar
// ---------------------------------------------------------------------------

function DayDetails({ day, lessons }: { day: string | null; lessons: CalendarLesson[] }) {
  const { t, date, weekday } = usePortalI18n()
  if (!day) return <Empty>{t('atd.pickDay')}</Empty>
  return (
    <div>
      <p className="mb-3 text-sm font-extrabold text-ink">{weekday(dow(day), true)}, {date(day, true)}
        <span className="ml-2 text-xs font-semibold text-ink-muted">{lessons.length ? t('atd.lessonsOnDay', { n: lessons.length }) : ''}</span>
      </p>
      {lessons.length ? (
        <ul className="space-y-2.5">
          {lessons.map((l) => (
            <li key={l.id} className={cn('rounded-2xl border border-border/70 p-3.5', STATE_STYLE[l.state].soft)}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className={cn('font-bold text-ink', l.state === 'cancelled' && 'line-through')}>{l.subject?.name ?? l.course?.name ?? '—'}</p>
                  <p className="text-xs text-ink-secondary">{l.start}–{l.end}{l.lesson_number ? ` · ${t('lesson.number', { n: l.lesson_number })}` : ''}</p>
                </div>
                <StateBadge state={l.state} />
              </div>
              {l.topic ? <p className="mt-1.5 text-sm text-ink">{l.topic}</p> : null}
              <p className="mt-1.5 flex flex-wrap gap-x-3 text-xs text-ink-muted">
                {l.teacher ? <span className="inline-flex items-center gap-1"><User className="size-3" aria-hidden />{l.teacher.name}</span> : null}
                {l.room || l.branch ? <span className="inline-flex items-center gap-1"><MapPin className="size-3" aria-hidden />{[l.branch?.name, l.room?.name].filter(Boolean).join(' · ')}</span> : null}
              </p>
              {l.excuse_reason ? <p className="mt-1 text-xs text-info">{t('atd.reason', { r: l.excuse_reason })}</p> : null}
              {l.comment ? <p className="mt-1 text-xs text-ink-secondary">{t('atd.comment', { c: l.comment })}</p> : null}
              {l.state === 'cancelled' && l.cancellation_reason ? <p className="mt-1 text-xs text-ink-muted">{l.cancellation_reason}</p> : null}
            </li>
          ))}
        </ul>
      ) : <Empty>{t('atd.noLessonsDay')}</Empty>}
    </div>
  )
}

function CalendarCard() {
  const { student } = usePortal()
  const { t, weekday } = usePortalI18n()
  const now = new Date()
  const [[year, month], setMonth] = useState<[number, number]>([now.getFullYear(), now.getMonth() + 1])
  const [picked, setPicked] = useState<string | null>(null)
  const [sheet, setSheet] = useState(false)
  const todayIso = isoDate(now)
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: [...PORTAL_KEY, 'attendance', student.id, year, month],
    queryFn: () => studentPortalApi.attendance(student.id, year, month),
    placeholderData: keepPreviousData,
    ...LIVE_QUERY,
  })
  const byDay = useMemo(() => {
    const map = new Map<string, CalendarLesson[]>()
    for (const l of data?.lessons ?? []) map.set(l.date, [...(map.get(l.date) ?? []), l])
    return map
  }, [data])
  // Default selection: today in the current month, else the latest day with lessons.
  useEffect(() => {
    if (!data) return
    const days = [...byDay.keys()].sort()
    setPicked(byDay.has(todayIso) ? todayIso : days.filter((d) => d <= todayIso).pop() ?? days[0] ?? null)
  }, [data, byDay, todayIso])

  const first = new Date(year, month - 1, 1)
  const lead = (first.getDay() + 6) % 7
  const daysInMonth = new Date(year, month, 0).getDate()
  const cells: (string | null)[] = [
    ...Array.from({ length: lead }, () => null),
    ...Array.from({ length: daysInMonth }, (_, i) => isoDate(new Date(year, month - 1, i + 1))),
  ]
  const choose = (iso: string) => { setPicked(iso); setSheet(true) }

  return (
    <PCard title={t('atd.calendar')} icon={<CalendarCheck2 className="size-4" aria-hidden />}>
      <div className="mb-4 flex justify-start sm:-mt-1"><MonthSwitcher year={year} month={month} onChange={(y, m) => setMonth([y, m])} allowFuture /></div>
      {isPending ? <Skeleton className="h-80" /> : isError || !data ? <LoadError onRetry={() => void refetch()} /> : (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_18rem]">
          <div>
            <p className="mb-2 text-xs font-semibold text-ink-secondary">{t('atd.monthSummary', { a: data.summary.attended, m: data.summary.marked })}</p>
            <div className="grid grid-cols-7 gap-1 text-center text-[11px] font-bold uppercase text-ink-muted">
              {Array.from({ length: 7 }, (_, i) => <span key={i} className="py-1">{weekday(i)}</span>)}
            </div>
            <div className="grid grid-cols-7 gap-1">
              {cells.map((iso, i) => {
                if (!iso) return <span key={`e${i}`} />
                const lessons = byDay.get(iso) ?? []
                const primary = lessons.find((l) => l.state !== 'cancelled') ?? lessons[0]
                const isToday = iso === todayIso
                return (
                  <button key={iso} type="button" onClick={() => choose(iso)} aria-pressed={picked === iso}
                    aria-label={`${iso}: ${lessons.map((l) => t(`atd.state.${l.state}`)).join(', ') || t('atd.noLessonsDay')}`}
                    className={cn('sp-press relative flex aspect-square flex-col items-center justify-center gap-1 rounded-xl text-sm font-semibold transition-colors sm:aspect-auto sm:min-h-16',
                      primary ? STATE_STYLE[primary.state].soft : 'hover:bg-surface-hover',
                      picked === iso && 'ring-2 ring-brand-500 ring-offset-1',
                      isToday && 'font-extrabold')}>
                    <span className={cn('flex size-7 items-center justify-center rounded-full tabular-nums',
                      isToday ? 'bg-ink text-white' : primary ? STATE_STYLE[primary.state].text.replace('line-through', '') : 'text-ink-secondary')}>
                      {Number(iso.slice(8))}
                    </span>
                    {lessons.length ? (
                      <span className="flex gap-0.5" aria-hidden>
                        {lessons.slice(0, 4).map((l) => <span key={l.id} className={cn('size-1.5 rounded-full', STATE_STYLE[l.state].dot)} />)}
                      </span>
                    ) : null}
                  </button>
                )
              })}
            </div>
            <ul className="mt-4 flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-ink-secondary" aria-label={t('atd.legend')}>
              {LEGEND.map((state) => (
                <li key={state} className="inline-flex items-center gap-1.5"><span className={cn('size-2.5 rounded-full', STATE_STYLE[state].dot)} />{t(`atd.state.${state}`)}</li>
              ))}
            </ul>
          </div>
          {/* Desktop: details beside the calendar. */}
          <aside className="hidden lg:block"><DayDetails day={picked} lessons={picked ? byDay.get(picked) ?? [] : []} /></aside>
        </div>
      )}
      {/* Phone / tablet: details in a bottom sheet. */}
      {sheet && picked ? createPortal(
        <div className="sp-root fixed inset-0 z-[60] flex items-end lg:hidden" role="dialog" aria-modal="true" aria-label={picked}>
          <button type="button" className="absolute inset-0 bg-ink/35" aria-label={t('atd.close')} onClick={() => setSheet(false)} />
          <div className="sp-sheet relative max-h-[80dvh] w-full overflow-y-auto rounded-t-3xl bg-surface p-5 pb-[calc(env(safe-area-inset-bottom)+1.25rem)] shadow-2xl">
            <div className="mb-3 flex items-center justify-between">
              <span className="h-1.5 w-10 rounded-full bg-border" aria-hidden />
              <button type="button" onClick={() => setSheet(false)} className="sp-press rounded-lg p-1.5 text-ink-secondary" aria-label={t('atd.close')}><X className="size-5" /></button>
            </div>
            <DayDetails day={picked} lessons={byDay.get(picked) ?? []} />
          </div>
        </div>,
        document.body,
      ) : null}
    </PCard>
  )
}

// ---------------------------------------------------------------------------
// Analytics — single-series charts (one colour, no legend; titles name them)
// ---------------------------------------------------------------------------

function PercentColumns({ points }: { points: { key: string; label: string; percent: number | null; detail: string }[] }) {
  const { t } = usePortalI18n()
  const [hover, setHover] = useState<number | null>(null)
  return (
    <div className="flex h-40 items-end gap-2" role="img" aria-label={points.map((p) => `${p.label}: ${pct(p.percent)}`).join(', ')}>
      {points.map((p, i) => (
        <div key={p.key} className="relative flex h-full flex-1 flex-col items-center justify-end gap-1"
          onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
          <span className="text-[11px] font-bold tabular-nums text-ink">{p.percent === null ? '' : pct(p.percent)}</span>
          <div className="flex min-h-0 w-full flex-1 items-end justify-center">
            {p.percent === null
              ? <span className="h-1 w-full max-w-7 rounded-full bg-border" title={t('atd.noData')} />
              : <span className="w-full max-w-7 rounded-t-[4px] bg-brand-500 motion-safe:transition-[height] motion-safe:duration-700" style={{ height: `${Math.max(p.percent, 2)}%`, opacity: i === points.length - 1 ? 1 : 0.6 }} />}
          </div>
          <span className="text-[11px] font-semibold text-ink-muted">{p.label}</span>
          {hover === i ? (
            <span className="pointer-events-none absolute bottom-full z-10 mb-1 whitespace-nowrap rounded-lg bg-ink px-2 py-1 text-[11px] font-semibold text-white">{p.detail}</span>
          ) : null}
        </div>
      ))}
    </div>
  )
}

function Analytics({ data }: { data: AttendanceOverview }) {
  const { t, month, date } = usePortalI18n()
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <PCard title={t('atd.trend')} icon={<BarChart3 className="size-4" aria-hidden />}>
        <PercentColumns points={data.months.map((m) => ({
          key: `${m.year}-${m.month}`, label: month(m.month).slice(0, 3), percent: m.percent,
          detail: m.marked ? `${month(m.month)}: ${m.attended}/${m.marked}` : t('atd.noData'),
        }))} />
      </PCard>
      <PCard title={t('atd.weekly')} icon={<CalendarDays className="size-4" aria-hidden />}>
        <PercentColumns points={data.weeks.map((w) => ({
          key: w.start, label: date(w.start), percent: w.percent,
          detail: w.marked ? `${t('atd.weekOf', { date: date(w.start) })}: ${w.attended}/${w.marked}` : t('atd.noData'),
        }))} />
      </PCard>
      <PCard title={t('atd.bySubject')} icon={<History className="size-4" aria-hidden />} className="lg:col-span-2">
        {data.subjects.length ? (
          <ul className="space-y-3">
            {data.subjects.map((s) => (
              <li key={s.subject ?? '—'}>
                <div className="mb-1 flex items-baseline justify-between gap-3 text-sm">
                  <span className="font-bold text-ink">{s.subject ?? '—'}</span>
                  <span className="text-xs font-semibold tabular-nums text-ink-secondary">{t('atd.ofMarked', { a: s.attended, m: s.marked })} · <b className="text-ink">{pct(s.percent)}</b></span>
                </div>
                {/* Stacked by status, 2px surface gaps between segments. */}
                <div className="flex h-2.5 gap-[2px] overflow-hidden rounded-full bg-surface-muted">
                  {(['present', 'late', 'excused', 'absent'] as const).map((k) => s[k] ? (
                    <span key={k} className={cn('sp-grow h-full', STATE_STYLE[k].dot)} style={{ width: `${(s[k] / s.marked) * 100}%` }} title={`${t(`atd.state.${k}`)}: ${s[k]}`} />
                  ) : null)}
                </div>
              </li>
            ))}
          </ul>
        ) : <Empty>{t('atd.noRecords')}</Empty>}
      </PCard>
    </div>
  )
}

// ---------------------------------------------------------------------------
// History — cards, filters, progressive loading
// ---------------------------------------------------------------------------

function HistoryCard({ row }: { row: AttendanceHistoryRow }) {
  const { t, date, weekday } = usePortalI18n()
  const l = row.lesson
  const s = STATE_STYLE[row.status]
  return (
    <li className="sp-card sp-card-hover relative flex gap-3.5 overflow-hidden p-3.5 pl-4">
      <span className={cn('absolute inset-y-3 left-0 w-1 rounded-r-full', s.dot)} aria-hidden />
      <div className={cn('flex w-14 shrink-0 flex-col items-center justify-center rounded-xl py-1.5', s.soft)}>
        <span className="text-[11px] font-bold uppercase text-ink-secondary">{weekday(dow(l.date))}</span>
        <span className="text-lg font-extrabold leading-tight tabular-nums text-ink">{l.date.slice(8)}</span>
        <span className="text-[10px] font-semibold text-ink-muted">{date(l.date).slice(3)}</span>
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <p className="truncate font-bold text-ink">{l.subject?.name ?? l.course?.name ?? '—'}</p>
          <StateBadge state={row.status} />
        </div>
        <p className="truncate text-sm text-ink-secondary">{l.lesson_number ? `${t('lesson.number', { n: l.lesson_number })} · ` : ''}{l.topic}</p>
        <p className="mt-1 flex flex-wrap gap-x-3 text-xs text-ink-muted">
          <span>{l.start}–{l.end}</span>
          {l.teacher ? <span className="inline-flex items-center gap-1"><User className="size-3" aria-hidden />{l.teacher.name}</span> : null}
        </p>
        {row.excuse_reason ? <p className="mt-1 text-xs text-info">{t('atd.reason', { r: row.excuse_reason })}</p> : null}
        {row.comment ? <p className="mt-1 text-xs text-ink-secondary">{t('atd.comment', { c: row.comment })}</p> : null}
      </div>
    </li>
  )
}

function HistorySection() {
  const { student } = usePortal()
  const { t } = usePortalI18n()
  const [filter, setFilter] = useState<'all' | AttendanceMark>('all')
  const query = useInfiniteQuery({
    queryKey: [...PORTAL_KEY, 'attendance-history', student.id, filter],
    queryFn: ({ pageParam }) => studentPortalApi.attendanceHistory(student.id, filter, pageParam),
    initialPageParam: 1,
    getNextPageParam: (last, pages) => (last.next ? pages.length + 1 : undefined),
  })
  const rows = query.data?.pages.flatMap((p) => p.results) ?? []
  return (
    <PCard title={t('atd.history')} icon={<History className="size-4" aria-hidden />}>
      <div className="-mx-1 mb-4 flex gap-2 overflow-x-auto px-1 pb-1">
        {FILTERS.map((f) => (
          <button key={f} type="button" aria-pressed={filter === f} onClick={() => setFilter(f)}
            className={cn('sp-press inline-flex shrink-0 items-center gap-1.5 rounded-full px-3.5 py-1.5 text-sm font-semibold ring-1',
              filter === f ? 'bg-ink text-white ring-ink' : 'bg-surface text-ink-secondary ring-border hover:text-ink')}>
            {f !== 'all' ? <span className={cn('size-2 rounded-full', STATE_STYLE[f].dot)} aria-hidden /> : null}
            {t(`atd.filter.${f}`)}
          </button>
        ))}
      </div>
      {query.isPending ? (
        <div className="space-y-2.5">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-20" />)}</div>
      ) : query.isError ? <LoadError onRetry={() => void query.refetch()} /> : rows.length === 0 ? (
        <Empty illustration title={filter === 'all' ? t('atd.noRecords') : t('atd.noHistory')} />
      ) : (
        <>
          <ul className="grid gap-2.5 md:grid-cols-2">{rows.map((row) => <HistoryCard key={row.id} row={row} />)}</ul>
          {query.hasNextPage ? (
            <div className="mt-4 flex justify-center">
              <button type="button" onClick={() => void query.fetchNextPage()} disabled={query.isFetchingNextPage}
                className="sp-press rounded-xl border border-brand-200 bg-surface px-5 py-2.5 text-sm font-bold text-brand-700 hover:bg-brand-50 disabled:opacity-60">
                {t('atd.more')}
              </button>
            </div>
          ) : null}
        </>
      )}
    </PCard>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function StudentAttendancePage() {
  const { student } = usePortal()
  const { t } = usePortalI18n()
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: [...PORTAL_KEY, 'attendance-overview', student.id],
    queryFn: () => studentPortalApi.attendanceOverview(student.id),
    ...LIVE_QUERY,
  })
  return (
    <div>
      <PageTitle title={t('attendance.title')} subtitle={t('atd.subtitle')} />
      {isPending ? (
        <div className="space-y-5" role="status"><Skeleton className="h-56" /><Skeleton className="h-96" /></div>
      ) : isError || !data ? <LoadError onRetry={() => void refetch()} /> : (
        <div className="space-y-5">
          <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_18rem]">
            <Overview data={data} />
            <StreakCard data={data} />
          </div>
          <CalendarCard />
          <Analytics data={data} />
          <HistorySection />
        </div>
      )}
    </div>
  )
}
