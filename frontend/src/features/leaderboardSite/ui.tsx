import type { CSSProperties, HTMLAttributes, ReactNode } from 'react'
import { AlertTriangle, ArrowDown, ArrowUp, EyeOff, Minus, RefreshCw, SearchX, Trophy } from 'lucide-react'

import type { RankChange } from '@/types/leaderboard'
import { cn } from '@/utils/cn'

/** Soft brand-adjacent tints for initials avatars, picked by the row's key
 * (stable for the same student, never a photo). */
const AVATAR_TINTS = [
  'bg-gradient-to-br from-[#ece6ff] to-[#d9cdfb] text-lb-deep',
  'bg-gradient-to-br from-[#fff3d3] to-[#fde3a1] text-lb-gold-dark',
  'bg-gradient-to-br from-[#e0f2fe] to-[#bfe3fb] text-[#075985]',
  'bg-gradient-to-br from-[#dcfce7] to-[#bbf0cf] text-[#166534]',
  'bg-gradient-to-br from-[#fce7f3] to-[#f8cbe3] text-[#9d174d]',
  'bg-gradient-to-br from-[#ffe9dc] to-[#fccfb3] text-[#9a3412]',
]

function tint(seed: string): string {
  let hash = 0
  for (const char of seed) hash = (hash * 31 + char.charCodeAt(0)) >>> 0
  return AVATAR_TINTS[hash % AVATAR_TINTS.length]
}

export function Avatar({ initials, seed, hidden = false, size = 'md', className }: {
  initials: string
  seed: string
  hidden?: boolean
  size?: 'sm' | 'md' | 'lg' | 'xl'
  className?: string
}) {
  const sizes = { sm: 'size-7 text-[10px] tracking-tighter', md: 'size-9 text-xs', lg: 'size-14 text-base', xl: 'size-[4.5rem] text-xl' }
  return (
    <span
      aria-hidden
      className={cn(
        'inline-flex shrink-0 select-none items-center justify-center rounded-full font-bold',
        sizes[size],
        hidden ? 'bg-lb-line text-lb-muted' : tint(seed),
        className,
      )}
    >
      {hidden ? <EyeOff className="size-[45%]" /> : initials || '?'}
    </span>
  )
}

/** ▲ +3 / ▼ −2 / — 0 / NEW; null — no previous data (neutral, never invented). */
export function RankChangeBadge({ change, className }: { change: RankChange; className?: string }) {
  const base = 'inline-flex h-6 items-center gap-0.5 whitespace-nowrap rounded-full px-2 text-xs font-bold tabular-nums'
  if (!change) {
    return <span className={cn(base, 'text-lb-muted/70', className)} title="Нет данных за прошлый период">—</span>
  }
  if (change.status === 'new') {
    return <span className={cn(base, 'bg-lb-gold-soft text-lb-gold-dark', className)} title="Впервые в рейтинге">NEW</span>
  }
  if (change.status === 'up') {
    return (
      <span className={cn(base, 'bg-[#e3f7ee] text-lb-success', className)} title={`Поднялся на ${change.value}`}>
        <ArrowUp className="size-3" strokeWidth={3} aria-hidden />+{change.value}
        <span className="sr-only"> позиций вверх</span>
      </span>
    )
  }
  if (change.status === 'down') {
    return (
      <span className={cn(base, 'bg-[#fdecec] text-[#d32f2f]', className)} title={`Опустился на ${-change.value}`}>
        <ArrowDown className="size-3" strokeWidth={3} aria-hidden />−{-change.value}
        <span className="sr-only"> позиций вниз</span>
      </span>
    )
  }
  return (
    <span className={cn(base, 'bg-lb-bg text-lb-muted', className)} title="Позиция не изменилась">
      <Minus className="size-3" strokeWidth={3} aria-hidden />0
    </span>
  )
}

export const MEDALS = {
  1: {
    label: 'Золото',
    ring: 'ring-lb-gold',
    chip: 'bg-gradient-to-br from-[#ffd56b] to-lb-gold text-lb-deep shadow-[0_2px_6px_-1px_rgba(246,184,47,0.6)]',
    pedestal: 'from-[#ffd76e] via-lb-gold to-[#e9a215]',
    soft: 'bg-lb-gold-soft',
    text: 'text-lb-deep',
  },
  2: {
    label: 'Серебро',
    ring: 'ring-lb-silver',
    chip: 'bg-gradient-to-br from-[#d7dce7] to-lb-silver text-white shadow-[0_2px_6px_-1px_rgba(120,130,155,0.5)]',
    pedestal: 'from-[#e3e7ef] via-[#c3cad8] to-lb-silver',
    soft: 'bg-lb-silver-soft',
    text: 'text-white',
  },
  3: {
    label: 'Бронза',
    ring: 'ring-lb-bronze',
    chip: 'bg-gradient-to-br from-[#eab088] to-lb-bronze text-white shadow-[0_2px_6px_-1px_rgba(205,131,70,0.55)]',
    pedestal: 'from-[#f1c4a0] via-[#dc9a64] to-lb-bronze',
    soft: 'bg-lb-bronze-soft',
    text: 'text-white',
  },
} as const

export function RankNumber({ rank, size = 'md' }: { rank: number; size?: 'sm' | 'md' }) {
  const medal = MEDALS[rank as 1 | 2 | 3]
  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center justify-center rounded-full font-extrabold tabular-nums',
        size === 'sm' ? 'size-7 text-xs' : 'size-8 text-sm',
        medal ? medal.chip : 'bg-lb-bg text-lb-muted ring-1 ring-lb-line',
      )}
      aria-label={`${rank} место`}
    >
      {rank}
    </span>
  )
}

