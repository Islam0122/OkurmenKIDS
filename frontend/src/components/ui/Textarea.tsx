import { forwardRef } from 'react'
import type { TextareaHTMLAttributes } from 'react'

import { cn } from '@/utils/cn'

export type TextareaProps = TextareaHTMLAttributes<HTMLTextAreaElement>

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { className, rows = 4, ...rest },
  ref,
) {
  return (
    <textarea
      ref={ref}
      rows={rows}
      className={cn(
        'w-full resize-y rounded-lg border border-border bg-surface px-3 py-2 text-sm text-ink focus-visible:border-brand-500',
        className,
      )}
      {...rest}
    />
  )
})
