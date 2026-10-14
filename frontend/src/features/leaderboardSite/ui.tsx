import type { HTMLAttributes, ReactNode } from 'react'
import { AlertTriangle, ArrowDown, ArrowUp, EyeOff, Minus, RefreshCw, Trophy } from 'lucide-react'

import type { RankChange } from '@/types/leaderboard'
import { cn } from '@/utils/cn'

/** Soft brand-adjacent tints for initials avatars, picked by the row's key
 * (stable for the same student, never a photo). */
const AVATAR_TINTS = [
  'bg-lb-purple-100 text-lb-deep',
  'bg-lb-gold-soft text-[#7a5300]',
  'bg-[#e0f2fe] text-[#075985]',
  'bg-[#dcfce7] text-[#166534]',
  'bg-[#fce7f3] text-[#9d174d]',
  'bg-[#ede9fe] text-[#5b21b6]',
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
  const sizes = { sm: 'size-7 text-[10px] tracking-tighter', md: 'size-9 text-xs', lg: 'size-14 text-base', xl: 'size-20 text-xl' }
  return (
    <span
      aria-hidden
      className={cn(
        'inline-flex shrink-0 select-none items-center justify-center rounded-full font-semibold',
        sizes[size],
        hidden ? 'bg-lb-line text-ink-muted' : tint(seed),
        className,
      )}
    >
      {hidden ? <EyeOff className="size-[45%]" /> : initials || '?'}
    </span>
  )
}

/** ▲ +3 / ▼ −2 / — 0 / NEW; null — no previous data (neutral, never invented). */
export function RankChangeBadge({ change, className }: { change: RankChange; className?: string }) {
  const base = 'inline-flex items-center gap-0.5 whitespace-nowrap rounded-md px-1.5 py-0.5 text-xs font-semibold tabular-nums'
  if (!change) {
    return <span className={cn(base, 'text-ink-muted', className)} title="Нет данных за прошлый период">·</span>
  }
  if (change.status === 'new') {
    return <span className={cn(base, 'bg-lb-gold-soft text-[#7a5300]', className)} title="Впервые в рейтинге">NEW</span>
  }
  if (change.status === 'up') {
    return (
      <span className={cn(base, 'bg-[#dcfce7] text-[#15803d]', className)} title={`Поднялся на ${change.value}`}>
        <ArrowUp className="size-3" aria-hidden />+{change.value}
        <span className="sr-only"> позиций вверх</span>
      </span>
    )
  }
  if (change.status === 'down') {
    return (
      <span className={cn(base, 'bg-[#fee2e2] text-[#b91c1c]', className)} title={`Опустился на ${-change.value}`}>
        <ArrowDown className="size-3" aria-hidden />−{-change.value}
        <span className="sr-only"> позиций вниз</span>
      </span>
    )
  }
  return (
    <span className={cn(base, 'text-ink-secondary', className)} title="Позиция не изменилась">
      <Minus className="size-3" aria-hidden />0
    </span>
  )
}

export const MEDALS = {
  1: { label: 'Золото', ring: 'ring-lb-gold', chip: 'bg-lb-gold text-lb-deep', bar: 'from-lb-gold/90 to-lb-gold/60' },
  2: { label: 'Серебро', ring: 'ring-lb-silver', chip: 'bg-lb-silver text-white', bar: 'from-lb-silver/80 to-lb-silver/50' },
  3: { label: 'Бронза', ring: 'ring-lb-bronze', chip: 'bg-lb-bronze text-white', bar: 'from-lb-bronze/80 to-lb-bronze/50' },
} as const

export function RankNumber({ rank }: { rank: number }) {
  const medal = MEDALS[rank as 1 | 2 | 3]
  return (
    <span
      className={cn(
        'inline-flex size-8 shrink-0 items-center justify-center rounded-full text-sm font-bold tabular-nums',
        medal ? medal.chip : 'bg-lb-bg text-ink-secondary',
      )}
      aria-label={`${rank} место`}
    >
      {rank}
    </span>
  )
}

