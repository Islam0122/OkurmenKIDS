import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { RefreshCw } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { applyUpdate, dismissUpdate } from '@/pwa/register'
import { usePwaState } from '@/pwa/store'

/** «Доступна новая версия»: switching is the user's call, so nobody loses a
 * half-filled form to an automatic reload. Ignoring it is safe too — every
 * fresh online start loads the newest version anyway. */
export function UpdatePrompt() {
  const { updateReady } = usePwaState()
  const reduceMotion = useReducedMotion()

  return (
    <AnimatePresence>
      {updateReady ? (
        <motion.div
          key="pwa-update"
          role="status"
          aria-live="polite"
          initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: -16 }}
          animate={{ opacity: 1, y: 0 }}
          exit={reduceMotion ? { opacity: 0 } : { opacity: 0, y: -12 }}
          transition={{ type: 'spring', stiffness: 380, damping: 32 }}
          className="fixed inset-x-4 top-[calc(env(safe-area-inset-top)+0.75rem)] z-[95] mx-auto flex max-w-md items-center gap-3 rounded-2xl border border-brand-200 bg-surface px-4 py-3 shadow-lg lg:inset-x-auto lg:right-6"
        >
          <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-brand-50 text-brand-700">
            <RefreshCw className="size-4" aria-hidden />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-ink">Доступна новая версия</p>
            <p className="text-xs text-ink-secondary">Сохраните изменения и обновите приложение.</p>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <Button size="sm" variant="ghost" onClick={dismissUpdate}>
              Позже
            </Button>
            <Button size="sm" onClick={applyUpdate}>
              Обновить
            </Button>
          </div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  )
}
