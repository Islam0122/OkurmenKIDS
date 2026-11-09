import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { InstallAppButton } from '@/components/pwa/InstallAppButton'
import { getPwaState, setPwaState, type BeforeInstallPromptEvent } from '@/pwa/store'

import { LanguageProvider } from './i18n'
import { PortalInstallButton } from './InstallButton'

function nativePrompt(outcome: 'accepted' | 'dismissed') {
  const prompt = vi.fn().mockResolvedValue(undefined)
  const event = { prompt, userChoice: Promise.resolve({ outcome, platform: 'web' }) } as unknown as BeforeInstallPromptEvent
  return { event, prompt }
}

const renderButton = () =>
  render(
    <LanguageProvider>
      <PortalInstallButton />
    </LanguageProvider>,
  )

beforeEach(() => {
  localStorage.clear()
  localStorage.setItem('okurmen-digital:lang', 'ru')
  setPwaState({ standalone: false, installedHere: false, method: 'prompt', promptEvent: null, online: true, updateReady: false, settingsOpen: false, inlineInstallButtons: 0 })
})

describe('PortalInstallButton', () => {
  it('calls the browser’s own install prompt and turns into «Open app» on accept', async () => {
    const { event, prompt } = nativePrompt('accepted')
    setPwaState({ promptEvent: event })
    renderButton()
    fireEvent.click(screen.getByRole('button', { name: 'Установить приложение' }))
    await waitFor(() => expect(prompt).toHaveBeenCalledOnce())
    // No dialog of our own: the native prompt is the whole flow.
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'Открыть приложение' })).toBeInTheDocument()
    expect(getPwaState().installedHere).toBe(true)
  })

  it('stays «Install» after the user dismisses the native prompt', async () => {
    const { event } = nativePrompt('dismissed')
    setPwaState({ promptEvent: event })
    renderButton()
    fireEvent.click(screen.getByRole('button', { name: 'Установить приложение' }))
    await waitFor(() => expect(getPwaState().promptEvent).toBeNull())
    expect(screen.getByRole('button', { name: 'Установить приложение' })).toBeInTheDocument()
    expect(getPwaState().installedHere).toBe(false)
  })

  it('explains Share → Add to Home Screen on iOS (no install API there)', () => {
    setPwaState({ method: 'ios' })
    renderButton()
    fireEvent.click(screen.getByRole('button', { name: 'Установить приложение' }))
    expect(screen.getByRole('dialog', { name: 'Установка на iPhone и iPad' })).toBeInTheDocument()
    expect(screen.getByText(/На экран „Домой“/)).toBeInTheDocument()
    fireEvent.keyDown(document, { key: 'Escape' })
  })

  it('explains when the browser cannot install', () => {
    setPwaState({ method: 'unsupported' })
    renderButton()
    fireEvent.click(screen.getByRole('button', { name: 'Установить приложение' }))
    expect(screen.getByText('Этот браузер не устанавливает приложения')).toBeInTheDocument()
  })

  it('shows «Open app» with where to find it once installed', () => {
    setPwaState({ installedHere: true })
    renderButton()
    fireEvent.click(screen.getByRole('button', { name: 'Открыть приложение' }))
    expect(screen.getByText('Okurmen Kids уже установлен')).toBeInTheDocument()
  })

  it('is hidden inside the installed app and keeps the floating card away meanwhile', () => {
    const { unmount } = renderButton()
    expect(getPwaState().inlineInstallButtons).toBe(1)
    unmount()
    expect(getPwaState().inlineInstallButtons).toBe(0)
    setPwaState({ standalone: true })
    renderButton()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('a later beforeinstallprompt (app uninstalled) clears the installed note', async () => {
    const { markNotInstalled } = await import('@/pwa/store')
    setPwaState({ installedHere: true })
    renderButton()
    act(() => markNotInstalled())
    expect(screen.getByRole('button', { name: 'Установить приложение' })).toBeInTheDocument()
  })
})

describe('cabinet header InstallAppButton', () => {
  it('opens the native prompt directly — no intermediate dialog', async () => {
    const { event, prompt } = nativePrompt('dismissed')
    setPwaState({ promptEvent: event })
    render(<InstallAppButton />)
    fireEvent.click(screen.getByRole('button', { name: 'Установить приложение' }))
    await waitFor(() => expect(prompt).toHaveBeenCalledOnce())
    expect(getPwaState().settingsOpen).toBe(false)
  })
})
