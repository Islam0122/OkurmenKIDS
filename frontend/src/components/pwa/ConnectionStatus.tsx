import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { Wifi, WifiOff } from 'lucide-react'

import { usePwaState } from '@/pwa/store'
import { cn } from '@/utils/cn'

/**
 * A small status pill while the device is offline — honest about what that
 * means (nothing is synchronised, saving will fail) — and a short
 * «Подключение восстановлено» when it comes back. React Query refetches
 * active data on reconnect by itself.
 */
export function ConnectionStatus() {
  const { online } = usePwaState()
  const [showRestored, setShowRestored] = useState(false)
  const wasOffline = useRef(!online)
  const reduceMotion = useReducedMotion()

  useEffect(() => {
    if (!online) {
      wasOffline.current = true
      setShowRestored(false)
      return
    }
    if (!wasOffline.current) return
    wasOffline.current = false
    setShowRestored(true)
    const timer = window.setTimeout(() => setShowRestored(false), 3500)
    return () => window.clearTimeout(timer)
  }, [online])

  const visible = !online || showRestored

  return (
    <AnimatePresence>
      {visible ? (
        <motion.div
          key={online ? 'online' : 'offline'}
          role="status"
          aria-live="polite"
          initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          exit={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 8 }}
          className={cn(
            'pointer-events-none fixed inset-x-4 bottom-[calc(var(--spacing-mobile-nav)+env(safe-area-inset-bottom)+0.75rem)] z-[96] mx-auto flex max-w-md items-start gap-2.5 rounded-xl border px-3.5 py-2.5 text-sm shadow-lg lg:bottom-6',
            online ? 'border-brand-200 bg-brand-50 text-brand-700' : 'border-warning/30 bg-warning-soft text-ink',
          )}
        >
          {online ? (
            <>
              <Wifi className="mt-0.5 size-4 shrink-0" aria-hidden />
              <span className="font-medium">Подключение восстановлено — данные обновляются.</span>
            </>
          ) : (
            <>
              <WifiOff className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
              <span>
                <span className="block font-semibold">Нет подключения к интернету</span>
                <span className="block text-xs text-ink-secondary sm:hidden">Изменения не сохранятся, пока связь не вернётся.</span>
                <span className="hidden text-xs text-ink-secondary sm:block">
                  На экране — ранее загруженные данные, они не обновляются. Изменения не сохранятся, пока связь не вернётся.
                </span>
              </span>
            </>
          )}
        </motion.div>
      ) : null}
    </AnimatePresence>
  )
}
