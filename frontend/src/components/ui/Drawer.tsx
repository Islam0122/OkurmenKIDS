import { useEffect } from 'react'
import type { ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'

import { cn } from '@/utils/cn'

export interface DrawerProps {
  isOpen: boolean
  onClose: () => void
  title: string
  children: ReactNode
  /** `bottom` reads naturally as a mobile sheet; `right` as a desktop side panel. */
  side?: 'bottom' | 'right'
}

export function Drawer({ isOpen, onClose, title, children, side = 'bottom' }: DrawerProps) {
  useEffect(() => {
    if (!isOpen) return
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  if (!isOpen) return null

  return createPortal(
    <div className="fixed inset-0 z-50 flex">
      <button type="button" aria-label="Закрыть" className="absolute inset-0 bg-ink/40" onClick={onClose} />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="drawer-title"
        className={cn(
          'relative z-10 flex max-h-[85vh] flex-col overflow-hidden bg-surface shadow-xl',
          side === 'bottom' && 'mt-auto w-full rounded-t-2xl',
          side === 'right' && 'ml-auto h-full w-full max-w-sm',
        )}
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h2 id="drawer-title" className="text-base font-semibold text-ink">
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Закрыть панель"
            className="flex size-8 items-center justify-center rounded-full text-ink-muted hover:bg-surface-hover"
          >
            <X className="size-4" aria-hidden />
          </button>
        </div>
        <div className="overflow-y-auto p-5">{children}</div>
      </div>
    </div>,
    document.body,
  )
}
