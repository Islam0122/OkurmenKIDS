import { AxiosError } from 'axios'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { extractErrorMessage, OFFLINE_MESSAGE } from '@/lib/apiError'

import { canAutoPrompt, promptInstall, rememberDismissal } from './install'
import { installMethod, isIOS } from './platform'
import { getPwaState, installAvailability, setPwaState, type BeforeInstallPromptEvent, type PwaState } from './store'

const DAY = 24 * 60 * 60 * 1000

function withUserAgent(agent: string, maxTouchPoints = 0) {
  vi.spyOn(navigator, 'userAgent', 'get').mockReturnValue(agent)
  // jsdom has no maxTouchPoints: define it for the iPadOS case.
  Object.defineProperty(navigator, 'maxTouchPoints', { value: maxTouchPoints, configurable: true })
}

const base: PwaState = {
  standalone: false, installedHere: false, method: 'prompt', promptEvent: null,
  online: true, updateReady: false, settingsOpen: false, inlineInstallButtons: 0,
}

beforeEach(() => localStorage.clear())
afterEach(() => vi.restoreAllMocks())

describe('install prompt memory', () => {
  it('snoozes for three weeks after «Не сейчас»', () => {
    const now = Date.now()
    expect(canAutoPrompt(now)).toBe(true)
    rememberDismissal(now)
    expect(canAutoPrompt(now + 20 * DAY)).toBe(false)
    expect(canAutoPrompt(now + 22 * DAY)).toBe(true)
  })

  it('stops offering on its own after three dismissals', () => {
    const now = Date.now()
    rememberDismissal(now)
    rememberDismissal(now + 30 * DAY)
    rememberDismissal(now + 60 * DAY)
    expect(canAutoPrompt(now + 365 * DAY)).toBe(false)
  })

  it('survives corrupted storage', () => {
    localStorage.setItem('okurmen.pwa.installPrompt', '{not json')
    expect(canAutoPrompt()).toBe(true)
  })
})

describe('install availability', () => {
  it('reports the running installed app first', () => {
    expect(installAvailability({ ...base, standalone: true, promptEvent: {} as BeforeInstallPromptEvent })).toBe('installed')
  })
  it('offers the native prompt when the browser provided one', () => {
    expect(installAvailability({ ...base, promptEvent: {} as BeforeInstallPromptEvent })).toBe('available')
  })
  it('falls back to manual steps (Chromium menu, Apple)', () => {
    expect(installAvailability(base)).toBe('manual')
    expect(installAvailability({ ...base, method: 'ios' })).toBe('manual')
    expect(installAvailability({ ...base, method: 'macos-safari' })).toBe('manual')
  })
  it('remembers an install made from this browser', () => {
    expect(installAvailability({ ...base, installedHere: true })).toBe('installed')
  })
  it('knows in-app and unsupported browsers', () => {
    expect(installAvailability({ ...base, method: 'in-app' })).toBe('in-app')
    expect(installAvailability({ ...base, method: 'unsupported' })).toBe('unsupported')
  })
})

describe('platform detection', () => {
  it('detects iPhone and iPadOS (which claims to be a Mac)', () => {
    withUserAgent('Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 Version/17.4 Mobile/15E148 Safari/604.1')
    expect(isIOS()).toBe(true)
    expect(installMethod()).toBe('ios')
    withUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/17.4 Safari/605.1.15', 5)
    expect(installMethod()).toBe('ios')
  })
  it('detects Safari on macOS', () => {
    withUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15')
    expect(installMethod()).toBe('macos-safari')
  })
  it('detects in-app browsers', () => {
    withUserAgent('Mozilla/5.0 (Linux; Android 14; wv) AppleWebKit/537.36 Instagram 300.0')
    expect(installMethod()).toBe('in-app')
  })
})

describe('promptInstall', () => {
  it('uses the deferred prompt once and remembers the install', async () => {
    const prompt = vi.fn().mockResolvedValue(undefined)
    setPwaState({ promptEvent: { prompt, userChoice: Promise.resolve({ outcome: 'accepted', platform: 'web' }) } as unknown as BeforeInstallPromptEvent })
    expect(await promptInstall()).toBe('accepted')
    expect(prompt).toHaveBeenCalledOnce()
    expect(getPwaState().promptEvent).toBeNull()
    expect(getPwaState().installedHere).toBe(true)
    expect(await promptInstall()).toBe('unavailable')
  })
})

describe('offline error message', () => {
  it('says plainly that nothing was sent', () => {
    const error = new AxiosError('Network Error', AxiosError.ERR_NETWORK)
    expect(extractErrorMessage(error)).toBe(OFFLINE_MESSAGE)
  })
  it('leaves real API errors alone', () => {
    const error = new AxiosError('fail', 'ERR', undefined, undefined, {
      status: 400, data: { detail: 'Плохие данные' }, statusText: '', headers: {}, config: {} as never,
    })
    expect(extractErrorMessage(error)).toBe('Плохие данные')
  })
})
