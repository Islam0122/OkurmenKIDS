import { AlertTriangle } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { cn } from '@/utils/cn'

export interface ErrorStateProps {
  title?: string
  message?: string
  onRetry?: () => void
  className?: string
}

export function ErrorState({
  title = 'Не удалось загрузить данные',
  message = 'Проверьте соединение и попробуйте ещё раз.',
  onRetry,
  className,
}: ErrorStateProps) {
  return (
    <div className={cn('flex flex-col items-center justify-center gap-3 rounded-xl border border-border bg-surface py-14 text-center', className)}>
      <span className="flex size-11 items-center justify-center rounded-full bg-danger-soft text-danger">
        <AlertTriangle className="size-5" aria-hidden />
      </span>
      <div>
        <p className="font-medium text-ink">{title}</p>
        <p className="mt-1 text-sm text-ink-secondary">{message}</p>
      </div>
      {onRetry ? (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Повторить
        </Button>
      ) : null}
    </div>
  )
}
