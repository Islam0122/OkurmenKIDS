import { useState } from 'react'
import type { ReactNode } from 'react'
import {
  AlertTriangle, CheckCircle2, CircleDashed, CircleX, Clock, MapPin, RefreshCw, ShieldCheck, User, XCircle,
} from 'lucide-react'

import { resolveMediaUrl } from '@/lib/mediaUrl'
import { cn } from '@/utils/cn'
import type { AttendanceMark, HomeworkState, PortalLesson, PortalStudent } from '@/types/studentPortal'

import { usePortalI18n } from './i18n'

/**
 * Building blocks of the Student & Parent Portal — one visual language for
 * every page: white cards with an 18px radius and a soft shadow on a very
 * light gray canvas, Manrope type, graphite text and the Okurmen Kids green
 * as the only accent (LMS tokens in index.css: brand-*, ink-*, surface-*).
 * Motion is short and subtle (.sp-rise / .sp-grow / .sp-press) and switched
 * off for prefers-reduced-motion.
 */

export function PCard({ title, action, children, className, padded = true, hover = false, icon }: {
  title?: ReactNode
  action?: ReactNode
  children: ReactNode
  className?: string
  padded?: boolean
  hover?: boolean
  icon?: ReactNode
}) {
  return (
    <section className={cn('sp-card sp-rise min-w-0', hover && 'sp-card-hover', className)}>
      {title || action ? (
        <header className="flex items-center justify-between gap-3 px-5 pt-5">
          {title ? (
            <h2 className="flex min-w-0 items-center gap-2.5 text-[15px] font-bold tracking-tight text-ink">
              {icon ? <span className="flex size-8 shrink-0 items-center justify-center rounded-[10px] bg-brand-50 text-brand-600">{icon}</span> : null}
              <span className="min-w-0">{title}</span>
            </h2>
          ) : <span />}
          {action}
        </header>
      ) : null}
      <div className={padded ? 'p-5 pt-4' : undefined}>{children}</div>
    </section>
  )
}

/** «Подробнее →» link style used in card headers. */
export const CARD_LINK = 'sp-press shrink-0 rounded-lg px-2 py-1 text-sm font-semibold text-brand-600 hover:bg-brand-50 hover:text-brand-700'

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('sp-skeleton', className)} aria-hidden />
}

/** Page-shaped loading placeholder (cards of skeleton lines), not a spinner. */
export function Loading({ variant = 'cards' }: { variant?: 'cards' | 'list' }) {
  const { t } = usePortalI18n()
  return (
    <div role="status" aria-label={t('common.loading')} className="space-y-4">
      <span className="sr-only">{t('common.loading')}</span>
      {variant === 'list' ? (
        [0, 1, 2].map((i) => <Skeleton key={i} className="h-24" />)
      ) : (
        <>
          <Skeleton className="h-36" />
          <div className="grid gap-4 md:grid-cols-3">
            <Skeleton className="h-40" /><Skeleton className="h-40" /><Skeleton className="h-40" />
          </div>
          <Skeleton className="h-56" />
        </>
      )}
    </div>
  )
}

export function LoadError({ onRetry }: { onRetry: () => void }) {
  const { t } = usePortalI18n()
  return (
    <div className="sp-card flex flex-col items-center gap-3 px-6 py-14 text-center text-sm text-ink-secondary">
      <span className="flex size-12 items-center justify-center rounded-2xl bg-warning-soft text-warning"><AlertTriangle className="size-6" aria-hidden /></span>
      {t('common.error')}
      <button type="button" onClick={onRetry} className="sp-press inline-flex items-center gap-1.5 rounded-xl border border-brand-200 px-4 py-2 font-semibold text-brand-700 hover:bg-brand-50">
        <RefreshCw className="size-4" aria-hidden /> {t('common.retry')}
      </button>
    </div>
  )
}

