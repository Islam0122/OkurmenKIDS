import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useAuth } from '@/hooks/useAuth'
import { tokenStorage } from '@/lib/tokenStorage'
import { buildUser } from '@/test/fixtures'

import { AuthProvider } from './AuthProvider'

const { me, sessionExpired } = vi.hoisted(() => ({ me: vi.fn(), sessionExpired: { handler: null as null | (() => void) } }))
vi.mock('@/api/auth', () => ({ authApi: { me, login: vi.fn() } }))
vi.mock('@/api/client', () => ({
  registerSessionExpiredHandler: (handler: () => void) => {
    sessionExpired.handler = handler
  },
}))
vi.mock('@/pwa/push', () => ({ unsubscribeOnLogout: vi.fn() }))

function Probe() {
  const { status, signedOut, logout } = useAuth()
  return (
    <div>
      <span data-testid="state">{`${status}:${String(signedOut)}`}</span>
      <button type="button" onClick={logout}>logout</button>
    </div>
  )
}

function renderProvider() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <AuthProvider>
        <Probe />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  localStorage.clear()
  tokenStorage.setTokens('access', 'refresh')
  me.mockResolvedValue(buildUser({ role: 'teacher', is_verified: true, is_active: true }))
})

describe('AuthProvider logout vs. session expiry', () => {
  it('«Выйти» clears the session and marks it as an explicit sign-out (→ /portal)', async () => {
    renderProvider()
    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('authenticated:false'))
    fireEvent.click(screen.getByRole('button', { name: 'logout' }))
    expect(screen.getByTestId('state')).toHaveTextContent('guest:true')
    expect(tokenStorage.getAccess()).toBeNull()
  })

  it('an expired session is NOT an explicit sign-out (→ /login, then back to the same page)', async () => {
    renderProvider()
    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('authenticated:false'))
    act(() => sessionExpired.handler?.())
    expect(screen.getByTestId('state')).toHaveTextContent('guest:false')
    expect(tokenStorage.getRefresh()).toBeNull()
  })
})
