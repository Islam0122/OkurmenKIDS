import { useId } from 'react'
import type { ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'

import { useOverlay } from '@/hooks/useOverlay'
import { cn } from '@/utils/cn'

export interface DrawerProps {
  isOpen: boolean
  onClose: () => void
  title: string
  children: ReactNode
  /** `bottom` reads naturally as a mobile sheet; `right` as a desktop side panel. */
  side?: 'bottom' | 'right'
  /** `lg` widens a `right` panel for detail views with tables/lists. */
  size?: 'md' | 'lg'
}

export function Drawer({ isOpen, onClose, title, children, side = 'bottom', size = 'md' }: DrawerProps) {
  const titleId = useId()
  useOverlay(isOpen, onClose)

  if (!isOpen) return null

  return createPortal(
    <div className="fixed inset-0 z-50 flex">
      <button type="button" aria-label="Закрыть" className="absolute inset-0 bg-ink/40" onClick={onClose} />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={cn(
          'relative z-10 flex min-w-0 flex-col overflow-hidden bg-surface shadow-xl',
          side === 'bottom' && 'mt-auto max-h-[85dvh] w-full rounded-t-2xl pb-[env(safe-area-inset-bottom)]',
          side === 'right' && 'ml-auto h-dvh w-full',
          side === 'right' && (size === 'lg' ? 'max-w-xl' : 'max-w-sm'),
        )}
      >
        <div className="flex shrink-0 items-center justify-between gap-3 border-b border-border px-4 py-4 sm:px-5">
          <h2 id={titleId} className="min-w-0 truncate text-base font-semibold text-ink">
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Закрыть панель"
            className="flex size-8 shrink-0 items-center justify-center rounded-full text-ink-muted hover:bg-surface-hover"
          >
            <X className="size-4" aria-hidden />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-5">{children}</div>
      </div>
    </div>,
    document.body,
  )
}