/** A friendly empty state; `illustration` adds the drawn scene for big, page-level ones. */
export function Empty({ children, title, illustration = false }: { children?: ReactNode; title?: ReactNode; illustration?: boolean }) {
  if (!illustration) {
    return <p className="rounded-2xl bg-surface-muted px-4 py-6 text-center text-sm text-ink-secondary">{children ?? title}</p>
  }
  return (
    <div className="flex flex-col items-center px-6 py-10 text-center">
      <EmptyIllustration className="mb-5 h-36 w-auto" />
      {title ? <p className="text-lg font-bold tracking-tight text-ink">{title}</p> : null}
      {children ? <p className="mt-1.5 max-w-sm text-sm text-ink-secondary">{children}</p> : null}
    </div>
  )
}

/** Original line-and-fill drawing: a stack of books, a pencil and a small star — brand green only. */
export function EmptyIllustration({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 220 160" className={className} role="presentation" aria-hidden>
      <ellipse cx="110" cy="142" rx="84" ry="10" fill="var(--color-brand-50)" />
      <circle cx="110" cy="74" r="62" fill="var(--color-brand-50)" />
      <rect x="62" y="104" width="96" height="20" rx="5" fill="var(--color-brand-500)" />
      <rect x="62" y="104" width="12" height="20" rx="3" fill="var(--color-brand-700)" />
      <rect x="70" y="84" width="84" height="20" rx="5" fill="#fff" stroke="var(--color-brand-200)" strokeWidth="2" />
      <path d="M82 94h50" stroke="var(--color-brand-200)" strokeWidth="3" strokeLinecap="round" />
      <rect x="66" y="64" width="90" height="20" rx="5" fill="var(--color-brand-200)" />
      <rect x="66" y="64" width="12" height="20" rx="3" fill="var(--color-brand-500)" />
      <g transform="rotate(-28 150 52)">
        <rect x="118" y="46" width="58" height="12" rx="3" fill="#f6c453" />
        <rect x="118" y="46" width="10" height="12" rx="2" fill="#f2a8a0" />
        <path d="M176 46l12 6-12 6z" fill="#f3dfbf" />
        <path d="M184 50l4 2-4 2z" fill="var(--color-ink)" />
      </g>
      <path d="M52 40l3.2 6.6 7.3 1-5.3 5.1 1.3 7.2-6.5-3.4-6.5 3.4 1.3-7.2-5.3-5.1 7.3-1z" fill="#f6c453" />
      <circle cx="176" cy="104" r="4" fill="var(--color-brand-200)" />
      <circle cx="40" cy="98" r="3" fill="var(--color-brand-200)" />
    </svg>
  )
}

