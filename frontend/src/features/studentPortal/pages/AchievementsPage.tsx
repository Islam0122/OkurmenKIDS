import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Award, BookOpenCheck, CalendarCheck2, Flame, History, Lock, PartyPopper, Sparkles, Star, Target, Trophy, Zap,
} from 'lucide-react'

import { studentPortalApi } from '@/api/studentPortal'
import { cn } from '@/utils/cn'
import type {
  AchievementCategory, AchievementCode, AchievementsOverview, CollectionItem, Goal, Rarity, TimelineEvent, WeeklyDay,
} from '@/types/studentPortal'

import { LIVE_QUERY, PORTAL_KEY, usePortal } from '../context'
import { usePortalI18n } from '../i18n'
import type { TFunction } from '../i18n'
import { Bar, Empty, LoadError, PageTitle, PCard, Skeleton } from '../ui'

/**
 * «Жетишкендиктер» — level, collectible achievements, next goals, weekly
 * activity and a timeline (backend: portal.services.gamification). Every
 * number is the LMS's own: XP by the leaderboard rules, levels by their real
 * thresholds, achievements unlocked only by real records (with the date of
 * the record that unlocked them). Nothing here is mocked or invented.
 *
 * «New» badges and the level-up celebration compare with what this device
 * saw last time (localStorage); the first visit only remembers, it never
 * celebrates something that may be old.
 */

const CODE_ICON: Record<AchievementCode, typeof Star> = {
  homework_done: BookOpenCheck,
  top_homework: Star,
  attendance: CalendarCheck2,
  level: Sparkles,
  perfect_month: Flame,
  scholarship: Trophy,
}

/** Medallion colours per rarity (fill gradient, rim, label pill). */
const RARITY: Record<Rarity, { from: string; to: string; rim: string; pill: string; glow: string }> = {
  common: { from: '#7d8a83', to: '#4f5b55', rim: '#cbd6cf', pill: 'bg-surface-muted text-ink-secondary ring-1 ring-border', glow: '' },
  rare: { from: '#3b82c4', to: '#1f4f8a', rim: '#bcd6f0', pill: 'bg-info-soft text-info', glow: 'shadow-[0_10px_28px_-14px_rgba(37,99,168,0.6)]' },
  epic: { from: '#2f8f5b', to: '#164a2e', rim: '#a3d3bb', pill: 'bg-brand-50 text-brand-700', glow: 'shadow-[0_10px_28px_-14px_rgba(31,95,60,0.65)]' },
  legendary: { from: '#f6c453', to: '#b7791f', rim: '#fde7a8', pill: 'bg-[#fff4d6] text-[#8a5a00]', glow: 'shadow-[0_12px_32px_-12px_rgba(183,121,31,0.7)]' },
}

const SERIES = [
  { key: 'xp_attendance', color: '#2f8f5b', label: 'gam.part.attendance' },
  { key: 'xp_homework', color: '#2563a8', label: 'gam.part.homework' },
  { key: 'xp_tests', color: '#c27c0e', label: 'gam.part.tests' },
] as const

function store<T>(key: string, fallback: T): [() => T, (value: T) => void] {
  return [
    () => {
      try {
        const raw = window.localStorage.getItem(key)
        return raw === null ? fallback : (JSON.parse(raw) as T)
      } catch {
        return fallback
      }
    },
    (value: T) => {
      try { window.localStorage.setItem(key, JSON.stringify(value)) } catch { /* private mode */ }
    },
  ]
}

export function itemName(t: TFunction, month: (i: number) => string, item: CollectionItem): string {
  if (item.code === 'level') return t('gam.a.level.name', { n: item.threshold })
  const base = t(`gam.a.${item.code}.name`)
  if (item.code === 'perfect_month' && item.params) return `${base} · ${month(item.params.month)} ${item.params.year}`
  if (item.code === 'scholarship') return item.params?.rank ? `${base} · ${t('gam.rank', { n: item.params.rank })}` : base
  return `${base} · ${item.threshold}`
}

function itemDesc(t: TFunction, item: { code: AchievementCode; threshold?: number; target?: number }): string {
  return t(`gam.a.${item.code}.desc`, { n: item.threshold ?? item.target ?? 0 })
}

