import type { ReactNode } from 'react'
import { motion } from 'framer-motion'
import {
  CalendarCheck2, CalendarDays, CalendarRange, ChevronLeft, ChevronRight, CircleCheckBig, Hourglass, Radio, RotateCcw, UserX,
} from 'lucide-react'

import { cn } from '@/utils/cn'
import type { PortalLesson } from '@/types/studentPortal'

import { usePortalI18n } from '../i18n'
import { EmptyIllustration, Skeleton, isoDate } from '../ui'
import { SUBJECT_TONE, pct, subjectKind, type ScheduleStats, type View } from './model'

// ---------------------------------------------------------------------------
// Header: title, today's date, the week's progress and the next lesson.
// ---------------------------------------------------------------------------

export function ScheduleHeader({ now, week, next, live, loading, groupLine }: {
  now: Date
  week: ScheduleStats | null
  next: PortalLesson | null
  live: PortalLesson | null
  loading: boolean
  groupLine: string
}) {
  const { t, weekday, dayMonth, date } = usePortalI18n()
  const iso = isoDate(now)
  const done = week?.completed ?? 0
  const total = week?.total ?? 0
  const progress = pct(done, total)
  const focus = live ?? next
  const focusDay = focus
    ? focus.date === iso ? t('common.today') : `${weekday((new Date(`${focus.date}T00:00:00`).getDay() + 6) % 7, true)}, ${date(focus.date)}`
    : ''

  return (
    <section className="sp-card sp-rise relative mb-5 overflow-hidden">
      <div className="pointer-events-none absolute -right-16 -top-24 size-72 rounded-full bg-brand-50 blur-2xl" aria-hidden />
      <div className="relative grid gap-5 p-5 sm:p-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)] lg:items-center lg:gap-8">
        <div className="min-w-0">
          <p className="inline-flex items-center gap-1.5 rounded-full bg-brand-50 px-2.5 py-1 text-xs font-semibold text-brand-700">
            <CalendarDays className="size-3.5" aria-hidden />
            {`${weekday((now.getDay() + 6) % 7, true)}, ${dayMonth(iso)} ${now.getFullYear()}`}
          </p>
          <h1 className="mt-3 text-2xl font-extrabold tracking-tight text-ink sm:text-[28px]">{t('schedule.myTitle')}</h1>
          <p className="mt-1 max-w-xl text-sm leading-relaxed text-ink-secondary">{t('schedule.subtitle')}</p>
          {groupLine ? <p className="mt-2 text-xs font-medium text-ink-muted">{groupLine}</p> : null}
        </div>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
          <div className="rounded-2xl bg-surface-muted p-4 ring-1 ring-border/60">
            <div className="flex items-center justify-between gap-2 text-xs font-semibold text-ink-secondary">
              <span>{t('schedule.weekProgress')}</span>
              {loading ? <Skeleton className="h-4 w-10" /> : <span className="tabular-nums text-brand-700">{progress}%</span>}
            </div>
            <div className="mt-2.5 h-2 overflow-hidden rounded-full bg-brand-100/70" role="progressbar" aria-valuemin={0} aria-valuemax={100}
              aria-valuenow={progress} aria-label={t('schedule.weekProgress')}>
              <motion.div className="h-full rounded-full bg-gradient-to-r from-brand-500 to-brand-600"
                initial={{ width: 0 }} animate={{ width: `${progress}%` }} transition={{ duration: 0.8, ease: [0.2, 0.7, 0.2, 1] }} />
            </div>
            <p className="mt-2 text-xs text-ink-muted">{loading ? ' ' : t('schedule.weekProgressValue', { done, total })}</p>
          </div>

          <div className={cn('flex min-w-0 items-center gap-3 rounded-2xl p-4 ring-1', live ? 'bg-brand-600 text-white ring-brand-600' : 'bg-surface ring-border/60')}>
            <span className={cn('flex size-10 shrink-0 items-center justify-center rounded-xl', live ? 'bg-white/15' : 'bg-brand-50 text-brand-600')}>
              {live ? <Radio className="size-5" aria-hidden /> : <Hourglass className="size-5" aria-hidden />}
            </span>
            <div className="min-w-0">
              <p className={cn('text-xs font-semibold', live ? 'text-white/80' : 'text-ink-secondary')}>
                {live ? t('schedule.liveNow') : t('schedule.nextLesson')}
              </p>
              {loading ? <Skeleton className="mt-1 h-4 w-32" /> : focus ? (
                <>
                  <p className="truncate text-sm font-bold">{focus.subject?.name ?? focus.course?.name ?? '—'}{focus.topic ? ` · ${focus.topic}` : ''}</p>
                  <p className={cn('text-xs tabular-nums', live ? 'text-white/80' : 'text-ink-muted')}>
                    {t('schedule.dayAt', { day: focusDay, time: `${focus.start ?? ''}${focus.end ? `–${focus.end}` : ''}` })}
                  </p>
                </>
              ) : <p className="text-sm font-semibold text-ink-secondary">{t('schedule.noMoreThisWeek')}</p>}
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Four statistic cards.
// ---------------------------------------------------------------------------

function StatCard({ icon, label, value, hint, accent, bar, delay }: {
  icon: ReactNode; label: string; value: number; hint: string; accent: string; bar: { value: number; tone: string } | null; delay: number
}) {
  return (
    <div className="sp-card sp-card-hover sp-rise relative min-w-0 overflow-hidden p-4 sm:p-5" style={{ animationDelay: `${delay}ms` }}>
      <div className="flex items-start justify-between gap-2">
        <p className="text-[13px] font-semibold text-ink-secondary">{label}</p>
        <span className={cn('flex size-9 shrink-0 items-center justify-center rounded-xl', accent)}>{icon}</span>
      </div>
      <p className="mt-1 text-[28px] font-extrabold leading-none tracking-tight tabular-nums text-ink sm:text-[32px]">{value}</p>
      <p className="mt-2 line-clamp-2 text-xs leading-snug text-ink-muted">{hint}</p>
      {bar ? (
        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-surface-muted" aria-hidden>
          <motion.div className={cn('h-full rounded-full', bar.tone)} initial={{ width: 0 }} animate={{ width: `${bar.value}%` }}
            transition={{ duration: 0.7, delay: delay / 1000, ease: [0.2, 0.7, 0.2, 1] }} />
        </div>
      ) : null}
    </div>
  )
}

export function StatCards({ stats, periodHint }: { stats: ScheduleStats; periodHint: string }) {
  const { t } = usePortalI18n()
  const held = stats.completed
  return (
    <section aria-label={t('schedule.statsLabel')} className="mb-5 grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
      <StatCard delay={0} label={t('schedule.stat.total')} value={stats.total} accent="bg-brand-50 text-brand-600"
        icon={<CalendarRange className="size-[18px]" aria-hidden />}
        hint={stats.cancelled ? `${periodHint} · ${t('schedule.hint.cancelled', { n: stats.cancelled })}` : periodHint} bar={null} />
      <StatCard delay={60} label={t('schedule.stat.completed')} value={stats.completed} accent="bg-brand-600 text-white"
        icon={<CircleCheckBig className="size-[18px]" aria-hidden />}
        hint={t('schedule.hint.completed', { p: pct(stats.completed, stats.total) })} bar={{ value: pct(stats.completed, stats.total), tone: 'bg-brand-600' }} />
      <StatCard delay={120} label={t('schedule.stat.upcoming')} value={stats.upcoming} accent="bg-info-soft text-info"
        icon={<CalendarCheck2 className="size-[18px]" aria-hidden />}
        hint={t('schedule.hint.upcoming')} bar={{ value: pct(stats.upcoming, stats.total), tone: 'bg-info' }} />
      <StatCard delay={180} label={t('schedule.stat.missed')} value={stats.missed}
        accent={stats.missed ? 'bg-danger-soft text-danger' : 'bg-surface-muted text-ink-muted'}
        icon={<UserX className="size-[18px]" aria-hidden />}
        hint={stats.missed ? t('schedule.hint.missed', { n: held }) : t('schedule.hint.noMissed')}
        bar={held ? { value: pct(stats.missed, held), tone: 'bg-danger' } : null} />
    </section>
  )
}

export function StatCardsSkeleton() {
  return (
    <div className="mb-5 grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4" aria-hidden>
      {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-[124px] rounded-[18px]" />)}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Calendar toolbar: Неделя / Месяц, ‹ range ›, Сегодня.
// ---------------------------------------------------------------------------

export function ScheduleToolbar({ view, onView, title, onShift, onToday, isCurrent }: {
  view: View; onView: (v: View) => void; title: string; onShift: (d: -1 | 1) => void; onToday: () => void; isCurrent: boolean
}) {
  const { t } = usePortalI18n()
  return (
    <div className="mb-4 flex flex-wrap items-center gap-2 sm:gap-3">
      <div className="relative inline-flex rounded-xl bg-surface p-1 shadow-sm ring-1 ring-border/70" role="group" aria-label={t('schedule.viewLabel')}>
        {(['week', 'month'] as View[]).map((v) => (
          <button key={v} type="button" onClick={() => onView(v)} aria-pressed={view === v}
            className={cn('sp-press relative min-h-9 rounded-lg px-4 text-sm font-semibold', view === v ? 'text-white' : 'text-ink-secondary hover:text-ink')}>
            {view === v ? (
              <motion.span layoutId="sp-schedule-view" className="absolute inset-0 rounded-lg bg-brand-500 shadow-sm shadow-brand-500/30"
                transition={{ type: 'spring', stiffness: 500, damping: 38 }} />
            ) : null}
            <span className="relative">{t(`schedule.${v}`)}</span>
          </button>
        ))}
      </div>

      <button type="button" onClick={onToday} disabled={isCurrent}
        className="sp-press ml-auto inline-flex min-h-10 items-center gap-1.5 rounded-xl border border-brand-200 bg-surface px-3.5 text-sm font-semibold text-brand-700 hover:bg-brand-50 disabled:cursor-default disabled:border-border disabled:text-ink-muted disabled:hover:bg-surface sm:order-last sm:ml-0">
        <RotateCcw className="size-4" aria-hidden />{t('schedule.current')}
      </button>

      <div className="flex w-full items-center justify-between gap-1 rounded-xl bg-surface p-1 shadow-sm ring-1 ring-border/70 sm:ml-auto sm:w-auto">
        <button type="button" onClick={() => onShift(-1)} aria-label={t('schedule.prev')}
          className="sp-press flex size-9 items-center justify-center rounded-lg text-ink-secondary hover:bg-surface-hover hover:text-ink">
          <ChevronLeft className="size-5" aria-hidden />
        </button>
        <span className="min-w-40 px-2 text-center text-sm font-bold tabular-nums text-ink" aria-live="polite">{title}</span>
        <button type="button" onClick={() => onShift(1)} aria-label={t('schedule.next')}
          className="sp-press flex size-9 items-center justify-center rounded-lg text-ink-secondary hover:bg-surface-hover hover:text-ink">
          <ChevronRight className="size-5" aria-hidden />
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Week strip: seven day buttons with a dot per lesson (subject colour).
// ---------------------------------------------------------------------------

export function WeekStrip({ days, byDay, picked, onPick, todayIso }: {
  days: Date[]; byDay: Map<string, PortalLesson[]>; picked: string | null; onPick: (iso: string | null) => void; todayIso: string
}) {
  const { t, weekday, date } = usePortalI18n()
  return (
    <div className="mb-4 grid grid-cols-7 gap-1 rounded-2xl bg-surface p-1.5 shadow-sm ring-1 ring-border/70 sm:gap-1.5" role="group" aria-label={t('schedule.pickDay')}>
      {days.map((day, i) => {
        const iso = isoDate(day)
        const lessons = byDay.get(iso) ?? []
        const selected = picked === iso
        const today = iso === todayIso
        return (
          <button key={iso} type="button" onClick={() => onPick(selected ? null : iso)} aria-pressed={selected}
            aria-label={t('schedule.lessonsOfDay', { date: `${weekday(i, true)} ${date(iso)}`, n: lessons.length })}
            className={cn('sp-press flex min-h-[68px] min-w-0 flex-col items-center justify-center gap-1 rounded-xl px-0.5 py-2 transition-colors',
              selected ? 'bg-brand-500 text-white shadow-sm shadow-brand-500/30' : today ? 'bg-brand-50 text-brand-700' : 'text-ink hover:bg-surface-hover')}>
            <span className={cn('text-[11px] font-semibold uppercase tracking-wide', selected ? 'text-white/80' : 'text-ink-muted', today && !selected && 'text-brand-600')}>{weekday(i)}</span>
            <span className="text-base font-extrabold tabular-nums leading-none">{day.getDate()}</span>
            <span className="flex h-1.5 items-center gap-0.5">
              {lessons.slice(0, 4).map((l) => (
                <span key={l.id} className={cn('size-1.5 rounded-full', selected ? 'bg-white' : l.status === 'cancelled' ? 'bg-border-strong' : SUBJECT_TONE[subjectKind(l)].dot)} />
              ))}
            </span>
          </button>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Month grid.
// ---------------------------------------------------------------------------

export function MonthGrid({ days, byDay, picked, onPick, todayIso, month }: {
  days: Date[]; byDay: Map<string, PortalLesson[]>; picked: string | null; onPick: (iso: string) => void; todayIso: string; month: number
}) {
  const { t, weekday, date } = usePortalI18n()
  return (
    <div className="sp-card overflow-hidden">
      <div className="grid grid-cols-7 border-b border-border/60 bg-surface-muted/60 text-center text-[11px] font-semibold uppercase tracking-wide text-ink-muted">
        {Array.from({ length: 7 }, (_, i) => <span key={i} className="py-2.5">{weekday(i)}</span>)}
      </div>
      <div className="grid grid-cols-7 gap-1 p-1.5 sm:gap-1.5 sm:p-2">
        {days.map((day) => {
          const iso = isoDate(day)
          const lessons = byDay.get(iso) ?? []
          const inMonth = day.getMonth() === month
          const selected = picked === iso
          return (
            <button key={iso} type="button" onClick={() => onPick(iso)} aria-pressed={selected}
              aria-label={t('schedule.lessonsOfDay', { date: date(iso, true), n: lessons.length })}
              className={cn('sp-press flex min-h-14 min-w-0 flex-col items-center rounded-xl p-1 text-sm transition-colors sm:min-h-[88px] sm:items-stretch sm:p-1.5',
                inMonth ? 'text-ink' : 'text-ink-muted/50',
                selected ? 'bg-brand-50 ring-2 ring-brand-500/60' : 'hover:bg-surface-hover')}>
              <span className={cn('flex size-7 items-center justify-center self-center rounded-full text-[13px] font-bold tabular-nums sm:self-start',
                iso === todayIso && 'bg-brand-500 text-white shadow-sm shadow-brand-500/30')}>{day.getDate()}</span>
              <span className="mt-1 flex flex-wrap justify-center gap-0.5 sm:hidden">
                {lessons.slice(0, 3).map((l) => (
                  <span key={l.id} className={cn('size-1.5 rounded-full', l.status === 'cancelled' ? 'bg-border-strong' : SUBJECT_TONE[subjectKind(l)].dot)} />
                ))}
              </span>
              <span className="mt-1 hidden min-w-0 space-y-0.5 sm:block">
                {lessons.slice(0, 2).map((l) => (
                  <span key={l.id} className={cn('block truncate rounded-md px-1.5 py-0.5 text-left text-[11px] font-semibold',
                    l.status === 'cancelled' ? 'bg-surface-muted text-ink-muted line-through' : SUBJECT_TONE[subjectKind(l)].soft,
                    !inMonth && 'opacity-60')}>
                    <span className="tabular-nums">{l.start}</span> {l.subject?.name ?? ''}
                  </span>
                ))}
                {lessons.length > 2 ? <span className="block px-1.5 text-[11px] font-semibold text-ink-muted">+{lessons.length - 2}</span> : null}
              </span>
            </button>
          )
        })}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 border-t border-border/60 px-4 py-2.5 text-[11px] font-medium text-ink-secondary">
        {(['it', 'english', 'soft'] as const).map((k) => (
          <span key={k} className="inline-flex items-center gap-1.5">
            <span className={cn('size-2 rounded-full', SUBJECT_TONE[k].dot)} aria-hidden />{k === 'it' ? 'IT' : k === 'english' ? 'English' : 'Soft Skills'}
          </span>
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Empty states.
// ---------------------------------------------------------------------------

export function EmptyState({ title, hint, actions, illustration = false }: { title: string; hint: string; actions?: ReactNode; illustration?: boolean }) {
  return (
    <div className="sp-card sp-rise flex flex-col items-center px-6 py-10 text-center">
      {illustration ? <EmptyIllustration className="mb-4 h-32 w-auto" /> : (
        <span className="mb-3 flex size-14 items-center justify-center rounded-2xl bg-brand-50 text-brand-600"><CalendarDays className="size-7" aria-hidden /></span>
      )}
      <p className="text-lg font-bold tracking-tight text-ink">{title}</p>
      <p className="mt-1 max-w-sm text-sm text-ink-secondary">{hint}</p>
      {actions ? <div className="mt-5 flex flex-wrap justify-center gap-2">{actions}</div> : null}
    </div>
  )
}

export const PRIMARY_BTN = 'sp-press inline-flex min-h-10 items-center gap-1.5 rounded-xl bg-brand-500 px-4 text-sm font-semibold text-white shadow-sm shadow-brand-500/30 hover:bg-brand-600'
export const GHOST_BTN = 'sp-press inline-flex min-h-10 items-center gap-1.5 rounded-xl border border-brand-200 bg-surface px-4 text-sm font-semibold text-brand-700 hover:bg-brand-50'