export function PageTitle({ title, subtitle, actions, eyebrow }: { title: string; subtitle?: ReactNode; actions?: ReactNode; eyebrow?: ReactNode }) {
  return (
    <div className="sp-rise mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {eyebrow ? <p className="mb-1 text-xs font-semibold uppercase tracking-[0.08em] text-brand-600">{eyebrow}</p> : null}
        <h1 className="text-2xl font-extrabold tracking-tight text-ink sm:text-[28px]">{title}</h1>
        {subtitle ? <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-ink-secondary">{subtitle}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  )
}

const PILL = 'inline-flex items-center gap-1.5 rounded-full py-1 pl-2 pr-2.5 text-xs font-semibold whitespace-nowrap'

/** The trainer's offline verdict — each with its own colour AND icon, never colour alone. */
export const HW_STYLE: Record<HomeworkState, { tone: string; dot: string; icon: typeof CheckCircle2 }> = {
  awaiting: { tone: 'bg-surface-muted text-ink-secondary ring-1 ring-border', dot: 'bg-ink-muted', icon: CircleDashed },
  not_submitted: { tone: 'bg-danger-soft text-danger', dot: 'bg-danger', icon: CircleX },
  submitted: { tone: 'bg-brand-50 text-brand-700', dot: 'bg-brand-500', icon: CheckCircle2 },
  late: { tone: 'bg-warning-soft text-warning', dot: 'bg-warning', icon: Clock },
  checked: { tone: 'bg-brand-600 text-white', dot: 'bg-brand-600', icon: ShieldCheck },
}

export function HomeworkBadge({ state }: { state: HomeworkState }) {
  const { t } = usePortalI18n()
  const { tone, icon: Icon } = HW_STYLE[state]
  return <span className={cn(PILL, tone)}><Icon className="size-3.5" aria-hidden />{t(`hw.state.${state}`)}</span>
}

const ATT_STYLE: Record<AttendanceMark, { tone: string; icon: typeof CheckCircle2 }> = {
  present: { tone: 'bg-brand-50 text-brand-700', icon: CheckCircle2 },
  late: { tone: 'bg-warning-soft text-warning', icon: Clock },
  absent: { tone: 'bg-danger-soft text-danger', icon: XCircle },
  excused: { tone: 'bg-info-soft text-info', icon: AlertTriangle },
}

export function AttendanceBadge({ mark }: { mark: AttendanceMark }) {
  const { t } = usePortalI18n()
  const { tone, icon: Icon } = ATT_STYLE[mark]
  return <span className={cn(PILL, tone)}><Icon className="size-3.5" aria-hidden />{t(`att.${mark}`)}</span>
}

export function LessonStatusBadge({ lesson }: { lesson: PortalLesson }) {
  const { t } = usePortalI18n()
  if (lesson.attendance) return <AttendanceBadge mark={lesson.attendance} />
  const tone = lesson.status === 'cancelled' ? 'bg-danger-soft text-danger' : lesson.status === 'in_progress'
    ? 'bg-brand-600 text-white' : lesson.status === 'completed' ? 'bg-surface-muted text-ink-secondary' : 'bg-info-soft text-info'
  return <span className={cn(PILL, 'pl-2.5', tone)}>{t(`lesson.status.${lesson.status}`)}</span>
}

export function LessonRow({ lesson, showDate = false }: { lesson: PortalLesson; showDate?: boolean }) {
  const { t, date, weekday } = usePortalI18n()
  const cancelled = lesson.status === 'cancelled'
  const day = (new Date(`${lesson.date}T00:00:00`).getDay() + 6) % 7
  return (
    <div className={cn('group flex gap-3.5 rounded-2xl border border-border/70 bg-surface p-3.5 transition-colors hover:border-brand-200 hover:bg-brand-50/30', cancelled && 'opacity-70')}>
      <div className="flex w-16 shrink-0 flex-col items-center justify-center rounded-xl bg-brand-50 py-2 text-brand-700">
        {showDate ? <span className="text-[11px] font-semibold uppercase tracking-wide">{weekday(day)} {date(lesson.date)}</span> : null}
        <span className="text-[15px] font-extrabold tabular-nums">{lesson.start ?? '—'}</span>
        <span className="text-[11px] font-medium tabular-nums text-brand-700/70">{lesson.end ?? ''}</span>
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <p className={cn('truncate font-bold text-ink', cancelled && 'line-through')}>{lesson.subject?.name ?? lesson.course?.name ?? '—'}</p>
          <LessonStatusBadge lesson={lesson} />
        </div>
        {lesson.topic ? <p className="truncate text-sm text-ink-secondary">{lesson.lesson_number ? `${t('lesson.number', { n: lesson.lesson_number })} · ` : ''}{lesson.topic}</p> : null}
        <p className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-ink-muted">
          {lesson.teacher ? <span className="inline-flex items-center gap-1"><User className="size-3" aria-hidden />{lesson.teacher.name}</span> : null}
          {lesson.group ? <span>{lesson.group.name}</span> : null}
          {lesson.room || lesson.branch ? (
            <span className="inline-flex items-center gap-1"><MapPin className="size-3" aria-hidden />
              {[lesson.branch?.name, lesson.room ? t('lesson.room', { room: lesson.room.name }) : null].filter(Boolean).join(' · ')}
            </span>
          ) : null}
        </p>
      </div>
    </div>
  )
}

/** Single-value ring (a percent): one series, no legend; the label names it. Draws itself in. */
export function ProgressRing({ value, size = 88, label, stroke = 9 }: { value: number | null; size?: number; label?: string; stroke?: number }) {
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const pct = value === null ? 0 : Math.max(0, Math.min(100, value))
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }} role="img" aria-label={`${label ?? ''} ${value === null ? '—' : `${Math.round(value)}%`}`}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--color-brand-50)" strokeWidth={stroke} />
        {value !== null ? (
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--color-brand-500)" strokeWidth={stroke}
            strokeLinecap="round" strokeDasharray={`${(pct / 100) * c} ${c}`}
            className="motion-safe:transition-[stroke-dasharray] motion-safe:duration-700" />
        ) : null}
      </svg>
      <span className="absolute inset-0 flex items-center justify-center text-lg font-extrabold tabular-nums text-ink">
        {value === null ? '—' : `${Math.round(value)}%`}
      </span>
    </div>
  )
}

