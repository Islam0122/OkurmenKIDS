import { act, fireEvent, screen, waitFor } from '@testing-library/react'
import jsQR from 'jsqr'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthContext, type AuthContextValue } from '@/features/auth/AuthContext'
import { setPwaState, type BeforeInstallPromptEvent } from '@/pwa/store'
import { renderWithProviders } from '@/test/testUtils'
import type { User } from '@/types/auth'

import { detectDevice, installFlow } from './detect'
import { InstallPage } from './InstallPage'
import { InstallQrPage } from './InstallQrPage'
import { installUrl, logoBox, makeQr, qrFor, qrSvg, QUIET_ZONE, type QrMatrix } from './qr'

const UA = {
  iphoneSafari: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1',
  iphoneChrome: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/138.0.7204.119 Mobile/15E148 Safari/604.1',
  iphoneInstagram: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Instagram 385.0.0.33.82 (iPhone15,3; iOS 18_5; ru_RU)',
  iphoneWebView: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148',
  ipadOS: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Safari/605.1.15',
  androidChrome: 'Mozilla/5.0 (Linux; Android 14; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Mobile Safari/537.36',
  samsung: 'Mozilla/5.0 (Linux; Android 14; SAMSUNG SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/27.0 Chrome/125.0.0.0 Mobile Safari/537.36',
  androidFirefox: 'Mozilla/5.0 (Android 14; Mobile; rv:139.0) Gecko/139.0 Firefox/139.0',
  androidTelegram: 'Mozilla/5.0 (Linux; Android 13; SM-A536B Build/TP1A.220624.014; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/137.0.0.0 Mobile Safari/537.36 Telegram-Android/11.9.0',
  windowsChrome: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
  windowsEdge: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0',
  windowsFirefox: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:139.0) Gecko/20100101 Firefox/139.0',
}

describe('detectDevice', () => {
  it.each([
    ['iphoneSafari', 0, 'ios', 'iphone', 'safari', 'ios-safari'],
    ['iphoneChrome', 0, 'ios', 'iphone', 'chrome', 'ios-browser'],
    ['iphoneInstagram', 0, 'ios', 'iphone', 'in-app', 'ios-in-app'],
    ['iphoneWebView', 0, 'ios', 'iphone', 'in-app', 'ios-in-app'],
    ['ipadOS', 5, 'ios', 'ipad', 'safari', 'ios-safari'],
    ['ipadOS', 0, 'desktop', 'mac', 'safari', 'desktop'], // a real Mac
    ['androidChrome', 0, 'android', 'android', 'chrome', 'android'],
    ['samsung', 0, 'android', 'android', 'samsung', 'android'],
    ['androidFirefox', 0, 'android', 'android', 'firefox', 'android'],
    ['androidTelegram', 0, 'android', 'android', 'in-app', 'android-in-app'],
    ['windowsChrome', 0, 'desktop', 'windows', 'chrome', 'desktop'],
    ['windowsEdge', 0, 'desktop', 'windows', 'edge', 'desktop'],
    ['windowsFirefox', 0, 'desktop', 'windows', 'firefox', 'desktop'],
  ] as const)('%s (touch %i) → %s / %s / %s', (key, touch, os, kind, browser, flow) => {
    const device = detectDevice(UA[key], touch)
    expect([device.os, device.kind, device.browser]).toEqual([os, kind, browser])
    expect(installFlow(device)).toBe(flow)
  })

  it('names the app around an in-app browser and reads the iOS version', () => {
    expect(detectDevice(UA.iphoneInstagram).inAppName).toBe('Instagram')
    expect(detectDevice(UA.androidTelegram).inAppName).toBe('Telegram')
    expect(detectDevice(UA.iphoneSafari).iosVersion).toBe(18)
    expect(detectDevice(UA.ipadOS, 5).iosVersion).toBe(18)
  })
})

/** Renders the matrix to RGBA (8 px per module) and reads it back like a camera would. */
function decode(matrix: QrMatrix, logoFill: 'white' | 'noise' | null): string | null {
  const cell = 8
  const total = matrix.size + QUIET_ZONE * 2
  const px = total * cell
  const data = new Uint8ClampedArray(px * px * 4).fill(255)
  const { start, span } = logoBox(matrix.size)
  let seed = 7
  const random = () => ((seed = (seed * 16807) % 2147483647) / 2147483647)
  for (let row = 0; row < matrix.size; row++) {
    for (let col = 0; col < matrix.size; col++) {
      const inLogo = logoFill && row >= start && row < start + span && col >= start && col < start + span
      const dark = inLogo ? logoFill === 'noise' && random() > 0.5 : matrix.isDark(row, col)
      if (!dark) continue
      for (let y = 0; y < cell; y++) {
        for (let x = 0; x < cell; x++) {
          const i = (((row + QUIET_ZONE) * cell + y) * px + (col + QUIET_ZONE) * cell + x) * 4
          data[i] = data[i + 1] = data[i + 2] = 0
        }
      }
    }
  }
  return jsQR(data, px, px)?.data ?? null
}

