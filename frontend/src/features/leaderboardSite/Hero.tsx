import type { ReactNode } from 'react'
import { CalendarRange, Clock, GraduationCap, Users } from 'lucide-react'

import type { LeaderboardPeriod } from '@/types/leaderboard'

import { formatDateTime, formatDateTimeShort, formatNumber, periodRange, periodRangeShort, periodTitle, plural } from './format'
import { Skeleton } from './ui'

/** The cup on the right of the hero — pure SVG/CSS in the brand colors, no
 * photos. Decorative only. */
function TrophyArt() {
  return (
    <div aria-hidden className="relative hidden h-full min-h-[11rem] w-[17rem] shrink-0 md:block">
      <div className="absolute inset-0 rounded-[2rem] bg-[radial-gradient(circle_at_50%_55%,rgba(246,184,47,0.35),transparent_60%)]" />
      <svg viewBox="0 0 220 180" className="lb-float absolute inset-x-0 top-1 mx-auto h-[10.5rem] w-auto drop-shadow-[0_14px_18px_rgba(41,16,100,0.25)]">
        <defs>
          <linearGradient id="lb-cup" x1="0" x2="1" y1="0" y2="1">
            <stop offset="0" stopColor="#ffe08a" />
            <stop offset="0.5" stopColor="#f6b82f" />
            <stop offset="1" stopColor="#d9940f" />
          </linearGradient>
          <linearGradient id="lb-base" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0" stopColor="#3b168d" />
            <stop offset="1" stopColor="#291064" />
          </linearGradient>
        </defs>
        {/* handles */}
        <path d="M70 46c-26 0-30 40 4 48" fill="none" stroke="#e9a215" strokeWidth="9" strokeLinecap="round" />
        <path d="M150 46c26 0 30 40-4 48" fill="none" stroke="#e9a215" strokeWidth="9" strokeLinecap="round" />
        {/* cup */}
        <path d="M66 30h88v26c0 30-20 52-44 52S66 86 66 56z" fill="url(#lb-cup)" />
        <path d="M78 36h12v22c0 16 7 30 18 36-17-2-30-18-30-36z" fill="#fff" opacity="0.35" />
        {/* star */}
        <path d="m110 44 5.3 10.8 11.9 1.7-8.6 8.4 2 11.8L110 71.1l-10.6 5.6 2-11.8-8.6-8.4 11.9-1.7z" fill="#fff8e1" />
        {/* stem + base */}
        <rect x="102" y="106" width="16" height="18" rx="3" fill="#e9a215" />
        <rect x="84" y="124" width="52" height="12" rx="4" fill="url(#lb-cup)" />
        <rect x="74" y="136" width="72" height="22" rx="6" fill="url(#lb-base)" />
        <rect x="94" y="142" width="32" height="10" rx="3" fill="#f6b82f" opacity="0.9" />
      </svg>
      {/* sparkles & chips around the cup */}
      <svg viewBox="0 0 24 24" className="lb-float absolute left-6 top-6 size-5 fill-lb-gold [animation-delay:0.8s]"><path d="M12 0l2.6 9.4L24 12l-9.4 2.6L12 24l-2.6-9.4L0 12l9.4-2.6z" /></svg>
      <svg viewBox="0 0 24 24" className="lb-float absolute right-8 top-12 size-3.5 fill-lb-purple/70 [animation-delay:1.6s]"><path d="M12 0l2.6 9.4L24 12l-9.4 2.6L12 24l-2.6-9.4L0 12l9.4-2.6z" /></svg>
      <svg viewBox="0 0 24 24" className="lb-float absolute bottom-10 left-10 size-3 fill-lb-gold/80 [animation-delay:2.2s]"><path d="M12 0l2.6 9.4L24 12l-9.4 2.6L12 24l-2.6-9.4L0 12l9.4-2.6z" /></svg>
      <span className="absolute bottom-7 right-3 rotate-6 rounded-full bg-white px-2.5 py-1 text-xs font-extrabold text-lb-purple shadow-[0_6px_16px_-6px_rgba(41,16,100,0.4)]">+XP</span>
      <span className="absolute left-1 top-[4.5rem] -rotate-6 rounded-full bg-lb-purple px-2.5 py-1 text-xs font-extrabold text-lb-gold shadow-[0_6px_16px_-6px_rgba(41,16,100,0.5)]">#1</span>
    </div>
  )
}

