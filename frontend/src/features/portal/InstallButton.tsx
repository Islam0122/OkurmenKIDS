import { useEffect, useId, useRef, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { AppWindow, Download, X } from 'lucide-react'

import { promptInstall } from '@/pwa/install'
import { desktopOS, isAndroid, isIOS } from '@/pwa/platform'
import { installAvailability, registerInlineInstallButton, usePwaState } from '@/pwa/store'
import { cn } from '@/utils/cn'

import { useI18n, type InstallText } from './i18n'

const focusRing = 'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-pd-green'

interface Hint {
  title: string
  steps?: string[]
  text?: string[]
}

/**
 * «Install app» in the portal header.
 *
 * Chromium (Chrome / Edge on Windows, macOS, Android): the click calls the
 * saved `beforeinstallprompt` event's `prompt()` — the browser's own, real
 * install dialog; `userChoice` and `appinstalled` are handled in src/pwa.
 * Nothing is simulated: where no install API exists (Safari, in-app
 * browsers, Firefox) the button explains the browser's own way instead.
 * Installed → «Open app» with where to find it; inside the app → hidden.
 */
export function PortalInstallButton() {
  const { t } = useI18n()
  const pwa = usePwaState()
  const availability = installAvailability(pwa)
  const [hintOpen, setHintOpen] = useState(false)
  const [prompting, setPrompting] = useState(false)
  const visible = !pwa.standalone

  // While this button is on screen the floating install card stays away.
  useEffect(() => (visible ? registerInlineInstallButton() : undefined), [visible])

  if (!visible) return null

  const installed = availability === 'installed'
  const label = installed ? t.install.open : t.install.install

  const onClick = async () => {
    if (availability === 'available') {
      setPrompting(true)
      try {
        await promptInstall()
      } finally {
        setPrompting(false)
      }
      return
    }
    setHintOpen((open) => !open)
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => void onClick()}
        disabled={prompting}
        aria-label={label}
        title={label}
        aria-haspopup={availability === 'available' ? undefined : 'dialog'}
        aria-expanded={availability === 'available' ? undefined : hintOpen}
        className={cn(
          'inline-flex h-9 items-center gap-1.5 rounded-lg border border-pd-line bg-white px-2 text-sm font-semibold text-pd-ink pd-shadow transition hover:border-pd-green-line hover:text-pd-green active:scale-[0.98] disabled:opacity-60 sm:px-3',
          focusRing,
        )}
      >
        {installed ? (
          <AppWindow className="size-4 text-pd-green" aria-hidden />
        ) : (
          <Download className="size-4 text-pd-green" aria-hidden />
        )}
        <span className="hidden lg:inline">{label}</span>
      </button>
      <InstallHint open={hintOpen} onClose={() => setHintOpen(false)} hint={hintFor(availability, pwa.method, t.install)} closeLabel={t.modal.close} />
    </div>
  )
}

function hintFor(availability: ReturnType<typeof installAvailability>, method: string, t: InstallText): Hint {
  if (availability === 'installed') {
    const where = isIOS() ? t.openIOS : isAndroid() ? t.openAndroid : desktopOS() === 'windows' ? t.openWindows : desktopOS() === 'macos' ? t.openMac : t.openOther
    const desktopChromium = method === 'prompt' && !isAndroid()
    return { title: t.openTitle, text: desktopChromium ? [where, t.openOmnibox] : [where] }
  }
  if (availability === 'in-app') return { title: t.inAppTitle, steps: t.inAppSteps }
  if (availability === 'unsupported') return { title: t.unsupportedTitle, text: [t.unsupportedText] }
  if (method === 'ios') return { title: t.iosTitle, steps: t.iosSteps }
  if (method === 'macos-safari') return { title: t.macSafariTitle, steps: t.macSafariSteps }
  // Chromium that has not (yet) offered its prompt: its own menu still installs.
  return { title: t.chromeMenuTitle, steps: t.chromeMenuSteps }
}

function InstallHint({ open, onClose, hint, closeLabel }: { open: boolean; onClose: () => void; hint: Hint; closeLabel: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const titleId = useId()
  const reduceMotion = useReducedMotion()

  useEffect(() => {
    if (!open) return
    const onPointer = (event: PointerEvent) => {
      if (ref.current && !ref.current.parentElement?.contains(event.target as Node)) onClose()
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('pointerdown', onPointer)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onPointer)
      document.removeEventListener('keydown', onKey)
    }
  }, [open, onClose])

  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          ref={ref}
          role="dialog"
          aria-labelledby={titleId}
          initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: -6, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={reduceMotion ? { opacity: 0 } : { opacity: 0, y: -4, scale: 0.98 }}
          transition={{ duration: 0.16, ease: 'easeOut' }}
          // Phones: pinned full-width under the header; larger screens: under the button.
          className="fixed inset-x-4 top-[4.5rem] z-40 rounded-2xl border border-pd-line bg-white p-4 text-left pd-shadow sm:absolute sm:inset-x-auto sm:right-0 sm:top-11 sm:w-80 sm:origin-top-right"
        >
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <img src="/icons/icon-192.png" alt="" width={32} height={32} className="size-8 shrink-0 rounded-lg border border-pd-line" />
              <h2 id={titleId} className="text-sm font-semibold text-pd-ink">
                {hint.title}
              </h2>
            </div>
            <button
              type="button"
              onClick={onClose}
              aria-label={closeLabel}
              className={cn('-mr-1 -mt-1 flex size-7 shrink-0 items-center justify-center rounded-full text-pd-faint hover:bg-zinc-100', focusRing)}
            >
              <X className="size-4" aria-hidden />
            </button>
          </div>
          {hint.steps ? (
            <ol className="mt-3 space-y-2.5">
              {hint.steps.map((step, index) => (
                <li key={step} className="flex gap-2.5 text-[13px] leading-snug text-pd-muted">
                  <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-pd-green-soft text-[11px] font-bold text-pd-green-deep">
                    {index + 1}
                  </span>
                  <span className="pt-px">{step}</span>
                </li>
              ))}
            </ol>
          ) : null}
          {hint.text?.map((line) => (
            <p key={line} className="mt-2.5 text-[13px] leading-snug text-pd-muted">
              {line}
            </p>
          ))}
        </motion.div>
      ) : null}
    </AnimatePresence>
  )
}
