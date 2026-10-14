import type { ReactNode } from 'react'
import { Crown } from 'lucide-react'

import { cn } from '@/utils/cn'

import { Avatar, MEDALS } from './ui'

export interface PodiumEntry {
  key: string
  rank: number
  title: string
  subtitle?: string | null
  detail?: string | null
  value: string
  valueHint?: string
  initials: string
  hidden?: boolean
  /** Replaces the single avatar (e.g. a group's member avatars). */
  avatar?: ReactNode
}

/** Read in rank order (1 · 2 · 3), shown as 2 · 1 · 3; the bar height
 * follows the position, the medal the real rank (a tie for first shows two
 * gold medals). */
const SLOTS = [
  { index: 0, height: 'h-24 sm:h-32', order: 'order-2' },
  { index: 1, height: 'h-16 sm:h-24', order: 'order-1' },
  { index: 2, height: 'h-12 sm:h-16', order: 'order-3' },
]

export function Podium({ entries, label }: { entries: PodiumEntry[]; label: string }) {
  if (!entries.length) return null
  return (
    <ol aria-label={label} className="grid grid-cols-3 items-end gap-2 sm:gap-4">
      {SLOTS.map(({ index, height, order }) => {
        const entry = entries[index]
        if (!entry) return <li key={index} aria-hidden className={order} />
        const medal = MEDALS[Math.min(entry.rank, 3) as 1 | 2 | 3]
        const first = index === 0
        return (
          <li key={entry.key} className={cn('flex min-w-0 flex-col items-center text-center', order)}>
            <div className="relative mb-2">
              {first ? (
                <Crown className="absolute -top-5 left-1/2 size-6 -translate-x-1/2 fill-lb-gold text-lb-gold drop-shadow-sm" aria-hidden />
              ) : null}
              {entry.avatar ?? (
                <Avatar
                  initials={entry.initials}
                  seed={entry.key}
                  hidden={entry.hidden}
                  size={first ? 'xl' : 'lg'}
                  className={cn('ring-4 ring-offset-2 ring-offset-white', medal.ring)}
                />
              )}
              <span className={cn('absolute -bottom-1.5 left-1/2 inline-flex size-6 -translate-x-1/2 items-center justify-center rounded-full text-xs font-bold ring-2 ring-white', medal.chip)}>
                {entry.rank}
              </span>
            </div>
            <p className={cn('mt-1.5 w-full truncate font-semibold text-ink', first ? 'text-sm sm:text-base' : 'text-xs sm:text-sm')} title={entry.title}>
              {entry.title}
            </p>
            {entry.subtitle ? <p className="w-full truncate text-xs text-ink-secondary" title={entry.subtitle}>{entry.subtitle}</p> : null}
            {entry.detail ? <p className="hidden w-full truncate text-[11px] text-ink-muted sm:block" title={entry.detail}>{entry.detail}</p> : null}
            <p className="mt-1 text-sm font-bold tabular-nums text-lb-purple sm:text-base" title={entry.valueHint}>
              {entry.value}
            </p>
            <div
              className={cn('mt-2 flex w-full items-start justify-center rounded-t-xl bg-gradient-to-b pt-2', height, medal.bar)}
              aria-hidden
            >
              <span className={cn('text-xs font-semibold uppercase tracking-wide', entry.rank === 1 ? 'text-lb-deep/80' : 'text-white')}>{medal.label}</span>
            </div>
            <span className="sr-only">{medal.label}, {entry.rank} место</span>
          </li>
        )
      })}
    </ol>
  )
}
