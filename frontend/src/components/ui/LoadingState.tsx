import { Loader2 } from 'lucide-react'

import { BrandWordmark } from '@/components/brand/BrandWordmark'
import { cn } from '@/utils/cn'

export interface LoadingStateProps {
  label?: string
  fullScreen?: boolean
  className?: string
}

export function LoadingState({ label = 'Загрузка…', fullScreen = false, className }: LoadingStateProps) {
  return (
    <div
      role="status"
      className={cn(
        'flex flex-col items-center justify-center gap-3 px-4 py-12 text-ink-secondary',
        fullScreen && 'min-h-dvh',
        className,
      )}
    >
      {fullScreen ? (
        <span className="mb-2 text-center font-display" aria-hidden>
          <BrandWordmark subtitle className="text-base tracking-[0.08em]" subtitleClassName="mt-1 text-[10px] tracking-[0.18em]" />
        </span>
      ) : null}
      <Loader2 className="size-6 animate-spin text-brand-500" aria-hidden />
      <p className="text-sm">{label}</p>
    </div>
  )
}