describe('install QR code', () => {
  const url = 'https://lms.okurmenkids.com/install'

  it('reads back without the logo, and with the logo area blank or covered by artwork', () => {
    expect(decode(qrFor(url, { withLogo: false }), null)).toBe(url)
    const withLogo = qrFor(url, { withLogo: true })
    expect(withLogo.ecc).toBe('H')
    expect(decode(withLogo, 'white')).toBe(url)
    expect(decode(withLogo, 'noise')).toBe(url)
  })

  it('keeps the logo small, centred and clear of the finder patterns', () => {
    for (const text of [url, 'https://okurmenkids-lms-preview.vercel.app/install']) {
      const { size } = makeQr(text, 'H')
      const { start, span } = logoBox(size)
      expect(start * 2 + span).toBe(size)
      expect((span * span) / (size * size)).toBeLessThan(0.065)
      expect(start).toBeGreaterThan(8) // finder pattern + separator = 8 modules
    }
  })

  it('builds a self-contained SVG with a quiet zone and the embedded logo', () => {
    const svg = qrSvg(qrFor(url, { withLogo: true }), { withLogo: true, logoHref: 'data:image/png;base64,AAAA', title: 'Scan' })
    const size = qrFor(url, { withLogo: true }).size
    expect(svg).toContain(`viewBox="0 0 ${size + 8} ${size + 8}"`)
    expect(svg).toContain('<title>Scan</title>')
    expect(svg).toContain('href="data:image/png;base64,AAAA"')
    expect(qrSvg(qrFor(url, { withLogo: false }), { withLogo: false })).not.toContain('<image')
  })

  it('points to /install of the public site', () => {
    expect(installUrl('https://lms.okurmenkids.com/')).toBe('https://lms.okurmenkids.com/install')
    vi.stubEnv('VITE_PUBLIC_APP_URL', 'https://app.okurmenkids.kg/')
    expect(installUrl('https://preview.example.com')).toBe('https://app.okurmenkids.kg/install')
    vi.unstubAllEnvs()
  })
})

function useUA(ua: string, touch = 0) {
  vi.spyOn(navigator, 'userAgent', 'get').mockReturnValue(ua)
  Object.defineProperty(navigator, 'maxTouchPoints', { value: touch, configurable: true })
}

const auth = (user: Partial<User> | null): AuthContextValue => ({
  user: user as User | null,
  status: user ? 'authenticated' : 'guest',
  login: vi.fn(),
  logout: vi.fn(),
  retry: vi.fn(),
})

function renderPage(user: Partial<User> | null = null) {
  return renderWithProviders(
    <AuthContext.Provider value={auth(user)}>
      <InstallPage />
    </AuthContext.Provider>,
    { route: '/install' },
  )
}

