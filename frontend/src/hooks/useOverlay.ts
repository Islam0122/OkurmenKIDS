import { useEffect } from 'react'

let lockCount = 0

/**
 * Shared behaviour of every Modal/Drawer: Escape closes it, and the page
 * behind stops scrolling while it's open. The lock sits on <html>, whose
 * scrollbar gutter is reserved (index.css), so opening an overlay never
 * shifts the layout sideways. Counted, so stacked overlays unlock correctly.
 */
export function useOverlay(isOpen: boolean, onClose: () => void) {
  useEffect(() => {
    if (!isOpen) return
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  useEffect(() => {
    if (!isOpen) return
    lockCount += 1
    document.documentElement.style.overflow = 'hidden'
    return () => {
      lockCount -= 1
      if (lockCount === 0) document.documentElement.style.overflow = ''
    }
  }, [isOpen])
}
