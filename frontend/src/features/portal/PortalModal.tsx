import { useEffect, useId, useRef, type KeyboardEvent, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { X } from 'lucide-react'

import { useOverlay } from '@/hooks/useOverlay'
import { cn } from '@/utils/cn'

import { useI18n } from './i18n'

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

interface PortalModalProps {
  open: boolean
  onClose: () => void
  title: string
  subtitle?: string
  icon?: ReactNode
  size?: 'sm' | 'lg'
  children: ReactNode
  footer?: ReactNode
}

/**
 * Centered portal dialog: Esc and a click outside close it, Tab stays inside,
 * focus returns to the button that opened it. Animated in and out.
 */
export function PortalModal(props: PortalModalProps) {
  return createPortal(<AnimatePresence>{props.open ? <Dialog {...props} /> : null}</AnimatePresence>, document.body)
}

function Dialog({ onClose, title, subtitle, icon, size = 'sm', children, footer }: PortalModalProps) {
  const { t } = useI18n()
  const titleId = useId()
  const descId = useId()
  const panelRef = useRef<HTMLDivElement>(null)
  useOverlay(true, onClose)

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null
    panelRef.current?.focus()
    return () => opener?.focus?.()
  }, [])

  function trapTab(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key !== 'Tab' || !panelRef.current) return
    const items = Array.from(panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE))
    if (items.length === 0) return
    const first = items[0]
    const last = items[items.length - 1]
    if (event.shiftKey && (document.activeElement === first || document.activeElement === panelRef.current)) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 font-display">
      <motion.div
        aria-hidden
        className="absolute inset-0 bg-zinc-950/30 backdrop-blur-[3px]"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.2 }}
        onClick={onClose}
        data-testid="modal-backdrop"
      />
      <motion.div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={subtitle ? descId : undefined}
        tabIndex={-1}
        onKeyDown={trapTab}
        initial={{ opacity: 0, y: 16, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 8, scale: 0.98 }}
        transition={{ type: 'spring', stiffness: 380, damping: 32 }}
        className={cn(
          'relative z-10 flex max-h-[calc(100dvh-2rem)] w-full flex-col overflow-hidden rounded-2xl border border-pd-line bg-pd-panel text-pd-ink shadow-[0_24px_64px_-16px_rgb(10_10_10/0.25)] outline-none',
          size === 'lg' ? 'max-w-2xl' : 'max-w-md',
        )}
      >
        <span aria-hidden className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-pd-green/60 to-transparent" />
        <div className="flex shrink-0 items-start justify-between gap-4 px-5 pb-4 pt-5 sm:px-6 sm:pt-6">
          <div className="flex min-w-0 items-center gap-3">
            {icon ? (
              <span className="grid size-10 shrink-0 place-items-center rounded-xl border border-pd-green-line bg-pd-green-soft text-pd-green">{icon}</span>
            ) : null}
            <div className="min-w-0">
              <h2 id={titleId} className="text-lg font-bold tracking-tight">
                {title}
              </h2>
              {subtitle ? (
                <p id={descId} className="text-xs font-medium uppercase tracking-[0.14em] text-pd-green">
                  {subtitle}
                </p>
              ) : null}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t.modal.close}
            className="grid size-8 shrink-0 place-items-center rounded-full text-pd-faint transition hover:bg-zinc-100 hover:text-pd-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-pd-green"
          >
            <X className="size-4" aria-hidden />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-5 sm:px-6 sm:pb-6">{children}</div>
        {footer ? <div className="shrink-0 border-t border-pd-line bg-pd-subtle px-5 py-3.5 sm:px-6">{footer}</div> : null}
      </motion.div>
    </div>
  )
}