export function Bar({ value, className, tone = 'brand' }: { value: number | null; className?: string; tone?: 'brand' | 'light' }) {
  return (
    <div className={cn('h-2.5 overflow-hidden rounded-full', tone === 'light' ? 'bg-white/25' : 'bg-brand-50', className)}>
      <div className={cn('sp-grow h-full rounded-full', tone === 'light' ? 'bg-white' : 'bg-brand-500')}
        style={{ width: `${Math.max(0, Math.min(100, value ?? 0))}%` }} />
    </div>
  )
}

export function Stat({ label, value, hint, accent = false, icon }: { label: string; value: ReactNode; hint?: ReactNode; accent?: boolean; icon?: ReactNode }) {
  return (
    <div className={cn('min-w-0 rounded-2xl p-3.5', accent ? 'bg-brand-50' : 'bg-surface-muted')}>
      <p className="flex items-center gap-1.5 truncate text-xs font-medium text-ink-secondary">{icon}{label}</p>
      <p className="mt-1 text-xl font-extrabold tabular-nums tracking-tight text-ink">{value}</p>
      {hint ? <p className="mt-0.5 text-xs text-ink-muted">{hint}</p> : null}
    </div>
  )
}

export function Avatar({ student, size = 'md' }: { student: PortalStudent; size?: 'sm' | 'md' | 'lg' }) {
  const cls = size === 'sm' ? 'size-8 text-xs' : size === 'lg' ? 'size-16 text-xl' : 'size-10 text-sm'
  const photo = resolveMediaUrl(student.photo)
  if (photo) return <img src={photo} alt="" className={cn(cls, 'shrink-0 rounded-full object-cover ring-2 ring-white')} />
  return (
    <span className={cn(cls, 'flex shrink-0 items-center justify-center rounded-full bg-brand-500 font-bold text-white ring-2 ring-white')}>
      {(student.first_name[0] ?? '') + (student.last_name[0] ?? '')}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Charts — inline SVG, palette validated (dataviz validator, light surface):
// series 1 brand green #2f8f5b, series 2 info blue #2563a8.
// ---------------------------------------------------------------------------

export const SERIES = ['var(--color-brand-500)', 'var(--color-info)'] as const

interface GroupedPoint {
  label: string
  values: (number | null)[]
}

/** Grouped columns on one 0–100 % axis (attendance vs homework by month).
 * Legend always shown (2 series); hover / focus shows the exact values. */
export function GroupedColumns({ points, series, max = 100, unit = '%' }: { points: GroupedPoint[]; series: string[]; max?: number; unit?: string }) {
  const [hover, setHover] = useState<number | null>(null)
  const W = 560
  const H = 200
  const pad = { l: 36, r: 8, t: 12, b: 26 }
  const plotW = W - pad.l - pad.r
  const plotH = H - pad.t - pad.b
  const slot = plotW / Math.max(points.length, 1)
  const barW = Math.min(18, (slot - 16) / series.length - 2)
  const y = (v: number) => pad.t + plotH - (v / max) * plotH
  const ticks = [0, max / 2, max]
  return (
    <div>
      <ul className="mb-2 flex flex-wrap gap-4 text-xs text-ink-secondary">
        {series.map((name, i) => (
          <li key={name} className="inline-flex items-center gap-1.5"><span className="size-2.5 rounded-sm" style={{ background: SERIES[i] }} />{name}</li>
        ))}
      </ul>
      <div className="relative">
        <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label={series.join(', ')}>
          {ticks.map((tick) => (
            <g key={tick}>
              <line x1={pad.l} x2={W - pad.r} y1={y(tick)} y2={y(tick)} stroke="var(--color-border)" strokeWidth={1} />
              <text x={pad.l - 6} y={y(tick) + 3} textAnchor="end" fontSize={10} fill="var(--color-ink-muted)">{tick}{unit}</text>
            </g>
          ))}
          {points.map((point, index) => {
            const cx = pad.l + slot * index + slot / 2
            const groupW = series.length * barW + (series.length - 1) * 2
            return (
              <g key={point.label} onMouseEnter={() => setHover(index)} onMouseLeave={() => setHover(null)}
                onFocus={() => setHover(index)} onBlur={() => setHover(null)} tabIndex={0} className="outline-none">
                <rect x={cx - slot / 2} y={pad.t} width={slot} height={plotH} fill={hover === index ? 'var(--color-surface-hover)' : 'transparent'} />
                {point.values.map((value, i) => {
                  if (value === null) return null
                  const h = Math.max((value / max) * plotH, 1.5)
                  const x = cx - groupW / 2 + i * (barW + 2)
                  const top = pad.t + plotH - h
                  const rr = Math.min(4, h)
                  return (
                    <path key={i} fill={SERIES[i]}
                      d={`M${x},${pad.t + plotH} V${top + rr} Q${x},${top} ${x + rr},${top} H${x + barW - rr} Q${x + barW},${top} ${x + barW},${top + rr} V${pad.t + plotH} Z`} />
                  )
                })}
                <text x={cx} y={H - 8} textAnchor="middle" fontSize={11} fill="var(--color-ink-secondary)">{point.label}</text>
              </g>
            )
          })}
        </svg>
        {hover !== null ? (
          <div className="pointer-events-none absolute top-0 rounded-lg border border-border bg-surface px-3 py-2 text-xs shadow-lg"
            style={{ left: `${((pad.l + slot * hover + slot / 2) / W) * 100}%`, transform: 'translateX(-50%)' }}>
            <p className="mb-1 font-semibold text-ink">{points[hover].label}</p>
            {series.map((name, i) => (
              <p key={name} className="flex items-center gap-1.5 text-ink-secondary">
                <span className="size-2 rounded-sm" style={{ background: SERIES[i] }} />{name}:
                <b className="text-ink">{points[hover].values[i] === null ? '—' : `${points[hover].values[i]}${unit}`}</b>
              </p>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  )
}

/** One series of columns (XP per month) — the title names it; value on the cap of the last one. */
export function Columns({ points }: { points: { label: string; value: number }[] }) {
  const [hover, setHover] = useState<number | null>(null)
  const max = Math.max(10, ...points.map((p) => p.value))
  return (
    <div className="flex h-36 items-end gap-2" role="img" aria-label={points.map((p) => `${p.label}: ${p.value}`).join(', ')}>
      {points.map((point, index) => (
        <div key={point.label} className="relative flex h-full flex-1 flex-col items-center justify-end gap-1"
          onMouseEnter={() => setHover(index)} onMouseLeave={() => setHover(null)}>
          {hover === index || index === points.length - 1 ? (
            <span className="text-xs font-semibold tabular-nums text-ink">{point.value}</span>
          ) : <span className="text-xs">&nbsp;</span>}
          <div className="flex w-full min-h-0 flex-1 items-end justify-center">
            <div className="w-full max-w-6 rounded-t bg-brand-500" style={{ height: `${Math.max((point.value / max) * 100, 2)}%`, opacity: index === points.length - 1 ? 1 : 0.55 }} />
          </div>
          <span className="text-[11px] text-ink-secondary">{point.label}</span>
        </div>
      ))}
    </div>
  )
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function isoDate(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