export function Panel({ children, className, ...rest }: { children: ReactNode; className?: string } & HTMLAttributes<HTMLElement>) {
  return (
    <section className={cn('rounded-2xl border border-lb-line bg-white shadow-[0_1px_2px_rgba(36,16,94,0.04),0_8px_24px_-12px_rgba(36,16,94,0.12)]', className)} {...rest}>
      {children}
    </section>
  )
}

export function Skeleton({ className }: { className?: string }) {
  return <span aria-hidden className={cn('block animate-pulse rounded-md bg-lb-line/70', className)} />
}

export function RowsSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div role="status" aria-label="Загрузка рейтинга" className="divide-y divide-lb-line">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-3 px-4 py-3">
          <Skeleton className="size-8 rounded-full" />
          <Skeleton className="size-9 rounded-full" />
          <div className="flex-1 space-y-1.5">
            <Skeleton className="h-3.5 w-2/5" />
            <Skeleton className="h-3 w-1/4" />
          </div>
          <Skeleton className="h-4 w-14" />
        </div>
      ))}
    </div>
  )
}

export function PodiumSkeleton() {
  return (
    <div role="status" aria-label="Загрузка пьедестала" className="grid grid-cols-3 items-end gap-2 sm:gap-4">
      {[28, 36, 24].map((h, i) => (
        <div key={i} className="flex flex-col items-center gap-2">
          <Skeleton className="size-14 rounded-full sm:size-20" />
          <Skeleton className="h-3.5 w-3/4" />
          <span aria-hidden className="block w-full animate-pulse rounded-t-xl bg-lb-line/70" style={{ height: `${h * 3}px` }} />
        </div>
      ))}
    </div>
  )
}

export function EmptyState({ title, description }: { title: string; description?: string }) {
  return (
    <div className="flex flex-col items-center px-6 py-12 text-center">
      <span className="mb-3 inline-flex size-12 items-center justify-center rounded-full bg-lb-purple-50 text-lb-purple">
        <Trophy className="size-6" aria-hidden />
      </span>
      <p className="font-semibold text-ink">{title}</p>
      {description ? <p className="mt-1 max-w-sm text-sm text-ink-secondary">{description}</p> : null}
    </div>
  )
}

export function ErrorState({ onRetry, message }: { onRetry: () => void; message?: string }) {
  return (
    <div role="alert" className="flex flex-col items-center px-6 py-12 text-center">
      <span className="mb-3 inline-flex size-12 items-center justify-center rounded-full bg-[#fee2e2] text-lb-danger">
        <AlertTriangle className="size-6" aria-hidden />
      </span>
      <p className="font-semibold text-ink">Не удалось загрузить рейтинг</p>
      <p className="mt-1 max-w-sm text-sm text-ink-secondary">{message ?? 'Проверьте подключение к интернету и попробуйте ещё раз.'}</p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-4 inline-flex h-9 items-center gap-2 rounded-lg bg-lb-purple px-4 text-sm font-medium text-white transition-colors hover:bg-lb-deep focus-visible:outline-lb-purple"
      >
        <RefreshCw className="size-4" aria-hidden />
        Повторить
      </button>
    </div>
  )
}

export function LoadMoreButton({ onClick, loading, shown, total }: { onClick: () => void; loading: boolean; shown: number; total: number }) {
  return (
    <div className="flex flex-col items-center gap-1 border-t border-lb-line px-4 py-4">
      <button
        type="button"
        onClick={onClick}
        disabled={loading}
        className="inline-flex h-9 items-center gap-2 rounded-lg border border-lb-line bg-white px-4 text-sm font-medium text-lb-purple transition-colors hover:border-lb-purple-100 hover:bg-lb-purple-50 disabled:cursor-wait disabled:opacity-60"
      >
        {loading ? <RefreshCw className="size-4 animate-spin" aria-hidden /> : null}
        Показать ещё
      </button>
      <span className="text-xs text-ink-muted">Показано {shown} из {total}</span>
    </div>
  )
}
