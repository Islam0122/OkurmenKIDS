import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/testUtils'
import type { User } from '@/types/auth'

import { PORTAL_APPS, resolveCard } from './config'
import { PortalPage } from './PortalPage'

const mockUseAuth = vi.fn()
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => mockUseAuth() }))

function user(role: User['role']): User {
  return { id: 1, username: 'aibek', email: '', first_name: 'Aibek', last_name: 'Asanov', role, is_verified: true, is_active: true }
}

function LoginProbe() {
  const location = useLocation()
  const from = (location.state as { from?: { pathname: string } } | null)?.from
  return <div>Login page, back to {from?.pathname}</div>
}

function renderPortal() {
  return renderWithProviders(
    <Routes>
      <Route path="/portal" element={<PortalPage />} />
      <Route path="/login" element={<LoginProbe />} />
      <Route path="/schedule" element={<div>Schedule site</div>} />
    </Routes>,
    { route: '/portal' },
  )
}

const card = (id: string) => document.querySelector(`[data-app="${id}"]`)

describe('OKURMEN DIGITAL portal', () => {
  beforeEach(() => mockUseAuth.mockReturnValue({ user: null, status: 'guest', logout: vi.fn() }))

  it('shows all seven applications to a guest, with a login button', () => {
    renderPortal()
    expect(screen.getByRole('heading', { name: /welcome to okurmen digital/i })).toBeInTheDocument()
    expect(screen.getAllByRole('listitem')).toHaveLength(7)
    expect(screen.getByRole('link', { name: 'Login' })).toHaveAttribute('href', '/login')
  })

  it('opens the known external applications in a new tab', () => {
    renderPortal()
    expect(card('training')).toHaveAttribute('href', 'https://training-portal-theta.vercel.app/')
    expect(card('performance')).toHaveAttribute('href', 'https://okurmen-kids-drab.vercel.app/monthly-performance')
    expect(card('performance')).toHaveAttribute('target', '_blank')
    expect(card('performance')).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('routes internal applications through React Router', async () => {
    renderPortal()
    expect(card('schedule')).toHaveAttribute('href', '/schedule')
    expect(card('programs')).toHaveAttribute('href', '/portal/programs')
    await userEvent.click(card('schedule') as HTMLElement)
    expect(screen.getByText('Schedule site')).toBeInTheDocument()
  })

  it('sends a guest to the login page for protected apps and remembers the app', async () => {
    renderPortal()
    await userEvent.click(card('lms') as HTMLElement)
    expect(screen.getByText('Login page, back to /app/dashboard')).toBeInTheDocument()
  })

  it('opens an app with its number key', async () => {
    renderPortal()
    await userEvent.keyboard('3')
    expect(screen.getByText('Schedule site')).toBeInTheDocument()
  })

  it('shows the profile and opens protected apps directly when signed in', () => {
    mockUseAuth.mockReturnValue({ user: user('teacher'), status: 'authenticated', logout: vi.fn() })
    renderPortal()
    expect(screen.getByText('Aibek Asanov')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Login' })).not.toBeInTheDocument()
    expect(card('lms')).toHaveAttribute('href', '/app/dashboard')
    expect(card('news')).toHaveAttribute('href', '/app/news')
  })

  it('hides LMS-only apps from roles without the LMS and sends them to their own cabinet', () => {
    mockUseAuth.mockReturnValue({ user: user('accountant'), status: 'authenticated', logout: vi.fn() })
    renderPortal()
    expect(card('news')).toBeNull()
    expect(screen.getAllByRole('listitem')).toHaveLength(6)
    expect(card('lms')).toHaveAttribute('href', '/accounting')
  })

  it('treats an unconfigured destination as unavailable instead of inventing a URL', () => {
    const app = { ...PORTAL_APPS[0], href: null }
    expect(resolveCard(app, null)).toEqual({ kind: 'unavailable' })
  })
})
