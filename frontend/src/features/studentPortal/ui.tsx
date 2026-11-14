import { useState } from 'react'
import type { ReactNode } from 'react'
import { AlertTriangle, CheckCircle2, Clock, Loader2, MapPin, RefreshCw, User, XCircle } from 'lucide-react'

import { resolveMediaUrl } from '@/lib/mediaUrl'
import { cn } from '@/utils/cn'
import type { AttendanceMark, HomeworkState, PortalLesson, PortalStudent } from '@/types/studentPortal'

import { usePortalI18n } from './i18n'

/** Building blocks of the Student & Parent Portal: white rounded cards,
 * green accents, the LMS palette tokens (index.css). */

export function PCard({ title, action, children, className, padded = true }: {
  title?: ReactNode
  action?: ReactNode
  children: ReactNode
  className?: string
  padded?: boolean
}) {
  return (
    <section className={cn('rounded-2xl border border-border/70 bg-surface shadow-[0_1px_2px_rgba(16,24,20,0.04),0_4px_16px_rgba(16,24,20,0.04)]', className)}>
      {title || action ? (
        <header className="flex items-center justify-between gap-3 px-5 pt-4">
          {title ? <h2 className="text-[15px] font-semibold text-ink">{title}</h2> : <span />}
          {action}
        </header>
      ) : null}
      <div className={padded ? 'p-5 pt-3' : undefined}>{children}</div>
    </section>
  )
}

export function Loading() {
  const { t } = usePortalI18n()
  return (
    <div className="flex items-center justify-center gap-2 py-16 text-sm text-ink-secondary" role="status">
      <Loader2 className="size-5 animate-spin text-brand-500" aria-hidden /> {t('common.loading')}
    </div>
  )
}

export function LoadError({ onRetry }: { onRetry: () => void }) {
  const { t } = usePortalI18n()
  return (
    <div className="flex flex-col items-center gap-3 py-16 text-center text-sm text-ink-secondary">
      <AlertTriangle className="size-6 text-warning" aria-hidden />
      {t('common.error')}
      <button type="button" onClick={onRetry} className="inline-flex items-center gap-1.5 rounded-lg border border-brand-200 px-3 py-1.5 font-medium text-brand-700 hover:bg-brand-50">
        <RefreshCw className="size-4" aria-hidden /> {t('common.retry')}
      </button>
    </div>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="rounded-xl bg-surface-muted px-4 py-6 text-center text-sm text-ink-secondary">{children}</p>
}

export function PageTitle({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        <h1 className="text-xl font-bold tracking-tight text-ink sm:text-2xl">{title}</h1>
        {subtitle ? <p className="mt-1 text-sm text-ink-secondary">{subtitle}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  )
}

const PILL = 'inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap'

const HW_TONE: Record<HomeworkState, string> = {
  pending: 'bg-info-soft text-info',
  overdue: 'bg-danger-soft text-danger',
  submitted: 'bg-brand-50 text-brand-700',
  late: 'bg-warning-soft text-warning',
  checked: 'bg-brand-500 text-white',
}

export function HomeworkBadge({ state }: { state: HomeworkState }) {
  const { t } = usePortalI18n()
  return <span className={cn(PILL, HW_TONE[state])}>{t(`hw.state.${state}`)}</span>
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
    ? 'bg-brand-500 text-white' : lesson.status === 'completed' ? 'bg-surface-muted text-ink-secondary' : 'bg-info-soft text-info'
  return <span className={cn(PILL, tone)}>{t(`lesson.status.${lesson.status}`)}</span>
}

export function LessonRow({ lesson, showDate = false }: { lesson: PortalLesson; showDate?: boolean }) {
  const { t, date, weekday } = usePortalI18n()
  const cancelled = lesson.status === 'cancelled'
  const day = (new Date(`${lesson.date}T00:00:00`).getDay() + 6) % 7
  return (
    <div className={cn('flex gap-3 rounded-xl border border-border/70 p-3', cancelled && 'opacity-70')}>
      <div className="flex w-14 shrink-0 flex-col items-center justify-center rounded-lg bg-brand-50 py-1.5 text-brand-700">
        {showDate ? <span className="text-[11px] font-medium uppercase">{weekday(day)} {date(lesson.date)}</span> : null}
        <span className="text-sm font-bold tabular-nums">{lesson.start ?? '—'}</span>
        <span className="text-[11px] tabular-nums text-brand-700/70">{lesson.end ?? ''}</span>
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <p className={cn('truncate font-semibold text-ink', cancelled && 'line-through')}>{lesson.subject?.name ?? lesson.course?.name ?? '—'}</p>
          <LessonStatusBadge lesson={lesson} />
        </div>
        {lesson.topic ? <p className="truncate text-sm text-ink-secondary">{lesson.topic}</p> : null}
        <p className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-ink-muted">
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

/** Single-value ring (a percent): one series, no legend; the label names it. */
export function ProgressRing({ value, size = 88, label }: { value: number | null; size?: number; label?: string }) {
  const stroke = 8
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const pct = value === null ? 0 : Math.max(0, Math.min(100, value))
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }} role="img" aria-label={`${label ?? ''} ${value === null ? '—' : `${value}%`}`}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--color-brand-50)" strokeWidth={stroke} />
        {value !== null ? (
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--color-brand-500)" strokeWidth={stroke}
            strokeLinecap="round" strokeDasharray={`${(pct / 100) * c} ${c}`} />
        ) : null}
      </svg>
      <span className="absolute inset-0 flex items-center justify-center text-lg font-bold tabular-nums text-ink">
        {value === null ? '—' : `${Math.round(value)}%`}
      </span>
    </div>
  )
}

export function Bar({ value, className }: { value: number | null; className?: string }) {
  return (
    <div className={cn('h-2 overflow-hidden rounded-full bg-brand-50', className)}>
      <div className="h-full rounded-full bg-brand-500 transition-[width]" style={{ width: `${Math.max(0, Math.min(100, value ?? 0))}%` }} />
    </div>
  )
}

export function Stat({ label, value, hint, accent = false }: { label: string; value: ReactNode; hint?: ReactNode; accent?: boolean }) {
  return (
    <div className={cn('rounded-xl p-3', accent ? 'bg-brand-50' : 'bg-surface-muted')}>
      <p className="text-xs text-ink-secondary">{label}</p>
      <p className="mt-0.5 text-xl font-bold tabular-nums text-ink">{value}</p>
      {hint ? <p className="mt-0.5 text-xs text-ink-muted">{hint}</p> : null}
    </div>
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

export function Avatar({ student, size = 'md' }: { student: PortalStudent; size?: 'sm' | 'md' }) {
  const cls = size === 'sm' ? 'size-8 text-xs' : 'size-10 text-sm'
  const photo = resolveMediaUrl(student.photo)
  if (photo) return <img src={photo} alt="" className={cn(cls, 'shrink-0 rounded-full object-cover ring-2 ring-brand-100')} />
  return (
    <span className={cn(cls, 'flex shrink-0 items-center justify-center rounded-full bg-brand-500 font-semibold text-white')}>
      {(student.first_name[0] ?? '') + (student.last_name[0] ?? '')}
    </span>
  )
}