function Stat({ icon, label, value, loading, accent = false }: { icon: ReactNode; label: string; value: ReactNode; loading?: boolean; accent?: boolean }) {
  return (
    <div className="flex min-w-0 items-center gap-2 rounded-xl bg-white/80 px-2.5 py-2 shadow-[0_0_0_1px_rgba(41,16,100,0.06)] sm:gap-2.5 sm:px-3">
      <span className={accent ? 'hidden size-8 shrink-0 sm:inline-flex items-center justify-center rounded-lg bg-lb-gold-soft text-lb-gold-dark' : 'hidden size-8 shrink-0 sm:inline-flex items-center justify-center rounded-lg bg-lb-purple-50 text-lb-purple'}>
        {icon}
      </span>
      <span className="min-w-0">
        <span className="block text-[11px] font-medium leading-tight text-lb-muted">{label}</span>
        {loading ? <Skeleton className="mt-1 h-4 w-20" /> : <span className="block truncate text-sm font-bold text-lb-ink">{value}</span>}
      </span>
    </div>
  )
}

/** The page head: what is ranked, real counts from the API, the period and
 * when the data last changed. Compact — the podium is the star. */
export function Hero({ description, students, groups, period, updatedAt }: {
  description: string
  students: number | undefined
  groups: number | undefined
  period: LeaderboardPeriod | undefined
  updatedAt: string | null | undefined
}) {
  return (
    <section className="lb-rise relative overflow-hidden rounded-3xl bg-gradient-to-br from-white via-white to-[#f3eefe] shadow-[0_0_0_1px_rgba(41,16,100,0.06),0_16px_40px_-24px_rgba(41,16,100,0.35)]">
      <div aria-hidden className="pointer-events-none absolute -right-20 -top-28 size-80 rounded-full bg-[radial-gradient(circle,rgba(59,22,141,0.16),transparent_65%)]" />
      <div aria-hidden className="pointer-events-none absolute -bottom-24 right-40 size-64 rounded-full bg-[radial-gradient(circle,rgba(246,184,47,0.22),transparent_65%)]" />
      <div className="relative flex items-center gap-6 px-5 py-5 sm:px-7 sm:py-6">
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-lb-gold-dark">OkurmenKIDS · Leaderboard</p>
          <h1 className="mt-1.5 text-2xl font-black tracking-tight text-lb-deep sm:text-[2rem] sm:leading-tight">
            Рейтинг <span className="bg-gradient-to-r from-lb-purple to-[#6d3fd6] bg-clip-text text-transparent">лучших</span>
          </h1>
          <p className="mt-1.5 line-clamp-2 max-w-xl text-sm text-lb-muted sm:line-clamp-none">{description}</p>
          <div className="mt-4 grid grid-cols-2 gap-2 xl:grid-cols-4">
            <Stat
              icon={<GraduationCap className="size-4" aria-hidden />}
              label="Студентов"
              loading={students === undefined}
              value={students === undefined ? '' : `${formatNumber(students)} ${plural(students, ['студент', 'студента', 'студентов'])}`}
            />
            <Stat
              icon={<Users className="size-4" aria-hidden />}
              label="Групп"
              loading={groups === undefined}
              value={groups === undefined ? '' : `${formatNumber(groups)} ${plural(groups, ['группа', 'группы', 'групп'])}`}
            />
            <Stat
              accent
              icon={<CalendarRange className="size-4" aria-hidden />}
              label={period ? periodTitle(period) : 'Период'}
              loading={!period}
              value={period ? <span title={periodRange(period)}>{periodRangeShort(period)}</span> : ''}
            />
            <Stat
              icon={<Clock className="size-4" aria-hidden />}
              label="Обновлено"
              loading={updatedAt === undefined}
              value={<span title={formatDateTime(updatedAt)}>{formatDateTimeShort(updatedAt)}</span>}
            />
          </div>
        </div>
        <TrophyArt />
      </div>
    </section>
  )
}
