import type { ReactNode } from 'react'

import { cn } from '@/utils/cn'

type Tone = 'brand' | 'gold' | 'green' | 'gray' | 'white'

const TONES: Record<Tone, string> = {
  brand: 'bg-brand-50 text-brand-700',
  gold: 'bg-gold-100 text-gold-700',
  green: 'bg-emerald-50 text-emerald-700',
  gray: 'bg-surface-soft text-muted',
  white: 'bg-white/90 text-brand-800 shadow-sm backdrop-blur',
}

export function Badge({ tone = 'brand', children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return <span className={cn('inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-bold', TONES[tone], className)}>{children}</span>
}
