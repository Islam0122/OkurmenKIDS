import { Route, Routes } from 'react-router-dom'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { LoginPage } from '@/features/auth/LoginPage'
import { buildUser } from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'
import type { AuthContextValue } from '@/features/auth/AuthContext'

const login = vi.fn()
const mockUseAuth = vi.fn<() => AuthContextValue>(() => ({ status: 'guest', user: null, login, logout: vi.fn(), retry: vi.fn() }))
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => mockUseAuth() }))

describe('LoginPage', () => {
  it('submits the entered username and password to login()', async () => {
    login.mockResolvedValueOnce(undefined)
    const user = userEvent.setup()
    renderWithProviders(<LoginPage />, { route: '/login' })

    await user.type(screen.getByLabelText('Логин'), 'trainer1')
    await user.type(screen.getByLabelText('Пароль'), 'secret-pass')
    await user.click(screen.getByRole('button', { name: 'Войти' }))

    expect(login).toHaveBeenCalledWith('trainer1', 'secret-pass')
  })

  it('shows the failure reason from the backend without ever logging the password', async () => {
    const consoleLogSpy = vi.spyOn(console, 'log').mockImplementation(() => {})
    login.mockRejectedValueOnce(new Error('Неверный логин или пароль.'))
    const user = userEvent.setup()
    renderWithProviders(<LoginPage />, { route: '/login' })

    await user.type(screen.getByLabelText('Логин'), 'trainer1')
    await user.type(screen.getByLabelText('Пароль'), 'wrong-pass')
    await user.click(screen.getByRole('button', { name: 'Войти' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Неверный логин или пароль.')
    expect(consoleLogSpy.mock.calls.flat().join(' ')).not.toContain('wrong-pass')
    consoleLogSpy.mockRestore()
  })

  it('redirects away from /login when already authenticated', () => {
    mockUseAuth.mockReturnValue({ status: 'authenticated', user: null, login, logout: vi.fn(), retry: vi.fn() })
    renderWithProviders(
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/app/dashboard" element={<div>Dashboard content</div>} />
      </Routes>,
      { route: '/login' },
    )
    expect(screen.getByText('Dashboard content')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Войти' })).not.toBeInTheDocument()
  })

  it('sends an Accountant straight to /accounting after sign-in', async () => {
    mockUseAuth.mockReturnValue({ status: 'guest', user: null, login, logout: vi.fn(), retry: vi.fn() })
    login.mockResolvedValueOnce(buildUser({ role: 'accountant' }))
    const user = userEvent.setup()
    renderWithProviders(
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/accounting" element={<div>Accounting home</div>} />
        <Route path="/app/dashboard" element={<div>Dashboard content</div>} />
      </Routes>,
      { route: '/login' },
    )
    await user.type(screen.getByLabelText('Логин'), 'buh')
    await user.type(screen.getByLabelText('Пароль'), 'secret-pass')
    await user.click(screen.getByRole('button', { name: 'Войти' }))
    expect(await screen.findByText('Accounting home')).toBeInTheDocument()
    expect(screen.queryByText('Dashboard content')).not.toBeInTheDocument()
  })

  it('keeps an authenticated Accountant out of the LMS home', () => {
    mockUseAuth.mockReturnValue({ status: 'authenticated', user: buildUser({ role: 'accountant' }), login, logout: vi.fn(), retry: vi.fn() })
    renderWithProviders(
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/accounting" element={<div>Accounting home</div>} />
        <Route path="/app/dashboard" element={<div>Dashboard content</div>} />
      </Routes>,
      { route: '/login' },
    )
    expect(screen.getByText('Accounting home')).toBeInTheDocument()
  })

  it('returns to the page that sent the user to log in (the Schedule site)', async () => {
    mockUseAuth.mockReturnValue({ status: 'guest', user: null, login, logout: vi.fn(), retry: vi.fn() })
    login.mockResolvedValueOnce(undefined)
    const user = userEvent.setup()
    const { MemoryRouter } = await import('react-router-dom')
    const { render } = await import('@testing-library/react')
    const { QueryClient, QueryClientProvider } = await import('@tanstack/react-query')
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter initialEntries={[{ pathname: '/login', state: { from: { pathname: '/schedule/week', search: '?teacher=2' } } }]}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/schedule/week" element={<div>Schedule week</div>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )
    await user.type(screen.getByLabelText('Логин'), 'assist')
    await user.type(screen.getByLabelText('Пароль'), 'secret-pass')
    await user.click(screen.getByRole('button', { name: 'Войти' }))
    expect(await screen.findByText('Schedule week')).toBeInTheDocument()
  })
})
