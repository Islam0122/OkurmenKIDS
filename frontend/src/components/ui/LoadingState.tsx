import { Loader2 } from 'lucide-react'

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
        'flex flex-col items-center justify-center gap-3 py-16 text-ink-secondary',
        fullScreen && 'min-h-screen',
        className,
      )}
    >
      <Loader2 className="size-6 animate-spin text-brand-500" aria-hidden />
      <p className="text-sm">{label}</p>
    </div>
  )
}
