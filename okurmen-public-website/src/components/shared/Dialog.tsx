import { AnimatePresence, motion } from 'framer-motion'
import { X } from 'lucide-react'
import { useEffect, useId, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

/**
 * Accessible modal: focus moves in and is trapped, Escape closes, focus
 * returns to the opener, page scroll is locked. A bottom sheet on phones.
 */
export function Dialog({ open, onClose, title, description, children }: { open: boolean; onClose: () => void; title: string; description?: string; children: ReactNode }) {
  const panel = useRef<HTMLDivElement>(null)
  const titleId = useId()
  const descId = useId()

  useEffect(() => {
    if (!open) return
    const opener = document.activeElement as HTMLElement | null
    document.body.style.overflow = 'hidden'
    const focusFirst = window.setTimeout(() => panel.current?.querySelector<HTMLElement>('input, select, textarea, button')?.focus(), 60)
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      if (e.key === 'Tab' && panel.current) {
        const items = panel.current.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), input:not([tabindex="-1"]), select, textarea')
        const first = items[0]
        const last = items[items.length - 1]
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault()
          last?.focus()
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault()
          first?.focus()
        }
      }
    }
    document.addEventListener('keydown', onKey)
    return () => {
      window.clearTimeout(focusFirst)
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
      opener?.focus?.()
    }
  }, [open, onClose])

  return createPortal(
    <AnimatePresence>
      {open ? (
        <motion.div className="fixed inset-0 z-[70] flex items-end justify-center sm:items-center sm:p-6" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <div className="absolute inset-0 bg-brand-950/60 backdrop-blur-sm" onClick={onClose} aria-hidden />
          <motion.div
            ref={panel}
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            aria-describedby={description ? descId : undefined}
            initial={{ y: 40, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 40, opacity: 0 }}
            transition={{ type: 'spring', damping: 28, stiffness: 320 }}
            className="relative max-h-[92dvh] w-full overflow-y-auto rounded-t-[1.75rem] bg-white p-6 pb-[calc(1.5rem+env(safe-area-inset-bottom))] shadow-lift sm:max-w-xl sm:rounded-(--radius-card) sm:p-8"
          >
            <div className="mx-auto mb-4 h-1.5 w-12 rounded-full bg-line sm:hidden" aria-hidden />
            <button type="button" onClick={onClose} className="absolute top-4 right-4 grid size-11 place-items-center rounded-full text-muted transition hover:bg-brand-50 hover:text-brand-800" aria-label="Close">
              <X className="size-5" aria-hidden />
            </button>
            <h2 id={titleId} className="pr-10 text-2xl font-extrabold">{title}</h2>
            {description ? <p id={descId} className="mt-2 text-muted">{description}</p> : null}
            <div className="mt-6">{children}</div>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>,
    document.body,
  )
}
