import { useId } from 'react'
import type { ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'

import { useOverlay } from '@/hooks/useOverlay'
import { cn } from '@/utils/cn'

export interface ModalProps {
  isOpen: boolean
  onClose: () => void
  title: string
  /** Optional small icon shown before the title (decorative). */
  icon?: ReactNode
  children: ReactNode
  /** `md` (512px) for forms/confirmations, `lg` (672px) for richer content. */
  size?: 'md' | 'lg'
  className?: string
}

const SIZE_CLASSES = { md: 'max-w-lg', lg: 'max-w-2xl' } as const

/**
 * The one dialog. Always 16px from every screen edge on a phone, capped at
 * the viewport height with its body scrolling inside — so a long form never
 * pushes the dialog off-screen.
 */
export function Modal({ isOpen, onClose, title, icon, children, size = 'md', className }: ModalProps) {
  const titleId = useId()
  useOverlay(isOpen, onClose)

  if (!isOpen) return null

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <button type="button" aria-label="Закрыть" className="absolute inset-0 bg-ink/40" onClick={onClose} />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={cn(
          'relative z-10 flex max-h-[calc(100dvh-2rem)] w-full flex-col overflow-hidden rounded-2xl bg-surface shadow-xl',
          SIZE_CLASSES[size],
          className,
        )}
      >
        <div className="flex shrink-0 items-start justify-between gap-3 px-4 pt-4 pb-3 sm:px-6 sm:pt-6">
          <h2 id={titleId} className="flex min-w-0 items-center gap-2 text-lg font-semibold text-ink">
            {icon}
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Закрыть окно"
            className="flex size-8 shrink-0 items-center justify-center rounded-full text-ink-muted hover:bg-surface-hover"
          >
            <X className="size-4" aria-hidden />
          </button>
        </div>
        <div className="min-h-0 overflow-y-auto px-4 pb-4 sm:px-6 sm:pb-6">{children}</div>
      </div>
    </div>,
    document.body,
  )
}