export function Panel({ children, className, ...rest }: { children: ReactNode; className?: string } & HTMLAttributes<HTMLElement>) {
  return (
    <section
      className={cn(
        'lb-rise rounded-2xl bg-white shadow-[0_0_0_1px_rgba(41,16,100,0.06),0_1px_2px_rgba(41,16,100,0.04),0_12px_32px_-16px_rgba(41,16,100,0.18)]',
        className,
      )}
      {...rest}
    >
      {children}
    </section>
  )
}

export function Skeleton({ className, style }: { className?: string; style?: CSSProperties }) {
  return <span aria-hidden style={style} className={cn('block animate-pulse rounded-md bg-lb-line/80', className)} />
}

export function RowsSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div role="status" aria-label="Загрузка рейтинга" className="divide-y divide-lb-line">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-3 px-4 py-3 sm:px-5">
          <Skeleton className="size-8 rounded-full" />
          <Skeleton className="size-9 rounded-full" />
          <div className="flex-1 space-y-1.5">
            <Skeleton className="h-3.5 w-2/5" />
            <Skeleton className="h-3 w-1/4" />
          </div>
          <Skeleton className="h-5 w-16 rounded-full" />
        </div>
      ))}
    </div>
  )
}

export function PodiumSkeleton() {
  return (
    <div role="status" aria-label="Загрузка пьедестала" className="grid grid-cols-3 items-end gap-2 sm:gap-4">
      {[96, 132, 80].map((h, i) => (
        <div key={i} className="flex flex-col items-center gap-2">
          <Skeleton className="size-14 rounded-full sm:size-[4.5rem]" />
          <Skeleton className="h-3.5 w-3/4" />
          <Skeleton className="h-3 w-1/2" />
          <Skeleton className="w-full rounded-b-none rounded-t-2xl" style={{ height: h }} />
        </div>
      ))}
    </div>
  )
}

export function EmptyState({ title, description, kind = 'empty' }: { title: string; description?: string; kind?: 'empty' | 'search' }) {
  const Icon = kind === 'search' ? SearchX : Trophy
  return (
    <div className="flex flex-col items-center px-6 py-10 text-center">
      <span className="mb-3 inline-flex size-14 items-center justify-center rounded-2xl bg-gradient-to-br from-lb-gold-soft to-lb-purple-50 text-lb-purple">
        <Icon className="size-6" aria-hidden />
      </span>
      <p className="font-bold text-lb-ink">{title}</p>
      {description ? <p className="mt-1 max-w-sm text-sm text-lb-muted">{description}</p> : null}
    </div>
  )
}

export function ErrorState({ onRetry, message }: { onRetry: () => void; message?: string }) {
  return (
    <div role="alert" className="flex flex-col items-center px-6 py-10 text-center">
      <span className="mb-3 inline-flex size-14 items-center justify-center rounded-2xl bg-[#fdecec] text-lb-danger">
        <AlertTriangle className="size-6" aria-hidden />
      </span>
      <p className="font-bold text-lb-ink">Не удалось загрузить рейтинг</p>
      <p className="mt-1 max-w-sm text-sm text-lb-muted">{message ?? 'Проверьте подключение к интернету и попробуйте ещё раз.'}</p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-4 inline-flex h-10 items-center gap-2 rounded-xl bg-lb-purple px-5 text-sm font-semibold text-white shadow-[0_6px_16px_-6px_rgba(59,22,141,0.6)] transition hover:bg-lb-deep focus-visible:outline-lb-purple"
      >
        <RefreshCw className="size-4" aria-hidden />
        Повторить
      </button>
    </div>
  )
}

export function LoadMoreButton({ onClick, loading, shown, total }: { onClick: () => void; loading: boolean; shown: number; total: number }) {
  return (
    <div className="flex flex-col items-center gap-1.5 border-t border-lb-line px-4 py-4">
      <button
        type="button"
        onClick={onClick}
        disabled={loading}
        className="inline-flex h-10 items-center gap-2 rounded-xl bg-lb-purple-50 px-5 text-sm font-semibold text-lb-purple transition hover:bg-lb-purple-100 disabled:cursor-wait disabled:opacity-60 focus-visible:outline-lb-purple"
      >
        {loading ? <RefreshCw className="size-4 animate-spin" aria-hidden /> : null}
        Показать ещё
      </button>
      <span className="text-xs text-lb-muted">Показано {shown} из {total}</span>
    </div>
  )
}

/** A compact «i» with an explanation on hover / focus (and for screen readers). */
export function InfoHint({ label, children }: { label: string; children: ReactNode }) {
  return (
    <span className="group relative inline-flex">
      <button
        type="button"
        aria-label={label}
        className="inline-flex size-5 items-center justify-center rounded-full bg-lb-purple-50 text-[11px] font-bold text-lb-purple transition hover:bg-lb-purple-100 focus-visible:outline-lb-purple"
      >
        i
      </button>
      <span
        role="tooltip"
        className="pointer-events-none invisible absolute left-1/2 top-full z-30 mt-2 w-64 -translate-x-1/2 rounded-xl bg-lb-deep px-3 py-2.5 text-xs font-normal leading-relaxed text-white opacity-0 shadow-xl transition group-focus-within:visible group-focus-within:opacity-100 group-hover:visible group-hover:opacity-100"
      >
        {children}
      </span>
    </span>
  )
}
