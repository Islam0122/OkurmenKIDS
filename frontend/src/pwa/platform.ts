/** What this browser can do for installation — read once, never sniffed for
 * anything else. Feature detection first; the user agent only tells apart
 * the platforms whose install flow is manual (Apple) or impossible. */

export type InstallMethod =
  /** Chromium (Chrome, Edge, Samsung Internet…): `beforeinstallprompt`. */
  | 'prompt'
  /** iPhone / iPad: Share → «На экран „Домой“». */
  | 'ios'
  /** Safari 17+ on macOS: File → «Добавить в Dock». */
  | 'macos-safari'
  /** An in-app browser (Instagram, Telegram…): open in the real browser first. */
  | 'in-app'
  /** No install support (Firefox desktop, old browsers). */
  | 'unsupported'

interface NavigatorWithStandalone extends Navigator {
  standalone?: boolean
}

function ua(): string {
  return typeof navigator === 'undefined' ? '' : navigator.userAgent
}

export function isIOS(): boolean {
  const agent = ua()
  // iPadOS 13+ reports itself as a Mac — only a touch screen gives it away.
  const iPadOS = /Macintosh/.test(agent) && typeof navigator !== 'undefined' && navigator.maxTouchPoints > 1
  return /iPhone|iPad|iPod/.test(agent) || iPadOS
}

export function isInAppBrowser(): boolean {
  return /FBAN|FBAV|Instagram|Line\/|Telegram|WhatsApp|; wv\)|GSA\//.test(ua())
}

function isMacSafari(): boolean {
  const agent = ua()
  return /Macintosh/.test(agent) && /Version\/(1[7-9]|[2-9]\d)/.test(agent) && /Safari\//.test(agent) &&
    !/Chrome|Chromium|Edg\/|Firefox|OPR\//.test(agent) && !isIOS()
}

/** Running as the installed app (any platform), not in a browser tab. */
export function isStandalone(): boolean {
  if (typeof window === 'undefined') return false
  const media = (query: string) => typeof window.matchMedia === 'function' && window.matchMedia(query).matches
  return (
    media('(display-mode: standalone)') ||
    media('(display-mode: minimal-ui)') ||
    media('(display-mode: window-controls-overlay)') ||
    (navigator as NavigatorWithStandalone).standalone === true
  )
}

export function installMethod(): InstallMethod {
  if (isInAppBrowser()) return 'in-app'
  if (isIOS()) return 'ios'
  if (isMacSafari()) return 'macos-safari'
  if (typeof window !== 'undefined' && 'onbeforeinstallprompt' in window) return 'prompt'
  return 'unsupported'
}

export function supportsServiceWorker(): boolean {
  return typeof navigator !== 'undefined' && 'serviceWorker' in navigator && window.isSecureContext
}

export function supportsPush(): boolean {
  return supportsServiceWorker() && 'PushManager' in window && 'Notification' in window
}
