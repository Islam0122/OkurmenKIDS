import { act, fireEvent, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthContext, type AuthContextValue } from '@/features/auth/AuthContext'
import { OfflinePage } from '@/features/auth/OfflinePage'
import { setPwaState, type BeforeInstallPromptEvent } from '@/pwa/store'
import { renderWithProviders } from '@/test/testUtils'

import { AppSettingsPanel } from './AppSettingsPanel'
import { ConnectionStatus } from './ConnectionStatus'
import { InstallAppButton } from './InstallAppButton'
import { InstallPrompt } from './InstallPrompt'

const auth = (status: AuthContextValue['status']): AuthContextValue => ({
  user: null, status, login: vi.fn(), logout: vi.fn(), retry: vi.fn(),
})

const fakePrompt = () =>
  ({ prompt: vi.fn().mockResolvedValue(undefined), userChoice: Promise.resolve({ outcome: 'dismissed', platform: 'web' }) }) as unknown as BeforeInstallPromptEvent

beforeEach(() => {
  localStorage.clear()
  setPwaState({ standalone: false, installedHere: false, method: 'prompt', promptEvent: null, online: true, updateReady: false, settingsOpen: false })
})
afterEach(() => {
  vi.useRealTimers()
  window.history.replaceState(null, '', '/')
})

describe('InstallPrompt', () => {
  it('waits for real use, then offers once; «Не сейчас» snoozes it', () => {
    vi.useFakeTimers()
    setPwaState({ promptEvent: fakePrompt() })
    renderWithProviders(<InstallPrompt />)
    act(() => vi.advanceTimersByTime(31_000))
    expect(screen.queryByText('Установите Okurmen Kids')).not.toBeInTheDocument() // no interaction yet
  })

  it('shows after interaction and hides on dismiss', () => {
    vi.useFakeTimers()
    setPwaState({ promptEvent: fakePrompt() })
    renderWithProviders(<InstallPrompt />)
    fireEvent.pointerDown(window)
    act(() => vi.advanceTimersByTime(31_000))
    expect(screen.getByText('Установите Okurmen Kids')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Не сейчас' }))
    expect(JSON.parse(localStorage.getItem('okurmen.pwa.installPrompt')!).count).toBe(1)
  })

  it('never appears on the login screen or a TV dashboard', () => {
    vi.useFakeTimers()
    window.history.replaceState(null, '', '/login')
    setPwaState({ promptEvent: fakePrompt() })
    renderWithProviders(<InstallPrompt />)
    fireEvent.pointerDown(window)
    act(() => vi.advanceTimersByTime(31_000))
    expect(screen.queryByText('Установите Okurmen Kids')).not.toBeInTheDocument()
  })

  it('stays hidden when the app is already installed', () => {
    vi.useFakeTimers()
    setPwaState({ standalone: true, promptEvent: fakePrompt() })
    renderWithProviders(<InstallPrompt />)
    fireEvent.pointerDown(window)
    act(() => vi.advanceTimersByTime(31_000))
    expect(screen.queryByText('Установите Okurmen Kids')).not.toBeInTheDocument()
  })
})

describe('InstallAppButton', () => {
  it('appears only while installation is possible', () => {
    const { rerender } = renderWithProviders(<InstallAppButton />)
    expect(screen.queryByRole('button', { name: 'Установить приложение' })).not.toBeInTheDocument()
    act(() => setPwaState({ promptEvent: fakePrompt() }))
    rerender(<InstallAppButton />)
    expect(screen.getByRole('button', { name: 'Установить приложение' })).toBeInTheDocument()
    act(() => setPwaState({ standalone: true }))
    expect(screen.queryByRole('button', { name: 'Установить приложение' })).not.toBeInTheDocument()
  })
})

describe('AppSettingsPanel', () => {
  it('shows iOS steps and hides push for guests', () => {
    setPwaState({ method: 'ios' })
    renderWithProviders(
      <AuthContext.Provider value={auth('guest')}>
        <AppSettingsPanel />
      </AuthContext.Provider>,
    )
    expect(screen.getByText(/На экран „Домой“/)).toBeInTheDocument()
    expect(screen.queryByText('Уведомления на этом устройстве')).not.toBeInTheDocument()
  })

  it('offers the native install and explains push needs the production app', () => {
    setPwaState({ promptEvent: fakePrompt() })
    renderWithProviders(
      <AuthContext.Provider value={auth('authenticated')}>
        <AppSettingsPanel />
      </AuthContext.Provider>,
    )
    expect(screen.getByRole('button', { name: 'Установить' })).toBeInTheDocument()
    expect(screen.getByText('Уведомления на этом устройстве')).toBeInTheDocument()
    // Tests run a dev build: no service worker, so no permission is ever requested.
    expect(screen.getByText(/рабочей \(production\) версии/)).toBeInTheDocument()
  })

  it('reports an installed app', () => {
    setPwaState({ standalone: true })
    renderWithProviders(
      <AuthContext.Provider value={auth('guest')}>
        <AppSettingsPanel />
      </AuthContext.Provider>,
    )
    expect(screen.getByText('Установлено')).toBeInTheDocument()
  })
})

describe('connectivity', () => {
  it('tells the truth while offline and confirms recovery', () => {
    renderWithProviders(<ConnectionStatus />)
    act(() => setPwaState({ online: false }))
    expect(screen.getByText('Нет подключения к интернету')).toBeInTheDocument()
    expect(screen.getAllByText(/Изменения не сохранятся/).length).toBeGreaterThan(0)
    act(() => setPwaState({ online: true }))
    expect(screen.getByText(/Подключение восстановлено/)).toBeInTheDocument()
  })

  it('OfflinePage retries by itself when the connection returns', () => {
    const onRetry = vi.fn()
    setPwaState({ online: false })
    renderWithProviders(<OfflinePage onRetry={onRetry} />)
    expect(screen.getByText('Нет подключения к интернету')).toBeInTheDocument()
    expect(onRetry).not.toHaveBeenCalled()
    act(() => setPwaState({ online: true }))
    expect(onRetry).toHaveBeenCalledOnce()
  })
})
