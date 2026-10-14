import type { ReactNode } from 'react'
import { Crown, Medal, Sparkle } from 'lucide-react'

import { cn } from '@/utils/cn'

import { Avatar, MEDALS } from './ui'

export interface PodiumEntry {
  key: string
  rank: number
  title: string
  subtitle?: string | null
  detail?: string | null
  value: string
  /** A small caption under the value («за период», «XP на студента»). */
  valueCaption?: string
  valueHint?: string
  initials: string
  hidden?: boolean
  /** Replaces the single avatar (e.g. a group's member avatars). */
  avatar?: ReactNode
}

/** Read in rank order (1 · 2 · 3), shown as 2 · 1 · 3. The pedestal height
 * follows the position, the medal the real rank (a tie for first shows two
 * gold medals). */
const SLOTS = [
  { index: 0, pedestal: 'h-20 sm:h-28', order: 'order-2', delay: '0ms' },
  { index: 1, pedestal: 'h-14 sm:h-20', order: 'order-1', delay: '90ms' },
  { index: 2, pedestal: 'h-10 sm:h-14', order: 'order-3', delay: '160ms' },
]

function PodiumCard({ entry, position }: { entry: PodiumEntry; position: number }) {
  const medal = MEDALS[Math.min(entry.rank, 3) as 1 | 2 | 3]
  const lead = position === 0
  return (
    <div
      className={cn(
        'relative flex w-full flex-col items-center rounded-2xl px-2 pb-3 text-center transition duration-300 hover:-translate-y-0.5 sm:px-4 sm:pb-4',
        lead
          ? 'bg-gradient-to-b from-[#fff8e4] to-white pt-7 shadow-[0_0_0_1px_rgba(246,184,47,0.45),0_18px_40px_-18px_rgba(246,184,47,0.75)] sm:pt-9'
          : 'bg-white pt-5 shadow-[0_0_0_1px_rgba(41,16,100,0.07),0_10px_28px_-18px_rgba(41,16,100,0.35)] sm:pt-6',
      )}
    >
      {lead ? (
        <>
          <Sparkle className="lb-float absolute left-3 top-3 size-3 fill-lb-gold text-lb-gold sm:left-4 sm:size-4" aria-hidden />
          <Sparkle className="lb-float absolute right-4 top-6 size-2.5 fill-lb-gold/70 text-lb-gold/70 [animation-delay:1.2s] sm:size-3" aria-hidden />
        </>
      ) : null}
      <div className="relative">
        {lead ? (
          <Crown className="lb-float absolute -top-6 left-1/2 size-7 -translate-x-1/2 fill-lb-gold text-[#e9a215] drop-shadow-[0_2px_4px_rgba(233,162,21,0.45)] sm:-top-7 sm:size-8" aria-hidden />
        ) : null}
        {entry.avatar ?? (
          <Avatar
            initials={entry.initials}
            seed={entry.key}
            hidden={entry.hidden}
            size={lead ? 'xl' : 'lg'}
            className={cn('ring-[3px] ring-offset-2 ring-offset-white', medal.ring, lead && 'ring-4')}
          />
        )}
        {!lead ? (
          <span className={cn('absolute -bottom-1 -right-1 inline-flex size-6 items-center justify-center rounded-full ring-2 ring-white', medal.chip)}>
            <Medal className="size-3.5" aria-hidden />
          </span>
        ) : null}
      </div>
      <p className={cn('mt-3 w-full truncate font-bold text-lb-ink', lead ? 'text-sm sm:text-lg' : 'text-xs sm:text-base')} title={entry.title}>
        {entry.title}
      </p>
      {entry.subtitle ? <p className="w-full truncate text-[11px] text-lb-muted sm:text-xs" title={entry.subtitle}>{entry.subtitle}</p> : null}
      {entry.detail ? <p className="hidden w-full truncate text-[11px] text-lb-muted/80 sm:block" title={entry.detail}>{entry.detail}</p> : null}
      <p
        className={cn(
          'mt-2 inline-flex max-w-full items-baseline gap-1 rounded-full px-2.5 py-1 font-extrabold tabular-nums sm:px-3',
          lead ? 'bg-lb-gold text-sm text-lb-deep sm:text-lg' : cn(medal.soft, 'text-xs text-lb-deep sm:text-sm'),
        )}
        title={entry.valueHint}
      >
        <span className="truncate">{entry.value}</span>
      </p>
      {entry.valueCaption ? <p className="mt-1 hidden text-[11px] text-lb-muted sm:block">{entry.valueCaption}</p> : null}
    </div>
  )
}

export function Podium({ entries, label }: { entries: PodiumEntry[]; label: string }) {
  if (!entries.length) return null
  return (
    <ol aria-label={label} className="grid grid-cols-3 items-end gap-2 sm:gap-4">
      {SLOTS.map(({ index, pedestal, order, delay }) => {
        const entry = entries[index]
        if (!entry) return <li key={index} aria-hidden className={order} />
        const medal = MEDALS[Math.min(entry.rank, 3) as 1 | 2 | 3]
        const lead = index === 0
        return (
          <li key={entry.key} className={cn('lb-rise flex min-w-0 flex-col items-center', order)} style={{ animationDelay: delay }}>
            <PodiumCard entry={entry} position={index} />
            <div
              aria-hidden
              className={cn(
                'mx-auto mt-2 flex w-[88%] items-center justify-center rounded-t-2xl bg-gradient-to-b',
                medal.pedestal,
                pedestal,
                lead && 'lb-shine',
              )}
            >
              <span className={cn('font-black leading-none tabular-nums drop-shadow-sm', medal.text, lead ? 'text-4xl sm:text-6xl' : 'text-2xl sm:text-4xl', !lead && 'opacity-90')}>
                {entry.rank}
              </span>
            </div>
            <span className="sr-only">{medal.label}, {entry.rank} место</span>
          </li>
        )
      })}
    </ol>
  )
}
