import type { ReactNode } from 'react'

import { cn } from '@/utils/cn'

/** Надзаголовок раздела: янтарная черта и подпись капителью. */
export function Eyebrow({ children, inverse = false }: { children: ReactNode; inverse?: boolean }) {
  return (
    <p className={cn('flex items-center gap-2.5 text-[13px] font-bold uppercase tracking-[0.18em]', inverse ? 'text-ok-amber' : 'text-ok-indigo')}>
      <span className="h-[3px] w-6 rounded-full bg-ok-amber" aria-hidden />
      {children}
    </p>
  )
}
