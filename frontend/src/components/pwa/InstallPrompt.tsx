import { useEffect, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { X } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { canAutoPrompt, promptInstall, rememberDismissal } from '@/pwa/install'
import { installAvailability, openAppSettings, usePwaState } from '@/pwa/store'

/** Wait for the person to actually use the app before offering anything. */
const SHOW_AFTER_MS = 30_000
/** Screens where a card would be in the way: TV dashboards and the login form. */
const QUIET_PATHS = ['/login', '/monthly-performance']

function isQuietScreen(): boolean {
  const { pathname, search } = window.location
  return QUIET_PATHS.some((path) => pathname.startsWith(path)) || new URLSearchParams(search).has('tv')
}

/**
 * The one unprompted install offer: a small card, at most once per visit,
 * only after real interaction, never on TV/login screens, snoozed for three
 * weeks on «Не сейчас» and silenced for good after three of those. The same
 * action is always available in «Приложение» (header / profile).
 */
export function InstallPrompt() {
  const pwa = usePwaState()
  const availability = installAvailability(pwa)
  const eligible = availability === 'available' || (availability === 'manual' && pwa.method === 'ios')
  const [visible, setVisible] = useState(false)
  const [shownThisVisit, setShownThisVisit] = useState(false)
  const reduceMotion = useReducedMotion()

  useEffect(() => {
    if (!eligible || shownThisVisit || !canAutoPrompt()) return
    let engaged = false
    const onEngage = () => {
      engaged = true
    }
    window.addEventListener('pointerdown', onEngage, { once: true })
    window.addEventListener('keydown', onEngage, { once: true })
    const timer = window.setTimeout(() => {
      if (engaged && !isQuietScreen()) {
        setVisible(true)
        setShownThisVisit(true)
      }
    }, SHOW_AFTER_MS)
    return () => {
      window.clearTimeout(timer)
      window.removeEventListener('pointerdown', onEngage)
      window.removeEventListener('keydown', onEngage)
    }
  }, [eligible, shownThisVisit])

  // Installed meanwhile (from the browser menu, another tab…): just go away.
  const open = visible && eligible

  const dismiss = () => {
    rememberDismissal()
    setVisible(false)
  }

  const install = async () => {
    if (availability !== 'available') {
      setVisible(false)
      openAppSettings()
      return
    }
    const outcome = await promptInstall()
    if (outcome === 'dismissed') rememberDismissal()
    setVisible(false)
  }

  return (
    <AnimatePresence>
      {open ? (
        <motion.aside
          key="install-prompt"
          role="dialog"
          aria-labelledby="pwa-install-title"
          initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 24, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 16, scale: 0.98 }}
          transition={{ type: 'spring', stiffness: 380, damping: 32 }}
          className="fixed inset-x-4 bottom-[calc(var(--spacing-mobile-nav)+env(safe-area-inset-bottom)+1rem)] z-[90] mx-auto max-w-md overflow-hidden rounded-2xl border border-border bg-surface shadow-[0_24px_60px_-20px_rgba(31,95,60,0.35)] lg:inset-x-auto lg:right-6 lg:bottom-6 lg:w-[380px]"
        >
          <div className="h-1 bg-gradient-to-r from-brand-500 via-brand-200 to-brand-500" aria-hidden />
          <div className="flex gap-3 p-4">
            <img src="/icons/icon-192.png" alt="" className="size-12 shrink-0 rounded-xl border border-border shadow-sm" width={48} height={48} />
            <div className="min-w-0 flex-1">
              <h2 id="pwa-install-title" className="text-sm font-semibold text-ink">
                Установите Okurmen Kids
              </h2>
              <p className="mt-0.5 text-xs leading-relaxed text-ink-secondary">
                {pwa.method === 'ios'
                  ? 'Добавьте приложение на экран «Домой»: запуск в одно касание, отдельное окно и уведомления.'
                  : 'Запуск с рабочего стола в одно нажатие, отдельное окно без вкладок и уведомления.'}
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button size="sm" onClick={() => void install()}>
                  {availability === 'available' ? 'Установить' : 'Как установить'}
                </Button>
                <Button size="sm" variant="ghost" onClick={dismiss}>
                  Не сейчас
                </Button>
              </div>
            </div>
            <button
              type="button"
              onClick={dismiss}
              aria-label="Закрыть предложение установки"
              className="-mt-1 -mr-1 flex size-8 shrink-0 items-center justify-center rounded-full text-ink-muted hover:bg-surface-hover"
            >
              <X className="size-4" aria-hidden />
            </button>
          </div>
        </motion.aside>
      ) : null}
    </AnimatePresence>
  )
}
