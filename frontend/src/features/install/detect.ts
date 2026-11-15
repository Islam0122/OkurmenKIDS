/**
 * Which phone / computer and which browser opened /install — only to pick the
 * right instructions. Nothing is stored or sent anywhere.
 *
 * The user agent decides the platform (Apple has no install API to feature-
 * detect); whether the browser can show its native install dialog is read
 * from the real `beforeinstallprompt` event (src/pwa/register.ts), never
 * assumed from the UA.
 */

export type DeviceOS = 'ios' | 'android' | 'desktop'

export type BrowserId =
  | 'safari'
  | 'chrome'
  | 'samsung'
  | 'firefox'
  | 'edge'
  | 'opera'
  | 'yandex'
  | 'in-app'
  | 'other'

export type DeviceKind = 'iphone' | 'ipad' | 'android' | 'windows' | 'mac' | 'linux' | 'chromeos' | 'computer'

export interface DeviceInfo {
  os: DeviceOS
  kind: DeviceKind
  browser: BrowserId
  /** The app around an in-app browser (Instagram, Telegram…), when known. */
  inAppName: string | null
  /** iOS / iPadOS major version, when the UA tells it. */
  iosVersion: number | null
}

/** In-app browsers: links opened inside a messenger or social app. */
const IN_APP: [RegExp, string][] = [
  [/Instagram/, 'Instagram'],
  [/FBAN|FBAV|FB_IAB|FBIOS/, 'Facebook'],
  [/Telegram/, 'Telegram'],
  [/WhatsApp/, 'WhatsApp'],
  [/musical_ly|TikTok|BytedanceWebview/, 'TikTok'],
  [/Snapchat/, 'Snapchat'],
  [/Line\//, 'LINE'],
  [/MicroMessenger/, 'WeChat'],
  [/VKClient|vkontakte/i, 'VK'],
  [/OKApp/, 'Одноклассники'],
  [/GSA\//, 'Google'],
]

function inAppName(ua: string): string | null {
  for (const [pattern, name] of IN_APP) if (pattern.test(ua)) return name
  return null
}

export function detectDevice(ua: string, maxTouchPoints = 0): DeviceInfo {
  // iPadOS 13+ reports a desktop Mac; only the touch screen gives it away.
  const iPadOS = /Macintosh/.test(ua) && maxTouchPoints > 1
  const ios = /iPhone|iPad|iPod/.test(ua) || iPadOS
  const appName = inAppName(ua)

  if (ios) {
    const kind: DeviceKind = /iPad/.test(ua) || iPadOS ? 'ipad' : 'iphone'
    const osMatch = /OS (\d+)[_.]\d+/.exec(ua)
    const versionMatch = /Version\/(\d+)/.exec(ua)
    const iosVersion = osMatch ? Number(osMatch[1]) : iPadOS && versionMatch ? Number(versionMatch[1]) : null
    let browser: BrowserId
    if (appName) browser = 'in-app'
    else if (/CriOS/.test(ua)) browser = 'chrome'
    else if (/FxiOS/.test(ua)) browser = 'firefox'
    else if (/EdgiOS/.test(ua)) browser = 'edge'
    else if (/OPiOS|OPT\//.test(ua)) browser = 'opera'
    else if (/YaBrowser/.test(ua)) browser = 'yandex'
    else if (/Safari\//.test(ua) && /Version\//.test(ua)) browser = 'safari'
    // A WebKit view without «Safari/» is some app's embedded browser.
    else if (!/Safari\//.test(ua)) browser = 'in-app'
    else browser = 'other'
    return { os: 'ios', kind, browser, inAppName: browser === 'in-app' ? appName : null, iosVersion }
  }

  if (/Android/.test(ua)) {
    let browser: BrowserId
    if (appName || /; wv\)/.test(ua)) browser = 'in-app'
    else if (/SamsungBrowser/.test(ua)) browser = 'samsung'
    else if (/Firefox\//.test(ua)) browser = 'firefox'
    else if (/EdgA\//.test(ua)) browser = 'edge'
    else if (/OPR\/|Opera/.test(ua)) browser = 'opera'
    else if (/YaBrowser/.test(ua)) browser = 'yandex'
    else if (/Chrome\//.test(ua)) browser = 'chrome'
    else browser = 'other'
    return { os: 'android', kind: 'android', browser, inAppName: browser === 'in-app' ? appName : null, iosVersion: null }
  }

  const kind: DeviceKind = /Windows/.test(ua)
    ? 'windows'
    : /CrOS/.test(ua)
      ? 'chromeos'
      : /Macintosh/.test(ua)
        ? 'mac'
        : /Linux/.test(ua)
          ? 'linux'
          : 'computer'
  let browser: BrowserId
  if (/Edg\//.test(ua)) browser = 'edge'
  else if (/OPR\//.test(ua)) browser = 'opera'
  else if (/YaBrowser/.test(ua)) browser = 'yandex'
  else if (/Firefox\//.test(ua)) browser = 'firefox'
  else if (/Chrome\/|Chromium\//.test(ua)) browser = 'chrome'
  else if (/Safari\//.test(ua) && /Version\//.test(ua)) browser = 'safari'
  else browser = 'other'
  return { os: 'desktop', kind, browser, inAppName: null, iosVersion: null }
}

export function currentDevice(): DeviceInfo {
  if (typeof navigator === 'undefined') return detectDevice('')
  return detectDevice(navigator.userAgent, navigator.maxTouchPoints ?? 0)
}

/** The instruction set /install shows. */
export type InstallFlow =
  /** iPhone / iPad in Safari: Share → Add to Home Screen → Add. */
  | 'ios-safari'
  /** Chrome / Edge / Firefox… on iOS: open in Safari (Chrome & Edge can also add from their own Share). */
  | 'ios-browser'
  /** Instagram, Telegram… on iOS: open in Safari first. */
  | 'ios-in-app'
  /** Instagram, Telegram… on Android: open in Chrome first. */
  | 'android-in-app'
  /** Any Android browser: the native prompt when offered, its menu otherwise. */
  | 'android'
  /** Computers: Chromium prompt / menu, Safari «Add to Dock», or the phone QR. */
  | 'desktop'

export function installFlow(device: DeviceInfo): InstallFlow {
  if (device.os === 'ios') {
    if (device.browser === 'safari') return 'ios-safari'
    if (device.browser === 'in-app') return 'ios-in-app'
    return 'ios-browser'
  }
  if (device.os === 'android') return device.browser === 'in-app' ? 'android-in-app' : 'android'
  return 'desktop'
}

/** Desktop browsers that can install a web app at all. */
export function desktopCanInstall(device: DeviceInfo): boolean {
  if (device.os !== 'desktop') return false
  if (device.browser === 'safari') return device.kind === 'mac'
  return device.browser === 'chrome' || device.browser === 'edge' || device.browser === 'opera' || device.browser === 'yandex'
}

const KIND_LABEL: Record<DeviceKind, string> = {
  iphone: 'iPhone',
  ipad: 'iPad',
  android: 'Android',
  windows: 'Windows',
  mac: 'Mac',
  linux: 'Linux',
  chromeos: 'ChromeOS',
  computer: '',
}

const BROWSER_LABEL: Record<BrowserId, string> = {
  safari: 'Safari',
  chrome: 'Chrome',
  samsung: 'Samsung Internet',
  firefox: 'Firefox',
  edge: 'Edge',
  opera: 'Opera',
  yandex: 'Яндекс Браузер',
  'in-app': '',
  other: '',
}

/** «iPhone · Safari», «Android · Samsung Internet», «Windows · Chrome». */
export function deviceLabel(device: DeviceInfo, fallback: { computer: string; browser: string }): string {
  const kind = KIND_LABEL[device.kind] || fallback.computer
  const browser = device.browser === 'in-app' ? device.inAppName ?? fallback.browser : BROWSER_LABEL[device.browser] || fallback.browser
  return `${kind} · ${browser}`
}
