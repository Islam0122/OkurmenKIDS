import { useEffect, useRef, type CSSProperties, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

import { Icon } from '../Icon'
import './Modal.css'

interface ModalProps {
  open: boolean
  onClose?: () => void
  title: string
  icon?: string
  tone?: 'navy' | 'amber' | 'red'
  width?: number
  children?: ReactNode
  actions?: ReactNode
  /** false: no close button / Esc / backdrop click (e.g. «Убакыт бүттү») */
  dismissible?: boolean
}

export function Modal({ open, onClose, title, icon, tone = 'navy', width, children, actions, dismissible = true }: ModalProps) {
  const box = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const previous = document.activeElement as HTMLElement | null
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const first = box.current?.querySelector<HTMLElement>('input, textarea, button:not(.modal__close), a')
    window.setTimeout(() => first?.focus(), 30)
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && dismissible) onClose?.()
      if (event.key === 'Tab' && box.current) {
        const focusable = box.current.querySelectorAll<HTMLElement>('a, button:not([disabled]), input, textarea')
        if (!focusable.length) return
        const [firstEl, lastEl] = [focusable[0], focusable[focusable.length - 1]]
        if (event.shiftKey && document.activeElement === firstEl) { event.preventDefault(); lastEl.focus() }
        else if (!event.shiftKey && document.activeElement === lastEl) { event.preventDefault(); firstEl.focus() }
      }
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = overflow
      previous?.focus?.()
    }
  }, [open, dismissible, onClose])

  if (!open) return null
  return createPortal(
    <div className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget && dismissible) onClose?.() }}>
      <div
        ref={box}
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
        style={width ? ({ '--modal-w': `${width}px` } as CSSProperties) : undefined}
      >
        {dismissible && onClose ? (
          <button type="button" className="modal__close" onClick={onClose} aria-label="Жабуу"><Icon name="x-lg" /></button>
        ) : null}
        {icon ? <div className={`modal__icon modal__icon--${tone}`}><Icon name={icon} /></div> : null}
        <h2 id="modal-title" className="modal__title">{title}</h2>
        {children}
        {actions ? <div className="modal__actions">{actions}</div> : null}
      </div>
    </div>,
    document.body,
  )
}
