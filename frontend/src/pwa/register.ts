import { markInstalled, setPwaState, type BeforeInstallPromptEvent } from './store'
import { isStandalone, supportsServiceWorker } from './platform'

const UPDATE_CHECK_MS = 60 * 60 * 1000

let waitingWorker: ServiceWorker | null = null
let reloadRequested = false

/** The service worker runs only in production builds (dev keeps Vite's HMR
 * untouched) and can be switched off at build time with VITE_PWA_DISABLED. */
export const SW_ENABLED = import.meta.env.PROD && import.meta.env.VITE_PWA_DISABLED !== 'true'

/** Called once from main.tsx before React renders, so the install prompt
 * and connectivity events are never missed. */
export function initPwa(): void {
  if (typeof window === 'undefined') return

  window.addEventListener('beforeinstallprompt', (event) => {
    // Keep the browser's mini-infobar from popping up: we offer our own,
    // calmer prompt (components/pwa/InstallPrompt) and a settings entry.
    event.preventDefault()
    setPwaState({ promptEvent: event as BeforeInstallPromptEvent })
  })
  window.addEventListener('appinstalled', () => markInstalled())

  window.addEventListener('online', () => setPwaState({ online: true }))
  window.addEventListener('offline', () => setPwaState({ online: false }))

  if (typeof window.matchMedia === 'function') {
    window.matchMedia('(display-mode: standalone)').addEventListener?.('change', () => {
      setPwaState({ standalone: isStandalone() })
    })
  }

  if (supportsServiceWorker()) {
    if (SW_ENABLED) {
      window.addEventListener('load', () => void registerServiceWorker())
    } else if (import.meta.env.PROD) {
      // Built with the PWA switched off: the build ships a self-destructing
      // sw.js; make sure a worker from an earlier deploy is replaced by it.
      void navigator.serviceWorker.getRegistrations().then((regs) => regs.forEach((reg) => void reg.update()))
    }
  }
}

async function registerServiceWorker(): Promise<void> {
  try {
    const registration = await navigator.serviceWorker.register('/sw.js', { scope: '/', updateViaCache: 'none' })

    const track = (worker: ServiceWorker | null) => {
      if (!worker) return
      const onState = () => {
        // «installed» with an active controller = an update, not the first install.
        if (worker.state === 'installed' && navigator.serviceWorker.controller) {
          waitingWorker = worker
          setPwaState({ updateReady: true })
        }
      }
      worker.addEventListener('statechange', onState)
      onState()
    }

    if (registration.waiting && navigator.serviceWorker.controller) track(registration.waiting)
    registration.addEventListener('updatefound', () => track(registration.installing))

    navigator.serviceWorker.addEventListener('controllerchange', () => {
      if (!reloadRequested) return
      reloadRequested = false
      window.location.reload()
    })

    // Long-lived windows (an installed app left open all week) check too.
    const check = () => void registration.update().catch(() => {})
    setInterval(check, UPDATE_CHECK_MS)
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') check()
    })
  } catch (error) {
    // A failed registration only costs offline support — never the app.
    console.warn('Service worker registration failed', error)
  }
}

/** «Обновить»: activate the waiting version, then reload once it controls the page. */
export function applyUpdate(): void {
  if (!waitingWorker) {
    window.location.reload()
    return
  }
  reloadRequested = true
  waitingWorker.postMessage({ type: 'SKIP_WAITING' })
}

export function dismissUpdate(): void {
  setPwaState({ updateReady: false })
}

/** Logout: ask the worker to drop its API copies (nothing private is cached,
 * but a shared computer should start clean). */
export function clearWorkerUserData(): void {
  if (!supportsServiceWorker()) return
  navigator.serviceWorker.controller?.postMessage({ type: 'CLEAR_USER_DATA' })
}