// ---------------------------------------------------------------------------
// Medallion
// ---------------------------------------------------------------------------

function Medallion({ item, size = 72, fresh = false }: { item: CollectionItem; size?: number; fresh?: boolean }) {
  const Icon = CODE_ICON[item.code]
  const r = RARITY[item.rarity]
  const id = `grad-${item.id}`
  return (
    <span className={cn('relative inline-flex shrink-0', fresh && 'sp-pop')} style={{ width: size, height: size }}>
      <svg viewBox="0 0 72 72" width={size} height={size} aria-hidden className={cn(item.unlocked ? r.glow : '', 'rounded-full')}>
        <defs>
          <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor={item.unlocked ? r.from : '#e5ebe7'} />
            <stop offset="1" stopColor={item.unlocked ? r.to : '#cfd8d2'} />
          </linearGradient>
        </defs>
        {/* Hexagonal medal with a rim and an inner facet. */}
        <path d="M36 3l28.6 16.5v33L36 69 7.4 52.5v-33z" fill={item.unlocked ? r.rim : '#eef2ef'} />
        <path d="M36 9l23.4 13.5v27L36 63 12.6 49.5v-27z" fill={`url(#${id})`} />
        <path d="M36 9l23.4 13.5L36 36 12.6 22.5z" fill="#fff" opacity={item.unlocked ? 0.16 : 0.35} />
      </svg>
      <span className={cn('absolute inset-0 flex items-center justify-center', item.unlocked ? 'text-white' : 'text-[#9aa79f]')}>
        <Icon className="size-[38%]" aria-hidden strokeWidth={2.2} />
      </span>
      {!item.unlocked ? (
        <span className="absolute -bottom-0.5 -right-0.5 flex size-6 items-center justify-center rounded-full bg-surface text-ink-muted shadow ring-1 ring-border">
          <Lock className="size-3.5" aria-hidden />
        </span>
      ) : null}
      {item.unlocked && item.rarity === 'legendary' ? <span className="sp-shine pointer-events-none absolute inset-[12%] rounded-full" aria-hidden /> : null}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Level card
// ---------------------------------------------------------------------------

function LevelCard({ data }: { data: AchievementsOverview }) {
  const { t } = usePortalI18n()
  const { level, xp } = data
  const [shown, setShown] = useState(0)
  useEffect(() => {
    const timer = window.setTimeout(() => setShown(level.progress), 60)
    return () => window.clearTimeout(timer)
  }, [level.progress])
  const size = 168
  const stroke = 14
  const radius = (size - stroke) / 2
  const circumference = 2 * Math.PI * radius
  const bucket = Math.min(3, Math.floor(level.progress / 25)) as 0 | 1 | 2 | 3
  const parts = [
    { key: 'attendance', icon: CalendarCheck2, value: xp.total.attendance, color: SERIES[0].color },
    { key: 'homework', icon: BookOpenCheck, value: xp.total.homework, color: SERIES[1].color },
    { key: 'tests', icon: Target, value: xp.total.tests, color: SERIES[2].color },
  ] as const

  return (
    <section className="sp-card sp-rise relative overflow-hidden p-5 sm:p-7">
      <div className="relative flex flex-col items-center gap-6 sm:flex-row sm:items-center">
        <div className="relative shrink-0" style={{ width: size, height: size }}
          role="img" aria-label={`${t('gam.levelLabel')} ${level.level}: ${level.progress}%`}>
          <svg width={size} height={size} className="-rotate-90">
            <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="var(--color-brand-50)" strokeWidth={stroke} />
            <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="url(#lvl)" strokeWidth={stroke} strokeLinecap="round"
              strokeDasharray={`${(shown / 100) * circumference} ${circumference}`}
              className="motion-safe:transition-[stroke-dasharray] motion-safe:duration-1000 motion-safe:ease-out" />
            <defs>
              <linearGradient id="lvl" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0" stopColor="#3aa36b" /><stop offset="1" stopColor="#1f5f3c" />
              </linearGradient>
            </defs>
          </svg>
          <span className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-[11px] font-bold uppercase tracking-[0.12em] text-ink-muted">{t('gam.levelLabel')}</span>
            <span className="text-5xl font-extrabold leading-none tabular-nums text-ink">{level.level}</span>
            <span className="mt-1 text-xs font-bold tabular-nums text-brand-600">{level.progress}%</span>
          </span>
        </div>

        <div className="min-w-0 flex-1 text-center sm:text-left">
          <p className="text-xs font-bold uppercase tracking-[0.1em] text-brand-600">{t('gam.totalXp')}</p>
          <p className="text-5xl font-extrabold tabular-nums tracking-tight text-ink">
            {level.total_xp}<span className="ml-1.5 text-xl font-bold text-ink-muted">XP</span>
          </p>
          <p className="mt-1 text-sm font-medium text-ink-secondary">{t('gam.toNext', { n: level.level + 1, xp: level.to_next })}</p>
          <Bar value={level.progress} className="mt-3 h-3" />
          <p className="mt-1.5 flex justify-between text-[11px] font-semibold tabular-nums text-ink-muted">
            <span>{level.floor} XP</span><span>{level.next} XP</span>
          </p>
          <p className="mt-3 rounded-2xl bg-brand-50/70 px-3.5 py-2.5 text-sm font-semibold text-brand-700">{t(`gam.msg.${bucket}`)}</p>
        </div>
      </div>

      <div className="relative mt-6">
        <p className="mb-2 flex items-center justify-between text-xs font-bold text-ink-secondary">
          <span>{t('gam.breakdown')}</span><span className="text-brand-600">{t('gam.thisMonth', { n: xp.month.total })}</span>
        </p>
        <div className="grid grid-cols-3 gap-2 sm:gap-3">
          {parts.map(({ key, icon: Icon, value, color }) => (
            <div key={key} className="rounded-2xl bg-surface-muted p-3 ring-1 ring-border/50">
              <p className="flex items-center gap-1.5 text-[11px] font-semibold text-ink-secondary sm:text-xs">
                <span className="size-2 shrink-0 rounded-full" style={{ background: color }} aria-hidden />
                <Icon className="hidden size-3.5 sm:block" aria-hidden />{t(`gam.part.${key}`)}
              </p>
              <p className="mt-1 text-lg font-extrabold tabular-nums text-ink sm:text-xl">+{value}</p>
            </div>
          ))}
        </div>
        {/* Projects earn no XP in the LMS (xp.projects_supported = false) — no line for them. */}
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Collection
// ---------------------------------------------------------------------------

function BadgeCard({ item, fresh }: { item: CollectionItem; fresh: boolean }) {
  const { t, date, month } = usePortalI18n()
  const r = RARITY[item.rarity]
  const condition = itemDesc(t, item)
  return (
    <li className={cn('sp-card group relative flex flex-col items-center p-4 text-center transition-transform motion-safe:hover:-translate-y-0.5',
      !item.unlocked && 'bg-surface/70')} tabIndex={0} aria-describedby={`tip-${item.id}`}>
      {fresh ? <span className="absolute right-3 top-3 rounded-full bg-brand-600 px-2 py-0.5 text-[10px] font-extrabold uppercase text-white">{t('gam.new')}</span> : null}
      <Medallion item={item} fresh={fresh} />
      <p className={cn('mt-3 text-sm font-extrabold leading-snug tracking-tight', item.unlocked ? 'text-ink' : 'text-ink-secondary')}>{itemName(t, month, item)}</p>
      <p className="mt-0.5 line-clamp-2 text-xs text-ink-muted">{condition}</p>
      <span className={cn('mt-2.5 rounded-full px-2.5 py-0.5 text-[11px] font-bold', r.pill)}>{t(`gam.rarity.${item.rarity}`)}</span>
      {item.unlocked ? (
        <p className="mt-2 text-[11px] font-semibold text-brand-600">{t('gam.unlockedOn', { date: date(item.unlocked_on, true) })}</p>
      ) : (
        <div className="mt-2.5 w-full">
          <Bar value={item.threshold ? (item.current / item.threshold) * 100 : 0} className="h-1.5" />
          <p className="mt-1 text-[11px] font-semibold tabular-nums text-ink-muted">{t('gam.progressOf', { current: item.current, target: item.threshold })}</p>
        </div>
      )}
      {item.xp_reward ? <p className="mt-1 text-[11px] font-bold text-brand-700">{t('gam.reward', { n: item.xp_reward })}</p> : null}
      {/* Tooltip: the condition, on hover and keyboard focus. */}
      <span id={`tip-${item.id}`} role="tooltip"
        className="pointer-events-none absolute bottom-full left-1/2 z-20 mb-2 w-56 -translate-x-1/2 rounded-xl bg-ink px-3 py-2 text-left text-xs leading-snug text-white opacity-0 shadow-lg transition-opacity group-hover:opacity-100 group-focus:opacity-100">
        <b className="block text-[11px] uppercase tracking-wide text-white/70">{t('gam.condition')}</b>
        {condition}
        {!item.xp_reward ? <span className="mt-1 block text-white/70">{t('gam.noReward')}</span> : null}
      </span>
    </li>
  )
}

type StateFilter = 'all' | 'unlocked' | 'locked'

function Collection({ data, fresh }: { data: AchievementsOverview; fresh: Set<string> }) {
  const { t } = usePortalI18n()
  const [state, setState] = useState<StateFilter>('all')
  const [category, setCategory] = useState<'all' | AchievementCategory>('all')
  const items = data.achievements
    .filter((i) => state === 'all' || (state === 'unlocked' ? i.unlocked : !i.unlocked))
    .filter((i) => category === 'all' || i.category === category)
    // Unlocked first (newest first), then the nearest locked ones.
    .sort((a, b) => Number(b.unlocked) - Number(a.unlocked)
      || (b.unlocked_on ?? '').localeCompare(a.unlocked_on ?? '')
      || (b.current / (b.threshold || 1)) - (a.current / (a.threshold || 1)))
  const unlocked = data.achievements.filter((i) => i.unlocked).length

  return (
    <PCard title={t('gam.collection')} icon={<Award className="size-4" aria-hidden />}
      action={<span className="whitespace-nowrap rounded-full bg-brand-50 px-2.5 py-1 text-xs font-bold text-brand-700">{t('gam.unlockedCount', { n: unlocked, total: data.achievements.length })}</span>}>
      <div className="mb-4 flex flex-col gap-2.5">
        <div className="inline-flex w-full rounded-2xl bg-surface-muted p-1 sm:w-fit" role="tablist">
          {(['all', 'unlocked', 'locked'] as StateFilter[]).map((v) => (
            <button key={v} type="button" role="tab" aria-selected={state === v} onClick={() => setState(v)}
              className={cn('sp-press flex-1 whitespace-nowrap rounded-xl px-2.5 py-2 text-xs font-bold sm:flex-none sm:px-3.5 sm:text-sm', state === v ? 'bg-surface text-brand-700 shadow-sm' : 'text-ink-secondary hover:text-ink')}>
              {t(`gam.filter.${v}`)}
            </button>
          ))}
        </div>
        <div className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1">
          {(['all', ...data.categories] as ('all' | AchievementCategory)[]).map((c) => (
            <button key={c} type="button" aria-pressed={category === c} onClick={() => setCategory(c)}
              className={cn('sp-press shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold ring-1',
                category === c ? 'bg-ink text-white ring-ink' : 'bg-surface text-ink-secondary ring-border hover:text-ink')}>
              {t(`gam.cat.${c}`)}
            </button>
          ))}
        </div>
      </div>
      {items.length ? (
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">
          {items.map((item) => <BadgeCard key={item.id} item={item} fresh={fresh.has(item.id)} />)}
        </ul>
      ) : <Empty>{t('gam.emptyCollection')}</Empty>}
    </PCard>
  )
}

// ---------------------------------------------------------------------------
// Goals
// ---------------------------------------------------------------------------

function GoalCard({ goal }: { goal: Goal }) {
  const { t } = usePortalI18n()
  const Icon = CODE_ICON[goal.code]
  const percent = goal.target ? Math.min(100, (goal.current / goal.target) * 100) : 0
  const title = goal.code === 'level' ? t('gam.goal.level', { level: goal.params?.level ?? '' }) : itemDesc(t, goal)
  return (
    <li className="rounded-2xl bg-surface-muted/70 p-3.5 ring-1 ring-border/50">
      <div className="flex items-center gap-3">
        <span className={cn('flex size-10 shrink-0 items-center justify-center rounded-xl text-white',
          goal.rarity === 'legendary' ? 'bg-[#b7791f]' : goal.rarity === 'epic' ? 'bg-brand-700' : goal.rarity === 'rare' ? 'bg-info' : 'bg-brand-500')}>
          <Icon className="size-5" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-bold leading-snug text-ink">{title}</p>
          <p className="text-xs font-semibold text-ink-muted">
            {goal.code === 'level' ? t('gam.remainingXp', { n: goal.remaining }) : t('gam.remaining', { n: goal.remaining })}
            {goal.rarity ? <> · {t(`gam.rarity.${goal.rarity}`)}</> : null}
          </p>
        </div>
        <span className="text-xs font-extrabold tabular-nums text-ink-secondary">{goal.current}/{goal.target}</span>
      </div>
      <Bar value={percent} className="mt-2.5 h-2" />
    </li>
  )
}

// ---------------------------------------------------------------------------
// Weekly activity — stacked columns (3 series, validated palette), legend, hover, table
// ---------------------------------------------------------------------------

function WeeklyChart({ days }: { days: WeeklyDay[] }) {
  const { t, weekday, date } = usePortalI18n()
  const [hover, setHover] = useState<number | null>(null)
  const max = Math.max(10, ...days.map((d) => d.xp))
  const H = 140
  return (
    <div>
      <ul className="mb-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-secondary">
        {SERIES.map((s) => <li key={s.key} className="inline-flex items-center gap-1.5"><span className="size-2.5 rounded-sm" style={{ background: s.color }} />{t(s.label)}</li>)}
      </ul>
      <div className="relative flex items-end gap-1.5" style={{ height: H + 34 }}>
        {days.map((day, i) => {
          const dow = (new Date(`${day.date}T00:00:00`).getDay() + 6) % 7
          const isToday = i === days.length - 1
          return (
            <div key={day.date} className="flex h-full flex-1 flex-col items-center justify-end"
              onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} onFocus={() => setHover(i)} onBlur={() => setHover(null)}
              tabIndex={0} aria-label={`${weekday(dow, true)}: ${day.xp} XP`}>
              <span className="mb-1 text-[11px] font-bold tabular-nums text-ink">{day.xp ? day.xp : ''}</span>
              <div className="flex w-full max-w-7 flex-col-reverse gap-[2px]" style={{ height: (day.xp / max) * H }}>
                {SERIES.map((s) => {
                  const value = day[s.key]
                  if (!value) return null
                  return <span key={s.key} className="w-full first:rounded-b-sm last:rounded-t-[4px] motion-safe:transition-[height]" style={{ height: `${(value / day.xp) * 100}%`, background: s.color }} />
                })}
              </div>
              <span className={cn('mt-1.5 text-[11px] font-semibold', isToday ? 'text-brand-700' : 'text-ink-muted')}>{weekday(dow)}</span>
              {hover === i ? (
                <div className="pointer-events-none absolute bottom-full z-10 mb-1 w-48 rounded-xl border border-border bg-surface p-2.5 text-xs shadow-lg"
                  style={{ left: `clamp(0px, calc(${(i + 0.5) / days.length * 100}% - 6rem), calc(100% - 12rem))` }}>
                  <p className="font-bold text-ink">{weekday(dow, true)}, {date(day.date)} · {day.xp} XP</p>
                  {SERIES.map((s) => (
                    <p key={s.key} className="mt-0.5 flex items-center gap-1.5 text-ink-secondary">
                      <span className="size-2 rounded-sm" style={{ background: s.color }} />{t(s.label)}: <b className="text-ink">{day[s.key]}</b>
                    </p>
                  ))}
                  <p className="mt-1 text-ink-muted">{t('gam.dayCounts', { l: day.lessons, h: day.homework, t: day.tests })}</p>
                </div>
              ) : null}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function WeeklyCard({ data }: { data: AchievementsOverview }) {
  const { t, weekday, date } = usePortalI18n()
  const [table, setTable] = useState(false)
  const { weekly } = data
  const diff = weekly.previous_total === null ? null : weekly.total - weekly.previous_total
  return (
    <PCard title={t('gam.week')} icon={<Zap className="size-4" aria-hidden />}
      action={<button type="button" onClick={() => setTable((v) => !v)} className="sp-press rounded-lg px-2 py-1 text-xs font-bold text-brand-600 hover:bg-brand-50">{table ? t('gam.chart') : t('gam.table')}</button>}>
      <p className="text-2xl font-extrabold tabular-nums tracking-tight text-ink">{t('gam.weekTotal', { n: weekly.total })}</p>
      <p className={cn('mb-4 text-xs font-semibold', diff === null ? 'text-ink-muted' : diff >= 0 ? 'text-brand-600' : 'text-danger')}>
        {diff === null ? t('gam.noPrev') : t('gam.vsPrev', { sign: diff > 0 ? '+' : diff < 0 ? '−' : '', n: Math.abs(diff) })}
      </p>
      {table ? (
        <table className="w-full text-xs">
          <thead><tr className="text-left text-ink-muted"><th className="py-1.5" /><th>{t('gam.part.attendance')}</th><th>{t('gam.part.homework')}</th><th>{t('gam.part.tests')}</th><th className="text-right">XP</th></tr></thead>
          <tbody className="divide-y divide-border/60 tabular-nums">
            {weekly.days.map((d) => (
              <tr key={d.date}><td className="py-1.5 font-semibold text-ink">{weekday((new Date(`${d.date}T00:00:00`).getDay() + 6) % 7)} {date(d.date)}</td>
                <td>{d.xp_attendance}</td><td>{d.xp_homework}</td><td>{d.xp_tests}</td><td className="text-right font-bold text-ink">{d.xp}</td></tr>
            ))}
          </tbody>
        </table>
      ) : <WeeklyChart days={weekly.days} />}
    </PCard>
  )
}

// ---------------------------------------------------------------------------
// Timeline
// ---------------------------------------------------------------------------

function TimelineCard({ events }: { events: TimelineEvent[] }) {
  const { t, date, month } = usePortalI18n()
  return (
    <PCard title={t('gam.timeline')} icon={<History className="size-4" aria-hidden />}>
      {events.length ? (
        <ol className="relative space-y-4 before:absolute before:inset-y-1 before:left-[17px] before:w-px before:bg-border">
          {events.map((e, i) => (
            <li key={i} className="relative flex gap-3.5">
              {e.kind === 'achievement' ? (
                <span className="relative z-10"><Medallion item={e.achievement} size={36} /></span>
              ) : (
                <span className={cn('relative z-10 flex size-9 shrink-0 items-center justify-center rounded-full ring-4 ring-surface',
                  e.kind === 'level' ? 'bg-[#f6c453] text-[#6b4500]' : 'bg-brand-50 text-brand-600')}>
                  {e.kind === 'level' ? <Sparkles className="size-4" aria-hidden /> : <Zap className="size-4" aria-hidden />}
                </span>
              )}
              <div className="min-w-0 pt-1">
                <p className="text-sm font-bold text-ink">
                  {e.kind === 'xp' ? t('gam.ev.xp', { n: e.xp })
                    : e.kind === 'level' ? t('gam.ev.level', { n: e.level })
                      : <>{t('gam.ev.achievement')}: <span className="text-brand-700">{itemName(t, month, e.achievement)}</span></>}
                </p>
                <p className="text-xs text-ink-muted">
                  {date(e.date, true)}
                  {e.kind === 'xp' ? ` · ${[
                    e.parts.attendance ? `${t('gam.part.attendance')} +${e.parts.attendance}` : '',
                    e.parts.homework ? `${t('gam.part.homework')} +${e.parts.homework}` : '',
                    e.parts.tests ? `${t('gam.part.tests')} +${e.parts.tests}` : '',
                  ].filter(Boolean).join(' · ')}` : ''}
                </p>
              </div>
            </li>
          ))}
        </ol>
      ) : <Empty illustration title={t('gam.emptyTimeline')} />}
    </PCard>
  )
}

// ---------------------------------------------------------------------------
// Celebration
// ---------------------------------------------------------------------------

const CONFETTI = ['#2f8f5b', '#f6c453', '#2563a8', '#a3d3bb', '#c27c0e', '#1f5f3c']

function Celebration({ level, onClose }: { level: number; onClose: () => void }) {
  const { t } = usePortalI18n()
  const pieces = useMemo(() => Array.from({ length: 36 }, (_, i) => ({
    left: `${(i * 37) % 100}%`, delay: `${(i % 9) * 0.12}s`, color: CONFETTI[i % CONFETTI.length],
    drift: `${((i * 53) % 120) - 60}px`, spin: `${360 + ((i * 97) % 540)}deg`,
  })), [])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="sp-root fixed inset-0 z-[70] flex items-center justify-center p-6" role="dialog" aria-modal="true" aria-label={t('gam.celebrate')}>
      <button type="button" className="absolute inset-0 bg-ink/40 backdrop-blur-[2px]" aria-label={t('gam.celebrateOk')} onClick={onClose} />
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
        {pieces.map((p, i) => (
          <span key={i} className="sp-confetti-piece" style={{ left: p.left, animationDelay: p.delay, background: p.color, ['--sp-drift' as string]: p.drift, ['--sp-spin' as string]: p.spin }} />
        ))}
      </div>
      <div className="sp-card sp-pop relative w-full max-w-sm p-7 text-center">
        <span className="mx-auto flex size-20 items-center justify-center rounded-full bg-gradient-to-br from-[#f6c453] to-[#b7791f] text-white shadow-lg">
          <PartyPopper className="size-9" aria-hidden />
        </span>
        <p className="mt-4 text-2xl font-extrabold tracking-tight text-ink">{t('gam.celebrate')}</p>
        <p className="mt-1 text-sm text-ink-secondary">{t('gam.celebrateText', { n: level })}</p>
        <button type="button" onClick={onClose} autoFocus
          className="sp-press mt-5 w-full rounded-2xl bg-brand-600 px-4 py-3 text-sm font-extrabold text-white shadow-sm hover:bg-brand-700">
          {t('gam.celebrateOk')}
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

function PageSkeleton() {
  return (
    <div role="status" className="space-y-5">
      <Skeleton className="h-72" />
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">{Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="h-48" />)}</div>
        <div className="space-y-3"><Skeleton className="h-56" /><Skeleton className="h-56" /></div>
      </div>
    </div>
  )
}

export function StudentAchievementsPage() {
  const { student } = usePortal()
  const { t } = usePortalI18n()
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: [...PORTAL_KEY, 'achievements', student.id],
    queryFn: () => studentPortalApi.achievements(student.id),
    ...LIVE_QUERY,
  })

  // What this device saw last time: unlocked ids and the level.
  const [readSeen, writeSeen] = store<string[] | null>(`okk-sp-seen-badges-${student.id}`, null)
  const [readLevel, writeLevel] = store<number | null>(`okk-sp-seen-level-${student.id}`, null)
  const [fresh, setFresh] = useState<Set<string>>(new Set())
  const [celebrate, setCelebrate] = useState<number | null>(null)
  useEffect(() => {
    if (!data) return
    const unlocked = data.achievements.filter((i) => i.unlocked).map((i) => i.id)
    const seen = readSeen()
    if (seen !== null) setFresh(new Set(unlocked.filter((id) => !seen.includes(id))))
    writeSeen(unlocked)
    const lastLevel = readLevel()
    if (lastLevel !== null && data.level.level > lastLevel) setCelebrate(data.level.level)
    writeLevel(data.level.level)
  }, [data]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div>
      <PageTitle title={t('ach.title')} subtitle={t('gam.subtitle')} />
      {isPending ? <PageSkeleton /> : isError || !data ? <LoadError onRetry={() => void refetch()} /> : (
        <div className="space-y-5">
          <LevelCard data={data} />
          <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_22rem]">
            <div className="min-w-0 space-y-5">
              <Collection data={data} fresh={fresh} />
              <TimelineCard events={data.timeline} />
            </div>
            <aside className="min-w-0 space-y-5">
              <PCard title={t('gam.goals')} icon={<Target className="size-4" aria-hidden />}>
                <ul className="space-y-2.5">{data.goals.map((g) => <GoalCard key={g.code} goal={g} />)}</ul>
              </PCard>
              <WeeklyCard data={data} />
            </aside>
          </div>
        </div>
      )}
      {celebrate !== null ? <Celebration level={celebrate} onClose={() => setCelebrate(null)} /> : null}
    </div>
  )
}