describe('InstallPage', () => {
  beforeEach(() => {
    localStorage.clear()
    setPwaState({ standalone: false, installedHere: false, promptEvent: null, inlineInstallButtons: 0 })
  })
  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it('iPhone Safari: the four Safari steps, browsable', () => {
    useUA(UA.iphoneSafari)
    renderPage()
    expect(screen.getByTestId('device-chip')).toHaveTextContent('iPhone · Safari')
    expect(screen.getByRole('heading', { name: 'Установка на iPhone' })).toBeInTheDocument()
    for (const step of ['Откройте в Safari', 'Нажмите «Поделиться»', 'Выберите «На экран „Домой“»', 'Нажмите «Добавить»']) {
      expect(screen.getByRole('button', { name: new RegExp(step) })).toBeInTheDocument()
    }
    fireEvent.click(screen.getByRole('button', { name: /Нажмите «Добавить»/ }))
    expect(screen.getByText('Шаг 4 / 4')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Установить приложение/ })).not.toBeInTheDocument()
  })

  it('iPad: the Share button is described at the top', () => {
    useUA(UA.ipadOS, 5)
    renderPage()
    expect(screen.getByRole('heading', { name: 'Установка на iPad' })).toBeInTheDocument()
    expect(screen.getByText(/вверху справа/)).toBeInTheDocument()
  })

  it('iPhone Chrome: explains how to open the page in Safari, with a copy button', async () => {
    useUA(UA.iphoneChrome)
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    renderPage()
    expect(screen.getByRole('heading', { name: 'Откройте эту страницу в Safari' })).toBeInTheDocument()
    expect(screen.getByText(/Можно и прямо в Chrome/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Скопировать ссылку' }))
    expect(writeText).toHaveBeenCalledWith(`${window.location.origin}/install`)
    expect(await screen.findByText('Ссылка скопирована')).toBeInTheDocument()
  })

  it('in-app browsers: open in Safari / Chrome first', () => {
    useUA(UA.iphoneInstagram)
    renderPage()
    expect(screen.getByRole('heading', { name: 'Ссылка открыта внутри Instagram' })).toBeInTheDocument()
    expect(screen.getByText(/Открыть в Safari/)).toBeInTheDocument()
  })

  it('Android: the native install dialog from the big button, then the installed screen', async () => {
    useUA(UA.androidChrome)
    let resolveChoice!: (v: { outcome: 'accepted'; platform: string }) => void
    const event = {
      prompt: vi.fn().mockResolvedValue(undefined),
      userChoice: new Promise((resolve) => (resolveChoice = resolve)),
    } as unknown as BeforeInstallPromptEvent
    setPwaState({ promptEvent: event, method: 'prompt' })
    renderPage()
    expect(screen.getByRole('heading', { name: 'Установка на Android' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Установить приложение/ }))
    expect(event.prompt).toHaveBeenCalledTimes(1)
    await act(async () => resolveChoice({ outcome: 'accepted', platform: 'web' }))
    expect(await screen.findByRole('heading', { name: 'Приложение установлено!' })).toBeInTheDocument()
    expect(screen.getByText(/с главного экрана телефона/)).toBeInTheDocument()
  })

  it('Android without an install prompt: the browser menu steps take over', () => {
    vi.useFakeTimers()
    useUA(UA.samsung)
    renderPage()
    expect(screen.getByRole('button', { name: /Проверяем/ })).toBeDisabled()
    act(() => vi.advanceTimersByTime(4000))
    expect(screen.queryByRole('button', { name: /Установить приложение/ })).not.toBeInTheDocument()
    expect(screen.getByText('Установка через меню браузера')).toBeInTheDocument()
    expect(screen.getByText('Выберите «Добавить страницу на» → «Главный экран»')).toBeInTheDocument()
  })

  it('desktop: install steps for the browser and a QR code to install on the phone', () => {
    useUA(UA.windowsFirefox)
    renderPage()
    expect(screen.getByText(/не устанавливает веб-приложения/)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Установить на телефон' })).toBeInTheDocument()
    expect(screen.getAllByRole('img', { name: 'Scan to install OkurmenKids LMS' }).length).toBeGreaterThan(0)
  })

  it('inside the installed app: the success screen, leading into the right cabinet', () => {
    useUA(UA.iphoneSafari)
    setPwaState({ standalone: true })
    const { unmount } = renderPage()
    expect(screen.getByRole('heading', { name: 'Приложение установлено!' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Войти в кабинет/ })).toHaveAttribute('href', '/login')
    unmount()
    renderPage({ id: 1, role: 'student_parent' })
    expect(screen.getByRole('link', { name: /Открыть кабинет/ })).toHaveAttribute('href', '/student')
  })

  it('switches to Kyrgyz and remembers it', () => {
    useUA(UA.iphoneSafari)
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'KG' }))
    expect(screen.getByRole('heading', { level: 1, name: 'OkurmenKids LMS орнотуңуз' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: "iPhone'го орнотуу" })).toBeInTheDocument()
    expect(localStorage.getItem('okurmen-digital:lang')).toBe('kg')
    expect(document.documentElement.lang).toBe('ky')
  })

  it('keeps the floating install card away while it is open', () => {
    useUA(UA.androidChrome)
    renderPage()
    expect(screen.getByRole('heading', { name: 'Установка на Android' })).toBeInTheDocument()
  })
})

describe('InstallQrPage', () => {
  afterEach(() => vi.restoreAllMocks())

  it('encodes the public /install address and shows the bilingual A4 poster', async () => {
    renderWithProviders(
      <AuthContext.Provider value={auth({ id: 2, role: 'assistant' })}>
        <InstallQrPage />
      </AuthContext.Provider>,
      { route: '/install/qr' },
    )
    expect(screen.getByTestId('qr-url')).toHaveTextContent(`${window.location.origin}/install`)
    expect(screen.getAllByText('Scan to install OkurmenKids LMS').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Тиркемени орнотуу үчүн телефондун камерасы менен сканерлеңиз').length).toBeGreaterThan(0)
    // jsdom has no canvas: the self-check cannot pass, so nothing unverified is exported.
    await waitFor(() => expect(screen.getByRole('status')).toHaveAttribute('data-check', 'failed'))
    expect(screen.getByRole('button', { name: /PNG/ })).toBeDisabled()
    expect(screen.getByRole('button', { name: /Печать A4/ })).toBeDisabled()
  })
})
